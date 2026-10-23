import { useId, useMemo, useState } from "react";
import { asObject } from "./api";
import "./CapacityCurve.css";

interface CapacityPoint {
  id: string;
  rate?: number;
  workers?: number;
  goodput?: number;
  p99Millis?: number;
  queueDrops?: number;
  clientNotSent?: number;
  rejected?: number;
  serverErrors?: number;
  unknown?: number;
  unresolved?: number;
  allOfferedAcceptedP99Millis?: number;
  drainSeconds?: number;
  classification?: string;
  peakBacklog?: number;
  valid?: boolean;
  stable?: boolean;
  windowSeconds?: number;
}

export interface CapacityEvidence {
  id?: string;
  title: string;
  scope?: string;
  updatedAt?: string;
  reportPath?: string;
  configurationFingerprint?: string;
  points: CapacityPoint[];
}

const number = (value: unknown) =>
  typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : undefined;
const text = (value: unknown) =>
  typeof value === "string" && value.trim() ? value : undefined;
const bool = (value: unknown) =>
  typeof value === "boolean" ? value : undefined;
const format = (value?: number, digits = 1) =>
  value === undefined
    ? "—"
    : value.toLocaleString("en-US", { maximumFractionDigits: digits });
const compact = (value: number) =>
  new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);

export function normalizeCapacity(
  value: unknown,
): CapacityEvidence | undefined {
  const data = asObject(value);
  if (!Array.isArray(data.points) || !data.points.length) return undefined;
  return {
    id: text(data.id),
    title: text(data.title) || "Capacity under load",
    scope: text(data.scope),
    updatedAt: text(data.updatedAt),
    reportPath: text(data.reportPath),
    configurationFingerprint: text(data.configurationFingerprint),
    points: data.points.map((value, index) => {
      const point = asObject(value);
      return {
        id: text(point.id) || `capacity-${index + 1}`,
        rate: number(point.rate),
        workers: number(point.workers),
        goodput: number(point.goodput),
        p99Millis: number(point.p99Millis),
        queueDrops: number(point.queueDrops),
        clientNotSent: number(point.clientNotSent),
        rejected: number(point.rejected),
        serverErrors: number(point.serverErrors),
        unknown: number(point.unknown),
        unresolved: number(point.unresolved),
        allOfferedAcceptedP99Millis: number(point.allOfferedAcceptedP99Millis),
        drainSeconds: number(point.drainSeconds),
        classification: text(point.classification),
        peakBacklog: number(point.peakBacklog),
        valid: bool(point.valid),
        stable: bool(point.stable),
        windowSeconds: number(point.windowSeconds),
      };
    }),
  };
}

export function normalizeCapacityCohorts(value: unknown): CapacityEvidence[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  return value.flatMap((entry, index) => {
    const evidence = normalizeCapacity(entry);
    if (!evidence) return [];
    const id = evidence.id || `cohort-${index + 1}`;
    if (seen.has(id)) return [];
    seen.add(id);
    return [{ ...evidence, id }];
  });
}

function verdict(point: CapacityPoint) {
  if (point.valid === false) return "invalid";
  if (point.valid !== true) return "unverified";
  if (
    point.windowSeconds === undefined ||
    point.windowSeconds < 10 ||
    point.classification === "INSUFFICIENT_WINDOW_OBSERVATIONS"
  )
    return "insufficient";
  if (point.stable === true) return "stable";
  if (point.stable === false) return "unstable";
  return "unverified";
}

function status(point: CapacityPoint) {
  if (point.valid === false) return "Invalid measurement";
  if (point.valid !== true) return "Validity not reported";
  if (point.windowSeconds === undefined) return "Window not reported";
  if (point.windowSeconds < 10) return "Short window · under 10 s";
  if (verdict(point) === "insufficient") return "Insufficient window evidence";
  if (point.stable === true) return "Stable window";
  if (point.stable === false) return "Unstable window";
  return "Stability not reported";
}

