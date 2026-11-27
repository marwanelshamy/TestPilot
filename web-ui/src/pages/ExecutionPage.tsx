import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { Evidence, Execution, Explanation } from "../api/types";
import { TERMINAL } from "../api/types";
import { useAuth } from "../auth";
import { Check, Chevron, Clock, Logo, Sparkles, Terminal, X } from "../components/icons";
import { AiBadge, ErrorBanner, Notice, Section, Status, Thinking, fmtTime } from "../components/ui";
import { can } from "../permissions";

export const POLL_MS = 2000;

function Stepper({ ex }: { ex: Execution }) {
  const running = ex.status === "RUNNING";
  const done = TERMINAL.includes(ex.status);
  const steps = [
    { lbl: "Queued", val: fmtTime(ex.createdAt), state: "done" },
    { lbl: "Running in sandbox", val: ex.startedAt ? fmtTime(ex.startedAt) : "waiting for a runner", state: done || running ? (done ? "done" : "active") : ex.status === "QUEUED" ? "active" : "" },
    { lbl: "Result", val: done ? ex.status : "pending", state: done ? "done" : "" },
  ];
  return (
    <div className="stepper">
      {steps.map((s) => (
        <div key={s.lbl} className={`step ${s.state}`}>
          <div className="lbl">{s.lbl}</div>
          <div className="val">{s.state === "active" && <Thinking />} {s.val}</div>
          <div className="bar" />
        </div>
      ))}
    </div>
  );
}

/** UC-3 results: polls until the run is terminal (A-05), shows the REAL runner outcome and logs (FR-07, FR-08),
 *  and AI explanations clearly labelled as hypotheses next to the original evidence (FR-09, C-10). */
export function ExecutionPage({ pollMs = POLL_MS }: { pollMs?: number }) {
  const executionId = useParams().id!;
  const { api, user } = useAuth();
  const [ex, setEx] = useState<Execution | null>(null);
  const [logs, setLogs] = useState<Evidence[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [explanations, setExplanations] = useState<Record<number, Explanation>>({});
  const [explaining, setExplaining] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const e = await api.getExecution(executionId);
        if (!alive) return;
        setEx(e);
        setError(null);
        if (TERMINAL.includes(e.status)) {
          const l = await api.executionLogs(executionId);
          if (alive) setLogs(l.items);
          return; // stop polling
        }
      } catch (err) {
        if (alive) setError(err);
      }
      if (alive) timer = setTimeout(poll, pollMs);
    }
    poll();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [api, executionId, pollMs]);

  async function explain(executionTestId: number) {
    setExplaining(executionTestId);
    setError(null);
    try {
      const e = await api.explainFailure(executionId, executionTestId);
      setExplanations((prev) => ({ ...prev, [executionTestId]: e }));
    } catch (err) {
      setError(err);
    } finally {
      setExplaining(null);
    }
  }

  if (!ex) return error ? <ErrorBanner error={error} /> : <p className="muted">Loading…</p>;
  const done = TERMINAL.includes(ex.status);
  const passed = ex.tests.filter((t) => t.resultStatus === "PASSED").length;

  return (
    <>
      <div className="crumbs">
        <Link to="/projects">Projects</Link> <Chevron size={14} /> <Link to={`/projects/${ex.projectId}`}>Project</Link>
        <Chevron size={14} /> <span>Run</span>
      </div>
      <div className="page-head">
        <div>
          <h1 className="page-title">
            Run <span className="mono" style={{ fontSize: ".8em" }}>{ex.executionId.slice(0, 8)}</span> <Status value={ex.status} />
          </h1>
          <div className="page-sub">
            {done && <span><b>{passed}</b> of {ex.tests.length} passed</span>}
            {ex.terminationReason && <span className="pill">reason: {ex.terminationReason}</span>}
          </div>
        </div>
      </div>

      <Stepper ex={ex} />
      <ErrorBanner error={error} />
      {!done && (
        <Notice>
          {ex.status === "QUEUED" ? "Waiting for a free runner…" : "Running in an isolated sandbox…"} This page updates automatically.
        </Notice>
      )}
      {ex.status === "INTERRUPTED" && (
        <Notice kind="warn">
          The run did not finish normally ({ex.terminationReason}). No result was recorded as passed — re-run after checking the logs.
        </Notice>
      )}

      <Section title="Results from the test runner" icon={<Check size={16} />} count={ex.tests.length}>
        <p className="small faint" style={{ marginTop: "-.4rem" }}>Pass/fail comes only from pytest's own report — never from the AI.</p>
        <div className="result-grid">
          {ex.tests.map((t) => {
            const bad = t.resultStatus === "FAILED" || t.resultStatus === "ERROR";
            const ok = t.resultStatus === "PASSED";
            const e = explanations[t.executionTestId];
            return (
              <div key={t.executionTestId} className={`result ${bad ? "failed" : ""}`}>
                <span className={`verdict ${ok ? "ok" : bad ? "bad" : "muted"}`}>{ok ? <Check /> : bad ? <X /> : <Clock />}</span>
                <div style={{ minWidth: 0 }}>
                  <div className="row">
                    <Link to={`/tests/${t.testCaseId}`}><b>Test #{t.testCaseId}</b></Link>
                    <span className="faint small">v{t.testCaseVersion}</span>
                    <Status value={t.resultStatus} />
                  </div>
                  {t.failureMessage && <div className="failure-msg">{t.failureMessage}</div>}
                  {bad && can(user?.role, "explain") && !e && (
                    <button className="secondary sm" style={{ marginTop: ".6rem" }} disabled={explaining === t.executionTestId} onClick={() => explain(t.executionTestId)}>
                      {explaining === t.executionTestId ? <>Thinking <Thinking /></> : <><Sparkles size={14} /> Explain with AI</>}
                    </button>
                  )}
                  {e && (
                    <div className="assistant">
                      <span className="avatar"><Logo size={15} /></span>
                      <div className="bubble">
                        <AiBadge text={e.label} />
                        <p>{e.explanationText}</p>
                      </div>
                    </div>
                  )}
                </div>
                <span className="faint small">{t.durationMs != null ? `${t.durationMs} ms` : "—"}</span>
              </div>
            );
          })}
        </div>
      </Section>

      {done && (
        <Section title="Runner evidence" icon={<Terminal size={16} />} count={logs.length}>
          {logs.length === 0 && <p className="muted">No logs recorded.</p>}
          {logs.map((l) => (
            <details key={l.evidenceId} className="terminal" open={l.evidenceType !== "JUNIT_XML"}>
              <summary>
                <Terminal size={14} /> {l.evidenceType.toLowerCase()} · {l.sizeBytes} bytes{l.truncated && " · truncated"}
              </summary>
              <pre>{l.content}</pre>
            </details>
          ))}
        </Section>
      )}
    </>
  );
}
