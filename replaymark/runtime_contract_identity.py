from __future__ import annotations

"""Verified runtime identity reuse for immutable ExplicitCompiledContract objects.

The semantic contract is content-addressed, but recomputing its canonical bytes and
SHA-256 for every runtime certificate is unnecessary once the exact in-memory
contract object has already been verified. This module keeps a small, bounded,
thread-safe cache keyed strictly by Python object identity.

No caller can supply a fingerprint to the bridge. On a cold miss this module reads
both identities directly from the frozen ExplicitCompiledContract. On a hit it
returns only the values previously derived from that same live object.

The cache deliberately holds a strong reference to each admitted contract while
cached. This prevents ``id()`` reuse from turning a stale entry into a false hit.
The bounded capacity prevents unbounded retention.
"""

from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock

from .compiled_contract import ExplicitCompiledContract


RUNTIME_CONTRACT_IDENTITY_CACHE_ID = (
    "replaymark.runtime.verified-contract-identity-cache.v1"
)
RUNTIME_CONTRACT_IDENTITY_CACHE_CAPACITY = 16


def _digest(name: str, value: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise ValueError(f"{name} must be canonical lowercase sha256 hex")
    return value


@dataclass(frozen=True, slots=True)
class RuntimeContractIdentity:
    """Content identities verified once from one immutable compiled contract."""

    cache_id: str
    contract_fingerprint: str
    claim_fingerprint: str

    def __post_init__(self) -> None:
        if self.cache_id != RUNTIME_CONTRACT_IDENTITY_CACHE_ID:
            raise ValueError("foreign runtime contract-identity cache")
        _digest("contract_fingerprint", self.contract_fingerprint)
        _digest("claim_fingerprint", self.claim_fingerprint)


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    contract: ExplicitCompiledContract
    identity: RuntimeContractIdentity


_LOCK = RLock()
_CACHE: OrderedDict[int, _CacheEntry] = OrderedDict()
_HITS = 0
_MISSES = 0
_EVICTIONS = 0


def verified_runtime_contract_identity(
    contract: ExplicitCompiledContract,
) -> RuntimeContractIdentity:
    """Return identities verified from exactly this immutable contract object.

    A cache hit is accepted only when both the integer object id and the stored
    strong-reference object identity match. Cold computation occurs while holding
    the lock, so concurrent first use of one contract performs exactly one
    canonical contract fingerprint computation.
    """

    if not isinstance(contract, ExplicitCompiledContract):
        raise TypeError("contract must be ExplicitCompiledContract")

    global _HITS, _MISSES, _EVICTIONS

    key = id(contract)
    with _LOCK:
        entry = _CACHE.get(key)
        if entry is not None and entry.contract is contract:
            _HITS += 1
            _CACHE.move_to_end(key)
            return entry.identity

        # A live strong reference makes an id collision impossible for a valid
        # entry, but fail closed on any internal inconsistency rather than reuse.
        if entry is not None:
            del _CACHE[key]

        identity = RuntimeContractIdentity(
            cache_id=RUNTIME_CONTRACT_IDENTITY_CACHE_ID,
            contract_fingerprint=contract.fingerprint(),
            claim_fingerprint=contract.claim_fingerprint,
        )
        _CACHE[key] = _CacheEntry(contract=contract, identity=identity)
        _CACHE.move_to_end(key)
        _MISSES += 1

        while len(_CACHE) > RUNTIME_CONTRACT_IDENTITY_CACHE_CAPACITY:
            _CACHE.popitem(last=False)
            _EVICTIONS += 1

        return identity


def runtime_contract_identity_cache_info() -> dict[str, int | str]:
    """Return non-semantic observability for verification and measurement."""

    with _LOCK:
        return {
            "cache_id": RUNTIME_CONTRACT_IDENTITY_CACHE_ID,
            "capacity": RUNTIME_CONTRACT_IDENTITY_CACHE_CAPACITY,
            "size": len(_CACHE),
            "hits": _HITS,
            "misses": _MISSES,
            "evictions": _EVICTIONS,
        }


__all__ = (
    "RUNTIME_CONTRACT_IDENTITY_CACHE_ID",
    "RUNTIME_CONTRACT_IDENTITY_CACHE_CAPACITY",
    "RuntimeContractIdentity",
    "verified_runtime_contract_identity",
    "runtime_contract_identity_cache_info",
)
