"""Task Lifecycle State Machine enforcing transitions across all 8 states."""

from typing import Dict, Set


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal or unauthorized state machine transition is attempted."""
    pass


class StateTransitionError(InvalidStateTransitionError):
    """Alias for InvalidStateTransitionError for flexible contract importing."""
    pass


class TaskStateMachine:
    """Enforces strict task lifecycle state transitions and terminal immutability."""

    STATES: Set[str] = {
        "queued",
        "planning",
        "running",
        "verifying",
        "completed",
        "failed",
        "cancelled",
        "blocked",
    }

    TERMINAL_STATES: Set[str] = {
        "completed",
        "failed",
        "cancelled",
    }

    ACTIVE_STATES: Set[str] = {
        "queued",
        "planning",
        "running",
        "verifying",
        "blocked",
    }

    ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
        "queued": {"planning", "cancelled"},
        "planning": {"running", "failed", "cancelled"},
        "running": {"verifying", "blocked", "failed", "cancelled"},
        "blocked": {"running", "failed", "cancelled"},
        "verifying": {"completed", "running", "failed", "cancelled"},
        "completed": set(),  # Terminal state: no outgoing transitions
        "failed": set(),     # Terminal state: no outgoing transitions
        "cancelled": set(),  # Terminal state: no outgoing transitions
    }

    @classmethod
    def is_valid_state(cls, state: str) -> bool:
        """Check if state string is a recognized task state."""
        return isinstance(state, str) and state in cls.STATES

    @classmethod
    def is_terminal(cls, state: str) -> bool:
        """Check if state represents an immutable terminal state."""
        return state in cls.TERMINAL_STATES

    @classmethod
    def is_active(cls, state: str) -> bool:
        """Check if state represents an in-flight, active task."""
        return state in cls.ACTIVE_STATES

    @classmethod
    def can_transition(cls, from_state: str, to_state: str) -> bool:
        """Return True if transition from from_state to to_state is permissible."""
        if not cls.is_valid_state(from_state) or not cls.is_valid_state(to_state):
            return False
        return to_state in cls.ALLOWED_TRANSITIONS.get(from_state, set())

    @classmethod
    def validate_transition(cls, from_state: str, to_state: str) -> None:
        """Validate state transition; raise InvalidStateTransitionError if illegal."""
        if not cls.can_transition(from_state, to_state):
            raise InvalidStateTransitionError(
                f"Invalid state transition: cannot transition from '{from_state}' to '{to_state}'."
            )

    @classmethod
    def allowed_transitions(cls, from_state: str) -> Set[str]:
        """Return set of valid target states from given from_state."""
        return set(cls.ALLOWED_TRANSITIONS.get(from_state, set()))
