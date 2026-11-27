# ADR-015: LLM provider: offline mock by default, Claude adapter, code sent only on opt-in

| Field | Content |
|---|---|
| ADR number & title | ADR-015: LLM provider: offline mock by default, Claude adapter, code sent only on opt-in |
| Status | Accepted (closes OI-003 for the prototype; the production provider stays a team decision) |
| Date & deciders | 27 November 2026 - Member 3 (AI Assistance Service) |
| Context | OI-003 (which LLM provider) was open. The prototype must run with no budget (C-08) and without sending private code to a third party unless approved (C-07); demos and tests must be repeatable. |
| Alternatives considered | 1. One hosted LLM only: realistic suggestions, but every demo and test costs money and needs a key and internet.<br>2. Offline deterministic mock as the default + one real adapter (Anthropic Claude, `claude-opus-5-5`, structured JSON output, server-side refusal fallback) behind the P8 interface (chosen).<br>3. Self-hosted open model: no data leaves the machine, but too heavy for the team's laptops. |
| Decision | `LLM_PROVIDER=mock|anthropic`; prompts and JSON schemas shared by all adapters (`prompts.py`); pasted code reaches an external provider only with `LLM_SEND_CODE=true`; the redaction pipeline always runs first. |
| Rationale | Keeps the system free, offline-capable and privacy-preserving by default while proving ASR-5 (replaceable provider) with a real adapter. |
| Consequences | + Demos, tests and QAS experiments are reproducible. + The QAS-4 exercise (add a second adapter) is ready. - The mock's suggestions are simple; realistic quality needs the real provider and a key in `.env`. - The real adapter is tested with a fake SDK client only. |
