package io.vectormatch.core;

import java.io.*;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.*;

/**
 * Deterministic, single-writer, single-market integer matching state machine.
 * One price tick costs one quote unit per base lot. No wall-clock or external I/O
 * participates in business decisions. Instances must be confined to one thread.
 */
public final class MatchingEngine {
    private static final int SNAPSHOT_MAGIC = 0x564D4331;
    private static final int SNAPSHOT_VERSION = 2;
    private static final int MAX_SNAPSHOT_ITEMS = 10_000_000;
    public enum Asset { BASE, QUOTE }
    public enum Side { BUY, SELL }
    public enum TimeInForce { GTC, IOC }
    public enum OrderStatus { OPEN, PARTIALLY_FILLED, FILLED, CANCELLED, EXPIRED }
    public enum ResultCode { ACCEPTED, REJECTED, INVALID_REQUEST, IDEMPOTENCY_CONFLICT, STALE_SEQUENCE }
    public enum EventType { DEPOSIT, ORDER_ACCEPTED, TRADE, ORDER_CANCELLED, ORDER_EXPIRED }

    public sealed interface Command permits Deposit, Place, Cancel {
        long accountId();
        String producerId();
        long requestSeq();
    }
    public record Deposit(long accountId, String producerId, long requestSeq, Asset asset, long amount)
            implements Command {}
    public record Place(long accountId, String producerId, long requestSeq, String clientOrderId,
                        Side side, long priceTicks, long quantityLots, TimeInForce timeInForce)
            implements Command {}
    public record Cancel(long accountId, String producerId, long requestSeq, long orderId)
            implements Command {}
    public record Result(ResultCode code, String reason, long commandSeq, long orderId,
                         long remainingQuantity, int tradeCount) {
        public boolean accepted() { return code == ResultCode.ACCEPTED; }
    }
    public record Execution(Result result, List<Event> events, boolean replayed) {
        public Execution { events = List.copyOf(events); }
    }
    /** marketSeq is zero for private deposits; public order/trade events are contiguous. */
    public record Event(long eventSeq, long marketSeq, EventType type, long accountId, long orderId,
                        long makerOrderId, long takerOrderId, Side side, long priceTicks,
                        long quantityLots, String detail) {}
    public record Balance(long available, long reserved) {}
    public record AccountView(long accountId, Balance base, Balance quote) {}
    public record OrderView(long orderId, long accountId, String clientOrderId, Side side,
                            long priceTicks, long originalQuantity, long remainingQuantity,
                            TimeInForce timeInForce, OrderStatus status, long acceptedCommandSeq) {}
    public record PriceLevel(long priceTicks, long quantityLots, int orderCount) {}
    public record BookView(long marketSeq, List<PriceLevel> bids, List<PriceLevel> asks) {
        public BookView { bids = List.copyOf(bids); asks = List.copyOf(asks); }
    }
    /** Explicit state bounds. Terminal orders are retained until a new engine is provisioned. */
    public record Limits(int maxAccounts, int maxProducers, int maxRetainedOrders, int maxCachedResults) {
        public Limits {
            if (maxAccounts < 1 || maxProducers < 1 || maxRetainedOrders < 1 || maxCachedResults < 1
                    || maxAccounts > MAX_SNAPSHOT_ITEMS || maxProducers > MAX_SNAPSHOT_ITEMS
                    || maxRetainedOrders > MAX_SNAPSHOT_ITEMS || maxCachedResults > MAX_SNAPSHOT_ITEMS)
                throw new IllegalArgumentException("limits must be between 1 and " + MAX_SNAPSHOT_ITEMS);
        }
        public static Limits defaults() { return new Limits(10_000, 10_000, 1_000_000, 100_000); }
    }

    private static final class Account {
        final long id;
        long baseAvailable, baseReserved, quoteAvailable, quoteReserved;
        Account(long id) { this.id = id; }
        AccountView view() {
            return new AccountView(id, new Balance(baseAvailable, baseReserved),
                    new Balance(quoteAvailable, quoteReserved));
        }
    }
    private static final class Order {
        final long id, accountId, price, original, acceptedSeq;
        final String clientId;
        final Side side;
        final TimeInForce tif;
        long remaining;
        OrderStatus status;
        Order(long id, long accountId, String clientId, Side side, long price, long quantity,
              TimeInForce tif, long acceptedSeq) {
            this.id = id; this.accountId = accountId; this.clientId = clientId;
            this.side = side; this.price = price; this.original = quantity;
            this.remaining = quantity; this.tif = tif; this.acceptedSeq = acceptedSeq;
            this.status = OrderStatus.OPEN;
        }
        OrderView view() {
            return new OrderView(id, accountId, clientId, side, price, original, remaining, tif, status, acceptedSeq);
        }
    }
    private record ProducerKey(long accountId, String producerId) implements Comparable<ProducerKey> {
        @Override public int compareTo(ProducerKey other) {
            int c = Long.compare(accountId, other.accountId);
            return c != 0 ? c : producerId.compareTo(other.producerId);
        }
    }
    private record ClientOrderKey(long accountId, String clientOrderId) {}
    private record Cached(Command command, Result result) {}
    private record CacheLocation(ProducerKey producer, long requestSeq) {}
    private static final class Producer {
        long highWater;
        final LinkedHashMap<Long, Cached> results = new LinkedHashMap<>();
    }

