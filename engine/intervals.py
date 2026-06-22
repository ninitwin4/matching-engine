"""Generic closed-interval overlap — one mechanism, many constraint
instances (ADR-001 amendment 2026-06-12 §2).

Works on any mutually comparable bound types: numbers, or ISO-format date
strings (which order correctly as strings). A None bound is unbounded.
Touching endpoints count as overlap.
"""

from typing import Sequence


def intervals_overlap(a: Sequence, b: Sequence) -> bool:
    a_lo, a_hi = a
    b_lo, b_hi = b
    if a_lo is not None and b_hi is not None and a_lo > b_hi:
        return False
    if b_lo is not None and a_hi is not None and b_lo > a_hi:
        return False
    return True
