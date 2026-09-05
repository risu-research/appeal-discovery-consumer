from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Iterable, Mapping


@dataclass(frozen=True, order=True)
class EventKey:
    operation: str
    target_class: str | None
    delay_ms: int
    next_state: str
    # Optional adapter-supplied semantic discriminator.  It is deliberately
    # opaque to the kernel: e.g. a Home Assistant adapter can distinguish the
    # same service invoked with preset=home vs preset=away without teaching the
    # generic replay semantics anything about climate domains.
    variant: str | None = None


@dataclass(frozen=True)
class Atom:
    probability: Fraction
    event: EventKey


def _prob(value: Any) -> Fraction:
    if isinstance(value, Fraction):
        return value
    return Fraction(str(value))


class ReactiveKernel:
    MISSING = "__AGENTMARK_MISSING__"

    def __init__(self, spec: Mapping[str, Any]):
        self.spec = dict(spec)
        self.initial_state = str(self.spec["initial_state"])
        states = self.spec.get("states")
        if not isinstance(states, Mapping) or self.initial_state not in states:
            raise ValueError("spec.states must contain initial_state")
        self.states = tuple(sorted(str(s) for s in states))
        self._states_raw: Mapping[str, Any] = states
        explicit = self.spec.get("feedback_alphabet")
        if explicit is not None:
            alphabet = [str(x) for x in explicit]
            if len(set(alphabet)) != len(alphabet):
                raise ValueError("feedback_alphabet contains duplicates")
        else:
            alphabet = sorted({str(feedback) for by_feedback in states.values() for feedback in by_feedback if feedback != "*"})
        if not alphabet:
            raise ValueError("feedback alphabet must not be empty")
        self.feedback_alphabet = tuple(alphabet)
        self._validate()

    def _validate(self) -> None:
        known = set(self.states)
        for state in self.states:
            by_feedback = self._states_raw[state]
            if not isinstance(by_feedback, Mapping):
                raise ValueError(f"state {state!r} must map feedback symbols to transitions")
            for feedback, rows in by_feedback.items():
                if not isinstance(rows, list) or not rows:
                    raise ValueError(f"{state}/{feedback} must have non-empty transitions")
                total = Fraction(0, 1)
                for row in rows:
                    p = _prob(row.get("p", row.get("probability", 0)))
                    if p < 0:
                        raise ValueError("transition probability must be non-negative")
                    total += p
                    nxt = str(row["next_state"])
                    if nxt not in known:
                        raise ValueError(f"unknown next_state {nxt!r}")
                    if not str(row.get("operation", "")):
                        raise ValueError("transition operation must be non-empty")
                    variant = row.get("variant")
                    if variant is not None and not isinstance(variant, str):
                        raise ValueError("transition variant must be a string or null")
                if abs(float(total) - 1.0) > 1e-12:
                    raise ValueError(f"probabilities for {state}/{feedback} sum to {float(total)}, not 1")

    def has_feedback(self, state: str, feedback: str) -> bool:
        by_feedback = self._states_raw[str(state)]
        return str(feedback) in by_feedback or "*" in by_feedback

    def raw_rows(self, state: str, feedback: str) -> list[Mapping[str, Any]]:
        by_feedback = self._states_raw[str(state)]
        feedback = str(feedback)
        if feedback in by_feedback:
            return list(by_feedback[feedback])
        if "*" in by_feedback:
            return list(by_feedback["*"])
        raise KeyError(f"no transition for state={state!r}, feedback={feedback!r}")

    def atoms(self, state: str, feedback: str, *, state_blocks: Mapping[str, str | int] | None = None) -> tuple[Atom, ...]:
        rows = self.raw_rows(state, feedback)
        raw_probs = [_prob(row.get("p", row.get("probability"))) for row in rows]
        total = sum(raw_probs, Fraction(0, 1))
        atoms = []
        for row, raw_p in zip(rows, raw_probs):
            nxt = str(row["next_state"])
            nxt_key = state_blocks[nxt] if state_blocks is not None else nxt
            atoms.append(
                Atom(
                    raw_p / total,
                    EventKey(
                        str(row["operation"]),
                        row.get("target_class"),
                        int(row.get("delay_ms", 0)),
                        str(nxt_key),
                        row.get("variant"),
                    ),
                )
            )
        return tuple(atoms)

    def distribution(self, state: str, feedback: str, *, state_blocks: Mapping[str, str | int] | None = None, projection: str = "full") -> dict[Any, Fraction]:
        out: dict[Any, Fraction] = defaultdict(Fraction)
        for atom in self.atoms(state, feedback, state_blocks=state_blocks):
            # Zero-mass rows are legal input syntax but are not part of a
            # probability distribution's support. Dropping them here keeps
            # canonical signatures invariant to semantically irrelevant
            # explicit p=0 rows.
            if atom.probability <= 0:
                continue
            if projection == "full":
                key: Any = (
                    atom.event.operation,
                    atom.event.target_class,
                    atom.event.variant,
                    atom.event.delay_ms,
                    atom.event.next_state,
                )
            elif projection == "operation":
                key = atom.event.operation
            elif projection == "action":
                # Parameter-sensitive action identity while deliberately
                # excluding timing and successor state.  ``variant`` is
                # adapter-supplied and must be declared before evaluation.
                key = (
                    atom.event.operation,
                    atom.event.target_class,
                    atom.event.variant,
                )
            elif projection == "semantic":
                # Legacy E3b/E3c projection retained byte-semantically for
                # compatibility: operation + target class + delay.
                key = (atom.event.operation, atom.event.target_class, atom.event.delay_ms)
            else:
                raise ValueError(f"unknown projection {projection!r}")
            out[key] += atom.probability
        return dict(out)

    def canonical_signature(self, state: str, feedback: str, *, state_blocks: Mapping[str, str | int] | None = None, projection: str = "full") -> tuple:
        if not self.has_feedback(state, feedback): return (self.MISSING,)
        dist = self.distribution(state, feedback, state_blocks=state_blocks, projection=projection)
        return tuple(sorted(((key, p.numerator, p.denominator) for key, p in dist.items()), key=repr))

    def event_probability(self, state: str, feedback: str, *, operation: str, target_class: str | None | object = ..., delay_ms: int | object = ..., next_state: str | object = ..., variant: str | None | object = ...) -> Fraction:
        total = Fraction(0, 1)
        for atom in self.atoms(state, feedback):
            e = atom.event
            if e.operation != str(operation): continue
            if target_class is not ... and e.target_class != target_class: continue
            if delay_ms is not ... and e.delay_ms != int(delay_ms): continue
            if next_state is not ... and e.next_state != str(next_state): continue
            if variant is not ... and e.variant != variant: continue
            total += atom.probability
        return total
