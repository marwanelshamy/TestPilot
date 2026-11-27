# QAS-6 — Usability formative test (not an ASR)

**Target:** ≥ 9 of 10 first-time participants finish without help, and ≥ 9 of 10 within 5 minutes
(AI response time excluded). 10 participants is a formative test, not proof of universal usability.

## Setup
- System running with `docker compose up --build`, `LLM_PROVIDER=mock` (identical AI answers for everyone).
- One fresh account per participant is not needed: participant uses `dev@testpilot.local` / demo password,
  and starts on `/projects` with no project of their own (the observer deletes nothing; each participant
  names their project `P<n>`).
- Screen recording optional (ask consent). Observer does not help unless the participant is stuck > 60 s
  (then it counts as "with help").

## Task script (read aloud)
> "You are a developer. Using TestPilot, create a project called P<n>, add the requirement
> *'add(a, b) returns the sum of two integers'*, ask the AI for test suggestions, look at one suggestion,
> and approve it so that it can run. Tell me when you think you are done."

Timer starts at "go", stops when the first suggestion shows **APPROVED**. Subtract the time spent waiting
for "Asking the AI…" (shown by the button text).

## Recording sheet

| # | Role / background | Finished? | Help needed? (when, why) | Time (mm:ss) | AI wait (s) | Net time | Issues observed |
|---|---|---|---|---|---|---|---|
| 1 | | | | | | | |
| 2 | | | | | | | |
| 3 | | | | | | | |
| 4 | | | | | | | |
| 5 | | | | | | | |
| 6 | | | | | | | |
| 7 | | | | | | | |
| 8 | | | | | | | |
| 9 | | | | | | | |
| 10 | | | | | | | |

**Result:** __/10 unaided, __/10 within 5 min → MET / NOT MET. List the usability issues found and what was
changed in the UI because of them.