const colors = ["#a2e7bb", "#8cbce6", "#e1bf81", "#c0a5df"];
function groupColor(workers?: number) {
  if (workers === 16) return colors[0];
  if (workers === 32) return colors[1];
  if (workers === 64) return colors[2];
  if (workers === 128) return colors[3];
  return colors[3];
}
function pointLabel(point: CapacityPoint) {
  return `${point.id}, ${format(point.workers, 0)} clients, offered ${format(point.rate)} commands per second, confirmed ${format(point.goodput)} commands per second, conditional p99 ${format(point.p99Millis, 2)} milliseconds, ${status(point)}, ${format(point.clientNotSent, 0)} client not sent, ${format(point.queueDrops, 0)} queue full, ${format(point.rejected, 0)} business rejects, ${format(point.serverErrors, 0)} server errors, ${format(point.unknown, 0)} initial unknowns, ${format(point.unresolved, 0)} unresolved`;
}
function niceMaximum(value: number) {
  if (value <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  return Math.ceil(value / power / 0.5) * power * 0.5;
}

function CapacityChart({
  points,
  selected,
  select,
  metric,
  chartId,
}: {
  points: CapacityPoint[];
  selected: number;
  select: (index: number) => void;
  metric: "goodput" | "p99Millis";
  chartId: string;
}) {
  const width = 580,
    height = 292,
    left = 62,
    right = 20,
    top = 22,
    bottom = 46;
  const plotWidth = width - left - right,
    plotHeight = height - top - bottom;
  const xMax = niceMaximum(Math.max(1, ...points.map((p) => p.rate || 0)));
  const yMax = niceMaximum(
    Math.max(
      1,
      metric === "goodput" ? xMax : 0,
      ...points.map((p) => p[metric] || 0),
    ),
  );
  const x = (rate: number) => left + (rate / xMax) * plotWidth;
  const y = (value: number) => top + plotHeight - (value / yMax) * plotHeight;
  const groups = useMemo(
    () =>
      [...new Set(points.map((p) => p.workers))].sort(
        (a, b) => (a || 0) - (b || 0),
      ),
    [points],
  );
  const plotted = points
    .map((point, index) => ({ point, index }))
    .filter(
      ({ point }) => point.rate !== undefined && point[metric] !== undefined,
    );
  const missing = points.length - plotted.length;
  return (
    <div className="capacity-chart">
      <div className="capacity-chart-heading">
        <h4>
          {metric === "goodput"
            ? "Confirmed goodput"
            : "Scheduled → confirmed p99"}
        </h4>
        <span>
          {metric === "goodput"
            ? "cmd/s · arrival window"
            : "ms · conditional on confirmation"}
        </span>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="group"
        aria-labelledby={`${chartId}-title ${chartId}-description`}
      >
        <title id={`${chartId}-title`}>
          {metric === "goodput"
            ? "Offered load versus arrival-window confirmed goodput"
            : "Offered load versus conditional scheduled-to-confirmed p99 latency"}
        </title>
        <desc id={`${chartId}-description`}>
          All recorded points are retained. Hollow crosses are invalid or
          unverified, diamonds have insufficient window evidence, triangles are
          unstable, and filled circles are stable windows of at least 10
          seconds. Focus a point or use the run selector to inspect its
          counters.{" "}
          {missing
            ? `${missing} points lack this metric and remain available in the selector.`
            : ""}
        </desc>
        {[0, 1, 2, 3, 4].map((tick) => {
          const fraction = tick / 4;
          return (
            <g key={tick} className="capacity-axis" aria-hidden="true">
              <line
                x1={left}
                x2={width - right}
                y1={y(yMax * fraction)}
                y2={y(yMax * fraction)}
              />
              <text x={left - 10} y={y(yMax * fraction) + 4} textAnchor="end">
                {compact(yMax * fraction)}
              </text>
              <text x={x(xMax * fraction)} y={height - 25} textAnchor="middle">
                {compact(xMax * fraction)}
              </text>
            </g>
          );
        })}
        {metric === "goodput" && (
          <g className="capacity-offered" aria-hidden="true">
            <line x1={x(0)} y1={y(0)} x2={x(xMax)} y2={y(xMax)} />
            <text x={x(xMax) - 7} y={y(xMax) + 16} textAnchor="end">
              offered = confirmed
            </text>
          </g>
        )}
        {groups.map((workers) => {
          const line = plotted
            .filter(({ point }) => point.workers === workers)
            .sort((a, b) => (a.point.rate || 0) - (b.point.rate || 0))
            .map(({ point }) => `${x(point.rate!)},${y(point[metric]!)}`)
            .join(" ");
          return (
            <polyline
              key={workers ?? "unreported"}
              points={line}
              fill="none"
              stroke={groupColor(workers)}
              strokeWidth="1.6"
              opacity="0.6"
              aria-hidden="true"
            />
          );
        })}
        {plotted.map(({ point, index }) => {
          const px = x(point.rate!),
            py = y(point[metric]!),
            state = verdict(point),
            invalid = state === "invalid" || state === "unverified",
            unstable = state === "unstable",
            color = groupColor(point.workers);
          return (
            <g
              key={`${point.id}-${index}`}
              className={`capacity-point ${selected === index ? "selected" : ""}`}
              transform={`translate(${px} ${py})`}
              role="button"
              tabIndex={0}
              aria-label={pointLabel(point)}
              aria-pressed={selected === index}
              data-capacity-index={index}
              onMouseEnter={() => select(index)}
              onFocus={() => select(index)}
              onClick={() => select(index)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  select(index);
                }
                if (
                  ["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(
                    event.key,
                  )
                ) {
                  event.preventDefault();
                  const current = plotted.findIndex(
                    (item) => item.index === index,
                  );
                  const step =
                    event.key === "ArrowRight" || event.key === "ArrowDown"
                      ? 1
                      : -1;
                  const next =
                    plotted[(current + step + plotted.length) % plotted.length]
                      .index;
                  event.currentTarget.ownerSVGElement
                    ?.querySelector<SVGElement>(
                      `[data-capacity-index="${next}"]`,
                    )
                    ?.focus();
                }
              }}
            >
              <title>{pointLabel(point)}</title>
              <circle r="13" fill="transparent" stroke="none" />
              {selected === index && (
                <circle
                  className="capacity-selection-ring"
                  r="10"
                  fill="none"
                  stroke={color}
                  strokeWidth="1"
                  opacity="0.65"
                  aria-hidden="true"
                />
              )}
              {state === "insufficient" ? (
                <path
                  d="M0 -6 6 0 0 6 -6 0Z"
                  fill="var(--panel)"
                  stroke={color}
                  strokeWidth="1.8"
                  aria-hidden="true"
                />
              ) : unstable ? (
                <path
                  d="M0 -6.5 6 5 -6 5Z"
                  fill={color}
                  stroke={color}
                  strokeWidth="1.3"
                  aria-hidden="true"
                />
              ) : (
                <circle
                  r="4.8"
                  fill={invalid ? "var(--panel)" : color}
                  stroke={color}
                  strokeWidth="1.8"
                  aria-hidden="true"
                />
              )}
              {invalid && (
                <path
                  d="m-2.2 -2.2 4.4 4.4m0-4.4-4.4 4.4"
                  stroke={color}
                  strokeWidth="1.2"
                  aria-hidden="true"
                />
              )}
            </g>
          );
        })}
        <text
          className="capacity-axis-label"
          x={left + plotWidth / 2}
          y={height - 4}
          textAnchor="middle"
          aria-hidden="true"
        >
          Offered load · cmd/s
        </text>
        {!plotted.length && (
          <text
            className="capacity-no-metric"
            x={left + plotWidth / 2}
            y={top + plotHeight / 2}
            textAnchor="middle"
          >
            Metric not reported
          </text>
        )}
      </svg>
      {missing > 0 && (
        <p className="capacity-missing">
          {missing} {missing === 1 ? "point has" : "points have"} no reported{" "}
          {metric === "goodput" ? "goodput" : "p99"}; inspect{" "}
          {missing === 1 ? "it" : "them"} below.
        </p>
      )}
    </div>
  );
}

