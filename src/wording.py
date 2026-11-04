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


# --------------------------------------------------------------------------- #
# Chapter V: the calendar and the forecasting models
# --------------------------------------------------------------------------- #
def money(x: float, currency: str = "USD") -> str:
    """12345 -> 'USD 12.3k' (absolute value; the sentence carries the sign)."""
    x = abs(x)
    if x >= 1e6:
        return f"{currency} {x / 1e6:.2f}m"
    if x >= 1e3:
        return f"{currency} {x / 1e3:.1f}k"
    return f"{currency} {x:.0f}"


def model_comparison_sentence(currency: str, winner_label: str, winner_loss: float, baseline_loss: float,
                              p_value: float | None, winner_is_baseline: bool) -> str:
    """Who won on test-period turn days, by how much, and whether it is significant."""
    if winner_is_baseline:
        return (f"In {currency} the naive baseline (same as the last comparable turn) had the lowest test-period "
                f"pinball loss on turn days ({winner_loss:.2f}); neither regression beat it.")
    gain = 1 - winner_loss / baseline_loss if baseline_loss else float("nan")
    sig = significance_phrase(p_value) if p_value is not None else "not testable"
    return (f"In {currency} the {winner_label.lower()} had the lowest test-period pinball loss on turn days "
            f"({winner_loss:.2f} against {baseline_loss:.2f} for the baseline, {gain:.0%} lower); the difference "
            f"is {sig}.")


def yearend_contrast_sentence(usd_mean: float, usd_share_up: float, usd_n: int,
                              eur_mean: float, eur_share_up: float, eur_n: int) -> str:
    """Direction and size of the year-end turn in each currency."""
    def one(name: str, mean: float, share: float, n: int) -> str:
        direction = "rose" if mean > 0 else "fell"
        return (f"{name} {direction} by {bp(mean)} on average at the year-end turn relative to the previous "
                f"two weeks ({share:.0%} of {n} year-ends up)")
    same = (usd_mean > 0) == (eur_mean > 0)
    link = "; in the same direction," if same else "; in the opposite direction,"
    return f"{one('The dollar spread (SOFR minus IOR)', usd_mean, usd_share_up, usd_n)}{link} " \
           f"{one('the euro spread (€STR minus DFR)', eur_mean, eur_share_up, eur_n)}."


def yearend_mechanism_sentence(usd_mean: float, eur_mean: float) -> str:
    """Why the two currencies differ, stated only when the data shows the difference."""
    if usd_mean > 0 >= eur_mean:
        return ("The pattern fits the two market structures: in dollars, banks shrink their balance sheets for "
                "year-end reporting and stop intermediating repo, so cash borrowers pay up; in euros, €STR is a "
                "deposit rate that banks pay to non-banks, and when banks turn deposits away at year-end, "
                "that rate falls further below the deposit facility rate.")
    if usd_mean > 0 and eur_mean > 0:
        return "Both currencies show year-end funding pressure, larger in dollars." if usd_mean > eur_mean else \
            "Both currencies show year-end funding pressure, larger in euros."
    return "Neither currency shows the usual dollar year-end squeeze in this sample."


def term_rule_sentence(saving_vs_on: float, saving_vs_term: float, n_locked: int, n_windows: int,
                       notional_label: str = "USD 100m") -> str:
    """Backtest of 'lock in term funding only when the forecast spike exceeds the term premium'."""
    vs_on = "saved" if saving_vs_on > 0 else "cost"
    vs_term = "saved" if saving_vs_term > 0 else "cost"
    return (f"On the test period the rule locked in term funding for {n_locked} of {n_windows} month-end turns; "
            f"per {notional_label} it {vs_on} {money(saving_vs_on)} against always borrowing overnight and "
            f"{vs_term} {money(saving_vs_term)} against always borrowing term.")


def calendar_answer(usd_win: bool, eur_win: bool, usd_p: float | None, eur_p: float | None,
                    usd_mean: float, eur_mean: float, test_start: str = "2023") -> tuple[str, str]:
    """(answer, explanation) for chapter V's question box."""
    significant = [c for c, w, p in (("dollars", usd_win, usd_p), ("euros", eur_win, eur_p))
                   if w and p is not None and p < 0.05]
    beaten = [c for c, w in (("dollars", usd_win), ("euros", eur_win)) if w]
    if len(significant) == 2:
        answer = "Yes, in both currencies"
    elif significant:
        answer = f"Partly: reliably in {significant[0]}"
    elif beaten:
        answer = "Partly: the models beat a naive rule, but not significantly"
    else:
        answer = "Not better than a naive rule"
    direction = ("dollar turns push funding costs up while euro turns push them down" if usd_mean > 0 >= eur_mean
                 else "the two currencies' turns move in the same direction")
    return answer, (f"Judged on the test period from {test_start}: the forecasts are compared with what happened. "
                    f"Across every year-end in the data, {direction} "
                    f"({signed_bp(usd_mean)} and {signed_bp(eur_mean)} on an average year-end).")
