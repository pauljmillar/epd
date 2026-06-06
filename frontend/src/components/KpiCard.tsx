import { Link } from "react-router-dom";
import type { BadDirection } from "../api/types";
import { DeltaText } from "./DeltaText";
import { Sparkline } from "./Sparkline";

interface Props {
  /** Metric display name (uppercased in the UI). */
  label: string;
  /**
   * Plain-English definition of the metric. REQUIRED per BRD §12: "No metric is
   * displayed without a tooltip. This is enforced: every <MetricCard> must accept
   * a `definition` prop; failing to pass it is a type error."
   */
  definition: string;
  value: number | null;
  unit: string;
  deltaPct: number | null;
  badDirection: BadDirection;
  spark: (number | null)[];
  /** If set, the stat value renders red when value > redWhenAbove (BRD §9.5 PR Size). */
  redWhenAbove?: number;
  /** Optional in-app navigation target. If provided, the card becomes a link. */
  to?: string;
  onClick?: () => void;
}

function formatValue(v: number | null, unit: string): string {
  if (v === null) return "—";
  switch (unit) {
    case "per_week":
      return `${v.toFixed(1)}/wk`;
    case "hours":
      if (v >= 48) return `${(v / 24).toFixed(1)}d`;
      return `${v.toFixed(1)}h`;
    case "pct":
      return `${v.toFixed(0)}%`;
    case "lines":
      return `${Math.round(v)} L`;
    default:
      return String(v);
  }
}

export function KpiCard({
  label,
  definition,
  value,
  unit,
  deltaPct,
  badDirection,
  spark,
  redWhenAbove,
  to,
  onClick,
}: Props) {
  const valueIsAlert =
    redWhenAbove !== undefined && value !== null && value > redWhenAbove;

  const inner = (
    <>
      <div className="flex items-start justify-between">
        <span className="text-text-secondary text-[11px] font-semibold uppercase tracking-wider">
          {label}
        </span>
        <span className="text-text-tertiary text-xs" title={definition}>
          ?
        </span>
      </div>
      <div
        className={`font-semibold text-[32px] leading-tight mt-3 ${
          valueIsAlert ? "text-alert" : "text-text"
        }`}
      >
        {formatValue(value, unit)}
      </div>
      <div className="flex items-end justify-between mt-2">
        <DeltaText pct={deltaPct} badDirection={badDirection} />
        <Sparkline values={spark} />
      </div>
    </>
  );

  const cls =
    "text-left bg-card border border-border rounded p-4 w-full block hover:border-text-tertiary transition-colors";
  if (to) {
    return (
      <Link to={to} className={cls}>
        {inner}
      </Link>
    );
  }
  return (
    <button type="button" onClick={onClick} className={cls}>
      {inner}
    </button>
  );
}
