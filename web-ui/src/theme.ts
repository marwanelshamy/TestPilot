// Light / dark theme. Stored per browser; defaults to the operating-system preference.
export type Theme = "light" | "dark";
const KEY = "testpilot.theme";

export function currentTheme(): Theme {
  const saved = localStorage.getItem(KEY);
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(theme: Theme = currentTheme()): void {
  document.documentElement.dataset.theme = theme;
}

export function toggleTheme(): Theme {
  const next: Theme = currentTheme() === "dark" ? "light" : "dark";
  localStorage.setItem(KEY, next);
  applyTheme(next);
  return next;
}

/** Other parts of the app announce that the project list changed (e.g. after creating one). */
export const PROJECTS_CHANGED = "testpilot:projects-changed";
export const announceProjectsChanged = () => window.dispatchEvent(new Event(PROJECTS_CHANGED));
