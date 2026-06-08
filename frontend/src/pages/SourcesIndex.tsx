import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  createDataSource,
  purgeDataSource,
  replaceDataSources,
  softRemoveDataSource,
  syncDataSource,
  updateDataSource,
  useDataSources,
  type DataSource,
} from "../api/client";
import { PageHeader } from "../components/PageHeader";

export function SourcesIndex() {
  const { data, refetch } = useDataSources();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const sources = data?.sources ?? [];
  const selected = useMemo(
    () => sources.find((s) => s.id === selectedId) ?? null,
    [sources, selectedId],
  );

  useEffect(() => {
    if (selectedId === null && sources.length > 0) {
      setSelectedId(sources[0].id);
    }
  }, [sources, selectedId]);

  const activeSources = sources.filter((s) => s.is_active);

  return (
    <div>
      <PageHeader title="Sources" period="" onPeriodChange={() => {}} />
      <DashboardStateHero activeSources={activeSources} />

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-4">
          <AddSourceForm
            activeSources={activeSources}
            onCreated={refetch}
          />
          <SourceList
            sources={sources}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </div>
        {selected ? (
          <SourceDetail
            source={selected}
            onRefresh={refetch}
          />
        ) : (
          <div className="bg-card border border-border rounded p-6 text-text-secondary text-sm">
            Add a source or select one to manage it.
          </div>
        )}
      </div>
    </div>
  );
}

function DashboardStateHero({ activeSources }: { activeSources: DataSource[] }) {
  if (activeSources.length === 0) {
    return (
      <div className="bg-card border border-border rounded p-4 -mt-4 mb-6 text-sm text-text-secondary">
        No active sources. Add one below to start collecting data — the nightly sync runs at
        02:00 UTC, or click "Sync now" on the source detail pane.
      </div>
    );
  }
  const totalRepos = activeSources.reduce((a, s) => a + s.repo_count, 0);
  const totalPrs = activeSources.reduce((a, s) => a + s.pr_count, 0);
  return (
    <div className="bg-card border border-border rounded p-4 -mt-4 mb-6 text-sm">
      <div className="text-text mb-2">
        Your dashboard is aggregating data from{" "}
        <strong>
          {activeSources.length} active source{activeSources.length === 1 ? "" : "s"}
        </strong>{" "}
        — {totalRepos} repos, {totalPrs.toLocaleString()} PRs.
      </div>
      <div className="flex flex-wrap gap-1.5">
        {activeSources.map((s) => (
          <span
            key={s.id}
            className="inline-block px-2 py-0.5 text-xs bg-active text-text rounded"
          >
            <span className="text-text-tertiary uppercase text-[10px] mr-1.5">
              {s.source}
            </span>
            {s.org_or_group}
          </span>
        ))}
      </div>
      {activeSources.length > 1 && (
        <div className="text-text-tertiary text-xs mt-2">
          Multiple active sources are merged into every KPI. Soft-remove a source to drop
          its data from the dashboard, or use <em>Replace existing</em> on the Add form to
          swap atomically.
        </div>
      )}
    </div>
  );
}

