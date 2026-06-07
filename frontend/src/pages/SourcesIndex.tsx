import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  createDataSource,
  purgeDataSource,
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

  return (
    <div>
      <PageHeader title="Sources" period="" onPeriodChange={() => {}} />
      <p className="text-text-secondary text-sm -mt-4 mb-6">
        Each source is a (GitHub org or GitLab group, token) pair. The dashboard aggregates
        every active source. Soft-remove hides a source's data; purge deletes it permanently.
      </p>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-4">
          <AddSourceForm onCreated={refetch} />
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

function AddSourceForm({ onCreated }: { onCreated: () => void }) {
  const [source, setSource] = useState<"github" | "gitlab">("github");
  const [orgOrGroup, setOrgOrGroup] = useState("");
  const [token, setToken] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!orgOrGroup || !token || submitting) return;
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const ds = await createDataSource({ source, org_or_group: orgOrGroup.trim(), token: token.trim() });
      setSuccess(`Added ${ds.source}/${ds.org_or_group}. Use Sync to backfill.`);
      setOrgOrGroup("");
      setToken("");
      onCreated();
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="bg-card border border-border rounded p-4 space-y-3">
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
        placeholder={source === "github" ? "Org slug (e.g. astral-sh)" : "Group path (e.g. mygroup or mygroup/sub)"}
        className="border border-border rounded px-3 py-2 text-sm w-full"
      />
      <input
        type="password"
        value={token}
        onChange={(e) => setToken(e.target.value)}
        placeholder={source === "github" ? "PAT (read:org + repo)" : "PAT (read_api + read_repository)"}
        className="border border-border rounded px-3 py-2 text-sm w-full"
        autoComplete="off"
      />
      {error && <div className="text-alert text-xs">{error}</div>}
      {success && <div className="text-text-secondary text-xs">{success}</div>}
      <button
        type="submit"
        disabled={!orgOrGroup || !token || submitting}
        className="bg-text text-white text-sm px-4 py-2 rounded disabled:opacity-40"
      >
        {submitting ? "Adding…" : "Add source"}
      </button>
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
