import { afterEach, describe, expect, it, vi } from "vitest";
import { Api, ApiError, friendlyError } from "../api/client";
import { can } from "../permissions";
import { err, fakeBackend } from "./fakeApi";

afterEach(() => vi.unstubAllGlobals());

describe("Api client (contract I1)", () => {
  it("sends the bearer token and parses JSON", async () => {
    const { calls } = fakeBackend({ "GET /me": () => ({ body: { userId: 1, role: "DEVELOPER" } }) });
    const me = await new Api(() => "abc").me();
    expect(me.userId).toBe(1);
    expect(calls[0].auth).toBe("Bearer abc");
  });

  it("turns the uniform error body into ApiError", async () => {
    fakeBackend({ "POST /executions": () => err(409, "TEST_NOT_APPROVED", "nope", { testCaseIds: [7] }) });
    const e = await new Api(() => "t").startExecution(1, [7]).catch((x) => x);
    expect(e).toBeInstanceOf(ApiError);
    expect([e.status, e.code, e.correlationId]).toEqual([409, "TEST_NOT_APPROVED", "c-1"]);
    expect(friendlyError(e)).toContain("Only approved tests can run");
    expect(friendlyError(e)).toContain("7");
  });

  it("calls onUnauthorized on 401 (expired session) but not on a failed login", async () => {
    fakeBackend({ "GET /projects": () => err(401, "TOKEN_EXPIRED"), "POST /auth/login": () => err(401, "INVALID_CREDENTIALS") });
    const onUnauth = vi.fn();
    const api = new Api(() => "t", onUnauth);
    await api.listProjects().catch(() => {});
    await api.login("a@b", "x").catch(() => {});
    expect(onUnauth).toHaveBeenCalledTimes(1);
  });

  it("explains AI outages and network errors in plain words (T26)", () => {
    expect(friendlyError(new ApiError(503, "AI_UNAVAILABLE", "x"))).toMatch(/add tests manually/);
    expect(friendlyError(new TypeError("fetch failed"))).toMatch(/Network error/);
  });
});

describe("role matrix mirror (docs/phase1/03 §3)", () => {
  it("QA Assistant is advisory: can edit, flag and run but not approve", () => {
    expect(["editTests", "flag", "run"].every((a) => can("QA_ASSISTANT", a as never))).toBe(true);
    expect(can("QA_ASSISTANT", "approve")).toBe(false);
  });
  it("only the Team Lead generates reports; admin does nothing in the prototype", () => {
    expect(can("TEAM_LEAD", "report")).toBe(true);
    expect(can("DEVELOPER", "report")).toBe(false);
    expect(can("ADMIN", "run")).toBe(false);
    expect(can(undefined, "run")).toBe(false);
  });
});