function AddSourceForm({
  activeSources,
  onCreated,
}: {
  activeSources: DataSource[];
  onCreated: () => void;
}) {
  const [source, setSource] = useState<"github" | "gitlab">("github");
  const [orgOrGroup, setOrgOrGroup] = useState("");
  const [token, setToken] = useState("");
  const [submitting, setSubmitting] = useState<null | "add" | "replace">(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const hasActive = activeSources.length > 0;

  function resetForm() {
    setOrgOrGroup("");
    setToken("");
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!orgOrGroup || !token || submitting) return;
    setSubmitting("add");
    setError(null);
    setSuccess(null);
    try {
      const ds = await createDataSource({
        source,
        org_or_group: orgOrGroup.trim(),
        token: token.trim(),
      });
      setSuccess(
        `Added ${ds.source}/${ds.org_or_group}. ${
          hasActive
            ? `Dashboard now aggregates ${activeSources.length + 1} sources. Use Sync to backfill.`
            : "Use Sync to backfill."
        }`,
      );
      resetForm();
      onCreated();
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(null);
    }
  }

  async function handleReplace() {
    if (!orgOrGroup || !token || submitting) return;
    const others = activeSources
      .map((s) => `${s.source}/${s.org_or_group}`)
      .join(", ");
    if (
      !confirm(
        `Replace existing sources?\n\n` +
          `This will:\n` +
          `  • Add ${source}/${orgOrGroup.trim()}\n` +
          `  • Soft-remove ${activeSources.length} existing active source(s): ${others}\n\n` +
          `Soft-removed sources are hidden from the dashboard but their data stays in the DB. ` +
          `You can re-activate or purge them later.`,
      )
    )
      return;

    setSubmitting("replace");
    setError(null);
    setSuccess(null);
    try {
      const r = await replaceDataSources({
        source,
        org_or_group: orgOrGroup.trim(),
        token: token.trim(),
      });
      setSuccess(
        `Switched to ${r.source}/${r.org_or_group}. Soft-removed ${
          r.soft_removed_source_ids.length
        } source(s). Use Sync to backfill.`,
      );
      resetForm();
      onCreated();
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(null);
    }
  }

  return (
    <form onSubmit={handleAdd} className="bg-card border border-border rounded p-4 space-y-3">
      <div className="text-text font-medium text-[13px]">Add source</div>
      <div className="flex gap-2">
        <label className="text-sm text-text-secondary flex items-center gap-1.5">
          <input
            type="radio"
            checked={source === "github"}
            onChange={() => setSource("github")}
          />
          GitHub
        </label>
        <label className="text-sm text-text-secondary flex items-center gap-1.5">
          <input
            type="radio"
            checked={source === "gitlab"}
            onChange={() => setSource("gitlab")}
          />
          GitLab
        </label>
      </div>
      <input
        type="text"
        value={orgOrGroup}
        onChange={(e) => setOrgOrGroup(e.target.value)}
        placeholder={
          source === "github"
            ? "Org slug (e.g. astral-sh)"
            : "Group path (e.g. mygroup or mygroup/sub)"
        }
        className="border border-border rounded px-3 py-2 text-sm w-full"
      />
      <input
        type="password"
        value={token}
        onChange={(e) => setToken(e.target.value)}
        placeholder={
          source === "github"
            ? "PAT (read:org + repo)"
            : "PAT (read_api + read_repository)"
        }
        className="border border-border rounded px-3 py-2 text-sm w-full"
        autoComplete="off"
      />

      {hasActive && (
        <div className="text-text-secondary text-xs border-l-2 border-border pl-2 py-1">
          ⚠️ <strong className="text-text">Add</strong> will aggregate this source's metrics
          with the {activeSources.length} existing active source
          {activeSources.length === 1 ? "" : "s"}. To swap instead, use{" "}
          <strong className="text-text">Replace existing</strong>.
        </div>
      )}

      {error && <div className="text-alert text-xs">{error}</div>}
      {success && <div className="text-text-secondary text-xs">{success}</div>}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={!orgOrGroup || !token || submitting !== null}
          className="bg-text text-white text-sm px-4 py-2 rounded disabled:opacity-40"
        >
          {submitting === "add" ? "Adding…" : "Add source"}
        </button>
        {hasActive && (
          <button
            type="button"
            onClick={handleReplace}
            disabled={!orgOrGroup || !token || submitting !== null}
            className="border border-border text-text text-sm px-4 py-2 rounded hover:bg-active disabled:opacity-40"
          >
            {submitting === "replace" ? "Replacing…" : "Replace existing"}
          </button>
        )}
      </div>
    </form>
  );
}

