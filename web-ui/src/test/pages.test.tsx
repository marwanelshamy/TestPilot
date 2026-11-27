import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ExecutionPage } from "../pages/ExecutionPage";
import { ProjectPage } from "../pages/ProjectPage";
import { TestPage } from "../pages/TestPage";
import { err, fakeBackend, renderAt, signIn } from "./fakeApi";

const page = <T,>(items: T[]) => ({ body: { items, page: 1, size: 100, total: items.length } });

const TEST = {
  testCaseId: 5,
  projectId: 1,
  title: "adds two numbers",
  description: null,
  testType: "NORMAL",
  source: "AI_GENERATED",
  testCode: "def test_add():\n    assert add(1, 2) == 3\n",
  status: "DRAFT",
  version: 2,
  requirementIds: [10],
  approvedVersion: null,
  aiGenerated: true,
  updatedAt: "2026-11-27T10:00:00Z",
};

const run = (status: string, results: string[] = []) => ({
  body: {
    executionId: "ex-123456789",
    projectId: 1,
    status,
    terminationReason: ["PASSED", "FAILED"].includes(status) ? "COMPLETED" : null,
    requestedBy: 1,
    createdAt: "2026-11-27T10:00:00Z",
    startedAt: null,
    finishedAt: null,
    tests: results.map((r, i) => ({
      executionTestId: 100 + i,
      testCaseId: 5 + i,
      testCaseVersion: 1,
      resultStatus: r,
      durationMs: 12,
      failureMessage: r === "FAILED" ? "assert 3 == 4" : null,
    })),
  },
});

