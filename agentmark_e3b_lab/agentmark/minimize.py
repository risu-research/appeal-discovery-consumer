from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .kernel import ReactiveKernel

@dataclass(frozen=True)
class QuotientResult:
    state_to_block: dict[str, str]
    blocks: dict[str, tuple[str, ...]]
    state_feedback_classes: dict[str, tuple[tuple[str, ...], ...]]
    state_unsupported_feedback: dict[str, tuple[str, ...]]
    global_feedback_classes: tuple[tuple[str, ...], ...]
    minimized_spec: dict[str, Any]

def quotient(kernel: ReactiveKernel) -> QuotientResult:
    # Exact partition refinement sufficient for the E3b finite controller.
    groups=[list(kernel.states)]
    changed=True
    while changed:
        changed=False; mapping={s:f"q{i}" for i,g in enumerate(groups) for s in g}; new=[]
        for g in groups:
            buckets={}
            for s in g:
                sig=tuple(kernel.canonical_signature(s,y,state_blocks=mapping) for y in kernel.feedback_alphabet)
                buckets.setdefault(sig,[]).append(s)
            if len(buckets)>1: changed=True
            new.extend(buckets.values())
        groups=new
    groups=[sorted(g) for g in groups]; groups.sort(key=lambda g:g[0])
    state_to_block={s:f"q{i}" for i,g in enumerate(groups) for s in g}
    blocks={f"q{i}":tuple(g) for i,g in enumerate(groups)}
    return QuotientResult(state_to_block,blocks,{},(),(),{})
