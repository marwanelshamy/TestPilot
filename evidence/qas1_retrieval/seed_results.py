"""QAS-1 data set: one project with 1,000 test cases and 10,000 finished execution records.

Writes directly to the database through the Core Backend's own models (the only component allowed to own
the data, ADR-004) — so it must run inside the core-backend container:

    docker compose exec -T core-backend python - < evidence/qas1_retrieval/seed_results.py

Prints the project id to use with load.py. Idempotent per project name.
"""

import os
import random
import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.core.database import init_engine, session_factory
from app.core.enums import ExecutionStatus, TerminationReason, TestCaseStatus, TestResultStatus, TestSource, TestType
from app.repositories.models import Execution, ExecutionTestCase, Project, ProjectMember, TestCase, User
from sqlalchemy import select

N_TESTS = int(os.environ.get("QAS1_TESTS", "1000"))
N_EXECUTIONS = int(os.environ.get("QAS1_EXECUTIONS", "10000"))
NAME = os.environ.get("QAS1_PROJECT", "QAS-1 retrieval data set")

init_engine(get_settings().database_url)
s = session_factory()()
dev = s.scalar(select(User).where(User.email == "dev@testpilot.local"))
project = s.scalar(select(Project).where(Project.name == NAME))
if project is None:
    project = Project(name=NAME, created_by=dev.user_id)
    s.add(project)
    s.flush()
    for u in s.scalars(select(User).where(User.role != "ADMIN")):
        s.add(ProjectMember(project_id=project.project_id, user_id=u.user_id))
    tests = [
        TestCase(
            project_id=project.project_id,
            title=f"generated test {i}",
            test_type=TestType.NORMAL,
            source=TestSource.MANUAL,
            test_code=f"def test_{i}():\n    assert True\n",
            status=TestCaseStatus.APPROVED,
            version=1,
            created_by=dev.user_id,
        )
        for i in range(N_TESTS)
    ]
    s.add_all(tests)
    s.flush()
    rnd = random.Random(42)
    start = datetime.now(UTC) - timedelta(days=30)
    for i in range(N_EXECUTIONS):
        created = start + timedelta(seconds=i * 250)
        failed = rnd.random() < 0.15
        ex = Execution(
            execution_id=uuid.uuid4(),
            project_id=project.project_id,
            requested_by=dev.user_id,
            status=ExecutionStatus.FAILED if failed else ExecutionStatus.PASSED,
            termination_reason=TerminationReason.COMPLETED,
            created_at=created,
            started_at=created + timedelta(seconds=2),
            last_heartbeat_at=created + timedelta(seconds=3),
            finished_at=created + timedelta(seconds=4),
        )
        s.add(ex)
        t = tests[i % N_TESTS]
        s.add(
            ExecutionTestCase(
                execution_id=ex.execution_id,
                test_case_id=t.test_case_id,
                test_case_version=1,
                result_status=TestResultStatus.FAILED if failed else TestResultStatus.PASSED,
                duration_ms=rnd.randint(5, 900),
            )
        )
        if i % 1000 == 999:
            s.flush()
            print(f"  {i + 1} executions")
    s.commit()
print(f"PROJECT_ID={project.project_id}")
