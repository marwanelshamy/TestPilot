# Test Sandbox image

Built from `python:3.12-slim` with pytest, runs as non-root user `sandbox`. Started per run by the Runner Worker with `network_mode=none`, read-only root FS, tmpfs `/tmp`, CPU/memory/time limits (ASR-1, ADR-003). Dockerfile added in Phase 2.
