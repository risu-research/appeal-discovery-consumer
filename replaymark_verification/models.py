from __future__ import annotations

from fractions import Fraction
import hashlib
import json
from typing import Mapping

from replaymark.contracts import ProjectedAction


def _hash_record(record: object) -> str:
    data = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _state_id(values: tuple[object, ...]) -> str:
    return json.dumps(list(values), separators=(",", ":")).lower()


def _parse_state(value: str) -> tuple[bool, bool, bool, str]:
    raw = json.loads(value)
    if not isinstance(raw, list) or len(raw) != 4:
        raise KeyError(value)
    p, m, n, preset = raw
    if not isinstance(p, bool) or not isinstance(m, bool) or not isinstance(n, bool):
        raise KeyError(value)
    if not isinstance(preset, str):
        raise KeyError(value)
    return p, m, n, preset


class BetterThermostatFrozenModel:
    """Verification-only exact 32/56-state frozen controller semantics.

    This is not a Home Assistant adapter and is never imported by production
    ReplayMark. It restates the already-frozen q-gate controller model so the
    new generic compiler can be checked against historical scientific authority.
    """

    CONTINUATIONS = (
        "presence_toggle",
        "motion_toggle",
        "night_toggle",
        "tick",
    )

    def __init__(self, presets: tuple[str, ...] = ("away", "home", "comfort", "sleep")):
        if len(set(presets)) != len(presets) or not presets:
            raise ValueError("presets must be nonempty and unique")
        self._presets = tuple(presets)
        self._decision_states = tuple(
            sorted(
                _state_id((presence, motion, night, preset))
                for presence in (False, True)
                for motion in (False, True)
                for night in (False, True)
                for preset in self._presets
            )
        )
        self._state_set = set(self._decision_states)
        self._fingerprint = _hash_record(
            {
                "schema": "replaymark.verify.better-thermostat-frozen.v1",
                "presets": list(self._presets),
                "continuations": list(self.CONTINUATIONS),
                "logic": "night?sleep:!presence?away:motion?comfort:home; no-action-if-at-target",
            }
        )

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    @property
    def decision_states(self) -> tuple[str, ...]:
        return self._decision_states

    @property
    def continuation_alphabet(self) -> tuple[str, ...]:
        return self.CONTINUATIONS

    @staticmethod
    def target_preset(state: tuple[bool, bool, bool, str]) -> str:
        presence, motion, night, _ = state
        if night:
            return "sleep"
        if not presence:
            return "away"
        if motion:
            return "comfort"
        return "home"

    def current_distribution(
        self, decision_state: str
    ) -> Mapping[tuple[ProjectedAction, str], Fraction]:
        state = _parse_state(str(decision_state))
        if str(decision_state) not in self._state_set:
            raise KeyError(decision_state)
        target = self.target_preset(state)
        operation = "NO_ACTION" if state[3] == target else f"SET_{target.upper()}"
        action = ProjectedAction.from_mapping({"operation": operation})
        post_state = _state_id((state[0], state[1], state[2], target))
        return {(action, post_state): Fraction(1, 1)}

    def advance_distribution(
        self, post_state: str, continuation: str
    ) -> Mapping[str, Fraction]:
        presence, motion, night, preset = _parse_state(str(post_state))
        continuation = str(continuation)
        if continuation not in self.CONTINUATIONS:
            raise KeyError(continuation)
        if continuation == "presence_toggle":
            presence = not presence
        elif continuation == "motion_toggle":
            motion = not motion
        elif continuation == "night_toggle":
            night = not night
        nxt = _state_id((presence, motion, night, preset))
        if nxt not in self._state_set:
            raise KeyError(nxt)
        return {nxt: Fraction(1, 1)}

    @staticmethod
    def encode(presence: bool, motion: bool, night: bool, preset: str) -> str:
        return _state_id((presence, motion, night, preset))

    def stable_key(self, decision_state: str) -> tuple[bool, bool, bool, bool]:
        state = _parse_state(str(decision_state))
        return state[0], state[1], state[2], state[3] == self.target_preset(state)


