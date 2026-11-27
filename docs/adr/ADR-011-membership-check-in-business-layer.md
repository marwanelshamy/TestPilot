# ADR-011: Project-membership check moves from the Auth & Access Filter to the business layer

| Field | Content |
|---|---|
| ADR number & title | ADR-011: Project-membership check moves from the Auth & Access Filter to the business layer |
| Status | Accepted |
| Date & deciders | 27 November 2026 - Member 1 (Core Backend) |
| Context | M2 §4.2 says the Auth & Access Filter checks token, role and project membership. Membership depends on data (which project a test or execution belongs to), so checking it in the API layer would make the filter call repositories, breaking the closed-layer rule (P1, T23). |
| Alternatives considered | 1. Filter checks membership through a repository: matches the M2 text but the API layer would depend on the data layer (a layer violation that import-linter reports).<br>2. Filter checks token + role; every service checks membership through `require_member()` (chosen): layers stay closed and the check sits where the data is loaded anyway. |
| Decision | `app/api/deps/auth.py` checks the JWT and the role matrix; `app/services/_access.require_member()` checks project membership in every service operation. |
| Rationale | Keeps the layered structure that the conformance checks enforce, without weakening authorization (T9). |
| Consequences | + Import contracts stay green; one membership rule used by all services. - Authorization is split across two places; documented in `docs/phase1/03` §3 and covered by 403 tests per role and for non-members. |
