import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import type { QualityReport, TestType } from "../api/types";
import { useAuth } from "../auth";
import { AiBadge, ErrorBanner, Section, Status, fmtTime, useLoad } from "../components/ui";
import { can } from "../permissions";

const TYPES: TestType[] = ["NORMAL", "BOUNDARY", "NEGATIVE"];

/** One project: requirements (UC-1), AI/manual tests (UC-2), runs (UC-3), quality (UC-4). */
export function ProjectPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const { api, user } = useAuth();
  const nav = useNavigate();
  const role = user?.role;

  const project = useLoad(() => api.getProject(projectId), [projectId]);
  const reqs = useLoad(() => api.listRequirements(projectId), [projectId]);
  const tests = useLoad(() => api.listTests(projectId), [projectId]);
  const runs = useLoad(() => api.listExecutions(projectId), [projectId]);
  const coverage = useLoad(() => api.coverage(projectId), [projectId]);
  const risks = useLoad(() => api.risks(projectId), [projectId]);

  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // forms
  const [reqTitle, setReqTitle] = useState("");
  const [reqText, setReqText] = useState("");
  const [genReq, setGenReq] = useState<number | "">("");
  const [genTypes, setGenTypes] = useState<TestType[]>(TYPES);
  const [genCode, setGenCode] = useState("");
  const [manualOpen, setManualOpen] = useState(false);
  const [manual, setManual] = useState({ title: "", testType: "NORMAL" as TestType, testCode: "def test_example():\n    assert True\n" });
  const [selected, setSelected] = useState<number[]>([]);
  const [report, setReport] = useState<QualityReport | null>(null);

  async function act(label: string, fn: () => Promise<void>) {
    setBusy(label);
    setError(null);
    setNotice(null);
    try {
      await fn();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  const addRequirement = (e: FormEvent) => {
    e.preventDefault();
    act("req", async () => {
      await api.addRequirement(projectId, reqTitle.trim(), reqText.trim());
      setReqTitle("");
      setReqText("");
      reqs.reload();
      coverage.reload();
      risks.reload();
    });
  };

  const generate = (e: FormEvent) => {
    e.preventDefault();
    if (genReq === "") return;
    act("gen", async () => {
      const r = await api.generateTests(projectId, genReq, genTypes, genCode);
      setNotice(`${r.testIds.length} AI suggestion(s) added as DRAFT. Review each one before it can run.`);
      tests.reload();
    });
  };

  const addManual = (e: FormEvent) => {
    e.preventDefault();
    act("manual", async () => {
      await api.createTest(projectId, { ...manual, requirementIds: genReq === "" ? [] : [genReq] });
      setManualOpen(false);
      setNotice("Manual test added as DRAFT.");
      tests.reload();
    });
  };

  const run = () =>
    act("run", async () => {
      const r = await api.startExecution(projectId, selected);
      nav(`/executions/${r.executionId}`);
    });

  const makeReport = () =>
    act("report", async () => {
      const { id: rid } = await api.createReport(projectId);
      setReport(await api.getReport(rid));
    });

  const approved = tests.data?.items.filter((t) => t.status === "APPROVED") ?? [];
  const reqTitleById = new Map(reqs.data?.items.map((r) => [r.requirementId, r.title]));

  return (
    <>
      <p className="crumbs">
        <Link to="/projects">Projects</Link> /
      </p>
      <h1>{project.data?.name ?? "…"}</h1>
      {project.data && (
        <p className="muted">
          {project.data.programmingLanguage} · {project.data.testFramework}
          {project.data.description ? ` — ${project.data.description}` : ""}
        </p>
      )}
      <ErrorBanner error={project.error} />
      <ErrorBanner error={error} />
      {notice && <div className="banner info">{notice}</div>}

      {/* ---------------- UC-1 requirements ---------------- */}
      <Section title="Requirements">
        {reqs.data?.items.length ? (
          <ol className="reqs">
            {reqs.data.items.map((r) => (
              <li key={r.requirementId}>
                <strong>{r.title}</strong>
                <div className="muted small pre">{r.description}</div>
              </li>
            ))}
          </ol>
        ) : (
          <p className="muted">No requirements yet.</p>
        )}
        {can(role, "addRequirement") && (
          <form className="stack" onSubmit={addRequirement}>
            <input placeholder="Requirement title" value={reqTitle} onChange={(e) => setReqTitle(e.target.value)} required maxLength={200} />
            <textarea placeholder="Describe the expected behaviour" value={reqText} onChange={(e) => setReqText(e.target.value)} required rows={3} />
            <button type="submit" disabled={busy === "req"}>
              Add requirement
            </button>
          </form>
        )}
      </Section>

      {/* ---------------- UC-2 tests ---------------- */}
      <Section title="Test cases">
        {can(role, "editTests") && (
          <form className="stack gen" onSubmit={generate}>
            <div className="row">
              <select value={genReq} onChange={(e) => setGenReq(e.target.value === "" ? "" : Number(e.target.value))} required aria-label="Requirement">
                <option value="">Choose a requirement…</option>
                {reqs.data?.items.map((r) => (
                  <option key={r.requirementId} value={r.requirementId}>
                    {r.title}
                  </option>
                ))}
              </select>
              {TYPES.map((t) => (
                <label key={t} className="check">
                  <input
                    type="checkbox"
                    aria-label={`${t.toLowerCase()} tests`}
                    checked={genTypes.includes(t)}
                    onChange={(e) => setGenTypes(e.target.checked ? [...genTypes, t] : genTypes.filter((x) => x !== t))}
                  />
                  {t.toLowerCase()}
                </label>
              ))}
              <button type="submit" disabled={busy === "gen" || genTypes.length === 0}>
                {busy === "gen" ? "Asking the AI…" : "✦ Generate tests with AI"}
              </button>
              <button type="button" className="secondary" onClick={() => setManualOpen((o) => !o)}>
                Add manually
              </button>
            </div>
            <textarea
              className="code"
              placeholder="Optional: paste the code under test (Python). The generated tests include it so they run in the sandbox."
              value={genCode}
              onChange={(e) => setGenCode(e.target.value)}
              rows={4}
            />
          </form>
        )}
        {manualOpen && (
          <form className="stack manual" onSubmit={addManual}>
            <div className="row">
              <input placeholder="Title" value={manual.title} onChange={(e) => setManual({ ...manual, title: e.target.value })} required />
              <select value={manual.testType} onChange={(e) => setManual({ ...manual, testType: e.target.value as TestType })} aria-label="Test type">
                {TYPES.map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </div>
            <textarea className="code" rows={6} value={manual.testCode} onChange={(e) => setManual({ ...manual, testCode: e.target.value })} required />
            <button type="submit" disabled={busy === "manual"}>
              Save as draft
            </button>
          </form>
        )}

        {tests.data?.items.length ? (
          <table>
            <thead>
              <tr>
                <th title="Only APPROVED tests can be selected to run">Run</th>
                <th>Test</th>
                <th>Requirement</th>
                <th>Type</th>
                <th>Status</th>
                <th>Version</th>
              </tr>
            </thead>
            <tbody>
              {tests.data.items.map((t) => (
                <tr key={t.testCaseId}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`select test ${t.testCaseId}`}
                      disabled={t.status !== "APPROVED"}
                      checked={selected.includes(t.testCaseId)}
                      onChange={(e) =>
                        setSelected(e.target.checked ? [...selected, t.testCaseId] : selected.filter((x) => x !== t.testCaseId))
                      }
                    />
                  </td>
                  <td>
                    <Link to={`/tests/${t.testCaseId}`}>{t.title}</Link> {t.aiGenerated && <AiBadge />}
                  </td>
                  <td className="small">{t.requirementIds.map((r) => reqTitleById.get(r) ?? r).join(", ") || "—"}</td>
                  <td>{t.testType.toLowerCase()}</td>
                  <td>
                    <Status value={t.status} />
                  </td>
                  <td>v{t.version}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">No test cases yet.</p>
        )}
        {can(role, "run") && (
          <div className="row end">
            <span className="muted small">
              {approved.length} approved · {selected.length} selected
            </span>
            <button onClick={run} disabled={selected.length === 0 || busy === "run"}>
              ▶ Run selected in sandbox
            </button>
          </div>
        )}
      </Section>

      {/* ---------------- UC-3 runs ---------------- */}
      <Section title="Recent runs" actions={<button className="link" onClick={runs.reload}>Refresh</button>}>
        {runs.data?.items.length ? (
          <table>
            <thead>
              <tr>
                <th>Run</th>
                <th>Status</th>
                <th>Tests</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {runs.data.items.map((r) => (
                <tr key={r.executionId}>
                  <td>
                    <Link to={`/executions/${r.executionId}`}>{r.executionId.slice(0, 8)}</Link>
                  </td>
                  <td>
                    <Status value={r.status} /> {r.terminationReason && r.terminationReason !== "COMPLETED" && <span className="muted small">{r.terminationReason}</span>}
                  </td>
                  <td>{r.tests.length}</td>
                  <td>{fmtTime(r.createdAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">No runs yet.</p>
        )}
      </Section>

      {/* ---------------- UC-4 quality ---------------- */}
      <Section
        title="Quality overview"
        actions={
          can(role, "report") && (
            <button onClick={makeReport} disabled={busy === "report"}>
              Generate quality report
            </button>
          )
        }
      >
        <div className="grid2">
          <div>
            <h3>Coverage</h3>
            <table>
              <tbody>
                {coverage.data?.requirements.map((c) => (
                  <tr key={c.requirementId}>
                    <td>{c.title}</td>
                    <td>{c.approvedTestCount} approved</td>
                    <td>{c.lastResult ? <Status value={c.lastResult} /> : <span className="muted">not run</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div>
            <h3>Risks (rule-based)</h3>
            {risks.data?.risks.length ? (
              <ul className="risks">
                {risks.data.risks.map((r) => (
                  <li key={r.rule + r.refId} className={`sev-${r.severity.toLowerCase()}`}>
                    <strong>{r.severity}</strong> {r.message}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">No open risks found.</p>
            )}
          </div>
        </div>
        {report && (
          <div className="report">
            <h3>Quality report #{report.reportId}</h3>
            <dl>
              {Object.entries(report.summary.totals).map(([k, v]) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
            </dl>
            <p className="muted small">{report.summary.disclaimer}</p>
          </div>
        )}
      </Section>
    </>
  );
}
