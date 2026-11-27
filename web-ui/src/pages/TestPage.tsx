import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import type { TestType } from "../api/types";
import { useAuth } from "../auth";
import { AiBadge, ErrorBanner, Section, Status, useLoad } from "../components/ui";
import { can } from "../permissions";

/** UC-2 review screen: read / edit the code, approve or reject THIS version (ADR-005), flag issues. */
export function TestPage() {
  const testId = Number(useParams().id);
  const { api, user } = useAuth();
  const role = user?.role;
  const test = useLoad(() => api.getTest(testId), [testId]);
  const t = test.data;

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({ title: "", testType: "NORMAL" as TestType, testCode: "" });
  const [comment, setComment] = useState("");
  const [flag, setFlag] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (t) setDraft({ title: t.title, testType: t.testType, testCode: t.testCode });
  }, [t]);

  async function act(fn: () => Promise<unknown>, done: string) {
    setError(null);
    setNotice(null);
    try {
      await fn();
      setNotice(done);
      test.reload();
    } catch (e) {
      setError(e);
      if (e instanceof ApiError && e.code === "VERSION_CONFLICT") test.reload();
    }
  }

  if (!t) return <ErrorBanner error={test.error} />;

  return (
    <>
      <p className="crumbs">
        <Link to="/projects">Projects</Link> / <Link to={`/projects/${t.projectId}`}>Project</Link> /
      </p>
      <h1>
        {t.title} {t.aiGenerated && <AiBadge text="AI suggestion" />}
      </h1>
      <p>
        <Status value={t.status} /> version {t.version} · {t.testType.toLowerCase()} ·{" "}
        {t.approvedVersion ? `approved v${t.approvedVersion} — can run` : "not approved — cannot run"}
      </p>
      <ErrorBanner error={error} />
      {notice && <div className="banner info">{notice}</div>}
      {t.aiGenerated && t.status === "DRAFT" && (
        <div className="banner warn">This test was written by the AI. Read the code before approving it — only approved tests run.</div>
      )}

      <Section
        title="Test code"
        actions={
          can(role, "editTests") &&
          !editing && (
            <button className="secondary" onClick={() => setEditing(true)}>
              Edit
            </button>
          )
        }
      >
        {editing ? (
          <div className="stack">
            <div className="row">
              <input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} aria-label="Title" />
              <select value={draft.testType} onChange={(e) => setDraft({ ...draft, testType: e.target.value as TestType })} aria-label="Test type">
                <option>NORMAL</option>
                <option>BOUNDARY</option>
                <option>NEGATIVE</option>
              </select>
            </div>
            <textarea className="code" rows={14} value={draft.testCode} onChange={(e) => setDraft({ ...draft, testCode: e.target.value })} aria-label="Test code" />
            <p className="muted small">Saving creates version {t.version + 1} and resets the status to DRAFT — it must be approved again.</p>
            <div className="row">
              <button onClick={() => act(() => api.updateTest(t.testCaseId, draft), "Saved. Status reset to DRAFT.").then(() => setEditing(false))}>
                Save new version
              </button>
              <button className="secondary" onClick={() => setEditing(false)}>
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <pre className="code">{t.testCode}</pre>
        )}
      </Section>

      {can(role, "approve") && !editing && (
        <Section title={`Review version ${t.version}`}>
          <div className="stack">
            <input placeholder="Comment (optional)" value={comment} onChange={(e) => setComment(e.target.value)} />
            <div className="row">
              <button disabled={t.status === "APPROVED"} onClick={() => act(() => api.approveTest(t.testCaseId, t.version, comment), `Version ${t.version} approved.`)}>
                ✓ Approve v{t.version}
              </button>
              <button className="danger" disabled={t.status === "REJECTED"} onClick={() => act(() => api.rejectTest(t.testCaseId, t.version, comment), "Rejected.")}>
                ✕ Reject
              </button>
            </div>
          </div>
        </Section>
      )}

      {can(role, "flag") && (
        <Section title="Flag an issue">
          <div className="row">
            <input placeholder="What looks wrong? (advisory)" value={flag} onChange={(e) => setFlag(e.target.value)} />
            <button className="secondary" disabled={!flag.trim()} onClick={() => act(() => api.flagTest(t.testCaseId, flag.trim()), "Flag recorded.").then(() => setFlag(""))}>
              Flag
            </button>
          </div>
        </Section>
      )}
    </>
  );
}
