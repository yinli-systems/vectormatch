import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE, asObject } from "./api";

interface EvidenceRun {
  id: string;
  label: string;
  scope?: string;
  model?: string;
  commands?: number;
  trades?: number;
  throughput?: number;
  p50Millis?: number;
  p99Millis?: number;
  unknown?: number;
  correctnessPassed?: boolean;
  durability?: string;
  limitations: string[];
  artifactPath?: string;
  timestamp?: string | number;
}

function ProofIcon({
  name,
  size = 16,
}: {
  name: "arrow" | "close" | "check" | "refresh" | "file" | "info";
  size?: number;
}) {
  const paths = {
    arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    check: (
      <>
        <path d="m7 12 3 3 7-7" />
        <path d="m12 2 8 3v6c0 5-4 9-8 11-4-2-8-6-8-11V5l8-3Z" />
      </>
    ),
    refresh: (
      <>
        <path d="M20 8a8 8 0 0 0-14-3L3 8M3 3v5h5M4 16a8 8 0 0 0 14 3l3-3M16 16h5v5" />
      </>
    ),
    file: (
      <>
        <path d="M14 2H5v20h14V7l-5-5ZM14 2v5h5M8 12h8M8 16h6" />
      </>
    ),
    info: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 10v7M12 6v.1" />
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
      strokeWidth="1.35"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

const numeric = (value: unknown) =>
  typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : undefined;
const text = (value: unknown) =>
  typeof value === "string" && value.trim() ? value : undefined;
const integer = (value?: number) =>
  value === undefined
    ? "—"
    : value.toLocaleString("en-US", { maximumFractionDigits: 0 });
const throughput = (value?: number) =>
  value === undefined
    ? "—"
    : new Intl.NumberFormat("en-US", {
        notation: "compact",
        maximumFractionDigits: 2,
      }).format(value);
function latency(millis?: number): { value: string; unit: string } {
  if (millis === undefined) return { value: "—", unit: "ms" };
  if (millis > 0 && millis < 1)
    return {
      value: (millis * 1000).toLocaleString("en-US", {
        maximumFractionDigits: 2,
      }),
      unit: "µs",
    };
  return {
    value: millis.toLocaleString("en-US", { maximumFractionDigits: 2 }),
    unit: "ms",
  };
}
function recordedAt(timestamp?: string | number) {
  if (timestamp === undefined) return "Timestamp not reported";
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime())
    ? "Timestamp not reported"
    : `${date.toLocaleDateString("en-GB", { year: "numeric", month: "short", day: "2-digit", timeZone: "UTC" })} · ${date.toLocaleTimeString("en-GB", { hour12: false, timeZone: "UTC" })} UTC`;
}

function normalize(value: unknown, index: number): EvidenceRun {
  const run = asObject(value);
  return {
    id: text(run.id) || `evidence-${index}`,
    label: text(run.label) || "Untitled measurement",
    scope: text(run.scope),
    model: text(run.model),
    commands: numeric(run.commands),
    trades: numeric(run.trades),
    throughput: numeric(run.throughput),
    p50Millis: numeric(run.p50Millis),
    p99Millis: numeric(run.p99Millis),
    unknown: numeric(run.unknown),
    correctnessPassed:
      typeof run.correctnessPassed === "boolean"
        ? run.correctnessPassed
        : undefined,
    durability: text(run.durability),
    limitations: Array.isArray(run.limitations)
      ? run.limitations.filter(
          (item): item is string => typeof item === "string",
        )
      : text(run.limitations)
        ? [String(run.limitations)]
        : [],
    artifactPath: text(run.artifactPath),
    timestamp:
      typeof run.timestamp === "string" || typeof run.timestamp === "number"
        ? run.timestamp
        : undefined,
  };
}

function EvidenceDrawer({
  run,
  close,
}: {
  run: EvidenceRun;
  close: () => void;
}) {
  const dialog = useRef<HTMLElement>(null);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.current?.focus();
    return () => {
      document.body.style.overflow = originalOverflow;
      previous?.focus();
    };
  }, []);
  const p50 = latency(run.p50Millis),
    p99 = latency(run.p99Millis);
  return (
    <div className="evidence-backdrop" onClick={close}>
      <aside
        className="evidence-drawer"
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-title"
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => {
          if (event.key === "Escape") close();
          if (event.key === "Tab") {
            const items = dialog.current?.querySelectorAll<HTMLElement>(
              'button:not(:disabled), [href], [tabindex="0"]',
            );
            if (!items?.length) {
              event.preventDefault();
              return;
            }
            const first = items[0],
              last = items[items.length - 1];
            if (
              event.shiftKey &&
              (document.activeElement === first ||
                document.activeElement === dialog.current)
            ) {
              event.preventDefault();
              last.focus();
            } else if (
              !event.shiftKey &&
              (document.activeElement === last ||
                document.activeElement === dialog.current)
            ) {
              event.preventDefault();
              first.focus();
            }
          }
        }}
      >
        <div className="evidence-drawer-head">
          <span className="eyebrow">MEASUREMENT RECORD</span>
          <button onClick={close} aria-label="Close evidence details">
            <ProofIcon name="close" size={20} />
          </button>
        </div>
        <div className="evidence-drawer-intro">
          <span
            className={`evidence-verdict ${run.correctnessPassed === true ? "passed" : run.correctnessPassed === false ? "failed" : "unreported"}`}
          >
            <ProofIcon
              name={run.correctnessPassed === true ? "check" : "info"}
              size={12}
            />
            {run.correctnessPassed === true
              ? "Correctness checks passed"
              : run.correctnessPassed === false
                ? "Correctness checks failed"
                : "Correctness not reported"}
          </span>
          <h2 id="evidence-title">{run.label}</h2>
          <span className="evidence-recorded">{recordedAt(run.timestamp)}</span>
        </div>
        <div className="evidence-drawer-stats">
          <div>
            <label>Reported throughput</label>
            <strong>
              {throughput(run.throughput)}
              <small>cmd/s</small>
            </strong>
          </div>
          <div>
            <label>Latency p99</label>
            <strong>
              {p99.value}
              <small>{p99.unit}</small>
            </strong>
          </div>
        </div>
        <section className="evidence-boundary">
          <span className="evidence-detail-label">WHAT THIS RUN MEASURES</span>
          <dl>
            <div>
              <dt>Timing scope</dt>
              <dd>{run.scope || "Not reported"}</dd>
            </div>
            <div>
              <dt>Load model</dt>
              <dd>{run.model || "Not reported"}</dd>
            </div>
            <div>
              <dt>Durability</dt>
              <dd>{run.durability || "Not reported"}</dd>
            </div>
          </dl>
        </section>
        <section className="evidence-detail-section">
          <span className="evidence-detail-label">RUN COUNTERS</span>
          <div className="evidence-counter-grid">
            <div>
              <span>Commands</span>
              <strong>{integer(run.commands)}</strong>
            </div>
            <div>
              <span>Trades</span>
              <strong>{integer(run.trades)}</strong>
            </div>
            <div>
              <span>Latency p50</span>
              <strong>
                {p50.value} <small>{p50.unit}</small>
              </strong>
            </div>
            <div>
              <span>Unknown outcomes</span>
              <strong
                className={
                  run.unknown === undefined
                    ? ""
                    : run.unknown > 0
                      ? "negative"
                      : "positive"
                }
              >
                {integer(run.unknown)}
              </strong>
            </div>
          </div>
        </section>
        <section className="evidence-detail-section">
          <span className="evidence-detail-label">LIMITATIONS & CONTEXT</span>
          {run.limitations.length ? (
            <ul className="evidence-limitations">
              {run.limitations.map((limitation, index) => (
                <li key={index}>{limitation}</li>
              ))}
            </ul>
          ) : (
            <p className="evidence-no-limitations">
              Limitations were not included in this artifact.
            </p>
          )}
        </section>
        <section className="evidence-artifact">
          <div>
            <ProofIcon name="file" size={14} />
            <span>Source artifact</span>
            {run.artifactPath && (
              <button
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(run.artifactPath!);
                    setCopied(true);
                  } catch {
                    setCopied(false);
                  }
                }}
              >
                {copied ? "Copied" : "Copy path"}
              </button>
            )}
          </div>
          <code>{run.artifactPath || "Artifact path not reported"}</code>
          <p>
            Repository path only. Inspect the artifact and workload before
            comparing runs.
          </p>
        </section>
        <div className="evidence-drawer-footer">
          <ProofIcon name="info" size={10} />
          Recorded evidence is separate from live runtime telemetry.
        </div>
      </aside>
    </div>
  );
}

