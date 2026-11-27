"""Execution lifecycle state machine (pattern P10). docs/phase1/03 §2.

QUEUED -> RUNNING -> {PASSED, FAILED, INTERRUPTED};  QUEUED/RUNNING -> {INTERRUPTED, CANCELLED}.
Terminal states never change again.
"""

from app.core.enums import ExecutionStatus as S

ALLOWED: dict[S, set[S]] = {
    S.QUEUED: {S.RUNNING, S.INTERRUPTED, S.CANCELLED},
    S.RUNNING: {S.PASSED, S.FAILED, S.INTERRUPTED, S.CANCELLED},
    S.PASSED: set(),
    S.FAILED: set(),
    S.INTERRUPTED: set(),
    S.CANCELLED: set(),
}


class IllegalTransition(Exception):
    pass


def can_move(current: S, target: S) -> bool:
    return target in ALLOWED[current]


def check_move(current: S, target: S) -> None:
    if not can_move(current, target):
        raise IllegalTransition(f"{current.value} -> {target.value} is not allowed")
