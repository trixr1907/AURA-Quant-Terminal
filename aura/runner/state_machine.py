"""System-Zustandsmaschine fuer AURA v3 (aura.runner.state_machine).

Zustaende: STARTING, WARMING_UP, RUNNING, DEGRADED, HALTED, RECOVERING.
Unterstuetzt idempotente Not-Halt-Steuerung und Zustandsueberwachung.
Dokumentiert in docs/ARCHITECTURE.md §6.
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("aura.runner.state_machine")


class SystemState(str, enum.Enum):
    STARTING = "STARTING"
    WARMING_UP = "WARMING_UP"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    HALTED = "HALTED"
    RECOVERING = "RECOVERING"


@dataclass
class SystemStatus:
    state: SystemState
    since_ms: int
    reason: str
    halted: bool
    data_fresh: bool
    active_positions_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


class RunnerStateMachine:
    """Server-authoritative Zustandsmaschine mit Not-Halt und Fail-Closed-Guards."""

    VALID_TRANSITIONS = {
        SystemState.STARTING: {SystemState.WARMING_UP, SystemState.HALTED, SystemState.DEGRADED},
        SystemState.WARMING_UP: {SystemState.RUNNING, SystemState.DEGRADED, SystemState.HALTED},
        SystemState.RUNNING: {SystemState.DEGRADED, SystemState.HALTED, SystemState.RECOVERING},
        SystemState.DEGRADED: {SystemState.RUNNING, SystemState.HALTED, SystemState.RECOVERING},
        SystemState.HALTED: {SystemState.RECOVERING, SystemState.WARMING_UP},
        SystemState.RECOVERING: {SystemState.WARMING_UP, SystemState.RUNNING, SystemState.DEGRADED, SystemState.HALTED},
    }

    def __init__(self, initial_state: SystemState = SystemState.STARTING):
        self._state = initial_state
        self._since_ms = int(time.time() * 1000)
        self._reason = "System gestartet"
        self._halted = False
        self._halt_reason = ""
        self._listeners: list[Callable[[SystemStatus], None]] = []

    @property
    def current_state(self) -> SystemState:
        return self._state

    @property
    def is_halted(self) -> bool:
        return self._halted

    @property
    def reason(self) -> str:
        return self._reason

    @property
    def halt_reason(self) -> str:
        return self._halt_reason

    def can_open_new_trades(self) -> bool:
        """Neuer Trade-Einstieg ist nur im Zustand RUNNING und wenn nicht gehaltet erlaubt."""
        return self._state == SystemState.RUNNING and not self._halted

    def can_manage_existing_trades(self) -> bool:
        """Bestehende Positionen werden in allen Zustaenden ausser bei Fatal-Crash ueberwacht."""
        return self._state in {
            SystemState.RUNNING,
            SystemState.DEGRADED,
            SystemState.HALTED,
            SystemState.RECOVERING,
            SystemState.WARMING_UP,
        }

    def transition_to(self, new_state: SystemState, reason: str = "") -> bool:
        """Fuehrt einen zulaessigen Zustandsuebergang durch."""
        if new_state == self._state:
            return True
        allowed = self.VALID_TRANSITIONS.get(self._state, set())
        if new_state not in allowed:
            logger.warning(
                "Ungueltiger Zustandsuebergang von %s nach %s ignoriert",
                self._state.value,
                new_state.value,
            )
            return False

        old_state = self._state
        self._state = new_state
        self._since_ms = int(time.time() * 1000)
        self._reason = reason or f"Transition {old_state.value} -> {new_state.value}"
        logger.info("Zustand gewechselt: %s -> %s (%s)", old_state.value, new_state.value, self._reason)
        self._notify_listeners()
        return True

    def emergency_halt(self, reason: str = "Benutzer Not-Halt ausgeloest") -> None:
        """Aktiviert den Not-Halt: blockiert neue Trades sofort, bestehende Positionen bleiben geschuetzt."""
        self._halted = True
        self._halt_reason = reason
        self.transition_to(SystemState.HALTED, reason=f"Not-Halt: {reason}")

    def resume_from_halt(self, reason: str = "Not-Halt aufgehoben") -> bool:
        """Hebt den Not-Halt auf und wechselt in RECOVERING/WARMING_UP."""
        self._halted = False
        self._halt_reason = ""
        return self.transition_to(SystemState.RECOVERING, reason=reason)

    def mark_degraded(self, reason: str) -> None:
        if self._state in (SystemState.RUNNING, SystemState.WARMING_UP):
            self.transition_to(SystemState.DEGRADED, reason=reason)

    def mark_healthy(self, reason: str = "Feeds wieder synchron") -> None:
        if self._state in (SystemState.DEGRADED, SystemState.RECOVERING, SystemState.WARMING_UP):
            self.transition_to(SystemState.RUNNING, reason=reason)

    def subscribe(self, listener: Callable[[SystemStatus], None]) -> None:
        self._listeners.append(listener)

    def get_status(self, active_count: int = 0, data_fresh: bool = True) -> SystemStatus:
        return SystemStatus(
            state=self._state,
            since_ms=self._since_ms,
            reason=self._reason,
            halted=self._halted,
            data_fresh=data_fresh,
            active_positions_count=active_count,
            metadata={"halt_reason": self._halt_reason} if self._halted else {},
        )

    def _notify_listeners(self) -> None:
        status = self.get_status()
        for listener in self._listeners:
            try:
                listener(status)
            except Exception as ex:
                logger.error("Fehler in Status-Listener: %s", ex)
