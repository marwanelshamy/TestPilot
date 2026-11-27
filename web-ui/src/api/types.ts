// Types of the public REST API (contract I1: docs/contracts/public-api.openapi.yaml).

export type Role = "DEVELOPER" | "QA_ASSISTANT" | "TEAM_LEAD" | "ADMIN";
export type TestType = "NORMAL" | "BOUNDARY" | "NEGATIVE";
export type TestCaseStatus = "DRAFT" | "APPROVED" | "REJECTED";
export type ExecutionStatus = "QUEUED" | "RUNNING" | "PASSED" | "FAILED" | "INTERRUPTED" | "CANCELLED";
export type TestResultStatus = "PASSED" | "FAILED" | "ERROR" | "SKIPPED" | "NOT_RUN";

export const TERMINAL: ExecutionStatus[] = ["PASSED", "FAILED", "INTERRUPTED", "CANCELLED"];

export interface Page<T> {
  items: T[];
  page: number;
  size: number;
  total: number;
}

export interface User {
  userId: number;
  name: string;
  email: string;
  role: Role;
}

export interface Project {
  projectId: number;
  name: string;
  description: string | null;
  programmingLanguage: string;
  testFramework: string;
  createdBy: number;
  createdAt: string;
}

export interface Requirement {
  requirementId: number;
  projectId: number;
  title: string;
  description: string;
  createdAt: string;
}

export interface TestCase {
  testCaseId: number;
  projectId: number;
  title: string;
  description: string | null;
  testType: TestType;
  source: "AI_GENERATED" | "MANUAL";
  testCode: string;
  status: TestCaseStatus;
  version: number;
  requirementIds: number[];
  approvedVersion: number | null;
  aiGenerated: boolean;
  updatedAt: string;
}

export interface ExecutionTest {
  executionTestId: number;
  testCaseId: number;
  testCaseVersion: number;
  resultStatus: TestResultStatus;
  durationMs: number | null;
  failureMessage: string | null;
}

export interface Execution {
  executionId: string;
  projectId: number;
  status: ExecutionStatus;
  terminationReason: string | null;
  tests: ExecutionTest[];
  requestedBy: number;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface Evidence {
  evidenceId: number;
  evidenceType: "STDOUT" | "STDERR" | "JUNIT_XML" | "RUNNER_LOG";
  content: string;
  sizeBytes: number;
  truncated: boolean;
}

export interface Explanation {
  explanationId: number;
  explanationText: string;
  aiGenerated: true;
  label: string;
  providerModel: string;
  createdAt: string;
}

export interface CoverageItem {
  requirementId: number;
  title: string;
  approvedTestCount: number;
  lastResult: string | null;
}

export interface Risk {
  rule: string;
  severity: "HIGH" | "MEDIUM" | "LOW";
  refId: string;
  message: string;
}

export interface QualityReport {
  reportId: number;
  projectId: number;
  createdAt: string;
  summary: {
    totals: Record<string, number>;
    coverage: CoverageItem[];
    risks: Risk[];
    disclaimer?: string;
  };
}
