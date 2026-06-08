import { useEffect, useRef, useState } from "react";
import { cancelSync } from "../api/client";
import type { SyncEvent, SyncStatus } from "../api/types";

interface Props {
  status: SyncStatus;
  onClose: () => void;
}

export function SyncPopover({ status, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [now, setNow] = useState(Date.now());
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  // Tick once a second so elapsed time updates live while running.
  useEffect(() => {
    if (status.status !== "running") return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [status.status]);

  // Outside click + Esc to dismiss.
  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  async function onCancel() {
    setCancelling(true);
    setCancelError(null);
    try {
      await cancelSync();
    } catch (e) {
      setCancelError(String(e));
      setCancelling(false);
    }
  }

  const running = status.status === "running";
  const startedAt = status.started_at ? new Date(status.started_at).getTime() : null;
  const elapsed =
    startedAt !== null ? Math.max(0, Math.round((now - startedAt) / 1000)) : null;
  const total = status.total_repos ?? 0;
  const done = status.repos_done ?? 0;
  const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
  const cancelRequested = !!status.cancel_requested;

  const events: SyncEvent[] = (status.events ?? []).slice(-10);

  return (
    <div
      ref={ref}
      className="absolute bottom-12 left-3 w-[360px] bg-card border border-border rounded shadow-lg p-3 text-sm z-50"
      role="dialog"
      aria-label="Sync status"
    >
      <div className="flex justify-between items-baseline mb-2">
        <div className="text-text font-medium">
          {running
            ? "Sync in progress"
            : status.status === "cancelled"
              ? "Sync cancelled"
              : status.status === "failed"
                ? "Sync failed"
                : status.status === "completed"
                  ? "Sync completed"
                  : "Sync status"}
        </div>
        {elapsed !== null && (
          <div className="text-text-tertiary text-xs">{fmtDuration(elapsed)}</div>
        )}
      </div>

      {status.current_source_label && (
        <div className="text-text-secondary text-xs mb-2">
          Source:{" "}
          <span className="text-text font-mono">{status.current_source_label}</span>
        </div>
      )}

      {total > 0 && (
        <>
          <div className="flex justify-between text-text-tertiary text-xs mb-1">
            <span>
              {done} / {total} repos
            </span>
            <span>{pct}%</span>
          </div>
          <div className="h-1.5 bg-border-subtle rounded mb-2">
            <div
              className="h-1.5 bg-text rounded"
              style={{ width: `${pct}%` }}
              aria-label={`${pct}% complete`}
            />
          </div>
        </>
      )}

      {status.current_repo && running && (
        <div className="text-text-secondary text-xs mb-2 truncate">
          → <span className="text-text font-mono">{status.current_repo}</span>
        </div>
      )}

      {events.length > 0 && (
        <div className="border-t border-border-subtle pt-2 mt-2">
          <div className="text-text-tertiary text-[10px] uppercase tracking-wider mb-1">
            Recent events
          </div>
          <ul className="font-mono text-[11px] leading-tight space-y-0.5 max-h-40 overflow-y-auto">
            {events.map((e, i) => (
              <li
                key={i}
                className={
                  e.level === "error"
                    ? "text-alert"
                    : e.level === "warning"
                      ? "text-text"
                      : "text-text-secondary"
                }
              >
                <span className="text-text-tertiary">
                  {new Date(e.ts).toLocaleTimeString()}
                </span>{" "}
                {e.msg}
              </li>
            ))}
          </ul>
        </div>
      )}

      {status.error && !running && (
        <div className="text-alert text-xs mt-2 border-t border-border-subtle pt-2 break-words">
          {status.error}
        </div>
      )}

      {running && (
        <div className="border-t border-border-subtle pt-2 mt-2 flex items-center justify-between">
          <button
            type="button"
            onClick={onCancel}
            disabled={cancelling || cancelRequested}
            className="border border-alert text-alert text-xs px-3 py-1 rounded hover:bg-alert hover:text-white disabled:opacity-40"
          >
            {cancelRequested
              ? "Cancelling…"
              : cancelling
                ? "Sending…"
                : "Cancel sync"}
          </button>
          {cancelRequested && (
            <span className="text-text-tertiary text-xs">
              Will stop after current repo
            </span>
          )}
          {cancelError && <span className="text-alert text-xs">{cancelError}</span>}
        </div>
      )}
    </div>
  );
}

function fmtDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m === 0) return `${s}s`;
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}
