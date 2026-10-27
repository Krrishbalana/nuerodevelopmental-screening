"""Errors of the Saathi engine (copied subset of the Saathi repo's app/core/errors.py)."""


class SaathiError(Exception):
    pass


class DatasetIntegrityError(SaathiError):
    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__(
            f"Dataset failed referential-integrity validation "
            f"({len(violations)} violation(s)):\n" + "\n".join(f"- {v}" for v in violations)
        )


class WrongQuestionError(SaathiError):
    def __init__(self, expected: str | None, got: str) -> None:
        self.expected = expected
        self.got = got
        super().__init__(f"Expected an answer for question {expected!r}, got {got!r}")


class NoCurrentQuestionError(SaathiError):
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"Session {session_id!r} has no pending question to answer")
