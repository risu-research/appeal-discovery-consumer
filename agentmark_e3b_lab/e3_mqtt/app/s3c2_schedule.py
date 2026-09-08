from __future__ import annotations

import hashlib

SEED_ASCII = "fd5b25ae05235eb460f426c716e1835783ced32e00ae81c7b67f24d09b83d596"
BARRIER_IMMEDIATE = "BARRIER_IMMEDIATE"
BARRIER_JITTERED = "BARRIER_JITTERED"
PROFILES = (BARRIER_IMMEDIATE, BARRIER_JITTERED)
GAP_SET_MS = (0, 125, 250, 500)
REPLICAS = ("A", "B")
BATCH_SIZES = (192, 196, 200, 204, 208)
TRIALS = range(6)
NS_PER_MS = 1_000_000
S3C1_PERIOD_NS = 500_000_000

ADMISSIBLE = "ADMISSIBLE"
BEFORE_QUIESCENCE = "BEFORE_QUIESCENCE"
BEFORE_REQUIRED_GAP = "BEFORE_REQUIRED_GAP"


class ScheduleInputError(ValueError):
    pass


def _check_cell(replica: str, batch_size: int, trial: int) -> None:
    if replica not in REPLICAS:
        raise ScheduleInputError("replica outside frozen matrix")
    if isinstance(batch_size, bool) or batch_size not in BATCH_SIZES:
        raise ScheduleInputError("batch_size outside frozen matrix")
    if isinstance(trial, bool) or trial not in TRIALS:
        raise ScheduleInputError("trial outside frozen matrix")


def _check_wave_index(wave_index: int) -> None:
    if isinstance(wave_index, bool) or not isinstance(wave_index, int) or wave_index < 0:
        raise ScheduleInputError("wave_index must be a non-negative integer")


def _check_ns(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ScheduleInputError(f"{name} must be a non-negative integer ns timestamp")


def canonical_decimal(value: int) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ScheduleInputError("canonical_decimal requires a non-negative integer")
    return str(value)


def _sha256(data: str) -> bytes:
    return hashlib.sha256(data.encode("utf-8")).digest()


def jitter_gap_permutation(replica: str, batch_size: int, trial: int) -> tuple[int, ...]:
    _check_cell(replica, batch_size, trial)
    cell_key = f"{SEED_ASCII}|{replica}|{batch_size}|{trial}"
    ranked = sorted(
        (
            hashlib.sha256(
                f"{cell_key}|gap|{canonical_decimal(gap_ms)}".encode("utf-8")
            ).hexdigest(),
            gap_ms,
        )
        for gap_ms in GAP_SET_MS
    )
    return tuple(gap_ms for _digest_hex, gap_ms in ranked)


def profile_order(replica: str, batch_size: int, trial: int) -> tuple[str, str]:
    _check_cell(replica, batch_size, trial)
    digest = _sha256(f"{SEED_ASCII}|order|{replica}|{batch_size}|{trial}")
    bit = digest[31] & 1
    if bit == 0:
        return (BARRIER_IMMEDIATE, BARRIER_JITTERED)
    return (BARRIER_JITTERED, BARRIER_IMMEDIATE)


def requested_gap_ms(
    profile: str,
    replica: str,
    batch_size: int,
    trial: int,
    wave_index: int,
) -> int:
    _check_cell(replica, batch_size, trial)
    _check_wave_index(wave_index)
    if profile == BARRIER_IMMEDIATE:
        return 0
    if profile == BARRIER_JITTERED:
        permutation = jitter_gap_permutation(replica, batch_size, trial)
        return permutation[wave_index % len(permutation)]
    raise ScheduleInputError("unknown schedule profile")


def next_wave_eligible_ns(
    profile: str,
    replica: str,
    batch_size: int,
    trial: int,
    wave_index: int,
    quiescence_ns: int,
) -> int:
    _check_ns(quiescence_ns, "quiescence_ns")
    gap_ms = requested_gap_ms(profile, replica, batch_size, trial, wave_index)
    return quiescence_ns + gap_ms * NS_PER_MS


def transition_disposition(
    profile: str,
    replica: str,
    batch_size: int,
    trial: int,
    wave_index: int,
    quiescence_ns: int,
    next_wave_actual_start_ns: int,
) -> str:
    _check_ns(quiescence_ns, "quiescence_ns")
    _check_ns(next_wave_actual_start_ns, "next_wave_actual_start_ns")
    eligible_ns = next_wave_eligible_ns(
        profile, replica, batch_size, trial, wave_index, quiescence_ns
    )
    if next_wave_actual_start_ns < quiescence_ns:
        return BEFORE_QUIESCENCE
    if next_wave_actual_start_ns < eligible_ns:
        return BEFORE_REQUIRED_GAP
    return ADMISSIBLE


def post_barrier_observed_gap_ns(
    quiescence_ns: int,
    next_wave_actual_start_ns: int,
) -> int:
    _check_ns(quiescence_ns, "quiescence_ns")
    _check_ns(next_wave_actual_start_ns, "next_wave_actual_start_ns")
    return next_wave_actual_start_ns - quiescence_ns


def host_start_lateness_after_eligibility_ns(
    eligible_ns: int,
    next_wave_actual_start_ns: int,
) -> int:
    _check_ns(eligible_ns, "eligible_ns")
    _check_ns(next_wave_actual_start_ns, "next_wave_actual_start_ns")
    return max(0, next_wave_actual_start_ns - eligible_ns)


def counterfactual_s3c1_500ms_overrun(
    wave_actual_start_ns: int,
    post_decision_quiescence_ns: int,
) -> bool:
    _check_ns(wave_actual_start_ns, "wave_actual_start_ns")
    _check_ns(post_decision_quiescence_ns, "post_decision_quiescence_ns")
    if post_decision_quiescence_ns < wave_actual_start_ns:
        raise ScheduleInputError("quiescence precedes wave start")
    return post_decision_quiescence_ns - wave_actual_start_ns > S3C1_PERIOD_NS
