"""Architecture erosion checks across the whole repository (M3 §3 "how you prevent architecture erosion").

Each rule is a design decision from the M2 SAD that the code or deployment could silently break.
Runs without Docker:  python -m pytest tests/architecture -v
(Inside each service, import-linter and the schema-drift test guard the internal layering.)
"""

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
COMPOSE = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
SERVICES = COMPOSE["services"]


def py_files(folder: str):
    return [p for p in (REPO / folder).rglob("*.py") if ".venv" not in p.parts and "tests" not in p.parts]


def imports_of(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r"^\s*(?:from|import)\s+([a-zA-Z_][\w]*)", text, flags=re.M))


def env_of(service: str) -> dict:
    env = SERVICES[service].get("environment") or {}
    return env if isinstance(env, dict) else dict(e.split("=", 1) for e in env)


# ---------------------------------------------------------------- deployment view (M2 §3.1, §3.5)
@pytest.mark.parametrize("service", ["runner-worker", "ai-service", "sandbox-image", "web-ui"])
def test_only_core_backend_gets_database_credentials(service):
    """ADR-004 single-writer: no container except the Core Backend can reach the data (ASR-1, ASR-3)."""
    assert "DATABASE_URL" not in env_of(service)
    assert "env_file" not in SERVICES[service] or service == "ai-service"  # ai-service reads .env for LLM keys only


def test_core_backend_is_the_only_database_client():
    assert "DATABASE_URL" in env_of("core-backend")


def test_sandbox_image_has_no_network():
    assert SERVICES["sandbox-image"].get("network_mode") == "none"


def test_only_ui_and_broker_console_publish_ports():
    published = {name for name, s in SERVICES.items() if s.get("ports")}
    assert published <= {"web-ui", "rabbitmq"}, published  # core, AI service, DB stay internal (contract I2)


def test_internal_network_has_no_internet_and_ai_service_alone_has_egress():
    assert COMPOSE["networks"]["internal"].get("internal") is True
    with_egress = {n for n, s in SERVICES.items() if "egress" in (s.get("networks") or [])}
    assert with_egress == {"ai-service"}


def test_docker_socket_only_in_trusted_runner_worker():
    mounts = {n for n, s in SERVICES.items() if any("docker.sock" in str(v) for v in s.get("volumes") or [])}
    assert mounts == {"runner-worker"}  # risk R-009: never in the sandbox, never in the core


def test_competing_runner_workers():
    assert SERVICES["runner-worker"]["deploy"]["replicas"] >= 2  # ASR-4 / P4


# ---------------------------------------------------------------- code-level "deliberately missing links" (M2 §3.1.2)
@pytest.mark.parametrize("folder", ["runner-worker/worker", "ai-service/app"])
def test_runner_and_ai_service_never_touch_the_database(folder):
    forbidden = {"sqlalchemy", "psycopg", "psycopg2", "asyncpg", "alembic"}
    for f in py_files(folder):
        assert not (imports_of(f) & forbidden), f"{f.relative_to(REPO)} imports a DB library"


def test_runner_never_decides_pass_or_fail():
    """ADR-006: the worker reports raw output only; only the Core orchestrator maps it to PASSED/FAILED."""
    for f in py_files("runner-worker/worker"):
        text = f.read_text(encoding="utf-8")
        assert '"PASSED"' not in text and "'PASSED'" not in text, f.relative_to(REPO)


def test_ai_service_has_no_path_to_test_status():
    for f in py_files("ai-service/app"):
        text = f.read_text(encoding="utf-8")
        assert "/executions" not in text and "execution_status" not in text, f.relative_to(REPO)


def test_web_ui_talks_only_to_the_core_api():
    src = REPO / "web-ui" / "src"
    for f in [*src.rglob("*.ts"), *src.rglob("*.tsx")]:
        text = f.read_text(encoding="utf-8")
        for target in ("ai-service", ":8001", "rabbitmq", "amqp://", ":5672", "postgres"):
            assert target not in text, f"{f.relative_to(REPO)} references {target}"
    nginx = (REPO / "web-ui" / "nginx.conf").read_text(encoding="utf-8")
    assert re.findall(r"proxy_pass\s+(\S+);", nginx) == ["http://core-backend:8000"]


def test_one_language_and_framework_in_the_mvp():
    """C-01 / ADR-007: Python + pytest only, enforced in the sandbox image and the database."""
    assert (REPO / "sandbox-image" / "requirements.txt").read_text().split()[-1].startswith("pytest==")
    schema = (REPO / "db" / "schema.sql").read_text(encoding="utf-8")
    assert "CHECK (programming_language = 'Python')" in schema and "CHECK (test_framework = 'pytest')" in schema


def test_message_contract_is_the_single_source():
    """Contract I4 schemas exist once, in docs/contracts, and every side's tests read them from there."""
    schemas = sorted(p.name for p in (REPO / "docs" / "contracts" / "messages").glob("*.json"))
    assert schemas == ["execution-finished.schema.json", "execution-heartbeat.schema.json", "execution-requested.schema.json"]
    for suite in ("core-backend/tests", "runner-worker/tests"):
        assert any("contracts" in p.read_text(encoding="utf-8") for p in (REPO / suite).rglob("*.py")), suite