    private final int resultCachePerProducer;
    private final Limits limits;
    private final NavigableMap<Long, Account> accounts = new TreeMap<>();
    private final NavigableMap<Long, Order> orders = new TreeMap<>();
    private final Map<ClientOrderKey, Long> clientIds = new HashMap<>();
    private final NavigableMap<ProducerKey, Producer> producers = new TreeMap<>();
    private final NavigableMap<Long, CacheLocation> cachedByCommandSeq = new TreeMap<>();
    private final NavigableMap<Long, LinkedHashMap<Long, Order>> bids = new TreeMap<>(Comparator.reverseOrder());
    private final NavigableMap<Long, LinkedHashMap<Long, Order>> asks = new TreeMap<>();
    private long commandSeq, eventSeq, marketSeq, nextOrderId = 1;
    private long totalBase, totalQuote;
    // Deliberately absent from legacy constructors and V2 snapshot encoding.
    // Only the explicit V3 facade enables this private embedded engine.
    private boolean retentionV3;

    public MatchingEngine() { this(1024); }
    public MatchingEngine(int resultCachePerProducer) { this(resultCachePerProducer, Limits.defaults()); }
    public MatchingEngine(int resultCachePerProducer, Limits limits) {
        if (resultCachePerProducer < 1 || resultCachePerProducer > 1_000_000)
            throw new IllegalArgumentException("result cache must be between 1 and 1000000");
        this.resultCachePerProducer = resultCachePerProducer;
        this.limits = Objects.requireNonNull(limits, "limits");
    }

    public long lastCommandSeq() { return commandSeq; }
    public long lastEventSeq() { return eventSeq; }
    public long lastMarketSeq() { return marketSeq; }
    public long totalBase() { return totalBase; }
    public long totalQuote() { return totalQuote; }
    public int resultCachePerProducer() { return resultCachePerProducer; }
    public Limits limits() { return limits; }
    public int retainedOrderCount() { return orders.size(); }
    public int producerCount() { return producers.size(); }
    public int cachedResultCount() { return cachedByCommandSeq.size(); }

    record RetentionProducer(long accountId, String producerId, long highWater) {}
    void enableRetentionV3() {
        if (retentionV3) throw new IllegalStateException("V3 bridge already enabled");
        retentionV3 = true;
    }
    private void requireRetentionV3() {
        if (!retentionV3) throw new IllegalStateException("terminal compaction requires explicit V3 facade");
    }
    long retentionAcceptedPlaceCount() { requireRetentionV3(); return nextOrderId - 1; }
    long retentionProducerHighWater(long account, String producerId) {
        requireRetentionV3();
        Producer producer = producers.get(new ProducerKey(account, producerId));
        return producer == null ? 0 : producer.highWater;
    }
    List<RetentionProducer> retentionProducers() {
        requireRetentionV3();
        return producers.entrySet().stream().map(e -> new RetentionProducer(
                e.getKey().accountId, e.getKey().producerId, e.getValue().highWater)).toList();
    }
    List<Command> retentionCachedCommands() {
        requireRetentionV3();
        return producers.values().stream().flatMap(p -> p.results.values().stream()).map(Cached::command).toList();
    }
    List<Result> retentionCachedResults() {
        requireRetentionV3();
        return producers.values().stream().flatMap(p -> p.results.values().stream()).map(Cached::result).toList();
    }
    int compactRetentionTerminalOrders(Collection<Long> orderIds) {
        requireRetentionV3();
        Set<Long> unique = new HashSet<>();
        // Validate the complete set before any mutation. Never alter book/FIFO,
        // balances, counters, producer high-water or retry results here.
        for (long id : orderIds) {
            Order order = orders.get(id);
            if (!unique.add(id) || order == null || isActive(order.status)
                    || !Objects.equals(clientIds.get(new ClientOrderKey(order.accountId, order.clientId)), id))
                throw new IllegalArgumentException("V3 compaction requires unique hot terminal orders");
        }
        for (long id : orderIds) {
            Order order = orders.remove(id);
            clientIds.remove(new ClientOrderKey(order.accountId, order.clientId));
        }
        return unique.size();
    }

