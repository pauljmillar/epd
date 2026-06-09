import { PeriodSelector } from "./PeriodSelector";
import { TeamFilterSelect } from "./TeamFilterSelect";

export function PageHeader({
  title,
  period,
  onPeriodChange,
  showTeamFilter,
}: {
  title: string;
  period: string;
  onPeriodChange: (p: string) => void;
  showTeamFilter?: boolean;
}) {
  return (
    <div className="border-b border-border pb-4 mb-6 flex items-center justify-between">
      <h1 className="text-text text-xl font-semibold">{title}</h1>
      <div className="flex items-center gap-3">
        {showTeamFilter && <TeamFilterSelect />}
        <PeriodSelector value={period} onChange={onPeriodChange} />
      </div>
    </div>
  );
}
