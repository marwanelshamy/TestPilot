// Mirror of the role matrix (docs/phase1/03-contracts-and-data.md §3). The UI only HIDES actions a role
// cannot perform; the Core Backend's Auth & Access Filter is what actually ENFORCES them (tactic T9).
import type { Role } from "./api/types";

export type Action =
  | "createProject"
  | "addRequirement"
  | "editTests"
  | "flag"
  | "approve"
  | "run"
  | "explain"
  | "report";

const MATRIX: Record<Action, Role[]> = {
  createProject: ["DEVELOPER", "TEAM_LEAD"],
  addRequirement: ["DEVELOPER"],
  editTests: ["DEVELOPER", "QA_ASSISTANT"],
  flag: ["DEVELOPER", "QA_ASSISTANT", "TEAM_LEAD"],
  approve: ["DEVELOPER", "TEAM_LEAD"],
  run: ["DEVELOPER", "QA_ASSISTANT", "TEAM_LEAD"],
  explain: ["DEVELOPER", "QA_ASSISTANT"],
  report: ["TEAM_LEAD"],
};

export function can(role: Role | undefined, action: Action): boolean {
  return !!role && MATRIX[action].includes(role);
}

export const ROLE_LABEL: Record<Role, string> = {
  DEVELOPER: "Developer",
  QA_ASSISTANT: "QA Assistant",
  TEAM_LEAD: "Team Lead",
  ADMIN: "Administrator",
};
