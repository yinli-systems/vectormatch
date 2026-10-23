import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  asObject,
  fetchState,
  metric,
  normalizeState,
  sendCommand,
  sendControl,
  socketUrl,
  textField,
  type CancelCommand,
  type CommandSample,
  type OrderCommand,
  type Sample,
  type Side,
  type State,
} from "./api";

type IconName =
  | "chevron"
  | "arrow"
  | "activity"
  | "layers"
  | "terminal"
  | "refresh"
  | "check"
  | "close"
  | "external"
  | "bolt"
  | "clock"
  | "info"
  | "copy";
function Icon({
  name,
  size = 16,
  className = "",
}: {
  name: IconName;
  size?: number;
  className?: string;
}) {
  const paths: Record<IconName, React.ReactNode> = {
    chevron: <path d="m6 9 6 6 6-6" />,
    arrow: (
      <>
        <path d="M5 12h14M13 6l6 6-6 6" />
      </>
    ),
    activity: <path d="M3 12h4l3-8 4 16 3-8h4" />,
    layers: (
      <>
        <path d="m12 3 10 5-10 5L2 8l10-5ZM2 12l10 5 10-5M2 16l10 5 10-5" />
      </>
    ),
    terminal: (
      <>
        <path d="m5 7 5 5-5 5M13 17h6" />
      </>
    ),
    refresh: (
      <>
        <path d="M20 8a8 8 0 0 0-14-3L3 8M3 3v5h5M4 16a8 8 0 0 0 14 3l3-3M16 16h5v5" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    external: (
      <>
        <path d="M14 3h7v7M21 3 10 14M10 3H3v18h18v-7" />
      </>
    ),
    bolt: <path d="m13 2-9 12h7l-1 8 10-12h-7l1-8Z" />,
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </>
    ),
    info: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 11v6M12 7v.1" />
      </>
    ),
    copy: (
      <>
        <rect x="8" y="8" width="12" height="12" rx="2" />
        <path d="M16 8V4H4v12h4" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}
const number = (value: number | undefined, digits = 0) =>
  value === undefined
    ? "—"
    : value.toLocaleString("en-US", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });
const compact = (value: number | undefined) =>
  value === undefined
    ? "—"
    : new Intl.NumberFormat("en-US", {
        notation: "compact",
        maximumFractionDigits: 1,
      }).format(value);
const decimals = (scale: number) => Math.max(0, Math.ceil(Math.log10(scale)));
const formatTime = (time: number) =>
  time
    ? new Date(time).toLocaleTimeString("en-GB", {
        timeZone: "UTC",
        hour12: false,
      })
    : "—";
const quantile = (values: number[], q: number) =>
  values.length
    ? [...values].sort((a, b) => a - b)[
        Math.min(values.length - 1, Math.ceil(values.length * q) - 1)
      ]
    : undefined;
const activeStatus = (status: string) =>
  ["OPEN", "NEW", "ACCEPTED", "PARTIALLY_FILLED", "PARTIAL"].includes(status);
interface Log {
  id: string;
  time: number;
  action: string;
  status: string;
  millis?: number;
  message: string;
}
interface Notice {
  type: "success" | "error" | "unknown";
  message: string;
}

function useMarket() {
  const [state, setState] = useState<State>();
  const [samples, setSamples] = useState<Sample[]>([]);
  const [socket, setSocket] = useState(false);
  const [error, setError] = useState<string>();
  const [fetching, setFetching] = useState(false);
  const fetchingRef = useRef(false);
  const accept = useCallback((next: State) => {
    setState(next);
    setError(undefined);
    const bid = next.bids[0]?.priceTicks;
    const ask = next.asks[0]?.priceTicks;
    const price =
      next.trades[0]?.priceTicks ??
      (bid && ask ? (bid + ask) / 2 : (bid ?? ask));
    if (price)
      setSamples((previous) =>
        [
          ...previous.filter((item) => item.timestamp > Date.now() - 3_600_000),
          { timestamp: Date.now(), price, bid, ask },
        ].slice(-1800),
      );
  }, []);
  const refresh = useCallback(async () => {
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    setFetching(true);
    try {
      accept(await fetchState());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cannot reach the engine");
    } finally {
      fetchingRef.current = false;
      setFetching(false);
    }
  }, [accept]);
  useEffect(() => {
    let disposed = false;
    let connection: WebSocket | undefined;
    let reconnect: ReturnType<typeof setTimeout>;
    const connect = () => {
      if (disposed) return;
      connection = new WebSocket(socketUrl());
      connection.onopen = () => setSocket(true);
      connection.onmessage = (event) => {
        try {
          const raw = JSON.parse(event.data);
          const data = asObject(raw);
          const inner = asObject(data.data);
          if (data.book || data.orderBook || inner.book || inner.orderBook)
            accept(normalizeState(raw));
          else if (data.type === "delta" || data.type === "update")
            void refresh();
        } catch {
          /* A malformed stream frame does not replace the last valid state. */
        }
      };
      connection.onclose = () => {
        setSocket(false);
        if (!disposed) reconnect = setTimeout(connect, 3000);
      };
      connection.onerror = () => connection?.close();
    };
    void refresh();
    connect();
    const polling = setInterval(() => {
      if (document.visibilityState === "visible") void refresh();
    }, 2000);
    return () => {
      disposed = true;
      clearInterval(polling);
      clearTimeout(reconnect);
      connection?.close();
    };
  }, [accept, refresh]);
  return { state, samples, socket, error, fetching, refresh };
}