beforeEach(() => sessionStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("TestPage (UC-2 review)", () => {
  it("labels AI output and approves exactly the version on screen (ADR-005)", async () => {
    signIn("TEAM_LEAD");
    const { calls } = fakeBackend({
      "GET /tests/5": [() => ({ body: TEST }), () => ({ body: { ...TEST, status: "APPROVED", approvedVersion: 2 } })],
      "POST /tests/5/approve": () => ({ body: { ...TEST, status: "APPROVED" } }),
    });
    renderAt("/tests/5", "/tests/:id", <TestPage />);
    expect(await screen.findByText(/AI suggestion/)).toBeInTheDocument();
    expect(screen.getByText(/written by the AI/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Approve v2/ }));
    await screen.findByText("Version 2 approved.");
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ version: 2 });
  });

  it("shows a clear message when the test changed meanwhile (409 VERSION_CONFLICT)", async () => {
    signIn("DEVELOPER");
    fakeBackend({ "GET /tests/5": () => ({ body: TEST }), "POST /tests/5/approve": () => err(409, "VERSION_CONFLICT") });
    renderAt("/tests/5", "/tests/:id", <TestPage />);
    await userEvent.click(await screen.findByRole("button", { name: /Approve v2/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/edited after you opened it/);
  });

  it("hides approve from the QA Assistant (role matrix)", async () => {
    signIn("QA_ASSISTANT");
    fakeBackend({ "GET /tests/5": () => ({ body: TEST }) });
    renderAt("/tests/5", "/tests/:id", <TestPage />);
    await screen.findByText("adds two numbers");
    expect(screen.queryByRole("button", { name: /Approve/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
  });
});

describe("ProjectPage (UC-1..UC-4)", () => {
  function projectBackend(extra: Record<string, unknown> = {}) {
    return fakeBackend({
      "GET /projects/1": () => ({ body: { projectId: 1, name: "Calc", description: null, programmingLanguage: "Python", testFramework: "pytest" } }),
      "GET /projects/1/requirements": () => page([{ requirementId: 10, projectId: 1, title: "add works", description: "d" }]),
      "GET /projects/1/tests": () =>
        page([TEST, { ...TEST, testCaseId: 6, title: "approved one", status: "APPROVED", approvedVersion: 2, aiGenerated: false }]),
      "GET /projects/1/executions": () => page([]),
      "GET /projects/1/coverage": () => ({ body: { requirements: [] } }),
      "GET /projects/1/risks": () => ({ body: { risks: [] } }),
      ...(extra as Record<string, never>),
    });
  }

  it("only approved tests can be selected to run", async () => {
    signIn("DEVELOPER");
    projectBackend();
    renderAt("/projects/1", "/projects/:id", <ProjectPage />);
    expect(await screen.findByLabelText("select test 5")).toBeDisabled();
    expect(screen.getByLabelText("select test 6")).toBeEnabled();
  });

  it("keeps working and explains when the AI is down (QAS-2)", async () => {
    signIn("DEVELOPER");
    projectBackend({ "POST /projects/1/tests/generate": () => err(503, "AI_UNAVAILABLE") });
    renderAt("/projects/1", "/projects/:id", <ProjectPage />);
    await userEvent.selectOptions(await screen.findByLabelText("Requirement"), "10");
    await userEvent.click(screen.getByRole("button", { name: /Generate tests with AI/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/add tests manually/);
    expect(screen.getByText("approved one")).toBeInTheDocument(); // existing data still shown
  });

  it("starting a run sends the selected approved test and opens the run page", async () => {
    signIn("QA_ASSISTANT");
    const { calls } = projectBackend({ "POST /executions": () => ({ status: 202, body: { executionId: "ex-1", status: "QUEUED" } }) });
    renderAt("/projects/1", "/projects/:id", <ProjectPage />);
    await userEvent.click(await screen.findByLabelText("select test 6"));
    await userEvent.click(screen.getByRole("button", { name: /Run selected/ }));
    await screen.findByText("other page");
    expect(calls.find((c) => c.path === "/executions")?.body).toEqual({ projectId: 1, testCaseIds: [6] });
  });
});

describe("ExecutionPage (UC-3 results)", () => {
  it("polls until terminal, then stops and shows runner results and logs", async () => {
    signIn("DEVELOPER");
    const { fetchMock } = fakeBackend({
      "GET /executions/ex-123456789": [() => run("QUEUED", ["NOT_RUN"]), () => run("RUNNING", ["NOT_RUN"]), () => run("FAILED", ["PASSED", "FAILED"])],
      "GET /executions/ex-123456789/logs": () => page([{ evidenceId: 1, evidenceType: "STDOUT", content: "1 failed", sizeBytes: 8, truncated: false }]),
      "POST /executions/ex-123456789/tests/101/explanation": () => ({
        status: 201,
        body: { explanationId: 1, explanationText: "Off by one.", aiGenerated: true, label: "AI-generated hypothesis — verify against the logs", providerModel: "mock/mock-1", createdAt: "" },
      }),
    });
    renderAt("/executions/ex-123456789", "/executions/:id", <ExecutionPage pollMs={5} />);
    expect(await screen.findByText("1 failed")).toBeInTheDocument();
    expect(screen.getByText("assert 3 == 4")).toBeInTheDocument();
    const callsAtEnd = fetchMock.mock.calls.length;
    await new Promise((r) => setTimeout(r, 60));
    expect(fetchMock.mock.calls.length).toBe(callsAtEnd); // polling stopped

    await userEvent.click(screen.getByRole("button", { name: /Explain with AI/ }));
    expect(await screen.findByText("Off by one.")).toBeInTheDocument();
    expect(screen.getByText(/AI-generated hypothesis/)).toBeInTheDocument();
  });

  it("warns that an interrupted run recorded nothing as passed", async () => {
    signIn("DEVELOPER");
    fakeBackend({
      "GET /executions/ex-123456789": () => ({ body: { ...run("INTERRUPTED", ["NOT_RUN"]).body, terminationReason: "RUNNER_LOST" } }),
      "GET /executions/ex-123456789/logs": () => page([]),
    });
    renderAt("/executions/ex-123456789", "/executions/:id", <ExecutionPage pollMs={5} />);
    expect(await screen.findByText(/No result was recorded as passed/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText(/RUNNER_LOST/).length).toBeGreaterThan(0));
  });
});
