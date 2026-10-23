export type Side = "BUY" | "SELL";
export interface Level {
  priceTicks: number;
  quantityLots: number;
  orderCount?: number;
}
export interface Trade {
  id: string;
  priceTicks: number;
  quantityLots: number;
  side: Side;
  timestamp: number;
}
export interface Account {
  id: string;
  name: string;
  quoteAvailable?: number;
  quoteReserved?: number;
  baseAvailable?: number;
  baseReserved?: number;
}
export interface Order {
  id: string;
  accountId: string;
  side: Side;
  priceTicks: number;
  quantityLots: number;
  remainingLots: number;
  status: string;
  timestamp: number;
}
export interface State {
  symbol: string;
  base: string;
  quote: string;
  priceScale: number;
  quantityScale: number;
  bids: Level[];
  asks: Level[];
  trades: Trade[];
  accounts: Account[];
  orders: Order[];
  metrics: Record<string, unknown>;
  health: Record<string, unknown>;
  verification: Record<string, unknown>;
  projection: Record<string, unknown>;
  sequence?: number;
  receivedAt: number;
}
export interface Sample {
  timestamp: number;
  price: number;
  bid?: number;
  ask?: number;
}
export interface CommandSample {
  timestamp: number;
  millis: number;
  accepted: boolean;
}
export interface OrderCommand {
  accountId: number;
  side: Side;
  priceTicks: number;
  quantityLots: number;
  timeInForce: string;
  producerId: string;
  requestSeq: number;
  clientOrderId: string;
}
export interface CancelCommand {
  accountId: number;
  orderId: string | number;
  producerId: string;
  requestSeq: number;
}
type Obj = Record<string, unknown>;
export const asObject = (value: unknown): Obj =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Obj)
    : {};
const number = (value: unknown, fallback = 0): number =>
  typeof value === "number" && Number.isFinite(value)
    ? value
    : typeof value === "string" &&
        value.trim() &&
        Number.isFinite(Number(value))
      ? Number(value)
      : fallback;
const optionalNumber = (value: unknown): number | undefined =>
  value === undefined || value === null ? undefined : number(value);
const string = (value: unknown, fallback = ""): string =>
  value == null ? fallback : String(value);
const array = (value: unknown): unknown[] =>
  Array.isArray(value)
    ? value
    : value && typeof value === "object"
      ? Object.entries(value).map(([id, item]) => ({ id, ...asObject(item) }))
      : [];
const side = (value: unknown): Side =>
  String(value).toUpperCase() === "SELL" ||
  String(value).toUpperCase() === "ASK"
    ? "SELL"
    : "BUY";
const timestamp = (value: unknown) =>
  typeof value === "string" && !/^\d+$/.test(value)
    ? Date.parse(value) || 0
    : number(value);
const levels = (value: unknown): Level[] =>
  array(value)
    .map((item) => {
      if (Array.isArray(item))
        return {
          priceTicks: number(item[0]),
          quantityLots: number(item[1]),
          orderCount: optionalNumber(item[2]),
        };
      const v = asObject(item);
      return {
        priceTicks: number(v.priceTicks ?? v.price),
        quantityLots: number(v.quantityLots ?? v.quantity ?? v.size),
        orderCount: optionalNumber(v.orderCount ?? v.orders),
      };
    })
    .filter((v) => v.quantityLots > 0 && v.priceTicks > 0);