function PriceChart({
  samples,
  scale,
  range,
}: {
  samples: Sample[];
  scale: number;
  range: string;
}) {
  const now = Date.now();
  const duration =
    range === "1M" ? 60_000 : range === "5M" ? 300_000 : 3_600_000;
  const data = samples.filter((sample) => now - sample.timestamp <= duration);
  const prices = data.map((s) => s.price / scale);
  const low = prices.length ? Math.min(...prices) : 0;
  const high = prices.length ? Math.max(...prices) : 1;
  const padding = Math.max((high - low) * 0.25, (high || 1) * 0.0004);
  const min = low - padding;
  const max = high + padding;
  const left = data[0]?.timestamp ?? now - duration;
  const right = Math.max(now, left + 1000);
  const x = (time: number) => 20 + ((time - left) / (right - left)) * 670;
  const y = (value: number) =>
    18 + (1 - (value / scale - min) / (max - min)) * 184;
  const path = data
    .map(
      (point, index) =>
        `${index === 0 ? "M" : "L"}${x(point.timestamp).toFixed(2)},${y(point.price).toFixed(2)}`,
    )
    .join(" ");
  const last = data.at(-1);
  return (
    <div className="chart-wrap">
      <svg
        viewBox="0 0 790 245"
        preserveAspectRatio="none"
        role="img"
        aria-label="Observed price history from live engine snapshots"
      >
        <defs>
          <linearGradient id="chart-fill" x1="0" y1="0" x2="0" y2="1">
            <stop stopColor="#9ce5b9" stopOpacity=".14" />
            <stop offset="1" stopColor="#9ce5b9" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 1, 2, 3, 4].map((i) => (
          <g key={i}>
            <line
              x1="0"
              x2="710"
              y1={18 + i * 46}
              y2={18 + i * 46}
              className="chart-grid"
            />
            <text x="730" y={22 + i * 46} className="chart-label">
              {prices.length
                ? number(max - ((max - min) * i) / 4, decimals(scale))
                : "—"}
            </text>
          </g>
        ))}
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <line
            key={i}
            x1={20 + i * 134}
            x2={20 + i * 134}
            y1="0"
            y2="212"
            className="chart-grid vertical"
          />
        ))}
        {data.length > 1 && (
          <>
            <path
              d={`${path} L${x(last!.timestamp)},212 L20,212Z`}
              fill="url(#chart-fill)"
            />
            <path
              d={path}
              fill="none"
              stroke="#a2e7bb"
              strokeWidth="1.8"
              vectorEffect="non-scaling-stroke"
            />
          </>
        )}
        {last && (
          <>
            <line
              x1="0"
              x2="710"
              y1={y(last.price)}
              y2={y(last.price)}
              className="chart-current-line"
            />
            <circle
              cx={x(last.timestamp)}
              cy={y(last.price)}
              r="3"
              fill="#a2e7bb"
            />
            <rect
              x="720"
              y={y(last.price) - 10}
              width="70"
              height="21"
              rx="3"
              fill="#a2e7bb"
            />
            <text
              x="755"
              y={y(last.price) + 4}
              textAnchor="middle"
              className="chart-last"
            >
              {number(last.price / scale, decimals(scale))}
            </text>
          </>
        )}
        {[0, 1, 2, 3, 4].map((i) => (
          <text
            x={20 + i * 167.5}
            y="238"
            className="chart-label"
            textAnchor={i === 0 ? "start" : "middle"}
            key={i}
          >
            {data.length ? formatTime(left + ((right - left) * i) / 4) : "—"}
          </text>
        ))}
      </svg>
      {!data.length && (
        <div className="chart-empty">
          <Icon name="activity" size={25} />
          <strong>Waiting for market data</strong>
          <span>Price history builds from live observations.</span>
        </div>
      )}
    </div>
  );
}

