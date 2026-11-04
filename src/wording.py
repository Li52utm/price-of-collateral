"""Conclusion sentences that depend on the numbers (pure functions, no Streamlit).

Every sentence that states a verdict is built here, so it changes with the data:
"wider" vs "narrower", "beat" vs "did not beat", "Yes" vs "No". tests/test_wording.py
runs each function with the sign flipped. Pages and the README never type a conclusion.
"""

from __future__ import annotations


# --------------------------------------------------------------------------- #
# Small building blocks
# --------------------------------------------------------------------------- #
def above_or_below(x: float) -> str:
    return "above" if x > 0 else "below" if x < 0 else "at"


def wider_or_narrower(x: float) -> str:
    return "wider" if x > 0 else "narrower" if x < 0 else "unchanged"


def rose_or_fell(x: float) -> str:
    return "rose" if x > 0 else "fell" if x < 0 else "was unchanged"


def bp(x: float, decimals: int = 1) -> str:
    """3.24 -> '3.2 bp' (absolute value; the sentence carries the sign)."""
    return f"{abs(x):.{decimals}f} bp"


def signed_bp(x: float, decimals: int = 1) -> str:
    return f"{x:+.{decimals}f} bp"


def share_words(k: int, n: int) -> str:
    """'3 of 5'; 'none of 5'; 'all 5'."""
    if n == 0:
        return "none of 0"
    if k == 0:
        return f"none of {n}"
    if k == n:
        return f"all {n}" if n > 2 else ("both" if n == 2 else "the only one")
    return f"{k} of {n}"


def significance_phrase(p_value: float, alpha: float = 0.05) -> str:
    """'statistically significant (p = 0.012)' or 'not statistically significant (p = 0.310)'."""
    if p_value != p_value:  # NaN
        return "not testable"
    word = "statistically significant" if p_value < alpha else "not statistically significant"
    return f"{word} (p = {p_value:.3f})" if p_value >= 0.001 else f"{word} (p < 0.001)"
