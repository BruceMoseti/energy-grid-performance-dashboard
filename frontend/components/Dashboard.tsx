"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";

import {
  fetchCurrent,
  fetchHistory,
  fetchRegions,
  type Current,
  type History,
  type Region,
} from "@/lib/api";

const DemandChart = dynamic(() => import("@/components/DemandChart"), {
  ssr: false,
  loading: () => <div className="chart chart--placeholder">Loading chart…</div>,
});

const WINDOWS = [
  { hours: 24, label: "Last 24 hours" },
  { hours: 48, label: "Last 48 hours" },
  { hours: 168, label: "Last 7 days" },
];

// EIA publishes hourly, so a minute is frequent enough to look live without
// hammering the API.
const REFRESH_MS = 60_000;

type Tone = "neutral" | "good" | "warn" | "bad";

const formatGw = (megawatts: number | null) =>
  megawatts === null ? "—" : `${(megawatts / 1000).toFixed(1)} GW`;

const formatPct = (value: number | null) =>
  value === null ? "—" : `${value.toFixed(1)}%`;

const formatSignedGw = (megawatts: number | null) => {
  if (megawatts === null) return "—";
  return `${megawatts >= 0 ? "+" : "−"}${Math.abs(megawatts / 1000).toFixed(1)} GW`;
};

const formatHour = (iso: string) =>
  `${new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  })} UTC`;

const forecastTone = (errorPct: number | null): Tone => {
  if (errorPct === null) return "neutral";
  if (errorPct < 2) return "good";
  if (errorPct < 5) return "warn";
  return "bad";
};

function Kpi({
  label,
  value,
  detail,
  tone = "neutral",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: Tone;
}) {
  return (
    <article className="kpi">
      <h2 className="kpi__label">{label}</h2>
      <p className={`kpi__value kpi__value--${tone}`}>{value}</p>
      <p className="kpi__detail">{detail}</p>
    </article>
  );
}

export default function Dashboard() {
  const [regions, setRegions] = useState<Region[]>([]);
  const [region, setRegion] = useState("PJM");
  const [hours, setHours] = useState(24);
  const [current, setCurrent] = useState<Current | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  const load = useCallback(async () => {
    try {
      const [regionList, currentData, historyData] = await Promise.all([
        fetchRegions(),
        fetchCurrent(region, hours),
        fetchHistory(region, hours),
      ]);
      setRegions(regionList);
      setCurrent(currentData);
      setHistory(historyData);
      setError(null);
      setUpdatedAt(new Date());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to reach the API");
    }
  }, [region, hours]);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  const windowLabel =
    WINDOWS.find((option) => option.hours === hours)?.label ?? `${hours}h`;
  const regionOptions = regions.length
    ? regions
    : [{ region_code: region, region_name: region }];

  return (
    <main className="page">
      <header className="header">
        <div className="brand">
          <span className="brand__mark" aria-hidden="true">
            ⚡
          </span>
          <div>
            <h1 className="brand__name">GridPulse</h1>
            <p className="brand__tagline">Real-time energy grid performance</p>
          </div>
        </div>

        <div className="controls">
          <label className="control">
            <span className="control__label">Region</span>
            <select value={region} onChange={(event) => setRegion(event.target.value)}>
              {regionOptions.map((option) => (
                <option key={option.region_code} value={option.region_code}>
                  {option.region_name}
                </option>
              ))}
            </select>
          </label>

          <label className="control">
            <span className="control__label">Window</span>
            <select
              value={hours}
              onChange={(event) => setHours(Number(event.target.value))}
            >
              {WINDOWS.map((option) => (
                <option key={option.hours} value={option.hours}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <button className="refresh" type="button" onClick={() => void load()}>
            Refresh
          </button>
        </div>
      </header>

      {error && (
        <p className="banner banner--error" role="alert">
          {error}
        </p>
      )}

      {!current && !error && <p className="banner">Connecting to the GridPulse API…</p>}

      {current && (
        <>
          <section className="kpis" aria-label="Grid performance indicators">
            <Kpi
              label="Grid load"
              value={formatGw(current.demand_mw)}
              detail={`Forecast ${formatGw(current.forecast_mw)}`}
            />
            <Kpi
              label="Peak load"
              value={formatGw(current.peak_demand_mw)}
              detail={windowLabel.toLowerCase()}
            />
            <Kpi
              label="Forecast error"
              value={formatPct(current.forecast_error_pct)}
              detail="latest hour vs day-ahead"
              tone={forecastTone(current.forecast_error_pct)}
            />
            <Kpi
              label="1-hour ramp"
              value={formatSignedGw(current.ramp_mw)}
              detail={
                current.ramp_mw !== null && current.ramp_mw >= 0
                  ? "demand rising"
                  : "demand falling"
              }
            />
            <Kpi
              label="Load factor"
              value={formatPct(current.load_factor_pct)}
              detail="average ÷ peak"
            />
          </section>

          <section className="panel">
            <div className="panel__head">
              <div>
                <h2 className="panel__title">Demand vs day-ahead forecast</h2>
                <p className="panel__subtitle">
                  {current.region_name} · reading for {formatHour(current.timestamp)}
                </p>
              </div>
              <span className="status">
                <span className="status__dot" aria-hidden="true" />
                Live
                {updatedAt
                  ? ` · updated ${updatedAt.toLocaleTimeString("en-US", { hour12: false })}`
                  : ""}
              </span>
            </div>

            {history && history.points.length > 0 ? (
              <DemandChart points={history.points} />
            ) : (
              <div className="chart chart--placeholder">
                No readings in this window yet.
              </div>
            )}

            <dl className="facts">
              <div>
                <dt>Net generation</dt>
                <dd>{formatGw(current.generation_mw)}</dd>
              </div>
              <div>
                <dt>Net interchange</dt>
                <dd>{formatSignedGw(current.interchange_mw)}</dd>
              </div>
              <div>
                <dt>Readings charted</dt>
                <dd>{history?.points.length ?? 0}</dd>
              </div>
            </dl>
          </section>
        </>
      )}

      <footer className="footer">
        Source: U.S. Energy Information Administration hourly grid monitor. Values are
        megawatthours per hour reported by each balancing authority.
      </footer>
    </main>
  );
}
