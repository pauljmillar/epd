import { useEffect, useState } from "react";
import { fetchHealth, getToken, setToken, verifyToken } from "../api/client";

type State =
  | { kind: "loading" }
  | { kind: "open" } // no auth required
  | { kind: "needs-token"; error?: string }
  | { kind: "authed" };

export function LoginGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    (async () => {
      try {
        const h = await fetchHealth();
        if (!h.auth_required) {
          setState({ kind: "open" });
          return;
        }
        const t = getToken();
        if (t && (await verifyToken(t))) {
          setState({ kind: "authed" });
        } else {
          setToken(null);
          setState({ kind: "needs-token" });
        }
      } catch (e) {
        setState({ kind: "needs-token", error: String(e) });
      }
    })();
  }, []);

  if (state.kind === "loading") {
    return (
      <div className="h-screen flex items-center justify-center text-text-secondary">
        Loading…
      </div>
    );
  }
  if (state.kind === "open" || state.kind === "authed") {
    return <>{children}</>;
  }
  return <PasswordPrompt onSuccess={() => setState({ kind: "authed" })} initialError={state.error} />;
}

function PasswordPrompt({
  onSuccess,
  initialError,
}: {
  onSuccess: () => void;
  initialError?: string;
}) {
  const [pw, setPw] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | undefined>(initialError);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!pw || submitting) return;
    setSubmitting(true);
    setError(undefined);
    try {
      const ok = await verifyToken(pw);
      if (ok) {
        setToken(pw);
        onSuccess();
      } else {
        setError("Incorrect password.");
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="h-screen flex items-center justify-center bg-page">
      <form
        onSubmit={submit}
        className="bg-card border border-border rounded p-8 w-[360px] flex flex-col gap-4"
      >
        <h1 className="text-text font-semibold text-lg">EPD</h1>
        <p className="text-text-secondary text-sm">
          This dashboard is password-protected.
        </p>
        <input
          type="password"
          autoFocus
          value={pw}
          onChange={(e) => setPw(e.target.value)}
          placeholder="Password"
          className="border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-text"
        />
        {error && <div className="text-alert text-xs">{error}</div>}
        <button
          type="submit"
          disabled={!pw || submitting}
          className="bg-text text-white text-sm font-medium py-2 rounded disabled:opacity-40"
        >
          {submitting ? "Checking…" : "Continue"}
        </button>
      </form>
    </div>
  );
}