    public Execution apply(Command command) { return execute(command); }

    /**
     * Exact event count for the current state, without mutation. Intended for a
     * replicated outbox capacity check on the same writer immediately before
     * execute; no intervening command may change this state. Replays, conflicts,
     * stale requests and business rejections produce zero events.
     */
    public int maximumEventsFor(Command command) {
        if (command == null || command.accountId() <= 0 || !validId(command.producerId()) || command.requestSeq() <= 0)
            return 0;
        Producer producer = producers.get(new ProducerKey(command.accountId(), command.producerId()));
        if ((producer != null && command.requestSeq() <= producer.highWater)
                || (producer == null && producers.size() == limits.maxProducers) || commandSeq == Long.MAX_VALUE)
            return 0;
        if (command instanceof Deposit deposit) {
            if (deposit.asset == null || deposit.amount <= 0) return 0;
            long total = deposit.asset == Asset.BASE ? totalBase : totalQuote;
            return deposit.amount <= Long.MAX_VALUE - total
                    && (accounts.containsKey(deposit.accountId) || accounts.size() < limits.maxAccounts) ? 1 : 0;
        }
        if (command instanceof Cancel cancel) {
            Order order = orders.get(cancel.orderId);
            return order != null && order.accountId == cancel.accountId && isActive(order.status) ? 1 : 0;
        }
        Place place = (Place) command;
        if (placementRejection(place) != null) return 0;
        int count = 1;
        long remaining = place.quantityLots;
        NavigableMap<Long, LinkedHashMap<Long, Order>> opposite = place.side == Side.BUY ? asks : bids;
        for (Map.Entry<Long, LinkedHashMap<Long, Order>> entry : opposite.entrySet()) {
            if (place.side == Side.BUY ? entry.getKey() > place.priceTicks : entry.getKey() < place.priceTicks) break;
            for (Order maker : entry.getValue().values()) {
                if (maker.accountId == place.accountId) return count + 1; // incoming residual expiry
                remaining -= Math.min(remaining, maker.remaining);
                count++;
                if (remaining == 0) return count;
            }
        }
        return place.timeInForce == TimeInForce.IOC ? count + 1 : count;
    }

    /** Retries return the original result, but never re-emit business events. */
    public Execution execute(Command command) {
        if (command == null || command.accountId() <= 0 || !validId(command.producerId()) || command.requestSeq() <= 0)
            return noEvents(ResultCode.INVALID_REQUEST, "invalid request identity", 0);
        if (command instanceof Place place && place.clientOrderId != null && place.clientOrderId.length() > 128)
            return noEvents(ResultCode.INVALID_REQUEST, "client order id exceeds 128 characters", 0);
        ProducerKey key = new ProducerKey(command.accountId(), command.producerId());
        Producer producer = producers.get(key);
        if (producer != null && command.requestSeq() <= producer.highWater) {
            Cached cached = producer.results.get(command.requestSeq());
            if (cached == null) return noEvents(ResultCode.STALE_SEQUENCE, "sequence no longer retained; not executed", 0);
            if (!cached.command.equals(command))
                return noEvents(ResultCode.IDEMPOTENCY_CONFLICT, "same sequence has different payload", 0);
            return new Execution(cached.result, List.of(), true);
        }
        if (producer == null && producers.size() == limits.maxProducers)
            return noEvents(ResultCode.REJECTED, "producer capacity reached", 0);
        if (commandSeq == Long.MAX_VALUE)
            return noEvents(ResultCode.REJECTED, "command sequence exhausted", 0);
        // An order can emit at most one acceptance, one expiry, and one trade
        // per retained maker. Keep the usual hot path O(1), and compute the
        // exact count only when a 64-bit event counter nears exhaustion.
        long upperEventBound = (long) orders.size() + 2L;
        if (eventSeq > Long.MAX_VALUE - upperEventBound
                || (!(command instanceof Deposit) && marketSeq > Long.MAX_VALUE - upperEventBound)) {
            int pendingEvents = maximumEventsFor(command);
            if (pendingEvents > Long.MAX_VALUE - eventSeq
                    || (!(command instanceof Deposit) && pendingEvents > Long.MAX_VALUE - marketSeq))
                return noEvents(ResultCode.REJECTED, "event sequence capacity reached", 0);
        }
        commandSeq++;
        List<Event> events = new ArrayList<>();
        Result result;
        if (command instanceof Deposit deposit) result = deposit(deposit, events);
        else if (command instanceof Place place) result = place(place, events);
        else result = cancel((Cancel) command, events);
        if (producer == null) { producer = new Producer(); producers.put(key, producer); }
        producer.highWater = command.requestSeq();
        producer.results.put(command.requestSeq(), new Cached(command, result));
        cachedByCommandSeq.put(commandSeq, new CacheLocation(key, command.requestSeq()));
        while (producer.results.size() > resultCachePerProducer) {
            Cached removed = producer.results.remove(producer.results.keySet().iterator().next());
            cachedByCommandSeq.remove(removed.result.commandSeq);
        }
        while (cachedByCommandSeq.size() > limits.maxCachedResults) {
            CacheLocation removed = cachedByCommandSeq.pollFirstEntry().getValue();
            producers.get(removed.producer).results.remove(removed.requestSeq);
        }
        return new Execution(result, events, false);
    }

