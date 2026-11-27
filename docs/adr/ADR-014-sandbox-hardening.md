# ADR-014: Sandbox hardening: read-only root file system with a /work volume, no capabilities, process limit

| Field | Content |
|---|---|
| ADR number & title | ADR-014: Sandbox hardening: read-only root file system with a /work volume, no capabilities, process limit |
| Status | Accepted |
| Date & deciders | 27 November 2026 - Member 2 (Runner Worker + Sandbox) |
| Context | M2 asked for 'no network, non-root, read-only file system except a scratch folder, CPU/memory/time limits' (ADR-003, T7, T8). Docker only allows copying files into a read-only container when the target is a volume, and fork bombs are not stopped by CPU and memory limits alone. |
| Alternatives considered | 1. Writable root file system: easy to copy tests in, but a test can modify the image's files during the run.<br>2. Read-only root FS + anonymous volume `/work` + tmpfs `/tmp` (noexec) + `cap_drop ALL` + `no-new-privileges` + `pids_limit 128` + memory limit without swap (chosen).<br>3. gVisor, Kata containers or a VM per run: stronger isolation, but not available on the team's machines and slower to start. |
| Decision | `runner-worker/worker/sandbox.py::container_options()` sets every control in one place; the container and its volume are removed after every run. |
| Rationale | Meets the M2 intent fully within Docker Desktop on the team's laptops. |
| Consequences | + QAS-3: 13/13 attacks blocked or contained (fork bomb, memory bomb and read-only write attempts included). - The Runner Worker still holds the Docker socket (risk R-009; proposal: a socket proxy). - Container start-up (about 1 s per run) limits throughput (QAS-5 sensitivity point). |
