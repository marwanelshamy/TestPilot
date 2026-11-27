import pytest

from app.core.enums import ExecutionStatus as S
from app.integration.ai_client import CircuitBreaker
from app.services.orchestrator.state_machine import IllegalTransition, can_move, check_move


@pytest.mark.parametrize("terminal", [S.PASSED, S.FAILED, S.INTERRUPTED, S.CANCELLED])
def test_terminal_states_never_change(terminal):
    for target in S:
        assert not can_move(terminal, target)


def test_queued_cannot_jump_to_passed():
    with pytest.raises(IllegalTransition):
        check_move(S.QUEUED, S.PASSED)


def test_happy_path_transitions():
    check_move(S.QUEUED, S.RUNNING)
    check_move(S.RUNNING, S.PASSED)
    check_move(S.RUNNING, S.INTERRUPTED)


def test_circuit_breaker_opens_and_half_opens():
    t = [0.0]
    cb = CircuitBreaker(threshold=2, reset_seconds=30, clock=lambda: t[0])
    assert cb.state == "CLOSED"
    cb.failure()
    assert cb.allow()
    cb.failure()
    assert cb.state == "OPEN" and not cb.allow()
    t[0] = 31
    assert cb.state == "HALF_OPEN" and cb.allow()
    cb.failure()  # trial call failed -> open again
    assert cb.state == "OPEN"
    t[0] = 62
    cb.success()
    assert cb.state == "CLOSED"