    private boolean validId(String value) { return value != null && !value.isBlank() && value.length() <= 128; }
    private Result rejected(String reason) { return new Result(ResultCode.REJECTED, reason, commandSeq, 0, 0, 0); }
    private Execution noEvents(ResultCode code, String reason, long orderId) {
        return new Execution(new Result(code, reason, commandSeq, orderId, 0, 0), List.of(), false);
    }
    private Result deposit(Deposit command, List<Event> events) {
        if (command.asset == null || command.amount <= 0) return rejected("deposit must have a positive amount and asset");
        long total = command.asset == Asset.BASE ? totalBase : totalQuote;
        if (command.amount > Long.MAX_VALUE - total) return rejected("asset supply overflow");
        if (!accounts.containsKey(command.accountId) && accounts.size() == limits.maxAccounts)
            return rejected("account capacity reached");
        Account account = accounts.computeIfAbsent(command.accountId, Account::new);
        if (command.asset == Asset.BASE) { totalBase += command.amount; account.baseAvailable += command.amount; }
        else { totalQuote += command.amount; account.quoteAvailable += command.amount; }
        emit(events, false, EventType.DEPOSIT, account.id, 0, 0, 0, null, 0, command.amount, command.asset.name());
        return new Result(ResultCode.ACCEPTED, "deposited", commandSeq, 0, 0, 0);
    }

    private Result place(Place command, List<Event> events) {
        String rejection = placementRejection(command);
        if (rejection != null) return rejected(rejection);
        Account account = accounts.get(command.accountId);
        long reserve = command.side == Side.BUY ? command.priceTicks * command.quantityLots : command.quantityLots;
        if (command.side == Side.BUY) { account.quoteAvailable -= reserve; account.quoteReserved += reserve; }
        else { account.baseAvailable -= reserve; account.baseReserved += reserve; }
        Order incoming = new Order(nextOrderId++, command.accountId, command.clientOrderId, command.side,
                command.priceTicks, command.quantityLots, command.timeInForce, commandSeq);
        orders.put(incoming.id, incoming);
        clientIds.put(new ClientOrderKey(incoming.accountId, incoming.clientId), incoming.id);
        emit(events, true, EventType.ORDER_ACCEPTED, incoming.accountId, incoming.id, 0, incoming.id,
                incoming.side, incoming.price, incoming.original, incoming.tif.name());
        NavigableMap<Long, LinkedHashMap<Long, Order>> opposite = incoming.side == Side.BUY ? asks : bids;
        int tradeCount = 0;
        while (incoming.remaining > 0 && !opposite.isEmpty()) {
            Map.Entry<Long, LinkedHashMap<Long, Order>> best = opposite.firstEntry();
            if (incoming.side == Side.BUY ? best.getKey() > incoming.price : best.getKey() < incoming.price) break;
            Order maker = best.getValue().values().iterator().next();
            // Self-trading is rejected before either order is changed: cancel the incoming residual.
            if (maker.accountId == incoming.accountId) break;
            long quantity = Math.min(incoming.remaining, maker.remaining);
            settle(incoming, maker, quantity);
            incoming.remaining -= quantity; maker.remaining -= quantity;
            maker.status = maker.remaining == 0 ? OrderStatus.FILLED : OrderStatus.PARTIALLY_FILLED;
            incoming.status = incoming.remaining == 0 ? OrderStatus.FILLED : OrderStatus.PARTIALLY_FILLED;
            if (maker.remaining == 0) {
                best.getValue().remove(maker.id);
                if (best.getValue().isEmpty()) opposite.remove(best.getKey());
            }
            tradeCount++;
            emit(events, true, EventType.TRADE, incoming.accountId, incoming.id, maker.id, incoming.id,
                    incoming.side, maker.price, quantity, "maker-price");
        }
        boolean selfTradeBlocked = incoming.remaining > 0 && !opposite.isEmpty()
                && crosses(incoming, opposite.firstKey())
                && opposite.firstEntry().getValue().values().iterator().next().accountId == incoming.accountId;
        if (incoming.remaining > 0 && (incoming.tif == TimeInForce.IOC || selfTradeBlocked)) {
            release(incoming);
            incoming.status = OrderStatus.EXPIRED;
            emit(events, true, EventType.ORDER_EXPIRED, incoming.accountId, incoming.id, 0, incoming.id,
                    incoming.side, incoming.price, incoming.remaining,
                    selfTradeBlocked ? "self-trade prevention: cancel incoming residual" : "IOC residual");
        } else if (incoming.remaining > 0) {
            bookFor(incoming.side).computeIfAbsent(incoming.price, ignored -> new LinkedHashMap<>()).put(incoming.id, incoming);
        }
        return new Result(ResultCode.ACCEPTED, "accepted", commandSeq, incoming.id, incoming.remaining, tradeCount);
    }

