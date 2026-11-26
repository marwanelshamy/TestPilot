## What changed

## Requirement / design link
- FR / UC: <!-- e.g. FR-06, UC-3 -->
- QAS / ASR / ADR: <!-- e.g. QAS-7, ASR-3, ADR-006 -->

## Contract impact
- [ ] No change to `docs/contracts/*` or `db/schema.sql`
- [ ] Contract changed — provider and consumer owners both approved

## How it was tested
- [ ] Unit tests
- [ ] Integration test
- [ ] Ran `docker compose up --build` and tried the flow manually

## Architecture checks
- [ ] `lint-imports` passes (core-backend layer rules)
- [ ] No new link that M2 forbids (runner/sandbox/AI → DB, sandbox → network, UI → AI/broker)
