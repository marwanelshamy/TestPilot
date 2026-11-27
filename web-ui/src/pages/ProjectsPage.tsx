import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth";
import { ArrowUp, Folder } from "../components/icons";
import { Empty, ErrorBanner, timeAgo, useLoad } from "../components/ui";
import { can } from "../permissions";
import { announceProjectsChanged } from "../theme";

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

/** UC-1, step 1: create a project (FR-01) and pick one to work on. */
export function ProjectsPage() {
  const { api, user } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const { data, error } = useLoad(() => api.listProjects(), [api]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [formError, setFormError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const nameRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (params.get("new")) nameRef.current?.focus();
  }, [params]);

  async function create(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    setBusy(true);
    try {
      const { id } = await api.createProject(name.trim(), description.trim());
      announceProjectsChanged();
      nav(`/projects/${id}`);
    } catch (err) {
      setFormError(err);
    } finally {
      setBusy(false);
    }
  }

  const first = user?.name.split(" ")[0] ?? "";

  return (
    <>
      <div className="hello">
        <h1>
          {greeting()}, <span className="grad-text">{first}</span>
        </h1>
        <p>What would you like to test today?</p>
      </div>

      {can(user?.role, "createProject") && (
        <form className="create-box" onSubmit={create} aria-label="New project">
          <Folder />
          <input ref={nameRef} placeholder="Name a new project…" value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} aria-label="Project name" />
          <input className="desc" placeholder="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} aria-label="Description" />
          <span className="pill" title="One language and framework in the MVP (C-01)">Python · pytest</span>
          <button type="submit" className="send" disabled={busy || !name.trim()} aria-label="Create">
            <ArrowUp />
          </button>
        </form>
      )}
      <div style={{ maxWidth: 720, margin: "-1.6rem auto 1.6rem" }}>
        <ErrorBanner error={formError} />
      </div>

      <ErrorBanner error={error} />
      <div className="row between" style={{ marginBottom: ".8rem" }}>
        <h2 className="serif" style={{ fontSize: "1.35rem" }}>Your projects</h2>
        {data && <span className="count">{data.total}</span>}
      </div>
      {!data ? (
        <p className="muted">Loading…</p>
      ) : data.items.length === 0 ? (
        <div className="card">
          <Empty icon={<Folder />} title="No projects yet">Create your first project above to start generating tests.</Empty>
        </div>
      ) : (
        <div className="project-grid">
          {data.items.map((p) => (
            <Link key={p.projectId} to={`/projects/${p.projectId}`} className="project-card">
              <span className="pill">{p.programmingLanguage} · {p.testFramework}</span>
              <h3>{p.name}</h3>
              <div className="small muted">{p.description || "No description"}</div>
              <div className="foot">
                <span>Created {timeAgo(p.createdAt)}</span>
                <span className="grad-text" style={{ fontWeight: 700 }}>Open →</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
