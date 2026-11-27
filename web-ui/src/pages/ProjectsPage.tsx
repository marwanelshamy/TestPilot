import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { ErrorBanner, Section, fmtTime, useLoad } from "../components/ui";
import { can } from "../permissions";

/** UC-1, step 1: list projects and create a new one (FR-01). */
export function ProjectsPage() {
  const { api, user } = useAuth();
  const nav = useNavigate();
  const { data, error } = useLoad(() => api.listProjects(), [api]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [formError, setFormError] = useState<unknown>(null);

  async function create(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    try {
      const { id } = await api.createProject(name.trim(), description.trim());
      nav(`/projects/${id}`);
    } catch (err) {
      setFormError(err);
    }
  }

  return (
    <>
      <h1>Projects</h1>
      <ErrorBanner error={error} />
      {can(user?.role, "createProject") && (
        <Section title="New project">
          <form className="row" onSubmit={create}>
            <input placeholder="Project name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} />
            <input placeholder="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} />
            <span className="pill" title="One language and framework in the MVP (C-01)">
              Python · pytest
            </span>
            <button type="submit">Create</button>
          </form>
          <ErrorBanner error={formError} />
        </Section>
      )}
      <Section title="Your projects">
        {!data ? (
          <p className="muted">Loading…</p>
        ) : data.items.length === 0 ? (
          <p className="muted">No projects yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Stack</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((p) => (
                <tr key={p.projectId}>
                  <td>
                    <Link to={`/projects/${p.projectId}`}>{p.name}</Link>
                    {p.description && <div className="muted small">{p.description}</div>}
                  </td>
                  <td>
                    {p.programmingLanguage} · {p.testFramework}
                  </td>
                  <td>{fmtTime(p.createdAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
    </>
  );
}