function App() {
  const { state, samples, socket, error, fetching, refresh } = useMarket();
  const [clock, setClock] = useState(Date.now());
  const [side, setSide] = useState<Side>("BUY");
  const [accountId, setAccountId] = useState("");
  const [price, setPrice] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [timeInForce, setTimeInForce] = useState("GTC");
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState<Notice>();
  const [commands, setCommands] = useState<CommandSample[]>([]);
  const [logs, setLogs] = useState<Log[]>([]);
  const [range, setRange] = useState("5M");
  const [bookMode, setBookMode] = useState("All");
  const [tableTab, setTableTab] = useState("Open orders");
  const [showApi, setShowApi] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [retryCommand, setRetryCommand] = useState<{
    path: "orders" | "cancel";
    command: OrderCommand | CancelCommand;
  }>();
  const [cancelPending, setCancelPending] = useState<string>();
  const [controlPending, setControlPending] = useState<"flow" | "replay">();
  const [controlError, setControlError] = useState<string>();
  const [flowRate, setFlowRate] = useState("10");
  const [verification, setVerification] = useState<Record<string, unknown>>();
  const producer = useRef(
    sessionStorage.getItem("vectormatch.producer") ||
      `web-${crypto.randomUUID()}`,
  );
  const requestSeq = useRef(
    Number(sessionStorage.getItem("vectormatch.sequence") || 0),
  );
  useEffect(() => {
    sessionStorage.setItem("vectormatch.producer", producer.current);
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!accountId && state?.accounts.length)
      setAccountId(state.accounts[0].id);
  }, [state, accountId]);
  const scale = state?.priceScale || 100;
  const quantityScale = state?.quantityScale || 1;
  const pd = decimals(scale);
  const qd = decimals(quantityScale);
  const base = state?.base || "BASE";
  const quote = state?.quote || "QUOTE";
  const bid = state?.bids[0]?.priceTicks;
  const ask = state?.asks[0]?.priceTicks;
  const lastPrice =
    state?.trades[0]?.priceTicks ??
    (bid && ask ? (bid + ask) / 2 : (bid ?? ask));
  const firstPrice = samples[0]?.price;
  const change =
    lastPrice && firstPrice
      ? ((lastPrice - firstPrice) / firstPrice) * 100
      : undefined;
  const spread = bid && ask ? (ask - bid) / scale : undefined;
  const spreadBps =
    bid && ask ? ((ask - bid) / ((ask + bid) / 2)) * 10_000 : undefined;
  const account = state?.accounts.find((a) => a.id === accountId);
  const openOrders =
    state?.orders.filter(
      (order) =>
        (!order.accountId || order.accountId === accountId) &&
        activeStatus(order.status),
    ) || [];
  const levelsCount = (state?.bids.length || 0) + (state?.asks.length || 0);
  const fresh = !!state && clock - state.receivedAt < 8000;
  const connected = fresh && !error;
  const engineWritable = connected && state?.health.status !== "STORAGE_FAILED";
  const measurements = useMemo(() => commands.map((s) => s.millis), [commands]);
  const p50 = quantile(measurements, 0.5);
  const p99 = quantile(measurements, 0.99);
  const m = state?.metrics || {};
  const h = state?.health || {};
  const sequence =
    state?.sequence ?? metric(h, "sequence", "eventCount", "eventSequence");
  const engineCommands = metric(
    m,
    "commandsTotal",
    "commands",
    "commandCount",
    "processedCommands",
    "commandsProcessed",
    "totalCommands",
  );
  const engineTrades = metric(
    m,
    "tradesTotal",
    "trades",
    "tradeCount",
    "totalTrades",
    "matchedTrades",
  );
  const uptime =
    metric(h, "uptimeMillis", "uptimeMs") ??
    metric(m, "uptimeMillis", "uptimeMs");
  const rawMode = textField(h, "mode", "deploymentMode");
  const mode =
    rawMode === "LOCAL_JOURNALED"
      ? "Local journal · single node"
      : rawMode || "Not reported";
  const verified = verification ?? state?.verification ?? {};
  const replay =
    verified.consistent === true
      ? "State hash verified"
      : verified.consistent === false
        ? "Verification failed"
        : textField(h, "replayStatus", "replay", "recoveryStatus");
  const flowEnabled = h.flowEnabled === true;
  const engineP99 = metric(
    m,
    "p99Micros",
    "commandP99Micros",
    "latencyP99Micros",
  );
  const nextSeq = () => {
    requestSeq.current++;
    sessionStorage.setItem("vectormatch.sequence", String(requestSeq.current));
    return requestSeq.current;
  };
  const control = async (path: "flow" | "replay") => {
    setControlPending(path);
    setControlError(undefined);
    try {
      const response = await sendControl(
        path,
        path === "flow"
          ? { enabled: !flowEnabled, rate: Number(flowRate) }
          : {},
      );
      if (path === "replay") setVerification(response);
      await refresh();
    } catch (e) {
      setControlError(
        e instanceof Error ? e.message : "Control request failed",
      );
    } finally {
      setControlPending(undefined);
    }
  };
  const execute = async (
    path: "orders" | "cancel",
    command: OrderCommand | CancelCommand,
  ) => {
    setPending(true);
    setNotice(undefined);
    setRetryCommand(undefined);
    try {
      const result = await sendCommand(path, command);
      setCommands((previous) =>
        [
          ...previous,
          {
            timestamp: Date.now(),
            millis: result.millis,
            accepted: result.accepted,
          },
        ].slice(-2000),
      );
      setLogs((previous) =>
        [
          {
            id: `${command.producerId}:${command.requestSeq}`,
            time: Date.now(),
            action:
              path === "orders"
                ? `${(command as OrderCommand).side} LIMIT`
                : "CANCEL",
            status: result.accepted ? "ACKNOWLEDGED" : "REJECTED",
            millis: result.millis,
            message: result.message,
          },
          ...previous,
        ].slice(0, 100),
      );
      setNotice({
        type: result.accepted ? "success" : "error",
        message: `${result.message} · ${result.millis.toFixed(1)} ms RTT`,
      });
      await refresh();
    } catch (e) {
      const message = e instanceof Error ? e.message : "Network request failed";
      setRetryCommand({ path, command });
      setNotice({
        type: "unknown",
        message: `Outcome unknown. Retry uses the same request key. ${message}`,
      });
      setLogs((previous) =>
        [
          {
            id: `${command.producerId}:${command.requestSeq}`,
            time: Date.now(),
            action:
              path === "orders"
                ? `${(command as OrderCommand).side} LIMIT`
                : "CANCEL",
            status: "UNKNOWN",
            message,
          },
          ...previous,
        ].slice(0, 100),
      );
    } finally {
      setPending(false);
      setCancelPending(undefined);
    }
  };
  const submitOrder = (event: React.FormEvent) => {
    event.preventDefault();
    const priceTicks = Math.round(Number(price) * scale);
    const quantityLots = Math.round(Number(quantity) * quantityScale);
    if (
      !Number.isSafeInteger(priceTicks) ||
      priceTicks <= 0 ||
      !Number.isSafeInteger(quantityLots) ||
      quantityLots <= 0 ||
      !accountId
    ) {
      setNotice({
        type: "error",
        message: "Enter a valid account, price and quantity.",
      });
      return;
    }
    const seq = nextSeq();
    void execute("orders", {
      accountId: Number(accountId),
      side,
      priceTicks,
      quantityLots,
      timeInForce,
      producerId: producer.current,
      requestSeq: seq,
      clientOrderId: `${producer.current}-${seq}`,
    });
  };
  const cancelOrder = (orderId: string) => {
    setCancelPending(orderId);
    void execute("cancel", {
      accountId: Number(accountId),
      orderId: Number.isSafeInteger(Number(orderId))
        ? Number(orderId)
        : orderId,
      producerId: producer.current,
      requestSeq: nextSeq(),
    });
  };
  const usePercent = (percent: number) => {
    if (!account) return;
    const available =
      side === "BUY"
        ? (account.quoteAvailable ?? 0) /
          (Number(price) * scale || ask || lastPrice || 1)
        : (account.baseAvailable ?? 0);
    setQuantity(String(Math.floor(available * percent) / quantityScale));
  };
  const choosePrice = (ticks: number) => setPrice((ticks / scale).toFixed(pd));
  const bookMax = Math.max(
    1,
    ...(state?.bids || []).slice(0, 10).map((l) => l.quantityLots),
    ...(state?.asks || []).slice(0, 10).map((l) => l.quantityLots),
  );
  const depthRows = (which: "bids" | "asks") => {
    const source = (state?.[which] || []).slice(0, bookMode === "All" ? 7 : 14);
    const rows = Array.from(
      { length: bookMode === "All" ? 7 : 14 },
      (_, i) => source[i],
    );
    if (which === "asks") rows.reverse();
    return (
      <div className={`book-levels ${which}`}>
        {rows.map((level, i) => (
          <button
            className="book-row"
            key={level?.priceTicks ?? `empty-${i}`}
            disabled={!level}
            onClick={() => level && choosePrice(level.priceTicks)}
            title={level ? "Use this limit price" : undefined}
          >
            {level && (
              <span
                className="depth-bar"
                style={{ width: `${(level.quantityLots / bookMax) * 100}%` }}
              />
            )}
            <span className="level-price">
              {level ? number(level.priceTicks / scale, pd) : "—"}
            </span>
            <span>
              {level ? number(level.quantityLots / quantityScale, qd) : "—"}
            </span>
            <span>
              {level
                ? number(
                    ((level.priceTicks / scale) * level.quantityLots) /
                      quantityScale,
                    pd,
                  )
                : "—"}
            </span>
          </button>
        ))}
      </div>
    );
  };
  const maxSample = Math.max(...measurements, 1);
  const histogram = Array.from(
    { length: 24 },
    (_, i) =>
      measurements.filter(
        (v) =>
          v >= (i * maxSample) / 24 &&
          (i === 23 ? v <= maxSample : v < ((i + 1) * maxSample) / 24),
      ).length,
  );
  const histogramMax = Math.max(...histogram, 1);

  return (
    <div className="app-shell">
      <header className="topbar">
        <a href="#" className="brand" aria-label="VectorMatch home">
          <svg viewBox="0 0 35 32" width="29" height="27" aria-hidden="true">
            <path d="M0 3h8l9.5 21L27 3h8L17.5 32Z" fill="currentColor" />
            <path d="M12 3h11l-5.5 12Z" fill="#9ce5b9" />
          </svg>
          <span>
            vector<span className="brand-light">match</span>
            <i>®</i>
          </span>
        </a>
        <nav className="primary-nav" aria-label="Main navigation">
          <a href="#market" className="active">
            Exchange
          </a>
          <a href="#diagnostics">
            System <span className="nav-dot" />
          </a>
          <button onClick={() => setShowApi(true)}>
            API <Icon name="external" size={12} />
          </button>
        </nav>
        <div className="topbar-right">
          <span className="environment">
            <span />
            SIMULATION
          </span>
          <span className="divider" />
          <button
            className="status-pill"
            onClick={() => setShowDetails(!showDetails)}
          >
            <span className={`status-dot ${connected ? "online" : ""}`} />
            {connected
              ? "Engine connected"
              : state
                ? "Connection interrupted"
                : "Connecting to engine"}
            <Icon name="chevron" size={12} />
          </button>
          <div className="avatar" title="Local simulation workspace">
            VM
          </div>
        </div>
      </header>

      <div className="workspace-bar">
        <div>
          <span className="workspace-icon">
            <Icon name="layers" size={13} />
          </span>
          <span>Infrastructure sandbox</span>
          <span className="slash">/</span>
          <strong>Spot exchange</strong>
          <span className="version">v0.1</span>
        </div>
        <div className="workspace-meta">
          <span>REAL ENGINE. OBSERVABLE RESULTS.</span>
          <button
            className={fetching ? "spinning-button" : ""}
            onClick={() => void refresh()}
            disabled={fetching}
            aria-label="Refresh engine state"
          >
            <Icon name="refresh" size={13} />
          </button>
        </div>
      </div>

      {showDetails && (
        <div className="connection-detail">
          <div>
            <Icon name="info" />
            <strong>{mode}</strong>
            <span>
              {socket
                ? "WebSocket transport connected"
                : "HTTP polling · reconnecting stream"}{" "}
              ·{" "}
              {replay
                ? `Recovery: ${replay}`
                : "Recovery status is not reported by this engine"}
            </span>
          </div>
          <button
            onClick={() => setShowDetails(false)}
            aria-label="Close connection details"
          >
            <Icon name="close" />
          </button>
        </div>
      )}
      {error && (
        <div className="connection-warning">
          <Icon name="info" size={15} />
          <span>
            {state
              ? "Displaying last received snapshot. "
              : "Engine is unavailable. "}
            {error}.{" "}
            {state
              ? "Order submission is disabled until state refreshes."
              : "Start the backend to load live market data."}
          </span>
          <button onClick={() => void refresh()}>
            Reconnect <Icon name="arrow" size={13} />
          </button>
        </div>
      )}

      <main id="market">
        <section className="market-header">
          <div className="market-name">
            <div className="market-coin">
              <span>{base.slice(0, 1)}</span>
              <small>↗</small>
            </div>
            <div>
              <h1>
                {base}
                <span>/ {quote}</span>
              </h1>
              <div className="market-subtitle">
                <span className="spot-tag">SPOT</span>
                <span>Price–time priority</span>
              </div>
            </div>
          </div>
          <div className="current-price">
            <strong
              className={
                change === undefined || change >= 0 ? "positive" : "negative"
              }
            >
              {lastPrice ? number(lastPrice / scale, pd) : "—"}
            </strong>
            <span
              className={
                change === undefined || change >= 0 ? "positive" : "negative"
              }
            >
              {change === undefined
                ? "Waiting for first observation"
                : `${change >= 0 ? "+" : ""}${change.toFixed(2)}% since connection`}
            </span>
          </div>
          <div className="market-stat">
            <label>Best bid</label>
            <strong>{bid ? number(bid / scale, pd) : "—"}</strong>
          </div>
          <div className="market-stat">
            <label>Best ask</label>
            <strong>{ask ? number(ask / scale, pd) : "—"}</strong>
          </div>
          <div className="market-stat">
            <label>
              Spread <span className="muted">/ bps</span>
            </label>
            <strong>
              {spread === undefined ? "—" : number(spread, pd)}{" "}
              <small>
                {spreadBps === undefined ? "" : number(spreadBps, 2)}
              </small>
            </strong>
          </div>
          <div className="market-stat last-stat">
            <label>Book levels</label>
            <strong>
              {state ? number(levelsCount) : "—"} <small>live</small>
            </strong>
          </div>
        </section>

        <div className="trading-grid">
          <section className="panel price-panel">
            <div className="panel-toolbar">
              <div className="tab-heading">
                <Icon name="activity" size={15} />
                <h2>Market overview</h2>
                <span className="small-label">OBSERVED PRICE</span>
              </div>
              <div className="segmented range-select">
                {["1M", "5M", "SESSION"].map((item) => (
                  <button
                    key={item}
                    className={range === item ? "selected" : ""}
                    onClick={() => setRange(item)}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>
            <div className="chart-caption">
              <span>
                <i className="line-dot" />
                Last trade / midpoint
              </span>
              <span>
                Live observations <span className="muted">· UTC</span>
              </span>
            </div>
            <PriceChart samples={samples} scale={scale} range={range} />
            <div className="chart-foot">
              <span>
                <Icon name="info" size={12} />
                History begins when this console connects.
              </span>
              <span>{samples.length} observations</span>
            </div>
          </section>

          <section className="panel book-panel">
            <div className="panel-toolbar">
              <h2>Order book</h2>
              <span className="tiny-pill">L2</span>
              <div className="book-filter">
                {["All", "Bids", "Asks"].map((item) => (
                  <button
                    key={item}
                    onClick={() => setBookMode(item)}
                    className={bookMode === item ? "selected" : ""}
                    aria-label={`Show ${item.toLowerCase()} order book`}
                  >
                    <span
                      className={`book-filter-icon ${item.toLowerCase()}`}
                    />
                  </button>
                ))}
              </div>
            </div>
            <div className="book-table-head">
              <span>
                Price <em>({quote})</em>
              </span>
              <span>
                Amount <em>({base})</em>
              </span>
              <span>Total</span>
            </div>
            {bookMode !== "Bids" && depthRows("asks")}
            <div className="book-mid">
              <strong className="positive">
                {lastPrice ? number(lastPrice / scale, pd) : "—"}
                <span>↗</span>
              </strong>
              <span>
                {spreadBps === undefined
                  ? "No two-sided book"
                  : `${spreadBps.toFixed(2)} bps spread`}
              </span>
            </div>
            {bookMode !== "Asks" && depthRows("bids")}
            <div className="book-footer">
              <span className="status-dot online" />
              Sequence{" "}
              <span>{sequence === undefined ? "—" : number(sequence)}</span>
              <Icon name="layers" size={12} />
            </div>
          </section>

          <section className="panel order-panel">
            <div className="panel-toolbar">
              <h2>Place order</h2>
              <span className="tiny-pill">SIMULATED FUNDS</span>
            </div>
            <form onSubmit={submitOrder}>
              <div className="side-select">
                <button
                  type="button"
                  className={`buy ${side === "BUY" ? "selected" : ""}`}
                  onClick={() => setSide("BUY")}
                >
                  Buy {base}
                </button>
                <button
                  type="button"
                  className={`sell ${side === "SELL" ? "selected" : ""}`}
                  onClick={() => setSide("SELL")}
                >
                  Sell {base}
                </button>
              </div>
              <div className="order-type">
                <span>Limit</span>
                <span>
                  Price–time priority
                  <Icon name="info" size={12} />
                </span>
              </div>
              <label className="field-label" htmlFor="account">
                Account
              </label>
              <div className="select-field">
                <select
                  id="account"
                  value={accountId}
                  onChange={(e) => setAccountId(e.target.value)}
                  disabled={!state?.accounts.length}
                >
                  {!state?.accounts.length && (
                    <option value="">Waiting for accounts</option>
                  )}
                  {state?.accounts.map((a) => (
                    <option value={a.id} key={a.id} disabled={a.id !== "1"}>
                      {a.name}
                      {a.id !== "1" ? " · read only" : ""}
                    </option>
                  ))}
                </select>
                <Icon name="chevron" size={13} />
              </div>
              <div className="field-heading">
                <label className="field-label" htmlFor="price">
                  Limit price
                </label>
                <button
                  type="button"
                  className="text-button"
                  disabled={!lastPrice}
                  onClick={() => lastPrice && choosePrice(lastPrice)}
                >
                  Use market
                </button>
              </div>
              <div className="input-field">
                <input
                  id="price"
                  type="number"
                  min={1 / scale}
                  step={1 / scale}
                  placeholder={
                    lastPrice ? (lastPrice / scale).toFixed(pd) : "0.00"
                  }
                  value={price}
                  onChange={(e) => setPrice(e.target.value)}
                  required
                  inputMode="decimal"
                />
                <span>{quote}</span>
              </div>
              <div className="field-heading">
                <label className="field-label" htmlFor="quantity">
                  Amount
                </label>
                <span className="field-hint">
                  Min {1 / quantityScale} {base}
                </span>
              </div>
              <div className="input-field">
                <input
                  id="quantity"
                  type="number"
                  min={1 / quantityScale}
                  step={1 / quantityScale}
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                  required
                  inputMode="decimal"
                />
                <span>{base}</span>
              </div>
              <div className="allocation">
                {[0.25, 0.5, 0.75, 1].map((value) => (
                  <button
                    key={value}
                    type="button"
                    disabled={!account}
                    onClick={() => usePercent(value)}
                  >
                    {value * 100}%
                  </button>
                ))}
              </div>
              <div className="order-total">
                <span>Order value</span>
                <strong>
                  {Number(price) > 0 && Number(quantity) > 0
                    ? number(Number(price) * Number(quantity), pd)
                    : "—"}{" "}
                  <small>{quote}</small>
                </strong>
              </div>
              <div className="time-in-force">
                <label htmlFor="tif">
                  Time in force <Icon name="info" size={12} />
                </label>
                <select
                  id="tif"
                  value={timeInForce}
                  onChange={(e) => setTimeInForce(e.target.value)}
                >
                  <option value="GTC">Good til cancelled</option>
                  <option value="IOC">Immediate or cancel</option>
                </select>
              </div>
              <button
                className={`submit-order ${side === "SELL" ? "sell-button" : ""}`}
                type="submit"
                disabled={pending || !engineWritable || !accountId}
              >
                {pending
                  ? "Awaiting engine…"
                  : `${side === "BUY" ? "Buy" : "Sell"} ${base}`}
                <Icon name={pending ? "clock" : "arrow"} size={17} />
              </button>
              <div className="available">
                <span>Available</span>
                <strong>
                  {account
                    ? number(
                        side === "BUY"
                          ? account.quoteAvailable === undefined
                            ? undefined
                            : account.quoteAvailable / scale
                          : account.baseAvailable === undefined
                            ? undefined
                            : account.baseAvailable / quantityScale,
                        side === "BUY" ? pd : qd,
                      )
                    : "—"}{" "}
                  <span>{side === "BUY" ? quote : base}</span>
                </strong>
              </div>
            </form>
            {notice && (
              <div className={`order-notice ${notice.type}`} role="status">
                <Icon
                  name={notice.type === "success" ? "check" : "info"}
                  size={14}
                />
                <span>{notice.message}</span>
                {retryCommand && (
                  <button
                    disabled={pending}
                    onClick={() =>
                      void execute(retryCommand.path, retryCommand.command)
                    }
                  >
                    Retry safely
                  </button>
                )}
              </div>
            )}
          </section>

          <section className="panel trades-panel">
            <div className="panel-toolbar">
              <h2>Recent trades</h2>
              <span className="live-label">
                <span className={`status-dot ${connected ? "online" : ""}`} />
                LIVE TAPE
              </span>
            </div>
            <div className="trade-table-head">
              <span>
                Price <em>({quote})</em>
              </span>
              <span>
                Amount <em>({base})</em>
              </span>
              <span>
                Time <em>(UTC)</em>
              </span>
            </div>
            <div className="trades-list">
              {state?.trades.length ? (
                state.trades.slice(0, 5).map((trade) => (
                  <div className="trade-row" key={trade.id}>
                    <span
                      className={trade.side === "BUY" ? "positive" : "negative"}
                    >
                      <span className="trade-direction">
                        {trade.side === "BUY" ? "↗" : "↘"}
                      </span>
                      {number(trade.priceTicks / scale, pd)}
                    </span>
                    <span>
                      {number(trade.quantityLots / quantityScale, qd)}
                    </span>
                    <span>{formatTime(trade.timestamp)}</span>
                  </div>
                ))
              ) : (
                <div className="empty-trades">
                  <Icon name="activity" size={18} />
                  <span>
                    No executions yet. Cross the spread to create a trade.
                  </span>
                </div>
              )}
            </div>
          </section>
        </div>

        <section className="panel activity-panel">
          <div className="panel-toolbar activity-toolbar">
            <div className="table-tabs">
              {["Open orders", "Balances", "Command log"].map((tab) => (
                <button
                  className={tableTab === tab ? "active" : ""}
                  onClick={() => setTableTab(tab)}
                  key={tab}
                >
                  {tab}
                  {tab === "Open orders" && <span>{openOrders.length}</span>}
                  {tab === "Command log" && logs.length > 0 && (
                    <span>{logs.length}</span>
                  )}
                </button>
              ))}
            </div>
            <span className="table-account">
              {accountId ? (
                <>
                  <span className="status-dot online" />
                  {accountId}
                </>
              ) : (
                "No account selected"
              )}
            </span>
          </div>
          <div className="activity-table-wrap">
            {tableTab === "Open orders" && (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Order ID</th>
                    <th>Market / Side</th>
                    <th>Limit price</th>
                    <th>Amount</th>
                    <th>Remaining</th>
                    <th>Status</th>
                    <th className="right">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {openOrders.length ? (
                    openOrders.slice(0, 8).map((order) => (
                      <tr key={order.id}>
                        <td className="order-id" title={order.id}>
                          #
                          {order.id.length > 15
                            ? order.id.slice(0, 12) + "…"
                            : order.id}
                        </td>
                        <td>
                          {state?.symbol}{" "}
                          <span
                            className={`side-tag ${order.side.toLowerCase()}`}
                          >
                            {order.side}
                          </span>
                        </td>
                        <td>{number(order.priceTicks / scale, pd)}</td>
                        <td>
                          {number(order.quantityLots / quantityScale, qd)}
                        </td>
                        <td>
                          {number(order.remainingLots / quantityScale, qd)}
                        </td>
                        <td>
                          <span className="order-status">
                            {order.status.replace(/_/g, " ")}
                          </span>
                        </td>
                        <td className="right">
                          <button
                            className="cancel-order"
                            onClick={() => cancelOrder(order.id)}
                            disabled={pending || !engineWritable}
                          >
                            {cancelPending === order.id ? "Pending…" : "Cancel"}
                            <Icon name="close" size={12} />
                          </button>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={7}>
                        <div className="table-empty">
                          <Icon name="layers" size={21} />
                          <span>No open orders for this account</span>
                          <small>Place a limit order to see it here.</small>
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            )}
            {tableTab === "Balances" && (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Asset</th>
                    <th>Available</th>
                    <th>Reserved</th>
                    <th>Total</th>
                    <th>Account</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    {
                      asset: quote,
                      available: account?.quoteAvailable,
                      reserved: account?.quoteReserved,
                      divisor: scale,
                      precision: pd,
                    },
                    {
                      asset: base,
                      available: account?.baseAvailable,
                      reserved: account?.baseReserved,
                      divisor: quantityScale,
                      precision: qd,
                    },
                  ].map((item) => (
                    <tr key={item.asset}>
                      <td className="asset-cell">
                        <span className="asset-token">{item.asset[0]}</span>
                        {item.asset}
                      </td>
                      <td>
                        {number(
                          item.available === undefined
                            ? undefined
                            : item.available / item.divisor,
                          item.precision,
                        )}
                      </td>
                      <td>
                        {number(
                          item.reserved === undefined
                            ? undefined
                            : item.reserved / item.divisor,
                          item.precision,
                        )}
                      </td>
                      <td>
                        {number(
                          item.available === undefined ||
                            item.reserved === undefined
                            ? undefined
                            : (item.available + item.reserved) / item.divisor,
                          item.precision,
                        )}
                      </td>
                      <td className="muted">{accountId || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {tableTab === "Command log" && (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Time (UTC)</th>
                    <th>Command</th>
                    <th>Request key</th>
                    <th>Result</th>
                    <th>Browser RTT</th>
                    <th>Message</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.length ? (
                    logs.slice(0, 8).map((log, index) => (
                      <tr key={`${log.id}-${index}`}>
                        <td>{formatTime(log.time)}</td>
                        <td>{log.action}</td>
                        <td className="order-id" title={log.id}>
                          {log.id.slice(-20)}
                        </td>
                        <td>
                          <span
                            className={`command-status ${log.status.toLowerCase()}`}
                          >
                            {log.status}
                          </span>
                        </td>
                        <td>
                          {log.millis === undefined
                            ? "—"
                            : `${log.millis.toFixed(2)} ms`}
                        </td>
                        <td className="log-message">{log.message}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={6}>
                        <div className="table-empty">
                          <Icon name="terminal" size={21} />
                          <span>Your command history appears here</span>
                          <small>
                            Measurements are collected from this browser
                            session.
                          </small>
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section
          className="lab-controls panel"
          aria-label="Simulation controls"
        >
          <div className="lab-identity">
            <span className="lab-symbol">
              <Icon name="bolt" size={18} />
            </span>
            <div>
              <strong>Make the market move.</strong>
              <span>
                Real orders from simulation accounts. Journaled by the same
                engine.
              </span>
            </div>
          </div>
          <div className="flow-control">
            <span className={`flow-state ${flowEnabled ? "positive" : ""}`}>
              <span className={`status-dot ${flowEnabled ? "online" : ""}`} />
              {flowEnabled
                ? `Flow running · ${metric(h, "flowRate") ?? flowRate}/s target`
                : "Market flow paused"}
            </span>
            <div className="flow-actions">
              <select
                value={flowRate}
                onChange={(e) => setFlowRate(e.target.value)}
                aria-label="Market flow target rate"
                disabled={flowEnabled || !!controlPending}
              >
                <option value="10">10 cmd/s</option>
                <option value="50">50 cmd/s</option>
                <option value="100">100 cmd/s</option>
              </select>
              <button
                className={`flow-button ${flowEnabled ? "stop" : ""}`}
                onClick={() => void control("flow")}
                disabled={!engineWritable || !!controlPending}
              >
                {controlPending === "flow"
                  ? "Applying…"
                  : flowEnabled
                    ? "Pause flow"
                    : "Start market flow"}
                <Icon name={flowEnabled ? "close" : "arrow"} size={12} />
              </button>
            </div>
          </div>
          <span className="control-divider" />
          <div className="replay-control">
            <button
              className="replay-button"
              disabled={!engineWritable || !!controlPending}
              onClick={() => void control("replay")}
            >
              <Icon
                name="refresh"
                size={13}
                className={controlPending === "replay" ? "spinning" : ""}
              />
              {controlPending === "replay"
                ? "Verifying journal…"
                : "Verify replay"}
            </button>
            <span
              className={
                verified.consistent === true
                  ? "positive"
                  : verified.consistent === false
                    ? "negative"
                    : ""
              }
            >
              {verified.consistent === true
                ? `${compact(metric(verified, "replayedCommands"))} commands · hash match`
                : verified.consistent === false
                  ? "State hash mismatch"
                  : "Compare live state to journal replay"}
            </span>
          </div>
          {controlError && (
            <div className="control-error" role="alert">
              <Icon name="info" size={12} />
              {controlError}
            </div>
          )}
        </section>

        <section className="diagnostics" id="diagnostics">
          <div className="section-heading">
            <div>
              <span className="eyebrow">UNDER THE HOOD</span>
              <h2>Every number, accountable.</h2>
            </div>
            <span>
              <Icon name="terminal" size={14} />
              Measured locally. Reported honestly.
            </span>
          </div>
          <div className="diagnostic-grid">
            <section className="panel latency-panel">
              <div className="panel-toolbar">
                <h3>Command round-trip</h3>
                <span className="source-tag">BROWSER → ENGINE → BROWSER</span>
              </div>
              <div className="latency-metrics">
                <div>
                  <label>
                    Median <span>p50</span>
                  </label>
                  <strong>
                    {p50 === undefined ? "—" : p50.toFixed(2)}
                    <small>ms</small>
                  </strong>
                </div>
                <div>
                  <label>
                    Tail <span>p99</span>
                  </label>
                  <strong>
                    {p99 === undefined ? "—" : p99.toFixed(2)}
                    <small>ms</small>
                  </strong>
                </div>
                <div>
                  <label>Samples</label>
                  <strong>
                    {measurements.length}
                    <small>cmd</small>
                  </strong>
                </div>
              </div>
              <div
                className="histogram"
                aria-label="Histogram of actual command round trip samples"
              >
                {histogram.map((count, i) => (
                  <div
                    key={i}
                    className={count ? "has-samples" : ""}
                    style={{
                      height: `${Math.max(count ? 4 : 1, (count / histogramMax) * 100)}%`,
                    }}
                    title={`${((i * maxSample) / 24).toFixed(1)}–${(((i + 1) * maxSample) / 24).toFixed(1)} ms: ${count} samples`}
                  />
                ))}
              </div>
              <div className="histogram-axis">
                <span>0 ms</span>
                <span>
                  {measurements.length
                    ? `${maxSample.toFixed(1)} ms`
                    : "Waiting for commands"}
                </span>
              </div>
              <div className="diagnostic-note">
                <Icon name="info" size={12} />
                Includes browser, network and engine. Not a load-test result.
              </div>
            </section>
            <section className="panel engine-panel">
              <div className="panel-toolbar">
                <h3>Engine telemetry</h3>
                <span className="source-tag">SERVER REPORTED</span>
              </div>
              <div className="engine-stats">
                <div>
                  <span>
                    <Icon name="terminal" />
                    Processed commands
                  </span>
                  <strong>{compact(engineCommands)}</strong>
                </div>
                <div>
                  <span>
                    <Icon name="activity" />
                    Executions
                  </span>
                  <strong>{compact(engineTrades)}</strong>
                </div>
                <div>
                  <span>
                    <Icon name="layers" />
                    Event sequence
                  </span>
                  <strong>{compact(sequence)}</strong>
                </div>
                <div>
                  <span>
                    <Icon name="bolt" />
                    Journal + core p99
                  </span>
                  <strong>
                    {engineP99 === undefined ? "—" : engineP99.toFixed(1)}
                    <small>µs</small>
                  </strong>
                </div>
              </div>
              <div className="diagnostic-note">
                <Icon name="info" size={12} />
                Service time excludes network and writer queue. No load-test
                claim.
              </div>
            </section>
            <section className="panel runtime-panel">
              <div className="panel-toolbar">
                <h3>Runtime status</h3>
                <span
                  className={`runtime-label ${connected ? "positive" : "muted"}`}
                >
                  {connected ? "OPERATIONAL" : "AWAITING ENGINE"}
                </span>
              </div>
              <div className="runtime-item">
                <span>Deployment</span>
                <strong>{mode}</strong>
              </div>
              <div className="runtime-item">
                <span>Transport</span>
                <strong>
                  <i className={`status-dot ${socket ? "online" : ""}`} />
                  {socket
                    ? "WebSocket · 5 Hz snapshots"
                    : connected
                      ? "HTTP polling"
                      : "Disconnected"}
                </strong>
              </div>
              <div className="runtime-item">
                <span>Recovery</span>
                <strong>{replay || "Not reported"}</strong>
              </div>
              <div className="runtime-item">
                <span>Uptime</span>
                <strong>
                  {uptime === undefined
                    ? "—"
                    : `${Math.floor(uptime / 3_600_000)}h ${Math.floor(uptime / 60_000) % 60}m ${Math.floor(uptime / 1000) % 60}s`}
                </strong>
              </div>
              <div className="runtime-bottom">
                <span className="pulse-dot" />
                {state
                  ? `Last snapshot ${Math.max(0, Math.floor((clock - state.receivedAt) / 1000))}s ago`
                  : "No snapshot received"}
                <button onClick={() => setShowApi(true)}>
                  Inspect API <Icon name="external" size={11} />
                </button>
              </div>
            </section>
          </div>
        </section>
      </main>

      <footer className="footer">
        <div>
          <span className={`status-dot ${connected ? "online" : ""}`} />
          <strong>
            {connected
              ? "All data from live engine"
              : "Waiting for live engine"}
          </strong>
          <span className="footer-separator">/</span>
          <span>Simulation environment · No real assets</span>
        </div>
        <div>
          <span>{formatTime(clock)} UTC</span>
          <span className="footer-separator">/</span>
          <span>
            VectorMatch <span className="muted">0.1</span>
          </span>
        </div>
      </footer>

      {showApi && (
        <div className="modal-backdrop" onClick={() => setShowApi(false)}>
          <section
            className="api-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="api-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <span className="eyebrow">DEVELOPER INTERFACE</span>
                <h2 id="api-title">Connected to the source.</h2>
              </div>
              <button
                onClick={() => setShowApi(false)}
                aria-label="Close API reference"
              >
                <Icon name="close" size={20} />
              </button>
            </div>
            <p>
              The console reads actual engine state and submits real simulation
              commands. Browser measurements are separate from engine telemetry.
              The WebSocket sends full workbench snapshots at 5 Hz; it is not a
              per-event recovery protocol.
            </p>
            <div className="endpoint">
              <span>GET</span>
              <code>/api/state</code>
              <small>Full market & account snapshot</small>
            </div>
            <div className="endpoint">
              <span>WS</span>
              <code>/ws</code>
              <small>5 Hz workbench snapshots</small>
            </div>
            <div className="endpoint">
              <span>POST</span>
              <code>/api/orders</code>
              <small>Idempotent order submission</small>
            </div>
            <div className="endpoint">
              <span>POST</span>
              <code>/api/cancel</code>
              <small>Cancel by account and order ID</small>
            </div>
            <div className="api-note">
              <Icon name="info" size={16} />
              <span>
                A timeout is an unknown outcome. Retry the same producer ID and
                request sequence to avoid a second business effect.
              </span>
            </div>
            <div className="modal-footer">
              <span>Session producer</span>
              <code>{producer.current}</code>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

export default App;
