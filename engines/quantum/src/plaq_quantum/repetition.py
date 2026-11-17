"""Repetition-code QEC that works without Stim.

Majority-vote decode of a length-d bit-flip repetition code. This is the
lite-profile stand-in for ``quantum.simulate`` so agents can still demo
logical vs physical error when C++ wheels are missing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict

import numpy as np


@dataclass
class RepetitionResult:
    distance: int
    physical_error: float
    shots: int
    logical_errors: int
    logical_error_rate: float
    majority_threshold: int
    seed: int
    model: str = "bit_flip_repetition_majority"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def run_repetition_code(
    distance: int = 3,
    physical_error: float = 0.1,
    shots: int = 2000,
    seed: int = 0,
    encoded_bit: int = 0,
) -> RepetitionResult:
    d = max(1, int(distance))
    if d % 2 == 0:
        d += 1
    p = float(min(1.0, max(0.0, physical_error)))
    rng = np.random.default_rng(int(seed))
    flips = rng.random((int(shots), d)) < p
    votes = flips.sum(axis=1)
    decoded = (votes > d / 2).astype(int)
    logical_errors = int(np.sum(decoded != int(encoded_bit) % 2))
    return RepetitionResult(
        distance=d,
        physical_error=p,
        shots=int(shots),
        logical_errors=logical_errors,
        logical_error_rate=logical_errors / float(shots or 1),
        majority_threshold=d // 2,
        seed=int(seed),
    )
