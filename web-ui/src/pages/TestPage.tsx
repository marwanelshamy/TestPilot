import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import type { TestType } from "../api/types";
import { useAuth } from "../auth";
import { Check, Chevron, Flag, Pencil, Shield, X } from "../components/icons";
import { AiBadge, ErrorBanner, Notice, Section, Status, timeAgo, useLoad } from "../components/ui";
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
      <div className="crumbs">
        <Link to="/projects">Projects</Link> <Chevron size={14} /> <Link to={`/projects/${t.projectId}`}>Project</Link>
        <Chevron size={14} /> <span>Test #{t.testCaseId}</span>
      </div>
      <div className="page-head">
        <div>
          <h1 className="page-title">
            {t.title} {t.aiGenerated && <AiBadge text="AI suggestion" />}
          </h1>
          <div className="page-sub">
            <Status value={t.status} />
            <span className="pill">version {t.version}</span>
            <span className="pill">{t.testType.toLowerCase()}</span>
            <span className="faint small">updated {timeAgo(t.updatedAt)}</span>
          </div>
        </div>
      </div>

      <ErrorBanner error={error} />
      {notice && <Notice kind="ok">{notice}</Notice>}
      {t.aiGenerated && t.status === "DRAFT" && (
        <Notice kind="warn">This test was written by the AI. Read the code before approving it — only approved tests run.</Notice>
      )}

      <div className="split">
        <div>
          {editing ? (
            <div className="stack">
              <div className="row">
                <input className="grow" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} aria-label="Title" />
                <select value={draft.testType} onChange={(e) => setDraft({ ...draft, testType: e.target.value as TestType })} aria-label="Test type">
                  <option>NORMAL</option>
                  <option>BOUNDARY</option>
                  <option>NEGATIVE</option>
                </select>
              </div>
              <div className="editor">
                <div className="editor-bar"><span className="lights"><i /><i /><i /></span>test_tc_{t.testCaseId}_v{t.version + 1}.py · editing</div>
                <textarea className="code" rows={16} value={draft.testCode} onChange={(e) => setDraft({ ...draft, testCode: e.target.value })} aria-label="Test code" spellCheck={false} />
              </div>
              <Notice kind="info">Saving creates version {t.version + 1} and resets the status to DRAFT — it must be approved again.</Notice>
              <div className="row">
                <button className="primary" onClick={() => act(() => api.updateTest(t.testCaseId, draft), "Saved. Status reset to DRAFT.").then(() => setEditing(false))}>
                  Save new version
                </button>
                <button className="ghost" onClick={() => setEditing(false)}>Cancel</button>
              </div>
            </div>
          ) : (
            <div className="editor">
              <div className="editor-bar">
                <span className="lights"><i /><i /><i /></span>test_tc_{t.testCaseId}_v{t.version}.py
                <span style={{ flex: 1 }} />
                {can(role, "editTests") && (
                  <button className="ghost sm" style={{ color: "#c7c3dc" }} onClick={() => setEditing(true)}>
                    <Pencil size={14} /> Edit
                  </button>
                )}
              </div>
              <pre className="code">{t.testCode}</pre>
            </div>
          )}
        </div>

        <div className="sticky">
          <Section title="Approval" icon={<Shield size={16} />}>
            <ul className="timeline" style={{ marginBottom: "1rem" }}>
              <li><span className={`bullet ${t.aiGenerated ? "" : "ok"}`} /><span>{t.aiGenerated ? "Suggested by the AI" : "Written manually"}</span></li>
              <li><span className="bullet" /><span>Current version: <b>v{t.version}</b></span></li>
              <li>
                <span className={`bullet ${t.approvedVersion ? "ok" : t.status === "REJECTED" ? "bad" : ""}`} />
                <span>{t.approvedVersion ? `Approved v${t.approvedVersion} — can run` : t.status === "REJECTED" ? "Rejected — cannot run" : "Not approved — cannot run"}</span>
              </li>
            </ul>
            {can(role, "approve") && !editing ? (
              <div className="stack">
                <input placeholder="Comment (optional)" value={comment} onChange={(e) => setComment(e.target.value)} aria-label="Review comment" />
                <div className="row">
                  <button className="ok" disabled={t.status === "APPROVED"} onClick={() => act(() => api.approveTest(t.testCaseId, t.version, comment), `Version ${t.version} approved.`)}>
                    <Check size={16} /> Approve v{t.version}
                  </button>
                  <button className="danger" disabled={t.status === "REJECTED"} onClick={() => act(() => api.rejectTest(t.testCaseId, t.version, comment), "Rejected.")}>
                    <X size={16} /> Reject
                  </button>
                </div>
              </div>
            ) : (
              !editing && <p className="small muted" style={{ margin: 0 }}>Only a Developer or Team Lead can approve tests.</p>
            )}
          </Section>

          {can(role, "flag") && (
            <Section title="Flag an issue" icon={<Flag size={16} />}>
              <div className="stack">
                <textarea rows={2} placeholder="What looks wrong? (advisory)" value={flag} onChange={(e) => setFlag(e.target.value)} aria-label="Flag comment" />
                <div>
                  <button className="secondary sm" disabled={!flag.trim()} onClick={() => act(() => api.flagTest(t.testCaseId, flag.trim()), "Flag recorded.").then(() => setFlag(""))}>
                    <Flag size={14} /> Flag
                  </button>
                </div>
              </div>
            </Section>
          )}
        </div>
      </div>
    </>
  );
}