    private String placementRejection(Place command) {
        if (!validId(command.clientOrderId) || command.side == null || command.timeInForce == null
                || command.priceTicks <= 0 || command.quantityLots <= 0)
            return "invalid limit order";
        if (command.priceTicks > Long.MAX_VALUE / command.quantityLots) return "order notional overflow";
        if (nextOrderId == Long.MAX_VALUE) return "order sequence exhausted";
        if (orders.size() == limits.maxRetainedOrders) return "retained order capacity reached";
        if (clientIds.containsKey(new ClientOrderKey(command.accountId, command.clientOrderId)))
            return "client order id already used";
        Account account = accounts.get(command.accountId);
        if (account == null) return "unknown account";
        long reserve = command.side == Side.BUY ? command.priceTicks * command.quantityLots : command.quantityLots;
        long available = command.side == Side.BUY ? account.quoteAvailable : account.baseAvailable;
        return available < reserve ? "insufficient available balance" : null;
    }

    private boolean crosses(Order order, long oppositePrice) {
        return order.side == Side.BUY ? oppositePrice <= order.price : oppositePrice >= order.price;
    }
    private NavigableMap<Long, LinkedHashMap<Long, Order>> bookFor(Side side) { return side == Side.BUY ? bids : asks; }
    private void settle(Order incoming, Order maker, long quantity) {
        Order buy = incoming.side == Side.BUY ? incoming : maker;
        Order sell = incoming.side == Side.SELL ? incoming : maker;
        Account buyer = accounts.get(buy.accountId), seller = accounts.get(sell.accountId);
        long reservedQuote = buy.price * quantity;
        long executedQuote = maker.price * quantity;
        buyer.quoteReserved -= reservedQuote;
        buyer.quoteAvailable += reservedQuote - executedQuote;
        buyer.baseAvailable += quantity;
        seller.baseReserved -= quantity;
        seller.quoteAvailable += executedQuote;
    }
    private void release(Order order) {
        Account account = accounts.get(order.accountId);
        if (order.side == Side.BUY) {
            long amount = order.price * order.remaining;
            account.quoteReserved -= amount; account.quoteAvailable += amount;
        } else { account.baseReserved -= order.remaining; account.baseAvailable += order.remaining; }
    }
    private Result cancel(Cancel command, List<Event> events) {
        Order order = orders.get(command.orderId);
        if (retentionV3 && order == null && command.orderId > 0 && command.orderId < nextOrderId)
            return rejected("V3 terminal order archived; hot cancellation unavailable");
        if (order == null || order.accountId != command.accountId) return rejected("order not found for account");
        if (!isActive(order.status)) return rejected("order is no longer active");
        LinkedHashMap<Long, Order> level = bookFor(order.side).get(order.price);
        level.remove(order.id);
        if (level.isEmpty()) bookFor(order.side).remove(order.price);
        release(order); order.status = OrderStatus.CANCELLED;
        emit(events, true, EventType.ORDER_CANCELLED, order.accountId, order.id, 0, 0,
                order.side, order.price, order.remaining, "cancelled");
        return new Result(ResultCode.ACCEPTED, "cancelled", commandSeq, order.id, order.remaining, 0);
    }
    private static boolean isActive(OrderStatus status) {
        return status == OrderStatus.OPEN || status == OrderStatus.PARTIALLY_FILLED;
    }
    private void emit(List<Event> events, boolean publicEvent, EventType type, long accountId, long orderId,
                      long makerId, long takerId, Side side, long price, long quantity, String detail) {
        events.add(new Event(++eventSeq, publicEvent ? ++marketSeq : 0, type, accountId, orderId,
                makerId, takerId, side, price, quantity, detail));
    }