export default function Evidence() {
  const [runs, setRuns] = useState<EvidenceRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [selected, setSelected] = useState<EvidenceRun>();
  const inFlight = useRef(false);
  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/evidence`, {
        signal: AbortSignal.timeout(5000),
        headers: { Accept: "application/json" },
      });
      if (!response.ok)
        throw new Error(`Evidence service returned HTTP ${response.status}`);
      const data = asObject(await response.json());
      if (!Array.isArray(data.runs))
        throw new Error("Evidence response does not contain a runs array");
      setRuns(data.runs.map(normalize));
      setError(undefined);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Evidence service is unavailable",
      );
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void refresh();
    const interval = setInterval(() => void refresh(), 30000);
    return () => clearInterval(interval);
  }, [refresh]);
  return (
    <section className="evidence-section" id="evidence">
      <div className="section-heading evidence-heading">
        <div>
          <span className="eyebrow">REPRODUCIBLE PERFORMANCE</span>
          <h2>Proof, with the boundaries.</h2>
        </div>
        <div className="evidence-heading-actions">
          <span className="evidence-run-count">
            <span
              className={`status-dot ${runs.length && !error ? "online" : ""}`}
            />
            {runs.length
              ? `${runs.length} recorded ${runs.length === 1 ? "run" : "runs"}`
              : "SOURCE ARTIFACTS"}
          </span>
          <button
            onClick={() => void refresh()}
            disabled={loading}
            aria-label="Refresh performance evidence"
          >
            <span className={loading ? "spinning" : ""}>
              <ProofIcon name="refresh" size={13} />
            </span>
          </button>
        </div>
      </div>
      <p className="evidence-intro">
        Different paths. Explicit timing scopes. Every result comes from a
        recorded run.
      </p>
      {error && runs.length > 0 && (
        <p className="evidence-fetch-error" role="status">
          {error}. Showing the last retrieved artifacts.
        </p>
      )}
      {runs.length ? (
        <div className="evidence-grid">
          {runs.map((run, index) => {
            const p99 = latency(run.p99Millis);
            return (
              <article
                className={`panel evidence-card ${run.correctnessPassed === false ? "evidence-card-failed" : ""}`}
                key={`${run.id}-${index}`}
              >
                <div className="evidence-card-top">
                  <span className="evidence-index">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span
                    className={`evidence-check ${run.correctnessPassed === true ? "passed" : run.correctnessPassed === false ? "failed" : ""}`}
                  >
                    <ProofIcon
                      name={run.correctnessPassed === true ? "check" : "info"}
                      size={12}
                    />
                    {run.correctnessPassed === true
                      ? "CHECKS PASSED"
                      : run.correctnessPassed === false
                        ? "CHECKS FAILED"
                        : "UNVERIFIED"}
                  </span>
                </div>
                <h3>{run.label}</h3>
                <div className="evidence-scope">
                  {run.scope || "Scope not reported"}
                </div>
                <div className="evidence-card-metrics">
                  <div>
                    <strong title={run.throughput?.toLocaleString("en-US")}>
                      {throughput(run.throughput)}
                      <small>cmd/s</small>
                    </strong>
                    <span>Reported throughput</span>
                  </div>
                  <div>
                    <strong>
                      {p99.value}
                      <small>{p99.unit}</small>
                    </strong>
                    <span>Latency p99</span>
                  </div>
                </div>
                <div className="evidence-model">
                  <span>LOAD MODEL</span>
                  <strong>{run.model || "Not reported"}</strong>
                </div>
                <div className="evidence-card-bottom">
                  <div>
                    <span>{integer(run.commands)} commands</span>
                    <span
                      className={
                        run.unknown === undefined
                          ? ""
                          : run.unknown > 0
                            ? "negative"
                            : "positive"
                      }
                    >
                      {run.unknown === undefined
                        ? "Unknowns not reported"
                        : `${integer(run.unknown)} unknown`}
                    </span>
                  </div>
                  <button
                    onClick={() => setSelected(run)}
                    aria-label={`Inspect ${run.label} measurement details`}
                  >
                    Inspect run
                    <ProofIcon name="arrow" size={13} />
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="panel evidence-empty">
          <span className="evidence-empty-icon">
            <ProofIcon name="file" size={23} />
          </span>
          <div>
            <strong>
              {loading
                ? "Loading measurement artifacts…"
                : "Awaiting verified runs"}
            </strong>
            <p>
              {error ||
                "Recorded performance results will appear when the evidence service publishes them."}
            </p>
          </div>
          <span className="evidence-empty-label">NO ESTIMATED RESULTS</span>
        </div>
      )}
      <div className="evidence-scope-note">
        <ProofIcon name="info" size={12} />
        <span>
          Scope and load model define each result. These cards are not directly
          comparable across different measurement boundaries.
        </span>
      </div>
      {selected && (
        <EvidenceDrawer run={selected} close={() => setSelected(undefined)} />
      )}
    </section>
  );
}

export function ProjectionStatus({
  projection,
}: {
  projection: Record<string, unknown>;
}) {
  const status = text(projection.status);
  const observed =
    typeof projection.observationAt === "string" ||
    typeof projection.observationAt === "number"
      ? projection.observationAt
      : undefined;
  const healthy =
    status &&
    ["UP", "CURRENT", "CONNECTED", "OK"].includes(status.toUpperCase());
  return (
    <section
      className="panel projection-strip"
      aria-label="PostgreSQL projection status"
    >
      <div className="projection-identity">
        <ProofIcon name="file" size={19} />
        <div>
          <strong>PostgreSQL projection</strong>
          <span>
            <i className={`status-dot ${healthy ? "online" : ""}`} />
            {status || "Awaiting projector observation"}
          </span>
        </div>
      </div>
      <div className="projection-counters">
        {[
          { label: "Durable cursor", value: projection.cursor },
          { label: "Observed lag", value: projection.lag },
          { label: "Events stored", value: projection.eventsStored },
          { label: "Trades stored", value: projection.tradesStored },
        ].map((item) => (
          <div key={item.label}>
            <span>{item.label}</span>
            <strong>{integer(numeric(item.value))}</strong>
          </div>
        ))}
      </div>
      <div className="projection-observation">
        <span>CACHED DATABASE OBSERVATION</span>
        <strong>{observed === undefined ? "—" : recordedAt(observed)}</strong>
      </div>
    </section>
  );
}