class TableTargetModel:
    """Tiny deterministic Moore-style model for exhaustive differential testing."""

    def __init__(
        self,
        *,
        outputs: tuple[str, ...],
        continuations: tuple[str, ...],
        next_state: tuple[tuple[int, ...], ...],
        variants: tuple[str | None, ...] | None = None,
        continuation_order: tuple[str, ...] | None = None,
    ):
        n = len(outputs)
        if n == 0:
            raise ValueError("at least one state required")
        if len(next_state) != n:
            raise ValueError("transition row count mismatch")
        if any(len(row) != len(continuations) for row in next_state):
            raise ValueError("transition width mismatch")
        if variants is None:
            variants = (None,) * n
        if len(variants) != n:
            raise ValueError("variant length mismatch")
        for row in next_state:
            if any(index < 0 or index >= n for index in row):
                raise ValueError("transition target out of range")
        self._states = tuple(f"s{i}" for i in range(n))
        self._outputs = tuple(outputs)
        self._variants = tuple(variants)
        self._continuations = tuple(
            continuations if continuation_order is None else continuation_order
        )
        if set(self._continuations) != set(continuations) or len(self._continuations) != len(continuations):
            raise ValueError("continuation_order must be a permutation")
        original_index = {symbol: i for i, symbol in enumerate(continuations)}
        self._next = {
            (f"s{i}", symbol): f"s{row[original_index[symbol]]}"
            for i, row in enumerate(next_state)
            for symbol in self._continuations
        }
        self._fingerprint = _hash_record(
            {
                "schema": "replaymark.verify.table-target.v1",
                "outputs": list(self._outputs),
                "variants": list(self._variants),
                "continuations": list(self._continuations),
                "next": sorted([[s, u, t] for (s, u), t in self._next.items()]),
            }
        )

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    @property
    def decision_states(self) -> tuple[str, ...]:
        return self._states

    @property
    def continuation_alphabet(self) -> tuple[str, ...]:
        return self._continuations

    def current_distribution(self, decision_state: str):
        state = str(decision_state)
        try:
            index = self._states.index(state)
        except ValueError as exc:
            raise KeyError(state) from exc
        action = ProjectedAction.from_mapping(
            {
                "operation": self._outputs[index],
                "variant": self._variants[index],
            }
        )
        return {(action, state): Fraction(1, 1)}

    def advance_distribution(self, post_state: str, continuation: str):
        try:
            nxt = self._next[(str(post_state), str(continuation))]
        except KeyError as exc:
            raise KeyError((post_state, continuation)) from exc
        return {nxt: Fraction(1, 1)}


class StochasticCurrentModel:
    """Verification fixture: stochastic current action, valid public TargetModel."""

    @property
    def fingerprint(self) -> str:
        return "stochastic-current-fixture"

    @property
    def decision_states(self) -> tuple[str, ...]:
        return ("s",)

    @property
    def continuation_alphabet(self) -> tuple[str, ...]:
        return ("tick",)

    def current_distribution(self, decision_state: str):
        if decision_state != "s":
            raise KeyError(decision_state)
        a = ProjectedAction.from_mapping({"operation": "A"})
        b = ProjectedAction.from_mapping({"operation": "B"})
        return {(a, "s"): Fraction(1, 2), (b, "s"): Fraction(1, 2)}

    def advance_distribution(self, post_state: str, continuation: str):
        return {"s": Fraction(1, 1)}


class StochasticAdvanceModel:
    """Verification fixture: deterministic current action, stochastic future state."""

    @property
    def fingerprint(self) -> str:
        return "stochastic-advance-fixture"

    @property
    def decision_states(self) -> tuple[str, ...]:
        return ("s0", "s1")

    @property
    def continuation_alphabet(self) -> tuple[str, ...]:
        return ("tick",)

    def current_distribution(self, decision_state: str):
        if decision_state not in self.decision_states:
            raise KeyError(decision_state)
        action = ProjectedAction.from_mapping({"operation": decision_state})
        return {(action, decision_state): Fraction(1, 1)}

    def advance_distribution(self, post_state: str, continuation: str):
        if continuation != "tick":
            raise KeyError(continuation)
        return {"s0": Fraction(1, 2), "s1": Fraction(1, 2)}