export function normalizeState(value: unknown): State {
  const raw = asObject(value);
  const d = asObject(
    raw.data && (raw.type === "state" || raw.type === "snapshot")
      ? raw.data
      : raw,
  );
  const market = asObject(d.market);
  const symbol = string(
    market.symbol ??
      market.name ??
      (typeof d.market === "string" ? d.market : d.symbol),
    "BASE/QUOTE",
  );
  const [base = "BASE", quote = "QUOTE"] = symbol
    .replace(/[-_]/g, "/")
    .split("/")
    .map((s) => s.trim());
  const book = asObject(d.book ?? d.orderBook);
  return {
    symbol,
    base: string(market.base ?? market.baseAsset, base),
    quote: string(market.quote ?? market.quoteAsset, quote),
    priceScale: number(market.priceScale ?? d.priceScale, 100) || 100,
    quantityScale: number(market.quantityScale ?? d.quantityScale, 1) || 1,
    bids: levels(book.bids ?? d.bids).sort(
      (a, b) => b.priceTicks - a.priceTicks,
    ),
    asks: levels(book.asks ?? d.asks).sort(
      (a, b) => a.priceTicks - b.priceTicks,
    ),
    trades: array(d.trades ?? d.recentTrades)
      .map((item, i) => {
        const v = asObject(item);
        return {
          id: string(v.id ?? v.tradeId, String(i)),
          priceTicks: number(v.priceTicks ?? v.price),
          quantityLots: number(v.quantityLots ?? v.quantity ?? v.size),
          side: side(v.side ?? v.aggressorSide ?? v.takerSide),
          timestamp: timestamp(v.timestamp ?? v.timestampMillis ?? v.time),
        };
      })
      .slice(0, 100),
    accounts: array(d.accounts).map((item) => {
      const v = asObject(item);
      const q = asObject(v.quote);
      const b = asObject(v.base);
      return {
        id: string(v.id ?? v.accountId),
        name: string(v.name ?? v.id ?? v.accountId),
        quoteAvailable: optionalNumber(
          v.quoteAvailable ?? v.availableQuote ?? q.available,
        ),
        quoteReserved: optionalNumber(
          v.quoteReserved ?? v.quoteFrozen ?? v.reservedQuote ?? q.reserved,
        ),
        baseAvailable: optionalNumber(
          v.baseAvailable ?? v.availableBase ?? b.available,
        ),
        baseReserved: optionalNumber(
          v.baseReserved ?? v.baseFrozen ?? v.reservedBase ?? b.reserved,
        ),
      };
    }),
    orders: array(d.orders ?? d.openOrders).map((item, i) => {
      const v = asObject(item);
      return {
        id: string(v.id ?? v.orderId, String(i)),
        accountId: string(v.accountId),
        side: side(v.side),
        priceTicks: number(v.priceTicks ?? v.price),
        quantityLots: number(
          v.quantityLots ?? v.originalQuantity ?? v.quantity,
        ),
        remainingLots: number(
          v.remainingLots ??
            v.remainingQuantity ??
            v.remaining ??
            v.quantityLots ??
            v.quantity,
        ),
        status: string(v.status, "OPEN").toUpperCase(),
        timestamp: timestamp(v.timestamp ?? v.timestampMillis ?? v.createdAt),
      };
    }),
    metrics: asObject(d.metrics),
    health: asObject(d.health),
    projection: asObject(d.projection),
    verification: asObject(
      d.replayVerification ?? d.verification ?? d.lastVerification,
    ),
    sequence: optionalNumber(
      d.sequence ??
        d.eventSeq ??
        asObject(d.health).sequence ??
        asObject(d.metrics).marketSeq,
    ),
    receivedAt: Date.now(),
  };
}

export const API_BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
export const socketUrl = () =>
  API_BASE
    ? `${API_BASE.replace(/^http/, "ws")}/ws`
    : `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/ws`;
export async function fetchState(): Promise<State> {
  const response = await fetch(`${API_BASE}/api/state`, {
    signal: AbortSignal.timeout(5000),
    headers: { Accept: "application/json" },
  });
  if (!response.ok)
    throw new Error(`State endpoint returned HTTP ${response.status}`);
  return normalizeState(await response.json());
}
export async function sendCommand(
  path: "orders" | "cancel",
  command: OrderCommand | CancelCommand,
): Promise<{ data: Obj; millis: number; accepted: boolean; message: string }> {
  const started = performance.now();
  const response = await fetch(`${API_BASE}/api/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(command),
    signal: AbortSignal.timeout(10000),
  });
  const text = await response.text();
  let data: Obj = {};
  try {
    data = asObject(JSON.parse(text));
  } catch {
    data = { message: text };
  }
  const result = asObject(data.result);
  const status = string(
    data.status ??
      result.code ??
      (typeof data.result === "string" ? data.result : ""),
  ).toUpperCase();
  const accepted =
    response.ok &&
    data.accepted !== false &&
    result.accepted !== false &&
    data.success !== false &&
    ![
      "REJECTED",
      "ERROR",
      "INSUFFICIENT",
      "INVALID",
      "NOT_FOUND",
      "CONFLICT",
      "STALE",
    ].some((s) => status.includes(s));
  return {
    data,
    millis: performance.now() - started,
    accepted,
    message: string(
      data.message ??
        data.error ??
        data.reason ??
        result.reason ??
        data.status ??
        result.code,
      response.ok
        ? path === "orders"
          ? "Order acknowledged"
          : "Cancel acknowledged"
        : `HTTP ${response.status}`,
    ),
  };
}

export async function sendControl(
  path: "flow" | "replay",
  body: Record<string, unknown> = {},
): Promise<Obj> {
  const response = await fetch(`${API_BASE}/api/control/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(30_000),
  });
  const data = asObject(await response.json());
  if (!response.ok)
    throw new Error(
      String(data.message ?? data.error ?? `HTTP ${response.status}`),
    );
  return data;
}

export function metric(
  source: Record<string, unknown>,
  ...keys: string[]
): number | undefined {
  for (const key of keys) {
    const value = source[key];
    if (value !== null && value !== undefined && Number.isFinite(Number(value)))
      return Number(value);
  }
  return undefined;
}
export function textField(
  source: Record<string, unknown>,
  ...keys: string[]
): string | undefined {
  for (const key of keys)
    if (source[key] !== null && source[key] !== undefined)
      return String(source[key]);
  return undefined;
}
