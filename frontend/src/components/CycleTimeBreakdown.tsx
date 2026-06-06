import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface Row {
  week: string;
  pickup: number | null;
  review: number | null;
  merge: number | null;
}

// Three shades of gray per BRD §12 (dark / medium / light).
const COLORS = { pickup: "#444444", review: "#999999", merge: "#CCCCCC" };

export function CycleTimeBreakdown({ data }: { data: Row[] }) {
  // Recharts can't stack `null` cleanly — coerce to 0 for rendering, but tooltip honors the
  // original value via a payload formatter.
  const safe = data.map((d) => ({
    week: d.week,
    Pickup: d.pickup ?? 0,
    Review: d.review ?? 0,
    Merge: d.merge ?? 0,
  }));
  return (
    <div className="w-full h-[260px]">
      <ResponsiveContainer>
        <BarChart data={safe} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#F0F0F0" vertical={false} />
          <XAxis
            dataKey="week"
            tick={{ fill: "#999999", fontSize: 11 }}
            stroke="#E5E5E5"
            tickFormatter={(v) => (typeof v === "string" ? v.slice(5) : String(v))}
            minTickGap={24}
          />
          <YAxis
            tick={{ fill: "#999999", fontSize: 11 }}
            stroke="#E5E5E5"
            label={{
              value: "hours",
              angle: -90,
              position: "insideLeft",
              fill: "#999999",
              fontSize: 11,
            }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#FFFFFF",
              border: "1px solid #E5E5E5",
              borderRadius: 4,
              fontSize: 12,
              color: "#111111",
            }}
            formatter={(v: number) => `${v.toFixed(1)}h`}
          />
          <Legend wrapperStyle={{ fontSize: 12, color: "#666666" }} />
          <Bar dataKey="Pickup" stackId="ct" fill={COLORS.pickup} />
          <Bar dataKey="Review" stackId="ct" fill={COLORS.review} />
          <Bar dataKey="Merge" stackId="ct" fill={COLORS.merge} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
