import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import type { QualityReport, TestType } from "../api/types";
import { useAuth } from "../auth";
import { ArrowUp, Chart, Check, Chevron, Doc, Flask, ListIcon, Pencil, Play, Plus, Refresh, Sparkles, Terminal, X } from "../components/icons";
import { AiBadge, Empty, ErrorBanner, Notice, Section, Status, Thinking, timeAgo, useLoad } from "../components/ui";
import { can } from "../permissions";

const TYPES: TestType[] = ["NORMAL", "BOUNDARY", "NEGATIVE"];
type Tab = "workspace" | "runs" | "quality";

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

  const [tab, setTab] = useState<Tab>("workspace");
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const [reqOpen, setReqOpen] = useState(false);
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
      setReqOpen(false);
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

  const items = tests.data?.items ?? [];
  const approved = items.filter((t) => t.status === "APPROVED");
  const reqTitleById = new Map(reqs.data?.items.map((r) => [r.requirementId, r.title]));
  const toggle = (id: number, on: boolean) => setSelected(on ? [...selected, id] : selected.filter((x) => x !== id));
  const canEdit = can(role, "editTests");

  return (
    <>
      <div className="crumbs">
        <Link to="/projects">Projects</Link> <Chevron size={14} /> <span>{project.data?.name ?? "…"}</span>
      </div>
      <div className="page-head">
        <div>
          <h1 className="page-title">{project.data?.name ?? "…"}</h1>
          {project.data && (
            <div className="page-sub">
              <span className="pill">{project.data.programmingLanguage} · {project.data.testFramework}</span>
              {project.data.description && <span>{project.data.description}</span>}
            </div>
          )}
        </div>
        <div className="tabs" role="tablist" aria-label="Project sections">
          {(["workspace", "runs", "quality"] as Tab[]).map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>
              {t === "workspace" ? "Workspace" : t === "runs" ? `Runs${runs.data ? ` · ${runs.data.total}` : ""}` : "Quality"}
            </button>
          ))}
        </div>
      </div>

      <ErrorBanner error={project.error} />
      <ErrorBanner error={error} />
      {notice && <Notice kind="ok">{notice}</Notice>}

      {/* ====================================================== WORKSPACE */}
      {tab === "workspace" && (
        <>
          <Section
            title="Requirements"
            icon={<Doc size={16} />}
            count={reqs.data?.total}
            actions={
              can(role, "addRequirement") && (
                <button className="secondary sm" onClick={() => setReqOpen((o) => !o)}>
                  <Plus size={15} /> Add requirement
                </button>
              )
            }
          >
            {reqOpen && (
              <form className="stack" onSubmit={addRequirement} style={{ marginBottom: ".9rem" }}>
                <input placeholder="Requirement title" value={reqTitle} onChange={(e) => setReqTitle(e.target.value)} required maxLength={200} aria-label="Requirement title" />
                <textarea placeholder="Describe the expected behaviour" value={reqText} onChange={(e) => setReqText(e.target.value)} required rows={3} aria-label="Requirement description" />
                <div className="row">
                  <button type="submit" className="primary sm" disabled={busy === "req"}>Add requirement</button>
                  <button type="button" className="ghost sm" onClick={() => setReqOpen(false)}>Cancel</button>
                </div>
              </form>
            )}
            {reqs.data?.items.length ? (
              <div className="req-list">
                {reqs.data.items.map((r, i) => (
                  <div className="req" key={r.requirementId}>
                    <span className="num">{i + 1}</span>
                    <div>
                      <b>{r.title}</b>
                      <div className="muted">{r.description}</div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <Empty icon={<Doc />} title="No requirements yet">Describe what the software must do — the AI turns it into tests.</Empty>
            )}
          </Section>

          <Section
            title="Test cases"
            icon={<Flask size={16} />}
            count={tests.data?.total}
            actions={<span className="small faint">{approved.length} approved · {selected.length} selected</span>}
          >
            {manualOpen && (
              <form className="stack" onSubmit={addManual} style={{ marginBottom: "1rem" }}>
                <div className="row">
                  <input className="grow" placeholder="Title" value={manual.title} onChange={(e) => setManual({ ...manual, title: e.target.value })} required aria-label="Manual test title" />
                  <select value={manual.testType} onChange={(e) => setManual({ ...manual, testType: e.target.value as TestType })} aria-label="Test type">
                    {TYPES.map((t) => (
                      <option key={t}>{t}</option>
                    ))}
                  </select>
                </div>
                <div className="editor">
                  <div className="editor-bar"><span className="lights"><i /><i /><i /></span>new_test.py</div>
                  <textarea className="code" rows={8} value={manual.testCode} onChange={(e) => setManual({ ...manual, testCode: e.target.value })} required aria-label="Manual test code" />
                </div>
                <div className="row">
                  <button type="submit" className="primary sm" disabled={busy === "manual"}>Save as draft</button>
                  <button type="button" className="ghost sm" onClick={() => setManualOpen(false)}>Cancel</button>
                </div>
              </form>
            )}
            {items.length ? (
              <div className="tests">
                {items.map((t) => {
                  const isSel = selected.includes(t.testCaseId);
                  return (
                    <div key={t.testCaseId} className={`test-row ${isSel ? "selected" : ""}`}>
                      <label className="check" title={t.status === "APPROVED" ? "Select to run" : "Only approved tests can run"}>
                        <input
                          type="checkbox"
                          aria-label={`select test ${t.testCaseId}`}
                          disabled={t.status !== "APPROVED"}
                          checked={isSel}
                          onChange={(e) => toggle(t.testCaseId, e.target.checked)}
                        />
                        <Check size={16} />
                      </label>
                      <div style={{ minWidth: 0 }}>
                        <div className="t-title">
                          <Link to={`/tests/${t.testCaseId}`}>{t.title}</Link> {t.aiGenerated && <AiBadge />}
                        </div>
                        <div className="t-meta">
                          <span>{t.testType.toLowerCase()}</span>
                          <span>v{t.version}</span>
                          <span>{t.requirementIds.map((r) => reqTitleById.get(r) ?? r).join(", ") || "no requirement"}</span>
                        </div>
                      </div>
                      <div className="t-right">
                        <Status value={t.status} />
                        <Link to={`/tests/${t.testCaseId}`} className="faint" aria-label={`Open test ${t.testCaseId}`}><Chevron /></Link>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <Empty icon={<Sparkles />} title="No test cases yet">
                {canEdit ? "Pick a requirement in the composer below and let the AI suggest tests." : "Developers and QA Assistants can add tests."}
              </Empty>
            )}
          </Section>
        </>
      )}

      {/* ====================================================== RUNS */}
      {tab === "runs" && (
        <Section title="Recent runs" icon={<Terminal size={16} />} actions={<button className="ghost sm" onClick={runs.reload}><Refresh size={15} /> Refresh</button>}>
          {runs.data?.items.length ? (
            <table>
              <thead>
                <tr><th>Run</th><th>Status</th><th>Tests</th><th>Started</th></tr>
              </thead>
              <tbody>
                {runs.data.items.map((r) => (
                  <tr key={r.executionId}>
                    <td><Link to={`/executions/${r.executionId}`} className="mono">{r.executionId.slice(0, 8)}</Link></td>
                    <td>
                      <Status value={r.status} />{" "}
                      {r.terminationReason && r.terminationReason !== "COMPLETED" && <span className="small faint">{r.terminationReason}</span>}
                    </td>
                    <td>{r.tests.length}</td>
                    <td className="faint">{timeAgo(r.createdAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty icon={<Play />} title="No runs yet">Approve tests, select them in the Workspace and run them in the sandbox.</Empty>
          )}
        </Section>
      )}

      {/* ====================================================== QUALITY */}
      {tab === "quality" && (
        <>
          <div className="grid2">
            <Section title="Coverage" icon={<ListIcon size={16} />}>
              {coverage.data?.requirements.length ? (
                <div className="stack">
                  {coverage.data.requirements.map((c) => (
                    <div key={c.requirementId}>
                      <div className="row between small">
                        <b>{c.title}</b>
                        {c.lastResult ? <Status value={c.lastResult} /> : <span className="faint">not run</span>}
                      </div>
                      <div className="row between small faint" style={{ margin: ".2rem 0 .3rem" }}>
                        <span>{c.approvedTestCount} approved test{c.approvedTestCount === 1 ? "" : "s"}</span>
                      </div>
                      <div className="meter"><i style={{ width: `${Math.min(100, c.approvedTestCount * 34)}%` }} /></div>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty icon={<Doc />} title="No requirements yet" />
              )}
            </Section>
            <Section title="Risks (rule-based)" icon={<Chart size={16} />}>
              {risks.data?.risks.length ? (
                risks.data.risks.map((r) => (
                  <div key={r.rule + r.refId} className={`risk sev-${r.severity.toLowerCase()}`}>
                    <span className="sev">{r.severity}</span>
                    <span>{r.message}</span>
                  </div>
                ))
              ) : (
                <Empty icon={<Check />} title="No open risks found" />
              )}
            </Section>
          </div>
          <Section
            title="Quality report"
            icon={<Doc size={16} />}
            actions={
              can(role, "report") && (
                <button className="primary sm" onClick={makeReport} disabled={busy === "report"}>
                  Generate quality report
                </button>
              )
            }
          >
            {report ? (
              <>
                <div className="kpis">
                  {Object.entries(report.summary.totals).map(([k, v]) => (
                    <div className="kpi" key={k}>
                      <div className="k">{k.replace(/([A-Z])/g, " $1").toLowerCase()}</div>
                      <div className="v">{v}</div>
                    </div>
                  ))}
                </div>
                <p className="small faint" style={{ marginBottom: 0 }}>{report.summary.disclaimer}</p>
              </>
            ) : (
              <p className="muted small" style={{ margin: 0 }}>
                {can(role, "report") ? "Generate a snapshot of results, coverage and risks for the release review." : "The Team Lead generates quality reports."}
              </p>
            )}
          </Section>
        </>
      )}

      {/* ====================================================== DOCK: run bar + AI composer */}
      <div className="composer-dock">
        <div className="composer-inner">
          {can(role, "run") && selected.length > 0 && tab === "workspace" && (
            <div className="runbar">
              <span>
                <b>{selected.length}</b> <span className="muted">approved test{selected.length === 1 ? "" : "s"} selected</span>
              </span>
              <div className="row">
                <button className="ghost sm" style={{ color: "var(--rail-muted)" }} onClick={() => setSelected([])} aria-label="Clear selection"><X size={15} /></button>
                <button className="primary" onClick={run} disabled={busy === "run"}>
                  <Play size={14} /> Run selected in sandbox
                </button>
              </div>
            </div>
          )}
          {canEdit && tab === "workspace" && (
            <form className="composer" onSubmit={generate}>
              <div className="composer-body">
                <textarea
                  className="code"
                  placeholder="Paste the code under test (optional) — the AI writes self-contained pytest tests for the requirement you pick…"
                  value={genCode}
                  onChange={(e) => setGenCode(e.target.value)}
                  rows={genCode ? 5 : 1}
                  aria-label="Code under test"
                />
                <div className="composer-bar">
                  <select value={genReq} onChange={(e) => setGenReq(e.target.value === "" ? "" : Number(e.target.value))} required aria-label="Requirement">
                    <option value="">Choose a requirement…</option>
                    {reqs.data?.items.map((r) => (
                      <option key={r.requirementId} value={r.requirementId}>{r.title}</option>
                    ))}
                  </select>
                  {TYPES.map((t) => (
                    <label key={t} className={`type-chip ${genTypes.includes(t) ? "on" : ""}`}>
                      <input
                        type="checkbox"
                        aria-label={`${t.toLowerCase()} tests`}
                        checked={genTypes.includes(t)}
                        onChange={(e) => setGenTypes(e.target.checked ? [...genTypes, t] : genTypes.filter((x) => x !== t))}
                      />
                      {genTypes.includes(t) && <Check size={13} />} {t.toLowerCase()}
                    </label>
                  ))}
                  <span className="spacer" />
                  <button type="button" className="ghost sm" onClick={() => setManualOpen((o) => !o)}>
                    <Pencil size={15} /> Add manually
                  </button>
                  {busy === "gen" ? (
                    <span className="pill" style={{ background: "var(--aurora-soft)", color: "var(--accent-ink)" }}>
                      Asking the AI <Thinking />
                    </span>
                  ) : null}
                  <button type="submit" className="send" disabled={busy === "gen" || genTypes.length === 0} aria-label="✦ Generate tests with AI" title="Generate tests with AI">
                    <ArrowUp />
                  </button>
                </div>
              </div>
            </form>
          )}
          {canEdit && tab === "workspace" && (
            <div className="composer-hint">AI suggestions are stored as drafts — a human approves every test before it runs.</div>
          )}
        </div>
      </div>
    </>
  );
}
