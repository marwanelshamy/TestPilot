// Thin typed client for contract I1. Every call goes to /api on the same origin (Nginx / Vite proxy).
import type {
  CoverageItem,
  Evidence,
  Execution,
  Explanation,
  Page,
  Project,
  QualityReport,
  Requirement,
  Risk,
  TestCase,
  TestType,
  User,
} from "./types";

/** The uniform error body of M2 §4.5, as a JS error. */
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
    public correlationId?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** User-facing text for an error code (tactic T26: clear feedback). */
export function friendlyError(e: unknown): string {
  if (!(e instanceof ApiError)) return "Network error — is the backend running?";
  switch (e.code) {
    case "AI_UNAVAILABLE":
      return "AI assistance is temporarily unavailable. Your project and results are safe — you can still add tests manually.";
    case "TEST_NOT_APPROVED":
      return `Only approved tests can run. Not approved in their current version: ${(e.details.testCaseIds as number[] | undefined)?.join(", ") ?? "?"}.`;
    case "VERSION_CONFLICT":
      return "This test was edited after you opened it. Reload it and review the new version before approving.";
    case "QUEUE_UNAVAILABLE":
      return "The execution queue is unavailable. Please try again shortly.";
    case "FORBIDDEN":
      return `Not allowed: ${e.message}`;
    case "VALIDATION_ERROR": {
      const fields = (e.details.fields as { field: string; error: string }[] | undefined) ?? [];
      return fields.length ? fields.map((f) => `${f.field}: ${f.error}`).join("; ") : e.message;
    }
    default:
      return e.message + (e.correlationId ? ` (ref ${e.correlationId})` : "");
  }
}

type TokenProvider = () => string | null;
type UnauthorizedHandler = () => void;

export class Api {
  constructor(
    private token: TokenProvider,
    private onUnauthorized: UnauthorizedHandler = () => {},
    private base = "/api",
  ) {}

  async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const t = this.token();
    if (t) headers.Authorization = `Bearer ${t}`;
    const res = await fetch(this.base + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await res.text();
    const data = text ? JSON.parse(text) : undefined;
    if (!res.ok) {
      const err = data?.error ?? {};
      if (res.status === 401 && path !== "/auth/login") this.onUnauthorized();
      throw new ApiError(res.status, err.code ?? `HTTP_${res.status}`, err.message ?? res.statusText, err.details ?? {}, err.correlationId);
    }
    return data as T;
  }

  // auth
  login = (email: string, password: string) =>
    this.request<{ token: string; user: User }>("POST", "/auth/login", { email, password });
  me = () => this.request<User>("GET", "/me");

  // UC-1
  listProjects = () => this.request<Page<Project>>("GET", "/projects?size=100");
  createProject = (name: string, description?: string) =>
    this.request<{ id: number }>("POST", "/projects", { name, description: description || undefined });
  getProject = (id: number) => this.request<Project>("GET", `/projects/${id}`);
  listRequirements = (projectId: number) =>
    this.request<Page<Requirement>>("GET", `/projects/${projectId}/requirements?size=100`);
  addRequirement = (projectId: number, title: string, description: string) =>
    this.request<{ id: number }>("POST", `/projects/${projectId}/requirements`, { title, description });

  // UC-2
  generateTests = (projectId: number, requirementId: number, testTypes: TestType[], codeUnderTest?: string) =>
    this.request<{ testIds: number[] }>("POST", `/projects/${projectId}/tests/generate`, {
      requirementId,
      testTypes,
      codeUnderTest: codeUnderTest || undefined,
    });
  createTest = (projectId: number, t: { title: string; testType: TestType; testCode: string; requirementIds: number[]; description?: string }) =>
    this.request<{ id: number }>("POST", `/projects/${projectId}/tests`, t);
  listTests = (projectId: number) => this.request<Page<TestCase>>("GET", `/projects/${projectId}/tests?size=100`);
  getTest = (id: number) => this.request<TestCase>("GET", `/tests/${id}`);
  updateTest = (id: number, changes: Partial<Pick<TestCase, "title" | "description" | "testType" | "testCode">>) =>
    this.request<{ version: number }>("PUT", `/tests/${id}`, changes);
  approveTest = (id: number, version: number, comment?: string) =>
    this.request<TestCase>("POST", `/tests/${id}/approve`, { version, comment: comment || undefined });
  rejectTest = (id: number, version: number, comment?: string) =>
    this.request<TestCase>("POST", `/tests/${id}/reject`, { version, comment: comment || undefined });
  flagTest = (id: number, comment: string) => this.request<{ id: number }>("POST", `/tests/${id}/flags`, { comment });

  // UC-3
  startExecution = (projectId: number, testCaseIds: number[]) =>
    this.request<{ executionId: string; status: string }>("POST", "/executions", { projectId, testCaseIds });
  getExecution = (id: string) => this.request<Execution>("GET", `/executions/${id}`);
  listExecutions = (projectId: number) =>
    this.request<Page<Execution>>("GET", `/projects/${projectId}/executions?size=20`);
  executionLogs = (id: string) => this.request<Page<Evidence>>("GET", `/executions/${id}/logs?size=50`);
  explainFailure = (executionId: string, executionTestId: number) =>
    this.request<Explanation>("POST", `/executions/${executionId}/tests/${executionTestId}/explanation`);

  // UC-4
  coverage = (projectId: number) =>
    this.request<{ requirements: CoverageItem[] }>("GET", `/projects/${projectId}/coverage`);
  risks = (projectId: number) => this.request<{ risks: Risk[] }>("GET", `/projects/${projectId}/risks`);
  createReport = (projectId: number) => this.request<{ id: number }>("POST", `/projects/${projectId}/reports`);
  getReport = (id: number) => this.request<QualityReport>("GET", `/reports/${id}`);
}
