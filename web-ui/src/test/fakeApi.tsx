import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import type { Role } from "../api/types";
import { AuthProvider } from "../auth";

type Handler = (body: unknown) => { status?: number; body?: unknown };

/** Fake backend: routes are "METHOD /path" (query string ignored). Records every call. */
export function fakeBackend(routes: Record<string, Handler | Handler[]>) {
  const calls: { method: string; path: string; body: unknown; auth: string | null }[] = [];
  const counters: Record<string, number> = {};
  const fetchMock = vi.fn(async (url: string, init: RequestInit = {}) => {
    const method = (init.method ?? "GET").toUpperCase();
    const path = url.replace(/^\/api/, "").split("?")[0];
    const body = init.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ method, path, body, auth: (init.headers as Record<string, string>)?.Authorization ?? null });
    const key = `${method} ${path}`;
    const h = routes[key];
    if (!h) return new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: key } }), { status: 404 });
    const list = Array.isArray(h) ? h : [h];
    const i = Math.min(counters[key] ?? 0, list.length - 1);
    counters[key] = (counters[key] ?? 0) + 1;
    const r = list[i](body);
    return new Response(r.body === undefined ? "" : JSON.stringify(r.body), { status: r.status ?? 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

export function signIn(role: Role = "DEVELOPER") {
  sessionStorage.setItem(
    "testpilot.session",
    JSON.stringify({ token: "tok", user: { userId: 1, name: "Test User", email: "t@x", role } }),
  );
}

export function renderAt(path: string, pattern: string, element: ReactElement) {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={pattern} element={element} />
          <Route path="*" element={<div>other page</div>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
}

export const err = (status: number, code: string, message = code, details = {}) => ({
  status,
  body: { error: { code, message, details, correlationId: "c-1" } },
});
