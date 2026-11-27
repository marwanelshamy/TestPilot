import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { friendlyError } from "../api/client";
import type { Project } from "../api/types";
import { useAuth } from "../auth";
import { ROLE_LABEL, can } from "../permissions";
import { PROJECTS_CHANGED, currentTheme, toggleTheme, type Theme } from "../theme";
import { Alert, Info, Logo, LogOut, Menu, Moon, Plus, Search, Sun } from "./icons";

/* ------------------------------------------------------------------ app shell: navigation rail + content */
export function Layout({ children }: { children: ReactNode }) {
  const { user, logout, api } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [projects, setProjects] = useState<Project[]>([]);
  const [query, setQuery] = useState("");
  const [theme, setTheme] = useState<Theme>(currentTheme());
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const load = () => api.listProjects().then((p) => setProjects(p.items), () => setProjects([]));
    load();
    window.addEventListener(PROJECTS_CHANGED, load);
    return () => window.removeEventListener(PROJECTS_CHANGED, load);
  }, [api]);
  useEffect(() => {
    setOpen(false);
    window.scrollTo(0, 0); // each screen starts at the top (SPA navigation keeps the old scroll otherwise)
  }, [loc.pathname]);

  const shown = useMemo(
    () => projects.filter((p) => p.name.toLowerCase().includes(query.trim().toLowerCase())),
    [projects, query],
  );
  const initials = (user?.name ?? "?").split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();

  return (
    <div className={`shell ${open ? "nav-open" : ""}`}>
      <aside className="rail" aria-label="Navigation">
        <Link to="/projects" className="brand">
          <span className="brand-mark"><Logo size={20} /></span>
          <span className="brand-name">TestPilot <span>AI</span></span>
        </Link>
        {can(user?.role, "createProject") && (
          <button className="new-btn" onClick={() => nav("/projects?new=1")}>
            <Plus /> New project
          </button>
        )}
        <div className="rail-search">
          <Search size={15} />
          <input placeholder="Search projects" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search projects" />
        </div>
        <div className="rail-label">Projects</div>
        <nav className="rail-list">
          {shown.map((p) => (
            <NavLink key={p.projectId} to={`/projects/${p.projectId}`} className={({ isActive }) => `rail-item ${isActive ? "active" : ""}`}>
              <span className="dot" />
              <span className="name">{p.name}</span>
            </NavLink>
          ))}
          {shown.length === 0 && <div className="rail-empty">{projects.length ? "No match" : "No projects yet"}</div>}
        </nav>
        {user && (
          <div className="rail-foot">
            <span className="avatar">{initials}</span>
            <div className="who">
              <div className="n">{user.name}</div>
              <div className="r">{ROLE_LABEL[user.role]}</div>
            </div>
            <button className="icon" title={theme === "dark" ? "Light theme" : "Dark theme"} aria-label="Toggle theme" onClick={() => setTheme(toggleTheme())}>
              {theme === "dark" ? <Sun /> : <Moon />}
            </button>
            <button
              className="icon"
              title="Sign out"
              aria-label="Sign out"
              onClick={() => {
                logout();
                nav("/login");
              }}
            >
              <LogOut />
            </button>
          </div>
        )}
      </aside>
      {open && <div className="scrim" onClick={() => setOpen(false)} />}
      <div className="main">
        <div className="topbar">
          <button className="icon" aria-label="Open navigation" onClick={() => setOpen(true)}><Menu /></button>
          <span className="brand-name">TestPilot <span>AI</span></span>
        </div>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ feedback */
export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <div className="banner error" role="alert">
      <Alert /> <span>{friendlyError(error)}</span>
    </div>
  );
}

export function Notice({ kind = "info", children }: { kind?: "info" | "warn" | "ok"; children: ReactNode }) {
  return (
    <div className={`banner ${kind}`} role="status">
      {kind === "warn" ? <Alert /> : <Info />} <span>{children}</span>
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
  PARTIAL: "warn",
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

export function Thinking() {
  return (
    <span className="thinking" aria-hidden>
      <i />
      <i />
      <i />
    </span>
  );
}

/* ------------------------------------------------------------------ layout helpers */
export function Section({
  title,
  icon,
  count,
  actions,
  children,
}: {
  title: string;
  icon?: ReactNode;
  count?: number;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="card">
      <div className="card-head">
        <h2 className="card-title">
          {icon && <span className="ic">{icon}</span>}
          {title}
          {count !== undefined && <span className="count">{count}</span>}
        </h2>
        {actions}
      </div>
      {children}
    </section>
  );
}

export function Empty({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <div className="ic">{icon}</div>
      <b>{title}</b>
      {children && <div className="small muted" style={{ marginTop: ".3rem" }}>{children}</div>}
    </div>
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

export function fmtTime(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleString() : "—";
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}
