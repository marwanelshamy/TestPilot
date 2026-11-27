import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectPage } from "../pages/ProjectPage";
import { applyTheme, currentTheme, toggleTheme } from "../theme";
import { fakeBackend, renderAt, signIn } from "./fakeApi";

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
});
afterEach(() => vi.unstubAllGlobals());

describe("theme", () => {
  it("toggles between light and dark and remembers the choice", () => {
    applyTheme("light");
    const first = currentTheme();
    const next = toggleTheme();
    expect(next).not.toBe(first);
    expect(document.documentElement.dataset.theme).toBe(next);
    expect(currentTheme()).toBe(next);
  });
});

describe("workspace run bar", () => {
  it("appears only once an approved test is selected", async () => {
    signIn("DEVELOPER");
    const t = { testCaseId: 6, projectId: 1, title: "approved", description: null, testType: "NORMAL", source: "MANUAL",
      testCode: "def test_a():\n    pass\n", status: "APPROVED", version: 1, requirementIds: [], approvedVersion: 1,
      aiGenerated: false, updatedAt: "2026-11-27T10:00:00Z" };
    const page = (items: unknown[]) => ({ body: { items, page: 1, size: 100, total: items.length } });
    fakeBackend({
      "GET /projects/1": () => ({ body: { projectId: 1, name: "Calc", description: null, programmingLanguage: "Python", testFramework: "pytest" } }),
      "GET /projects/1/requirements": () => page([]),
      "GET /projects/1/tests": () => page([t]),
      "GET /projects/1/executions": () => page([]),
      "GET /projects/1/coverage": () => ({ body: { requirements: [] } }),
      "GET /projects/1/risks": () => ({ body: { risks: [] } }),
    });
    renderAt("/projects/1", "/projects/:id", <ProjectPage />);
    await screen.findByLabelText("select test 6");
    expect(screen.queryByRole("button", { name: /Run selected/ })).toBeNull();
    await userEvent.click(screen.getByLabelText("select test 6"));
    expect(screen.getByRole("button", { name: /Run selected/ })).toBeEnabled();
  });
});
