package io.vectormatch.core;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.io.*;
import java.math.BigInteger;
import java.security.*;
import java.util.*;
import static io.vectormatch.core.MatchingEngine.*;

/** Bounded, single-writer escrow protocol. Unknown delivery never recreates spendable parent credit. */
public final class MarketEscrow {
    private MarketEscrow() {}
    private static final int MAX_ENTRIES = 10_000, MAX_SNAPSHOT = 128 * 1024 * 1024;
    private static final String RISK_PRODUCER = "risk-";
    public record Market(String id, String baseAsset, String quoteAsset, int groupId) {
        public Market {
            token(id); asset(baseAsset); asset(quoteAsset);
            if (baseAsset.equals(quoteAsset) || groupId < 0 || groupId > 1023) throw new IllegalArgumentException("market scope");
        }
    }
    public record BalanceKey(long accountId, String asset) implements Comparable<BalanceKey> {
        public BalanceKey { if (accountId < 1) throw new IllegalArgumentException("account"); MarketEscrow.asset(asset); }
        public int compareTo(BalanceKey other) { int c=Long.compare(accountId,other.accountId); return c==0?asset.compareTo(other.asset):c; }
    }
    public record Transfer(String id, long accountId, String market, String asset, long amount) {
        public Transfer { token(id); token(market); MarketEscrow.asset(asset); if(accountId<1||amount<1)throw new IllegalArgumentException("transfer"); }
    }
    public record Grant(String issuer, long sequence, Transfer transfer, int groupId, String signature) {
        public Grant { token(issuer); Objects.requireNonNull(transfer); if(sequence<1||groupId<0||groupId>1023)throw new IllegalArgumentException("grant"); hex(signature); }
    }
    public record Receipt(Grant grant, long destinationCommandSeq, String signature) {
        public Receipt { Objects.requireNonNull(grant); if(destinationCommandSeq<1)throw new IllegalArgumentException("receipt"); hex(signature); }
    }
    public enum Code { GRANTED, REJECTED, IDEMPOTENCY_CONFLICT }
    public enum Delivery { PENDING, DELIVERED }
    public record Reservation(Code code, Grant grant, String reason, boolean replayed) {}
    private record Cached(Transfer transfer, Code code, Grant grant, String reason) {
        Reservation result(boolean replayed) { return new Reservation(code,grant,reason,replayed); }
    }
    private static final class Owner {
        final Thread thread=Thread.currentThread();
        void require() { if(Thread.currentThread()!=thread)throw new IllegalStateException("single-writer ownership"); }
    }
    private static void token(String s) { if(s==null||!s.matches("[A-Za-z0-9_.-]{1,64}"))throw new IllegalArgumentException("identity"); }
    private static void asset(String s) { if(s==null||!s.matches("[A-Z][A-Z0-9]{0,11}"))throw new IllegalArgumentException("asset"); }
    private static void hex(String s) { if(s==null||!s.matches("[0-9a-f]{64}"))throw new IllegalArgumentException("signature"); }
    private static byte[] key(byte[] source) { if(source==null||source.length!=32)throw new IllegalArgumentException("32-byte key"); return source.clone(); }
    private static String hash(byte[] value) { try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));}catch(GeneralSecurityException e){throw new IllegalStateException(e);} }
    private static String sign(byte[] key, byte[] value) {
        try { Mac mac=Mac.getInstance("HmacSHA256");mac.init(new SecretKeySpec(key,"HmacSHA256"));return HexFormat.of().formatHex(mac.doFinal(value)); }
        catch(GeneralSecurityException e){throw new IllegalStateException(e);}
    }
    private static boolean equalSignature(String a,String b) { return MessageDigest.isEqual(HexFormat.of().parseHex(a),HexFormat.of().parseHex(b)); }
    @FunctionalInterface private interface Writer { void write(DataOutputStream out)throws IOException; }
    private static byte[] bytes(Writer writer) { try{var b=new ByteArrayOutputStream();try(var out=new DataOutputStream(b)){writer.write(out);}return b.toByteArray();}catch(IOException e){throw new UncheckedIOException(e);} }
    private static void writeMarket(DataOutputStream out,Market m)throws IOException {out.writeUTF(m.id);out.writeUTF(m.baseAsset);out.writeUTF(m.quoteAsset);out.writeInt(m.groupId);}
    private static Market readMarket(DataInputStream in)throws IOException{return new Market(in.readUTF(),in.readUTF(),in.readUTF(),in.readInt());}
    private static void writeTransfer(DataOutputStream out,Transfer t)throws IOException {out.writeUTF(t.id);out.writeLong(t.accountId);out.writeUTF(t.market);out.writeUTF(t.asset);out.writeLong(t.amount);}
    private static Transfer readTransfer(DataInputStream in)throws IOException{return new Transfer(in.readUTF(),in.readLong(),in.readUTF(),in.readUTF(),in.readLong());}
    private static byte[] grantBody(String issuer,long seq,Transfer transfer,int group) {return bytes(out->{out.writeUTF("VECTORMATCH_ESCROW_GRANT_V1");out.writeUTF(issuer);out.writeLong(seq);writeTransfer(out,transfer);out.writeInt(group);});}
    private static byte[] receiptBody(Grant grant,long seq) {return bytes(out->{out.writeUTF("VECTORMATCH_ESCROW_RECEIPT_V1");writeGrant(out,grant);out.writeLong(seq);});}
    public static void writeGrant(DataOutputStream out,Grant g)throws IOException {out.writeUTF(g.issuer);out.writeLong(g.sequence);writeTransfer(out,g.transfer);out.writeInt(g.groupId);out.writeUTF(g.signature);}
    public static Grant readGrant(DataInputStream in)throws IOException{return new Grant(in.readUTF(),in.readLong(),readTransfer(in),in.readInt(),in.readUTF());}
    public static void writeReceipt(DataOutputStream out,Receipt r)throws IOException{writeGrant(out,r.grant);out.writeLong(r.destinationCommandSeq);out.writeUTF(r.signature);}
    public static Receipt readReceipt(DataInputStream in)throws IOException{return new Receipt(readGrant(in),in.readLong(),in.readUTF());}
    private static byte[] seal(byte[] payload) {
        if(payload.length>MAX_SNAPSHOT-32)throw new IllegalStateException("snapshot bound");
        return bytes(out->{out.write(payload);out.write(HexFormat.of().parseHex(hash(payload)));});
    }
    private static DataInputStream open(byte[] snapshot)throws IOException {
        if(snapshot==null||snapshot.length<40||snapshot.length>MAX_SNAPSHOT)throw new IOException("snapshot length");
        byte[] payload=Arrays.copyOf(snapshot,snapshot.length-32);
        if(!MessageDigest.isEqual(HexFormat.of().parseHex(hash(payload)),Arrays.copyOfRange(snapshot,payload.length,snapshot.length)))throw new IOException("snapshot checksum");
        return new DataInputStream(new ByteArrayInputStream(payload));
    }
    private static int count(DataInputStream in,int maximum)throws IOException {int n=in.readInt();if(n<0||n>maximum)throw new IOException("entry bound");return n;}
    private static void bounds(int limit){if(limit<1||limit>MAX_ENTRIES)throw new IllegalArgumentException("entry bound");}

    /** Static funded parent. No timeout/refund API: failed or unknown delivery keeps the grant reserved. */
    public static final class Issuer {
        private final Owner owner=new Owner();
        private final String id;
        private final int maxTransfers;
        private final NavigableMap<String,Market> markets=new TreeMap<>();
        private final Map<String,byte[]> keys=new TreeMap<>();
        private final NavigableMap<BalanceKey,Long> initial=new TreeMap<>(),available=new TreeMap<>();
        private final NavigableMap<String,Cached> requests=new TreeMap<>();
        private final NavigableMap<String,Receipt> delivered=new TreeMap<>();
        private long sequence;
        public Issuer(String id,Map<Market,byte[]> markets,Map<BalanceKey,Long> funded,int maxTransfers) {
            token(id);bounds(maxTransfers);this.id=id;this.maxTransfers=maxTransfers;
            if(markets.isEmpty()||markets.size()>1024||funded.size()>MAX_ENTRIES)throw new IllegalArgumentException("profile bounds");
            for(var entry:markets.entrySet()) {
                Market market=entry.getKey();if(this.markets.put(market.id,market)!=null)throw new IllegalArgumentException("duplicate market");
                keys.put(market.id,key(entry.getValue()));
            }
            for(var entry:funded.entrySet()){Objects.requireNonNull(entry.getKey());if(entry.getValue()==null||entry.getValue()<0)throw new IllegalArgumentException("funding");initial.put(entry.getKey(),entry.getValue());}
            available.putAll(initial);
            sign(keys.values().iterator().next(),new byte[0]); // Fail provider setup before any financial mutation.
        }
        public Reservation reserve(Transfer transfer) {
            owner.require();Objects.requireNonNull(transfer);Market market=markets.get(transfer.market);
            if(market==null||!Set.of(market.baseAsset,market.quoteAsset).contains(transfer.asset))throw new IllegalArgumentException("market/asset scope");
            Cached prior=requests.get(transfer.id);
            if(prior!=null)return prior.transfer.equals(transfer)?prior.result(true):new Reservation(Code.IDEMPOTENCY_CONFLICT,null,"different transfer payload",false);
            if(requests.size()>=maxTransfers)throw new IllegalStateException("permanent transfer registry full");
            BalanceKey balance=new BalanceKey(transfer.accountId,transfer.asset);long free=available.getOrDefault(balance,0L);
            Cached result;
            if(transfer.amount>free)result=new Cached(transfer,Code.REJECTED,null,"INSUFFICIENT_FUNDS");
            else {
                long next=Math.addExact(sequence,1);String signature=sign(keys.get(market.id),grantBody(id,next,transfer,market.groupId));
                Grant grant=new Grant(id,next,transfer,market.groupId,signature);
                result=new Cached(transfer,Code.GRANTED,grant,"");
                available.put(balance,Math.subtractExact(free,transfer.amount));sequence=next;
            }
            requests.put(transfer.id,result);return result.result(false);
        }
        public Delivery delivery(String transferId){owner.require();Cached c=requests.get(transferId);if(c==null||c.grant==null)throw new IllegalArgumentException("no grant");return delivered.containsKey(transferId)?Delivery.DELIVERED:Delivery.PENDING;}
        public boolean acknowledge(Receipt receipt) {
            owner.require();Objects.requireNonNull(receipt);Cached cached=requests.get(receipt.grant.transfer.id);
            if(cached==null||cached.grant==null||!cached.grant.equals(receipt.grant))throw new IllegalArgumentException("receipt grant mismatch");
            if(!equalSignature(receipt.signature,sign(keys.get(receipt.grant.transfer.market),receiptBody(receipt.grant,receipt.destinationCommandSeq))))throw new IllegalArgumentException("receipt authentication");
            Receipt old=delivered.get(receipt.grant.transfer.id);if(old!=null){if(!old.equals(receipt))throw new IllegalArgumentException("conflicting receipt");return false;}
            delivered.put(receipt.grant.transfer.id,receipt);return true;
        }
        public long available(long account,String asset){owner.require();return available.getOrDefault(new BalanceKey(account,asset),0L);}
        public Map<BalanceKey,Long> available(){owner.require();return Collections.unmodifiableMap(new TreeMap<>(available));}
        public void checkInvariants() {
            owner.require();NavigableMap<BalanceKey,Long> expected=new TreeMap<>(initial);Set<Long> sequences=new HashSet<>();
            for(Cached c:requests.values()){Market scope=markets.get(c.transfer.market);if(scope==null||!Set.of(scope.baseAsset,scope.quoteAsset).contains(c.transfer.asset)||c.code==Code.IDEMPOTENCY_CONFLICT||(c.code==Code.GRANTED)!=(c.grant!=null)||!c.reason.equals(c.grant==null?"INSUFFICIENT_FUNDS":""))throw new IllegalStateException("cached transfer invariant");}
            for(Cached c:requests.values())if(c.grant!=null){Grant g=c.grant;Market m=markets.get(g.transfer.market);if(m==null||!g.issuer.equals(id)||g.groupId!=m.groupId||!c.transfer.equals(g.transfer)||!equalSignature(g.signature,sign(keys.get(m.id),grantBody(id,g.sequence,g.transfer,g.groupId)))||!sequences.add(g.sequence))throw new IllegalStateException("grant invariant");BalanceKey k=new BalanceKey(g.transfer.accountId,g.transfer.asset);expected.put(k,Math.subtractExact(expected.getOrDefault(k,0L),g.transfer.amount));}
            if(!expected.equals(available)||expected.values().stream().anyMatch(x->x<0)||sequences.size()!=sequence||sequences.stream().anyMatch(x->x<1||x>sequence)||requests.size()>maxTransfers)throw new IllegalStateException("funding/sequence invariant");
            for(Receipt receipt:delivered.values()){Cached c=requests.get(receipt.grant.transfer.id);if(c==null||!receipt.grant.equals(c.grant)||!equalSignature(receipt.signature,sign(keys.get(receipt.grant.transfer.market),receiptBody(receipt.grant,receipt.destinationCommandSeq))))throw new IllegalStateException("delivery invariant");}
        }
        public byte[] snapshot() {
            owner.require();checkInvariants();return seal(bytes(out->{out.writeInt(0x56454931);out.writeInt(1);out.writeUTF(id);out.writeInt(maxTransfers);out.writeInt(markets.size());for(Market m:markets.values()){writeMarket(out,m);out.writeUTF(hash(keys.get(m.id)));}out.writeInt(initial.size());for(var e:initial.entrySet()){out.writeLong(e.getKey().accountId);out.writeUTF(e.getKey().asset);out.writeLong(e.getValue());out.writeLong(available.get(e.getKey()));}out.writeLong(sequence);out.writeInt(requests.size());for(Cached c:requests.values()){writeTransfer(out,c.transfer);out.writeInt(c.code.ordinal());out.writeUTF(c.reason);out.writeBoolean(c.grant!=null);if(c.grant!=null)writeGrant(out,c.grant);}out.writeInt(delivered.size());for(Receipt r:delivered.values())writeReceipt(out,r);}));
        }
        public static Issuer restore(byte[] snapshot,String id,Map<Market,byte[]> markets,Map<BalanceKey,Long> funding,int maxTransfers) {
            Issuer result=new Issuer(id,markets,funding,maxTransfers);
            try(var in=open(snapshot)) {
                if(in.readInt()!=0x56454931||in.readInt()!=1||!in.readUTF().equals(id)||in.readInt()!=maxTransfers)throw new IOException("issuer contract");
                int n=count(in,1024);if(n!=result.markets.size())throw new IOException("markets");for(int i=0;i<n;i++){Market m=readMarket(in);if(!m.equals(result.markets.get(m.id))||!in.readUTF().equals(hash(result.keys.get(m.id))))throw new IOException("market/key profile");}
                n=count(in,MAX_ENTRIES);NavigableMap<BalanceKey,Long> funded=new TreeMap<>();result.available.clear();for(int i=0;i<n;i++){BalanceKey k=new BalanceKey(in.readLong(),in.readUTF());if(funded.put(k,in.readLong())!=null)throw new IOException("duplicate balance");result.available.put(k,in.readLong());}if(!funded.equals(result.initial))throw new IOException("funding profile");
                result.sequence=in.readLong();n=count(in,maxTransfers);for(int i=0;i<n;i++){Transfer t=readTransfer(in);int code=in.readInt();if(code<0||code>=2)throw new IOException("cached status");String reason=in.readUTF();Grant g=in.readBoolean()?readGrant(in):null;if((code==0)!=(g!=null)||result.requests.put(t.id,new Cached(t,Code.values()[code],g,reason))!=null)throw new IOException("cached request");}
                n=count(in,maxTransfers);for(int i=0;i<n;i++){Receipt r=readReceipt(in);if(result.delivered.put(r.grant.transfer.id,r)!=null)throw new IOException("duplicate receipt");}if(in.available()!=0)throw new IOException("trailing bytes");result.checkInvariants();if(!Arrays.equals(snapshot,result.snapshot()))throw new IOException("noncanonical snapshot");return result;
            }catch(IOException|IllegalStateException|ArithmeticException e){throw new IllegalArgumentException("invalid issuer snapshot",e);}
        }
    }

    /** One independent book. Only authenticated grants can credit it; normal clients cannot deposit. */
    public static final class Shard {
        private final Owner owner=new Owner();private final Market market;private final String issuer;private final byte[] key;private final int maxGrants;
        private MatchingEngine engine;private final NavigableMap<String,Receipt> credits=new TreeMap<>();
        public Shard(Market market,String issuer,byte[] key,Limits limits,int maxGrants) {
            this.market=Objects.requireNonNull(market);token(issuer);this.issuer=issuer;this.key=key(key);bounds(maxGrants);this.maxGrants=maxGrants;this.engine=new MatchingEngine(16,limits);sign(this.key,new byte[0]);
        }
        public Receipt apply(Grant grant) {
            owner.require();Objects.requireNonNull(grant);Transfer t=grant.transfer;
            if(!grant.issuer.equals(issuer)||!t.market.equals(market.id)||grant.groupId!=market.groupId||!Set.of(market.baseAsset,market.quoteAsset).contains(t.asset)||!equalSignature(grant.signature,sign(key,grantBody(grant.issuer,grant.sequence,t,grant.groupId))))throw new IllegalArgumentException("grant scope/authentication");
            Receipt old=credits.get(t.id);if(old!=null){if(!old.grant.equals(grant))throw new IllegalArgumentException("conflicting credit");return old;}
            if(credits.size()>=maxGrants)throw new IllegalStateException("permanent credit registry full");
            String producer=RISK_PRODUCER+hash((issuer+"/"+t.id).getBytes(java.nio.charset.StandardCharsets.UTF_8)).substring(0,40);
            Deposit deposit=new Deposit(t.accountId,producer,1,t.asset.equals(market.baseAsset)?Asset.BASE:Asset.QUOTE,t.amount);
            if(engine.maximumEventsFor(deposit)!=1)throw new IllegalStateException("credit exceeds book capacity or supply bound");
            Execution applied=engine.apply(deposit);
            if(!applied.result().accepted())throw new IllegalStateException("credit rejected: "+applied.result().code());
            Receipt receipt=new Receipt(grant,applied.result().commandSeq(),sign(key,receiptBody(grant,applied.result().commandSeq())));credits.put(t.id,receipt);return receipt;
        }
        public Execution execute(String marketId,Command command) {
            owner.require();Objects.requireNonNull(command);
            if(!market.id.equals(marketId)||command instanceof Deposit||command.producerId()==null||command.producerId().startsWith(RISK_PRODUCER))throw new IllegalArgumentException("business market/credit namespace");
            return engine.apply(command);
        }
        public AccountView account(long id){owner.require();return engine.account(id);}
        public BookView book(int depth){owner.require();return engine.book(depth);}
        public List<AccountView> accounts(){owner.require();return engine.accounts();}
        public long commandSeq(){owner.require();return engine.lastCommandSeq();}
        public Market market(){return market;}
        public Optional<Receipt> receipt(String id){owner.require();return Optional.ofNullable(credits.get(id));}
        public void checkInvariants() {
            owner.require();engine.checkInvariants();Map<String,BigInteger> expected=new TreeMap<>();expected.put(market.baseAsset,BigInteger.ZERO);expected.put(market.quoteAsset,BigInteger.ZERO);
            for(Receipt receipt:credits.values()){Grant g=receipt.grant;Transfer t=g.transfer;if(!g.issuer.equals(issuer)||!t.market.equals(market.id)||g.groupId!=market.groupId||!Set.of(market.baseAsset,market.quoteAsset).contains(t.asset)||receipt.destinationCommandSeq>engine.lastCommandSeq()||!equalSignature(g.signature,sign(key,grantBody(issuer,g.sequence,t,g.groupId)))||!equalSignature(receipt.signature,sign(key,receiptBody(g,receipt.destinationCommandSeq))))throw new IllegalStateException("credit invariant");expected.compute(t.asset,(k,v)->v.add(BigInteger.valueOf(t.amount)));}
            BigInteger base=BigInteger.ZERO,quote=BigInteger.ZERO;for(AccountView a:engine.accounts()){base=base.add(BigInteger.valueOf(a.base().available())).add(BigInteger.valueOf(a.base().reserved()));quote=quote.add(BigInteger.valueOf(a.quote().available())).add(BigInteger.valueOf(a.quote().reserved()));}
            if(!base.equals(expected.get(market.baseAsset))||!quote.equals(expected.get(market.quoteAsset))||credits.size()>maxGrants)throw new IllegalStateException("book asset conservation");
        }
        public byte[] snapshot() {
            owner.require();checkInvariants();return seal(bytes(out->{out.writeInt(0x56455331);out.writeInt(1);writeMarket(out,market);out.writeUTF(issuer);out.writeUTF(hash(key));out.writeInt(maxGrants);out.writeInt(credits.size());for(Receipt r:credits.values())writeReceipt(out,r);byte[] core=engine.snapshot();out.writeInt(core.length);out.write(core);}));
        }
        public static Shard restore(byte[] snapshot,Market market,String issuer,byte[] key,Limits limits,int maxGrants) {
            Shard shard=new Shard(market,issuer,key,limits,maxGrants);
            try(var in=open(snapshot)) {
                if(in.readInt()!=0x56455331||in.readInt()!=1||!readMarket(in).equals(market)||!in.readUTF().equals(issuer)||!in.readUTF().equals(hash(key))||in.readInt()!=maxGrants)throw new IOException("shard contract/profile");
                int n=count(in,maxGrants);for(int i=0;i<n;i++){Receipt receipt=readReceipt(in);if(shard.credits.put(receipt.grant.transfer.id,receipt)!=null)throw new IOException("duplicate credit");}
                n=count(in,MAX_SNAPSHOT);if(n>in.available())throw new IOException("core length");shard.engine=MatchingEngine.restore(in.readNBytes(n));if(!shard.engine.limits().equals(limits)||shard.engine.resultCachePerProducer()!=16||in.available()!=0)throw new IOException("core profile/trailing data");shard.checkInvariants();if(!Arrays.equals(snapshot,shard.snapshot()))throw new IOException("noncanonical snapshot");return shard;
            }catch(IOException|IllegalStateException|ArithmeticException e){throw new IllegalArgumentException("invalid shard snapshot",e);}
        }
    }
}
