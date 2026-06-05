import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface Series {
  key: string;
  label: string;
  dashed?: boolean;
}

export function MetricLineChart({
  data,
  series,
  yLabel,
}: {
  data: Record<string, string | number | null>[];
  series: Series[];
  yLabel?: string;
}) {
  return (
    <div className="w-full h-[240px]">
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
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
            label={
              yLabel
                ? { value: yLabel, angle: -90, position: "insideLeft", fill: "#999999", fontSize: 11 }
                : undefined
            }
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#FFFFFF",
              border: "1px solid #E5E5E5",
              borderRadius: 4,
              fontSize: 12,
              color: "#111111",
            }}
          />
          {series.map((s) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.label}
              stroke={s.dashed ? "#AAAAAA" : "#111111"}
              strokeWidth={s.dashed ? 1.5 : 2}
              strokeDasharray={s.dashed ? "4 4" : undefined}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