export default function CapacityCurve({
  evidence,
  cohorts,
}: {
  evidence?: CapacityEvidence;
  cohorts?: CapacityEvidence[];
}) {
  const available = cohorts?.length ? cohorts : evidence ? [evidence] : [];
  const [selectedCohortId, setSelectedCohortId] = useState<string>();
  const chosen =
    available.find((cohort) => cohort.id === selectedCohortId) ||
    available[available.length - 1];
  const [selectedIndex, setSelectedIndex] = useState(0);
  const chartId = useId().replaceAll(":", "");
  const [copied, setCopied] = useState(false);
  if (!chosen) return null;
  const selected = Math.min(selectedIndex, chosen.points.length - 1);
  const point = chosen.points[selected];
  const groups = [...new Set(chosen.points.map((p) => p.workers))].sort(
    (a, b) => (a || 0) - (b || 0),
  );
  const updated = chosen.updatedAt ? new Date(chosen.updatedAt) : undefined;
  return (
    <section
      className="panel capacity-panel"
      aria-labelledby={`${chartId}-heading`}
    >
      <div className="capacity-panel-heading">
        <div>
          <span className="eyebrow">FIXED-ARRIVAL CAPACITY</span>
          <h3 id={`${chartId}-heading`}>{chosen.title}</h3>
        </div>
        <span className="capacity-point-count">
          {chosen.points.length} RECORDED{" "}
          {chosen.points.length === 1 ? "POINT" : "POINTS"}
        </span>
      </div>
      {available.length > 1 && (
        <div className="capacity-cohort-selector">
          <label htmlFor={`${chartId}-cohort`}>FIXED CONFIGURATION GROUP</label>
          <select
            id={`${chartId}-cohort`}
            value={chosen.id}
            onChange={(event) => {
              setSelectedCohortId(event.target.value);
              setSelectedIndex(0);
              setCopied(false);
            }}
          >
            {available.map((cohort, index) => (
              <option key={cohort.id || index} value={cohort.id}>
                {cohort.title} · {cohort.points.length} points
              </option>
            ))}
          </select>
          <span>{available.length} groups · charted separately</span>
        </div>
      )}
      {chosen.scope && <p className="capacity-scope">{chosen.scope}</p>}
      <div className="capacity-legend" aria-label="Chart legend">
        <div className="capacity-client-groups">
          {groups.map((workers) => (
            <span key={workers ?? "unreported"}>
              <i style={{ background: groupColor(workers) }} />
              {workers === undefined
                ? "Unreported clients"
                : `${format(workers, 0)} clients`}
            </span>
          ))}
        </div>
        <div className="capacity-marker-legend">
          <span>● Stable</span>
          <span>▲ Unstable</span>
          <span>◇ Short / incomplete window</span>
          <span>⊗ Invalid / unverified</span>
        </div>
      </div>
      <div className="capacity-charts">
        <CapacityChart
          points={chosen.points}
          selected={selected}
          select={setSelectedIndex}
          metric="goodput"
          chartId={`${chartId}-goodput`}
        />
        <CapacityChart
          points={chosen.points}
          selected={selected}
          select={setSelectedIndex}
          metric="p99Millis"
          chartId={`${chartId}-latency`}
        />
      </div>
      <div className="capacity-inspector">
        <div className="capacity-inspector-heading">
          <label htmlFor={`${chartId}-run`}>INSPECT A RECORDED POINT</label>
          <select
            id={`${chartId}-run`}
            value={selected}
            onChange={(event) => setSelectedIndex(Number(event.target.value))}
          >
            {chosen.points.map((item, index) => (
              <option value={index} key={`${item.id}-${index}`}>
                {item.id} · {format(item.workers, 0)} clients ·{" "}
                {format(item.rate)} cmd/s
              </option>
            ))}
          </select>
          <span className={`capacity-verdict ${verdict(point)}`}>
            {status(point)}
          </span>
        </div>
        <dl
          className="capacity-point-details"
          aria-live="polite"
          aria-atomic="true"
        >
          {[
            ["Offered load", format(point.rate), "cmd/s"],
            ["Confirmed in window", format(point.goodput), "cmd/s"],
            ["Conditional p99", format(point.p99Millis, 2), "ms"],
            [
              "All-offered accepted p99",
              format(point.allOfferedAcceptedP99Millis, 2),
              "ms",
            ],
            ["Arrival window", format(point.windowSeconds, 2), "s"],
            ["Drain after window", format(point.drainSeconds, 3), "s"],
            ["Client not sent", format(point.clientNotSent, 0), ""],
            ["Queue full · not sent", format(point.queueDrops, 0), ""],
            [
              "Business rejects / server errors",
              `${format(point.rejected, 0)} / ${format(point.serverErrors, 0)}`,
              "",
            ],
            ["Initial unknowns", format(point.unknown, 0), ""],
            ["Unresolved", format(point.unresolved, 0), ""],
            ["Peak backlog", format(point.peakBacklog, 0), "requests"],
          ].map(([label, value, unit]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>
                {value}
                <small>{unit}</small>
              </dd>
            </div>
          ))}
        </dl>
      </div>
      <p className="capacity-boundary">
        <span aria-hidden="true">ⓘ</span> Goodput counts confirmations inside
        the arrival window. P99 includes scheduling and queue time, conditional
        on confirmed commands. Drops and unresolved requests have no confirmed
        latency; a low conditional p99 cannot establish the p99 of all offered
        requests. Windows shorter than 10 seconds are marked as insufficient
        evidence. Every recorded point remains available within its
        configuration group.
      </p>
      <div className="capacity-footer">
        <span>
          {updated && !Number.isNaN(updated.getTime())
            ? `Updated ${updated.toLocaleString("en-GB", { timeZone: "UTC", hour12: false })} UTC`
            : "Recorded capacity evidence"}
        </span>
        {chosen.reportPath && (
          <button
            title={chosen.reportPath}
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(chosen.reportPath!);
                setCopied(true);
              } catch {
                setCopied(false);
              }
            }}
          >
            {copied ? "Report path copied" : "Copy report path"}
            <span aria-hidden="true">↗</span>
          </button>
        )}
      </div>
    </section>
  );
}