    /** Unknown accounts have a zero balance; querying does not create an account. */
    public AccountView account(long accountId) {
        Account account = accounts.get(accountId);
        return account == null ? new AccountView(accountId, new Balance(0, 0), new Balance(0, 0)) : account.view();
    }
    public List<AccountView> accounts() { return accounts.values().stream().map(Account::view).toList(); }
    public Optional<OrderView> order(long orderId) { return Optional.ofNullable(orders.get(orderId)).map(Order::view); }
    public List<OrderView> orders(long accountId) {
        return orders.values().stream().filter(order -> order.accountId == accountId).map(Order::view).toList();
    }
    public List<OrderView> orders() { return orders.values().stream().map(Order::view).toList(); }
    public BookView book(int depth) {
        if (depth < 0 || depth > 100_000) throw new IllegalArgumentException("depth must be 0..100000");
        return new BookView(marketSeq, levels(bids, depth), levels(asks, depth));
    }
    private List<PriceLevel> levels(NavigableMap<Long, LinkedHashMap<Long, Order>> book, int depth) {
        List<PriceLevel> levels = new ArrayList<>();
        for (Map.Entry<Long, LinkedHashMap<Long, Order>> entry : book.entrySet()) {
            if (levels.size() == depth) break;
            long quantity = 0;
            for (Order order : entry.getValue().values()) quantity = Math.addExact(quantity, order.remaining);
            levels.add(new PriceLevel(entry.getKey(), quantity, entry.getValue().size()));
        }
        return levels;
    }

