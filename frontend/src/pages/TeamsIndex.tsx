import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  addTeamMember,
  createTeam,
  deleteTeam,
  getTeamMembers,
  removeTeamMember,
  useContributorsList,
  useTeamsList,
} from "../api/client";
import type { TeamMember, TeamSummary } from "../api/types";
import { PageHeader } from "../components/PageHeader";

export function TeamsIndex() {
  const { data: teams, refetch } = useTeamsList();
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const selected = useMemo(
    () => teams?.teams.find((t) => t.id === selectedId) ?? null,
    [teams, selectedId],
  );

  // Pick the first team as default once loaded
  useEffect(() => {
    if (selectedId === null && teams && teams.teams.length > 0) {
      setSelectedId(teams.teams[0].id);
    }
  }, [teams, selectedId]);

  return (
    <div>
      <PageHeader title="Teams" period="" onPeriodChange={() => {}} />
      <p className="text-text-secondary text-sm -mt-4 mb-6">
        A team is a named group of contributors. Metrics for a team aggregate their PRs
        across all repos they touched.
      </p>

      <div className="grid grid-cols-2 gap-4">
        <TeamList
          teams={teams?.teams ?? []}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onRefresh={refetch}
        />
        {selected ? (
          <TeamMembers team={selected} onRefreshList={refetch} />
        ) : (
          <div className="bg-card border border-border rounded p-6 text-text-secondary text-sm">
            Select or create a team to manage its members.
          </div>
        )}
      </div>
    </div>
  );
}

function TeamList({
  teams,
  selectedId,
  onSelect,
  onRefresh,
}: {
  teams: TeamSummary[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onRefresh: () => void;
}) {
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!newName || creating) return;
    setCreating(true);
    setError(null);
    try {
      await createTeam(newName.trim());
      setNewName("");
      onRefresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setCreating(false);
    }
  }

  async function onDelete(id: number, name: string) {
    if (!confirm(`Delete team "${name}"?`)) return;
    try {
      await deleteTeam(id);
      onRefresh();
    } catch (e) {
      alert(String(e));
    }
  }

  return (
    <div className="bg-card border border-border rounded">
      <div className="px-4 py-3 border-b border-border text-text font-medium text-[13px]">
        Teams
      </div>
      <ul>
        {teams.map((t) => (
          <li
            key={t.id}
            onClick={() => onSelect(t.id)}
            className={`flex items-center justify-between px-4 py-2.5 border-t border-border-subtle cursor-pointer ${
              t.id === selectedId ? "bg-active" : "hover:bg-active"
            }`}
          >
            <div className="flex flex-col">
              <span className="text-text text-sm">
                <Link
                  to={`/teams/${t.id}/view`}
                  onClick={(e) => e.stopPropagation()}
                  className="hover:underline"
                >
                  {t.name}
                </Link>
              </span>
              <span className="text-text-tertiary text-xs">
                {t.members} member{t.members === 1 ? "" : "s"}
              </span>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete(t.id, t.name);
              }}
              className="text-text-tertiary text-xs hover:text-alert"
              aria-label={`Delete ${t.name}`}
            >
              Delete
            </button>
          </li>
        ))}
        {teams.length === 0 && (
          <li className="px-4 py-6 text-text-tertiary text-sm">
            No teams yet — create one below.
          </li>
        )}
      </ul>
      <form onSubmit={submit} className="border-t border-border p-3 flex gap-2">
        <input
          type="text"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="New team name"
          className="border border-border rounded px-2 py-1.5 text-sm flex-1"
        />
        <button
          type="submit"
          disabled={!newName.trim() || creating}
          className="bg-text text-white text-sm px-3 py-1.5 rounded disabled:opacity-40"
        >
          Add
        </button>
      </form>
      {error && <div className="text-alert text-xs px-3 pb-2">{error}</div>}
    </div>
  );
}

function TeamMembers({
  team,
  onRefreshList,
}: {
  team: TeamSummary;
  onRefreshList: () => void;
}) {
  const [members, setMembers] = useState<TeamMember[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { data: allContribs } = useContributorsList();
  const [filter, setFilter] = useState("");
  const qc = useQueryClient();

  async function loadMembers() {
    try {
      const r = await getTeamMembers(team.id);
      setMembers(r.members);
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    loadMembers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [team.id]);

  async function add(login: string) {
    try {
      await addTeamMember(team.id, login);
      await loadMembers();
      onRefreshList();
      qc.invalidateQueries({ queryKey: ["team", team.id] });
    } catch (e) {
      setError(String(e));
    }
  }

  async function remove(login: string) {
    try {
      await removeTeamMember(team.id, login);
      await loadMembers();
      onRefreshList();
      qc.invalidateQueries({ queryKey: ["team", team.id] });
    } catch (e) {
      setError(String(e));
    }
  }

  const memberLogins = new Set((members ?? []).map((m) => m.login));
  const available = (allContribs?.contributors ?? [])
    .filter((c) => !memberLogins.has(c.login))
    .filter((c) => c.login.toLowerCase().includes(filter.toLowerCase()));

  return (
    <div className="bg-card border border-border rounded flex flex-col">
      <div className="px-4 py-3 border-b border-border text-text font-medium text-[13px] flex items-center justify-between">
        <span>{team.name} — members</span>
        <Link
          to={`/teams/${team.id}/view`}
          className="text-text-tertiary text-xs hover:text-text"
        >
          View team metrics →
        </Link>
      </div>
      {error && <div className="text-alert text-xs px-4 py-2 border-b border-border-subtle">{error}</div>}
      <div className="p-3 border-b border-border-subtle min-h-[80px]">
        {members === null && <div className="text-text-tertiary text-sm">Loading…</div>}
        {members && members.length === 0 && (
          <div className="text-text-tertiary text-sm">No members yet.</div>
        )}
        <div className="flex flex-wrap gap-1.5">
          {(members ?? []).map((m) => (
            <span
              key={m.login}
              className="inline-flex items-center gap-1 px-2 py-0.5 text-xs bg-active text-text rounded"
            >
              {m.login}
              <button
                onClick={() => remove(m.login)}
                className="text-text-tertiary hover:text-alert text-xs"
                aria-label={`Remove ${m.login}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      </div>
      <div className="p-3 border-b border-border-subtle">
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Search contributors…"
          className="border border-border rounded px-2 py-1.5 text-sm w-full"
        />
      </div>
      <ul className="overflow-y-auto max-h-[400px]">
        {available.map((c) => (
          <li
            key={c.login}
            className="flex items-center justify-between px-4 py-2 border-t border-border-subtle text-sm"
          >
            <span className="text-text">{c.login}</span>
            <div className="flex items-center gap-3">
              <span className="text-text-tertiary text-xs">{c.prs_merged_90d} PRs/90d</span>
              <button
                onClick={() => add(c.login)}
                className="text-text-secondary text-xs hover:text-text"
              >
                + Add
              </button>
            </div>
          </li>
        ))}
        {available.length === 0 && filter !== "" && (
          <li className="text-text-tertiary text-sm px-4 py-3">No match.</li>
        )}
      </ul>
    </div>
  );
}
