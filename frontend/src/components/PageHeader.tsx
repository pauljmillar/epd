import { PeriodSelector } from "./PeriodSelector";

export function PageHeader({
  title,
  period,
  onPeriodChange,
}: {
  title: string;
  period: string;
  onPeriodChange: (p: string) => void;
}) {
  return (
    <div className="border-b border-border pb-4 mb-6 flex items-center justify-between">
      <h1 className="text-text text-xl font-semibold">{title}</h1>
      <PeriodSelector value={period} onChange={onPeriodChange} />
    </div>
  );
}
