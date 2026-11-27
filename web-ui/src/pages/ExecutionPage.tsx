import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { Evidence, Execution, Explanation } from "../api/types";
import { TERMINAL } from "../api/types";
import { useAuth } from "../auth";
import { AiBadge, ErrorBanner, Section, Status, fmtTime } from "../components/ui";
import { can } from "../permissions";

export const POLL_MS = 2000;

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

  return (
    <>
      <p className="crumbs">
        <Link to="/projects">Projects</Link> / <Link to={`/projects/${ex.projectId}`}>Project</Link> /
      </p>
      <h1>
        Run {ex.executionId.slice(0, 8)} <Status value={ex.status} />
      </h1>
      <p className="muted">
        Requested {fmtTime(ex.createdAt)} · started {fmtTime(ex.startedAt)} · finished {fmtTime(ex.finishedAt)}
        {ex.terminationReason && ` · reason: ${ex.terminationReason}`}
      </p>
      <ErrorBanner error={error} />
      {!done && (
        <div className="banner info" role="status">
          {ex.status === "QUEUED" ? "Waiting for a free runner…" : "Running in an isolated sandbox…"} This page updates automatically.
        </div>
      )}
      {ex.status === "INTERRUPTED" && (
        <div className="banner warn">
          The run did not finish normally ({ex.terminationReason}). No result was recorded as passed — re-run after checking the logs.
        </div>
      )}

      <Section title="Results from the test runner">
        <p className="muted small">Pass/fail comes only from pytest's own report — never from the AI.</p>
        <table>
          <thead>
            <tr>
              <th>Test case</th>
              <th>Result</th>
              <th>Duration</th>
              <th>Failure</th>
            </tr>
          </thead>
          <tbody>
            {ex.tests.map((t) => (
              <tr key={t.executionTestId}>
                <td>
                  <Link to={`/tests/${t.testCaseId}`}>#{t.testCaseId}</Link> v{t.testCaseVersion}
                </td>
                <td>
                  <Status value={t.resultStatus} />
                </td>
                <td>{t.durationMs != null ? `${t.durationMs} ms` : "—"}</td>
                <td className="failure">
                  {t.failureMessage && <code>{t.failureMessage}</code>}
                  {(t.resultStatus === "FAILED" || t.resultStatus === "ERROR") && can(user?.role, "explain") && !explanations[t.executionTestId] && (
                    <button className="secondary small" disabled={explaining === t.executionTestId} onClick={() => explain(t.executionTestId)}>
                      {explaining === t.executionTestId ? "Asking…" : "✦ Explain with AI"}
                    </button>
                  )}
                  {explanations[t.executionTestId] && (
                    <div className="explanation">
                      <AiBadge text={explanations[t.executionTestId].label} />
                      <p>{explanations[t.executionTestId].explanationText}</p>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      {done && (
        <Section title="Runner evidence (logs)">
          {logs.length === 0 && <p className="muted">No logs recorded.</p>}
          {logs.map((l) => (
            <details key={l.evidenceId} open={l.evidenceType !== "JUNIT_XML"}>
              <summary>
                {l.evidenceType} · {l.sizeBytes} bytes{l.truncated && " · truncated"}
              </summary>
              <pre className="code">{l.content}</pre>
            </details>
          ))}
        </Section>
      )}
    </>
  );
}
