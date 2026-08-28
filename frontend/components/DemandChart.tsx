"use client";

import { useEffect, useMemo, useRef } from "react";
import type { Config, Data, Layout } from "plotly.js";

import type { HistoryPoint } from "@/lib/api";

type PlotlyModule = typeof import("plotly.js-dist-min");

const LAYOUT: Partial<Layout> = {
  autosize: true,
  paper_bgcolor: "transparent",
  plot_bgcolor: "transparent",
  // Plotly writes this straight into SVG attributes, so it needs a real stack.
  font: { color: "#7f8ea9", family: "ui-sans-serif, system-ui, sans-serif", size: 12 },
  margin: { l: 60, r: 20, t: 10, b: 44 },
  hovermode: "x unified",
  legend: { orientation: "h", x: 0, y: 1.18, bgcolor: "transparent" },
  xaxis: { gridcolor: "#16203a", zeroline: false },
  yaxis: {
    gridcolor: "#16203a",
    zeroline: false,
    title: { text: "Demand (GW)" },
  },
};

const CONFIG: Partial<Config> = { displayModeBar: false, responsive: true };

const toGigawatts = (megawatts: number | null) =>
  megawatts === null ? null : megawatts / 1000;

function buildTraces(points: HistoryPoint[]): Data[] {
  const timestamps = points.map((point) => point.timestamp);

  return [
    {
      x: timestamps,
      y: points.map((point) => toGigawatts(point.forecast_mw)),
      name: "Day-ahead forecast",
      type: "scatter",
      mode: "lines",
      line: { color: "#64748b", width: 2, dash: "dot" },
      hovertemplate: "%{y:.1f} GW<extra>Forecast</extra>",
    },
    {
      x: timestamps,
      y: points.map((point) => toGigawatts(point.demand_mw)),
      name: "Actual demand",
      type: "scatter",
      mode: "lines",
      line: { color: "#38bdf8", width: 2.5 },
      hovertemplate: "%{y:.1f} GW<extra>Actual</extra>",
    },
  ];
}

export default function DemandChart({ points }: { points: HistoryPoint[] }) {
  const container = useRef<HTMLDivElement>(null);
  const plotly = useRef<PlotlyModule | null>(null);
  const traces = useMemo(() => buildTraces(points), [points]);

  useEffect(() => {
    const node = container.current;
    if (!node) return;

    let cancelled = false;

    const draw = async () => {
      plotly.current ??= await import("plotly.js-dist-min");
      if (cancelled) return;
      await plotly.current.react(node, traces, LAYOUT, CONFIG);
    };
    void draw();

    return () => {
      cancelled = true;
    };
  }, [traces]);

  // Plotly attaches listeners outside React, so release them on unmount only.
  useEffect(() => {
    const node = container.current;
    return () => {
      if (node) plotly.current?.purge(node);
    };
  }, []);

  return <div ref={container} className="chart" />;
}
