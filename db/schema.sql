-- TestPilot AI — PostgreSQL 16 schema (Phase 1 agreed contract)
-- Source: M2 SAD §3.6 Data view (14 entities). Owner: Core Backend ONLY (ADR-004).
-- Runner Worker, Test Sandbox and AI Service have no database credentials.
-- In Phase 2 this file is turned into the first Alembic migration in core-backend/migrations.

BEGIN;

-- ---------- Enumerations ----------
CREATE TYPE user_role          AS ENUM ('DEVELOPER', 'QA_ASSISTANT', 'TEAM_LEAD', 'ADMIN');
CREATE TYPE test_type          AS ENUM ('NORMAL', 'BOUNDARY', 'NEGATIVE');
CREATE TYPE test_source        AS ENUM ('AI_GENERATED', 'MANUAL');
CREATE TYPE test_case_status   AS ENUM ('DRAFT', 'APPROVED', 'REJECTED');
CREATE TYPE approval_decision  AS ENUM ('APPROVED', 'REJECTED');
CREATE TYPE flag_status        AS ENUM ('OPEN', 'RESOLVED');
CREATE TYPE execution_status   AS ENUM ('QUEUED', 'RUNNING', 'PASSED', 'FAILED', 'INTERRUPTED', 'CANCELLED');
CREATE TYPE termination_reason AS ENUM ('COMPLETED', 'TIMEOUT', 'RUNNER_LOST', 'INVALID_REPORT',
                                        'RESOURCE_LIMIT', 'CANCELLED_BY_USER', 'INTERNAL_ERROR');
CREATE TYPE test_result_status AS ENUM ('PASSED', 'FAILED', 'ERROR', 'SKIPPED', 'NOT_RUN');
CREATE TYPE evidence_type      AS ENUM ('STDOUT', 'STDERR', 'JUNIT_XML', 'RUNNER_LOG');

