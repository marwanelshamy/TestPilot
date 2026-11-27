import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { friendlyError } from "../api/client";
import { useAuth } from "../auth";
import { ROLE_LABEL } from "../permissions";

export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/projects" className="brand">
          TestPilot <span>AI</span>
        </Link>
        {user && (
          <div className="who">
            <span>{user.name}</span>
            <span className="role">{ROLE_LABEL[user.role]}</span>
            <button
              className="link"
              onClick={() => {
                logout();
                nav("/login");
              }}
            >
              Sign out
            </button>
          </div>
        )}
      </header>
      <main className="content">{children}</main>
    </div>
  );
}

export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <div className="banner error" role="alert">
      {friendlyError(error)}
    </div>
  );
}

const STATUS_CLASS: Record<string, string> = {
  PASSED: "ok",
  APPROVED: "ok",
  FAILED: "bad",
  ERROR: "bad",
  REJECTED: "bad",
  INTERRUPTED: "warn",
  CANCELLED: "warn",
  QUEUED: "info",
  RUNNING: "info",
  DRAFT: "muted",
  NOT_RUN: "muted",
  SKIPPED: "muted",
};

export function Status({ value }: { value: string }) {
  return <span className={`status ${STATUS_CLASS[value] ?? "muted"}`}>{value.replace("_", " ")}</span>;
}

/** C-10: AI output is always labelled as AI-generated. */
export function AiBadge({ text = "AI-generated" }: { text?: string }) {
  return (
    <span className="ai-badge" title="Produced by the AI assistant — review before trusting it">
      ✦ {text}
    </span>
  );
}

/** Loads data with an async function; re-runs when `deps` change or `reload()` is called. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setError(null);
    fn().then(
      (d) => alive && setData(d),
      (e) => alive && setError(e),
    );
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { data, error, reload: () => setTick((t) => t + 1), setData };
}

export function Section({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="card">
      <div className="card-head">
        <h2>{title}</h2>
        {actions}
      </div>
      {children}
    </section>
  );
}

export function fmtTime(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleString() : "—";
}