function SourceList({
  sources,
  selectedId,
  onSelect,
}: {
  sources: DataSource[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <div className="bg-card border border-border rounded">
      <div className="px-4 py-3 border-b border-border text-text font-medium text-[13px]">
        Configured sources
      </div>
      {sources.length === 0 ? (
        <div className="p-4 text-text-tertiary text-sm">None yet.</div>
      ) : (
        <ul>
          {sources.map((s) => (
            <li
              key={s.id}
              onClick={() => onSelect(s.id)}
              className={`px-4 py-2.5 border-t border-border-subtle cursor-pointer ${
                s.id === selectedId ? "bg-active" : "hover:bg-active"
              } ${s.is_active ? "" : "opacity-60"}`}
            >
              <div className="flex justify-between items-baseline">
                <span className="text-text text-sm">
                  <span className="text-text-tertiary uppercase text-[10px] mr-2">
                    {s.source}
                  </span>
                  {s.org_or_group}
                </span>
                <span className="text-text-tertiary text-xs">
                  {s.is_active ? "active" : "inactive"}
                </span>
              </div>
              <div className="text-text-tertiary text-xs mt-1">
                {s.repo_count} repos · {s.pr_count.toLocaleString()} PRs ·{" "}
                {s.last_synced_at ? `synced ${relTime(s.last_synced_at)}` : "never synced"}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SourceDetail({
  source,
  onRefresh,
}: {
  source: DataSource;
  onRefresh: () => void;
}) {
  const qc = useQueryClient();
  const [tokenInput, setTokenInput] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function invalidateAll() {
    qc.invalidateQueries({ queryKey: ["data-sources"] });
    qc.invalidateQueries({ queryKey: ["admin-repos"] });
    qc.invalidateQueries({ queryKey: ["repos"] });
    qc.invalidateQueries({ queryKey: ["admin-contributors"] });
    qc.invalidateQueries({ queryKey: ["contributors-list"] });
    qc.invalidateQueries({ queryKey: ["org"] });
    qc.invalidateQueries({ queryKey: ["teams-list"] });
  }

  async function withBusy(label: string, fn: () => Promise<string | null>) {
    setBusy(label);
    setError(null);
    setMessage(null);
    try {
      const out = await fn();
      if (out) setMessage(out);
      invalidateAll();
      onRefresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  async function onRotateToken() {
    if (!tokenInput.trim()) return;
    await withBusy("token", async () => {
      await updateDataSource(source.id, { token: tokenInput.trim() });
      setTokenInput("");
      return "Token rotated.";
    });
  }

  async function onReactivate() {
    await withBusy("activate", async () => {
      await updateDataSource(source.id, { is_active: true });
      return "Re-activated and repos restored to tracked.";
    });
  }

  async function onSync() {
    await withBusy("sync", async () => {
      const r = await syncDataSource(source.id);
      return `Sync ${r.status}: ${r.repos_synced ?? 0} repos, ${r.prs_synced ?? 0} PRs.`;
    });
  }

  async function onSoftRemove() {
    if (
      !confirm(
        `Hide "${source.org_or_group}" from the dashboard? This soft-removes ${source.repo_count} repos and ${source.pr_count.toLocaleString()} PRs. Data stays in the DB until you purge.`,
      )
    )
      return;
    await withBusy("remove", async () => {
      await softRemoveDataSource(source.id);
      return "Soft-removed. Re-activate to restore.";
    });
  }

  async function onPurge() {
    if (
      !confirm(
        `PERMANENTLY DELETE all data for "${source.org_or_group}"? This removes ${source.repo_count} repos and ${source.pr_count.toLocaleString()} PRs from the database. Cannot be undone.`,
      )
    )
      return;
    await withBusy("purge", async () => {
      const r = await purgeDataSource(source.id);
      return `Purged ${r.deleted_repos} repos and all attached data.`;
    });
  }

  return (
    <div className="bg-card border border-border rounded p-4 space-y-4">
      <div>
        <div className="text-text font-medium">
          <span className="text-text-tertiary uppercase text-[10px] mr-2">
            {source.source}
          </span>
          {source.org_or_group}
        </div>
        <div className="text-text-tertiary text-xs mt-1">
          {source.repo_count} repos · {source.pr_count.toLocaleString()} PRs · token{" "}
          <span className="font-mono">{source.token_preview}</span>
          {source.last_synced_at && ` · synced ${relTime(source.last_synced_at)}`}
        </div>
        {!source.is_active && (
          <div className="text-alert text-xs mt-1">
            Soft-removed. Repos are hidden from the dashboard. Re-activate or purge.
          </div>
        )}
      </div>

      {message && (
        <div className="bg-active text-text text-xs px-3 py-2 rounded">{message}</div>
      )}
      {error && (
        <div className="bg-card border border-alert text-alert text-xs px-3 py-2 rounded">
          {error}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {source.is_active ? (
          <>
            <button
              onClick={onSync}
              disabled={busy !== null}
              className="bg-text text-white text-sm px-3 py-1.5 rounded disabled:opacity-40"
            >
              {busy === "sync" ? "Syncing…" : "Sync now"}
            </button>
            <button
              onClick={onSoftRemove}
              disabled={busy !== null}
              className="border border-border text-text-secondary text-sm px-3 py-1.5 rounded hover:text-text disabled:opacity-40"
            >
              Soft remove
            </button>
          </>
        ) : (
          <button
            onClick={onReactivate}
            disabled={busy !== null}
            className="bg-text text-white text-sm px-3 py-1.5 rounded disabled:opacity-40"
          >
            Re-activate
          </button>
        )}
        <button
          onClick={onPurge}
          disabled={busy !== null}
          className="border border-alert text-alert text-sm px-3 py-1.5 rounded hover:bg-alert hover:text-white disabled:opacity-40"
        >
          Purge data
        </button>
      </div>

      <div className="border-t border-border-subtle pt-4">
        <div className="text-text font-medium text-[13px] mb-2">Rotate token</div>
        <div className="flex gap-2">
          <input
            type="password"
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            placeholder="New PAT"
            className="border border-border rounded px-3 py-1.5 text-sm flex-1"
            autoComplete="off"
          />
          <button
            onClick={onRotateToken}
            disabled={!tokenInput.trim() || busy !== null}
            className="border border-border text-text text-sm px-3 py-1.5 rounded disabled:opacity-40"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

function relTime(iso: string): string {
  const d = new Date(iso);
  const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}
