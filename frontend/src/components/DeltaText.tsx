import type { BadDirection } from "../api/types";

export function DeltaText({
  pct,
  badDirection,
}: {
  pct: number | null;
  badDirection: BadDirection;
}) {
  if (pct === null || pct === undefined) {
    return <span className="text-text-secondary text-[13px]">— no prior data</span>;
  }
  let arrow = "→";
  let direction: "up" | "down" | "flat" = "flat";
  if (pct > 0.5) {
    arrow = "↑";
    direction = "up";
  } else if (pct < -0.5) {
    arrow = "↓";
    direction = "down";
  }

  const isBad =
    badDirection !== null &&
    ((badDirection === "up" && direction === "up") ||
      (badDirection === "down" && direction === "down"));

  const sign = pct > 0 ? "+" : "";
  return (
    <span
      className={`text-[13px] ${isBad ? "text-alert" : "text-text"}`}
      aria-label={`${arrow} ${sign}${pct}%`}
    >
      {arrow} {sign}
      {pct}% vs prior period
    </span>
  );
}