-- ---------- Identity & Access ----------
CREATE TABLE app_user (                       -- "USER" in the data view (USER is reserved in SQL)
    user_id        BIGSERIAL PRIMARY KEY,
    name           VARCHAR(120) NOT NULL,
    email          VARCHAR(254) NOT NULL UNIQUE,
    password_hash  VARCHAR(255) NOT NULL,      -- bcrypt
    role           user_role    NOT NULL,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ---------- Projects & Requirements ----------
CREATE TABLE project (
    project_id           BIGSERIAL PRIMARY KEY,
    name                 VARCHAR(120) NOT NULL,
    description          TEXT,
    programming_language VARCHAR(20)  NOT NULL DEFAULT 'Python' CHECK (programming_language = 'Python'),  -- C-01
    test_framework       VARCHAR(20)  NOT NULL DEFAULT 'pytest' CHECK (test_framework = 'pytest'),        -- C-01
    created_by           BIGINT       NOT NULL REFERENCES app_user(user_id),
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE project_member (
    project_id  BIGINT      NOT NULL REFERENCES project(project_id) ON DELETE CASCADE,
    user_id     BIGINT      NOT NULL REFERENCES app_user(user_id)   ON DELETE CASCADE,
    joined_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, user_id)
);

CREATE TABLE requirement (
    requirement_id BIGSERIAL PRIMARY KEY,
    project_id     BIGINT       NOT NULL REFERENCES project(project_id) ON DELETE CASCADE,
    title          VARCHAR(200) NOT NULL,
    description    TEXT         NOT NULL,
    created_by     BIGINT       NOT NULL REFERENCES app_user(user_id),
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX ix_requirement_project ON requirement(project_id, created_at);

-- ---------- Test Design & Approval ----------
CREATE TABLE test_case (
    test_case_id  BIGSERIAL PRIMARY KEY,
    project_id    BIGINT           NOT NULL REFERENCES project(project_id) ON DELETE CASCADE,
    title         VARCHAR(200)     NOT NULL,
    description   TEXT,
    test_type     test_type        NOT NULL,
    source        test_source      NOT NULL,
    test_code     TEXT             NOT NULL,
    status        test_case_status NOT NULL DEFAULT 'DRAFT',
    version       INTEGER          NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_by    BIGINT           NOT NULL REFERENCES app_user(user_id),
    created_at    TIMESTAMPTZ      NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ      NOT NULL DEFAULT now()
);
CREATE INDEX ix_test_case_project_status ON test_case(project_id, status);

CREATE TABLE requirement_test_case (
    requirement_id BIGINT NOT NULL REFERENCES requirement(requirement_id) ON DELETE CASCADE,
    test_case_id   BIGINT NOT NULL REFERENCES test_case(test_case_id)     ON DELETE CASCADE,
    PRIMARY KEY (requirement_id, test_case_id)
);
CREATE INDEX ix_rtc_test_case ON requirement_test_case(test_case_id);

-- Version-bound approval (ADR-005): a decision is valid only for test_case_version.
-- Rule enforced in the service AND checked at run time: test_case.status = 'APPROVED'
-- AND a TEST_APPROVAL row exists with decision = 'APPROVED' and test_case_version = test_case.version.
CREATE TABLE test_approval (
    approval_id        BIGSERIAL PRIMARY KEY,
    test_case_id       BIGINT            NOT NULL REFERENCES test_case(test_case_id) ON DELETE CASCADE,
    test_case_version  INTEGER           NOT NULL,
    decision           approval_decision NOT NULL,
    comment            TEXT,
    decided_by         BIGINT            NOT NULL REFERENCES app_user(user_id),
    decided_at         TIMESTAMPTZ       NOT NULL DEFAULT now()
);
CREATE INDEX ix_approval_test_version ON test_approval(test_case_id, test_case_version);

CREATE TABLE review_flag (
    flag_id       BIGSERIAL PRIMARY KEY,
    test_case_id  BIGINT      NOT NULL REFERENCES test_case(test_case_id) ON DELETE CASCADE,
    comment       TEXT        NOT NULL,
    status        flag_status NOT NULL DEFAULT 'OPEN',
    raised_by     BIGINT      NOT NULL REFERENCES app_user(user_id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- Execution & Evidence (written ONLY by the Execution Orchestrator) ----------
CREATE TABLE execution (
    execution_id        UUID               PRIMARY KEY,
    project_id          BIGINT             NOT NULL REFERENCES project(project_id) ON DELETE CASCADE,
    requested_by        BIGINT             NOT NULL REFERENCES app_user(user_id),
    status              execution_status   NOT NULL DEFAULT 'QUEUED',
    termination_reason  termination_reason,
    time_limit_seconds  INTEGER            NOT NULL DEFAULT 30,
    created_at          TIMESTAMPTZ        NOT NULL DEFAULT now(),
    started_at          TIMESTAMPTZ,
    last_heartbeat_at   TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    -- terminal states must carry a reason and a finish time; non-terminal must not
    CONSTRAINT ck_terminal_has_reason CHECK (
        (status IN ('QUEUED','RUNNING') AND termination_reason IS NULL AND finished_at IS NULL)
     OR (status NOT IN ('QUEUED','RUNNING') AND termination_reason IS NOT NULL AND finished_at IS NOT NULL)
    ),
    -- PASSED/FAILED only from a completed, valid runner report (ADR-006, QAS-7)
    CONSTRAINT ck_pass_fail_needs_completed CHECK (
        status NOT IN ('PASSED','FAILED') OR termination_reason = 'COMPLETED'
    )
);
CREATE INDEX ix_execution_project_created ON execution(project_id, created_at DESC);   -- QAS-1
CREATE INDEX ix_execution_running         ON execution(status, last_heartbeat_at)
    WHERE status IN ('QUEUED','RUNNING');                                              -- watchdog scan

CREATE TABLE execution_test_case (
    execution_test_id  BIGSERIAL          PRIMARY KEY,
    execution_id       UUID               NOT NULL REFERENCES execution(execution_id) ON DELETE CASCADE,
    test_case_id       BIGINT             NOT NULL REFERENCES test_case(test_case_id),
    test_case_version  INTEGER            NOT NULL,
    result_status      test_result_status NOT NULL DEFAULT 'NOT_RUN',
    duration_ms        INTEGER,
    failure_message    TEXT,
    UNIQUE (execution_id, test_case_id)
);

CREATE TABLE execution_evidence (
    evidence_id        BIGSERIAL     PRIMARY KEY,
    execution_id       UUID          NOT NULL REFERENCES execution(execution_id) ON DELETE CASCADE,
    execution_test_id  BIGINT        REFERENCES execution_test_case(execution_test_id) ON DELETE CASCADE,
    evidence_type      evidence_type NOT NULL,
    content            TEXT          NOT NULL,          -- capped at 64 KB by the orchestrator (OI-008)
    size_bytes         INTEGER       NOT NULL,          -- original size before truncation
    truncated          BOOLEAN       NOT NULL DEFAULT false,
    created_at         TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX ix_evidence_execution ON execution_evidence(execution_id);

-- Idempotency for AMQP events: a message is processed at most once (duplicate/late events ignored).
CREATE TABLE processed_message (
    message_id    UUID        PRIMARY KEY,
    execution_id  UUID        NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- Results & Reporting ----------
CREATE TABLE ai_explanation (
    explanation_id     BIGSERIAL   PRIMARY KEY,
    execution_test_id  BIGINT      NOT NULL REFERENCES execution_test_case(execution_test_id) ON DELETE CASCADE,
    explanation_text   TEXT        NOT NULL,           -- shown as AI hypothesis (C-10)
    provider_model     VARCHAR(120) NOT NULL,
    requested_by       BIGINT      NOT NULL REFERENCES app_user(user_id),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE quality_report (
    report_id     BIGSERIAL   PRIMARY KEY,
    project_id    BIGINT      NOT NULL REFERENCES project(project_id) ON DELETE CASCADE,
    summary       JSONB       NOT NULL,                -- totals, coverage, risks
    generated_by  BIGINT      NOT NULL REFERENCES app_user(user_id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_report_project ON quality_report(project_id, created_at DESC);

COMMIT;