    /** Canonical binary state, including bounded replay results and producer high-water marks. */
    public byte[] snapshot() {
        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            DataOutputStream out = new DataOutputStream(bytes);
            out.writeInt(SNAPSHOT_MAGIC); out.writeInt(SNAPSHOT_VERSION); out.writeInt(resultCachePerProducer);
            out.writeInt(limits.maxAccounts); out.writeInt(limits.maxProducers);
            out.writeInt(limits.maxRetainedOrders); out.writeInt(limits.maxCachedResults);
            out.writeLong(commandSeq); out.writeLong(eventSeq); out.writeLong(marketSeq); out.writeLong(nextOrderId);
            out.writeLong(totalBase); out.writeLong(totalQuote);
            out.writeInt(accounts.size());
            for (Account account : accounts.values()) {
                out.writeLong(account.id); out.writeLong(account.baseAvailable); out.writeLong(account.baseReserved);
                out.writeLong(account.quoteAvailable); out.writeLong(account.quoteReserved);
            }
            out.writeInt(orders.size());
            for (Order order : orders.values()) {
                out.writeLong(order.id); out.writeLong(order.accountId); writeString(out, order.clientId);
                out.writeByte(order.side.ordinal()); out.writeLong(order.price); out.writeLong(order.original);
                out.writeLong(order.remaining); out.writeByte(order.tif.ordinal()); out.writeByte(order.status.ordinal());
                out.writeLong(order.acceptedSeq);
            }
            out.writeInt(producers.size());
            for (Map.Entry<ProducerKey, Producer> entry : producers.entrySet()) {
                out.writeLong(entry.getKey().accountId); writeString(out, entry.getKey().producerId);
                out.writeLong(entry.getValue().highWater); out.writeInt(entry.getValue().results.size());
                for (Cached cached : entry.getValue().results.values()) {
                    writeCommand(out, cached.command); writeResult(out, cached.result);
                }
            }
            out.flush(); byte[] payload = bytes.toByteArray(); bytes.write(digest(payload)); return bytes.toByteArray();
        } catch (IOException impossible) { throw new UncheckedIOException(impossible); }
    }

    public static MatchingEngine restore(byte[] snapshot) {
        Objects.requireNonNull(snapshot, "snapshot");
        try {
            if (snapshot.length < 32) throw new IllegalArgumentException("truncated snapshot");
            byte[] payload = Arrays.copyOf(snapshot, snapshot.length - 32);
            if (!MessageDigest.isEqual(digest(payload), Arrays.copyOfRange(snapshot, payload.length, snapshot.length)))
                throw new IllegalArgumentException("snapshot checksum mismatch");
            DataInputStream in = new DataInputStream(new ByteArrayInputStream(payload));
            if (in.readInt() != SNAPSHOT_MAGIC || in.readInt() != SNAPSHOT_VERSION)
                throw new IllegalArgumentException("unsupported snapshot format");
            int resultCachePerProducer = in.readInt();
            MatchingEngine engine = new MatchingEngine(resultCachePerProducer,
                    new Limits(in.readInt(), in.readInt(), in.readInt(), in.readInt()));
            engine.commandSeq = nonnegative(in.readLong()); engine.eventSeq = nonnegative(in.readLong());
            engine.marketSeq = nonnegative(in.readLong()); engine.nextOrderId = positive(in.readLong());
            engine.totalBase = nonnegative(in.readLong()); engine.totalQuote = nonnegative(in.readLong());
            int accountCount = count(in);
            for (int i = 0; i < accountCount; i++) {
                Account account = new Account(positive(in.readLong()));
                account.baseAvailable = nonnegative(in.readLong()); account.baseReserved = nonnegative(in.readLong());
                account.quoteAvailable = nonnegative(in.readLong()); account.quoteReserved = nonnegative(in.readLong());
                if (engine.accounts.put(account.id, account) != null) throw new IllegalArgumentException("duplicate account");
            }
            int orderCount = count(in);
            for (int i = 0; i < orderCount; i++) {
                long id = positive(in.readLong()), account = positive(in.readLong()); String clientId = readString(in);
                Side side = enumValue(Side.values(), in.readByte()); long price = positive(in.readLong());
                long original = positive(in.readLong()), remaining = nonnegative(in.readLong());
                TimeInForce tif = enumValue(TimeInForce.values(), in.readByte());
                OrderStatus status = enumValue(OrderStatus.values(), in.readByte()); long acceptedSeq = positive(in.readLong());
                Order order = new Order(id, account, clientId, side, price, original, tif, acceptedSeq);
                order.remaining = remaining; order.status = status;
                if (engine.orders.put(id, order) != null) throw new IllegalArgumentException("duplicate order");
                if (engine.clientIds.put(new ClientOrderKey(account, clientId), id) != null)
                    throw new IllegalArgumentException("duplicate client order id");
                if (isActive(status)) engine.bookFor(side).computeIfAbsent(price, ignored -> new LinkedHashMap<>()).put(id, order);
            }
            int producerCount = count(in);
            for (int i = 0; i < producerCount; i++) {
                ProducerKey key = new ProducerKey(positive(in.readLong()), readString(in));
                Producer producer = new Producer(); producer.highWater = positive(in.readLong());
                int cacheCount = count(in);
                if (!engine.validId(key.producerId) || cacheCount > engine.resultCachePerProducer)
                    throw new IllegalArgumentException("invalid producer cache");
                long previous = 0;
                for (int c = 0; c < cacheCount; c++) {
                    Command command = readCommand(in); Result result = readResult(in);
                    if (command.accountId() != key.accountId || !Objects.equals(command.producerId(), key.producerId)
                            || command.requestSeq() <= previous || command.requestSeq() > producer.highWater)
                        throw new IllegalArgumentException("invalid cached command");
                    previous = command.requestSeq(); producer.results.put(previous, new Cached(command, result));
                    if (result.commandSeq <= 0 || result.commandSeq > engine.commandSeq
                            || engine.cachedByCommandSeq.put(result.commandSeq, new CacheLocation(key, previous)) != null)
                        throw new IllegalArgumentException("invalid cached result sequence");
                }
                if ((cacheCount > 0 && previous != producer.highWater) || engine.producers.put(key, producer) != null)
                    throw new IllegalArgumentException("invalid producer state");
            }
            if (in.available() != 0) throw new IllegalArgumentException("trailing snapshot data");
            engine.checkInvariants();
            return engine;
        } catch (IOException | ArithmeticException | IllegalStateException exception) {
            throw new IllegalArgumentException("corrupt snapshot", exception);
        }
    }
    public String stateHash() {
        return HexFormat.of().formatHex(digest(snapshot()));
    }
    private static byte[] digest(byte[] bytes) {
        try { return MessageDigest.getInstance("SHA-256").digest(bytes); }
        catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }

    /** Expensive diagnostic, intentionally absent from the command hot path. */
    public void checkInvariants() {
        long base = 0, quote = 0;
        Map<Long, Long> reservedBase = new HashMap<>(), reservedQuote = new HashMap<>();
        if (accounts.size() > limits.maxAccounts || producers.size() > limits.maxProducers
                || orders.size() > limits.maxRetainedOrders || cachedByCommandSeq.size() > limits.maxCachedResults)
            throw new IllegalStateException("capacity exceeded");
        if (marketSeq > eventSeq || nextOrderId <= (orders.isEmpty() ? 0 : orders.lastKey()))
            throw new IllegalStateException("invalid engine sequence");
        for (Order order : orders.values()) {
            if (!accounts.containsKey(order.accountId) || order.remaining > order.original || order.price > Long.MAX_VALUE / order.original
                    || order.acceptedSeq > commandSeq || order.remaining < 0)
                throw new IllegalStateException("invalid order");
            if (order.status == OrderStatus.FILLED && order.remaining != 0) throw new IllegalStateException("filled order has residual");
            if (isActive(order.status)) {
                if (order.remaining == 0 || order.tif != TimeInForce.GTC) throw new IllegalStateException("invalid active order");
                if (order.side == Side.BUY) reservedQuote.merge(order.accountId, order.price * order.remaining, Math::addExact);
                else reservedBase.merge(order.accountId, order.remaining, Math::addExact);
                LinkedHashMap<Long, Order> level = bookFor(order.side).get(order.price);
                if (level == null || level.get(order.id) != order) throw new IllegalStateException("active order missing from book");
            }
        }
        for (Account account : accounts.values()) {
            if (account.baseAvailable < 0 || account.baseReserved < 0 || account.quoteAvailable < 0 || account.quoteReserved < 0)
                throw new IllegalStateException("negative balance");
            if (account.baseReserved != reservedBase.getOrDefault(account.id, 0L)
                    || account.quoteReserved != reservedQuote.getOrDefault(account.id, 0L))
                throw new IllegalStateException("reservation mismatch");
            base = Math.addExact(base, Math.addExact(account.baseAvailable, account.baseReserved));
            quote = Math.addExact(quote, Math.addExact(account.quoteAvailable, account.quoteReserved));
        }
        if (base != totalBase || quote != totalQuote) throw new IllegalStateException("asset conservation violated");
        if (!bids.isEmpty() && !asks.isEmpty() && bids.firstKey() >= asks.firstKey())
            throw new IllegalStateException("crossed resting book");
    }

    private static int count(DataInputStream in) throws IOException {
        int value = in.readInt();
        if (value < 0 || value > MAX_SNAPSHOT_ITEMS) throw new IllegalArgumentException("invalid snapshot count");
        return value;
    }
    private static long nonnegative(long value) {
        if (value < 0) throw new IllegalArgumentException("negative snapshot value"); return value;
    }
    private static long positive(long value) {
        if (value <= 0) throw new IllegalArgumentException("nonpositive snapshot value"); return value;
    }
    private static <T> T enumValue(T[] values, int ordinal) {
        if (ordinal < 0 || ordinal >= values.length) throw new IllegalArgumentException("invalid enum");
        return values[ordinal];
    }
    private static void writeString(DataOutputStream out, String value) throws IOException {
        if (value == null) { out.writeInt(-1); return; }
        // UTF-16 code units preserve even malformed Java strings in rejected-command caches.
        out.writeInt(value.length());
        for (int i = 0; i < value.length(); i++) out.writeChar(value.charAt(i));
    }
    private static String readString(DataInputStream in) throws IOException {
        int length = in.readInt(); if (length == -1) return null;
        if (length < 0 || length > 65536 || length > in.available() / 2) throw new IllegalArgumentException("invalid string size");
        char[] characters = new char[length];
        for (int i = 0; i < length; i++) characters[i] = in.readChar();
        return new String(characters);
    }
    private static void writeCommand(DataOutputStream out, Command command) throws IOException {
        out.writeByte(command instanceof Deposit ? 0 : command instanceof Place ? 1 : 2);
        out.writeLong(command.accountId()); writeString(out, command.producerId()); out.writeLong(command.requestSeq());
        if (command instanceof Deposit deposit) {
            out.writeByte(deposit.asset == null ? -1 : deposit.asset.ordinal()); out.writeLong(deposit.amount);
        } else if (command instanceof Place place) {
            writeString(out, place.clientOrderId); out.writeByte(place.side == null ? -1 : place.side.ordinal());
            out.writeLong(place.priceTicks); out.writeLong(place.quantityLots);
            out.writeByte(place.timeInForce == null ? -1 : place.timeInForce.ordinal());
        } else out.writeLong(((Cancel) command).orderId);
    }
    private static Command readCommand(DataInputStream in) throws IOException {
        int type = in.readByte(); long account = in.readLong(); String producer = readString(in); long seq = in.readLong();
        if (type == 0) {
            int asset = in.readByte(); return new Deposit(account, producer, seq, asset == -1 ? null : enumValue(Asset.values(), asset), in.readLong());
        }
        if (type == 1) {
            String client = readString(in); int side = in.readByte(); long price = in.readLong(), quantity = in.readLong(); int tif = in.readByte();
            return new Place(account, producer, seq, client, side == -1 ? null : enumValue(Side.values(), side), price, quantity,
                    tif == -1 ? null : enumValue(TimeInForce.values(), tif));
        }
        if (type == 2) return new Cancel(account, producer, seq, in.readLong());
        throw new IllegalArgumentException("invalid command type");
    }
    private static void writeResult(DataOutputStream out, Result result) throws IOException {
        out.writeByte(result.code.ordinal()); writeString(out, result.reason); out.writeLong(result.commandSeq);
        out.writeLong(result.orderId); out.writeLong(result.remainingQuantity); out.writeInt(result.tradeCount);
    }
    private static Result readResult(DataInputStream in) throws IOException {
        return new Result(enumValue(ResultCode.values(), in.readByte()), readString(in), in.readLong(), in.readLong(), in.readLong(), in.readInt());
    }
}
