interface Props {
  values: (number | null)[];
  width?: number;
  height?: number;
}

export function Sparkline({ values, width = 60, height = 20 }: Props) {
  const pts = values.filter((v): v is number => v !== null);
  if (pts.length < 2) {
    return <svg width={width} height={height} />;
  }
  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const range = max - min || 1;
  const stepX = width / (values.length - 1);

  const path = values
    .map((v, i) => {
      if (v === null) return "";
      const x = i * stepX;
      const y = height - ((v - min) / range) * (height - 2) - 1;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .filter(Boolean)
    .join(" ");

  return (
    <svg width={width} height={height} className="block">
      <path d={path} fill="none" stroke="#999999" strokeWidth="1" />
    </svg>
  );
}
