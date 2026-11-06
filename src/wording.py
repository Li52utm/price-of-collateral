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
    """'above', 'below' or 'at' for the sign of x."""
    return "above" if x > 0 else "below" if x < 0 else "at"


def wider_or_narrower(x: float) -> str:
    """'wider', 'narrower' or 'unchanged' for the sign of x."""
    return "wider" if x > 0 else "narrower" if x < 0 else "unchanged"


def more_or_less(x: float) -> str:
    """'more' for a positive difference, 'less' for a negative one (the number is printed as a magnitude)."""
    return "more" if x >= 0 else "less"


def rose_or_fell(x: float) -> str:
    """'rose', 'fell' or 'was unchanged' for the sign of x."""
    return "rose" if x > 0 else "fell" if x < 0 else "was unchanged"


def bp(x: float, decimals: int = 1) -> str:
    """3.24 -> '3.2 bp' (absolute value; the sentence carries the sign)."""
    return f"{abs(x):.{decimals}f} bp"


def signed_bp(x: float, decimals: int = 1) -> str:
    """x with its sign in basis points, e.g. '+3.2 bp'."""
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


def significance_phrase(p_value: float, alpha: float = 0.05, adjusted: bool = False) -> str:
    """'statistically significant (p = 0.012)' or 'not statistically significant (Holm-adjusted p = 0.310)'."""
    if p_value is None or p_value != p_value:  # NaN
        return "not testable"
    word = "statistically significant" if p_value < alpha else "not statistically significant"
    label = "Holm-adjusted p" if adjusted else "p"
    return f"{word} ({label} = {p_value:.3f})" if p_value >= 0.001 else f"{word} ({label} < 0.001)"


def ci_text(lower: float | None, upper: float | None, unit: str = " bp", decimals: int = 1) -> str:
    """'95% CI -1.1 to -0.1 bp' (signed bounds), or '' when the interval is missing."""
    if lower is None or upper is None or lower != lower or upper != upper:
        return ""
    return f"95% CI {lower:+.{decimals}f} to {upper:+.{decimals}f}{unit}"


def excludes_zero(lower: float | None, upper: float | None) -> bool:
    """True if a confidence interval lies entirely on one side of zero."""
    return lower is not None and upper is not None and lower == lower and (lower > 0 or upper < 0)


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
                              p_value: float | None, winner_is_baseline: bool, ci: dict | None = None,
                              adjusted: bool = False) -> str:
    """Who won on test-period turn days, by how much, and whether it is significant (Holm-adjusted DM)."""
    if winner_is_baseline:
        return (f"In {currency} the naive baseline (same as the last comparable turn) had the lowest test-period "
                f"pinball loss on turn days ({winner_loss:.2f}); neither regression beat it.")
    gain = 1 - winner_loss / baseline_loss if baseline_loss else float("nan")
    sig = significance_phrase(p_value, adjusted=adjusted) if p_value is not None else "not testable"
    text = (f"In {currency} the {winner_label.lower()} had the lowest test-period pinball loss on turn days "
            f"({winner_loss:.2f} against {baseline_loss:.2f} for the baseline, {gain:.0%} lower); the difference "
            f"is {sig}")
    if ci and ci.get("lower") is not None and ci["lower"] == ci["lower"]:
        side = ("excludes zero" if excludes_zero(ci["lower"], ci["upper"]) else "includes zero")
        text += (f"; the block-bootstrap interval of the loss difference ({ci_text(ci['lower'], ci['upper'], '', 2)}) "
                 f"{side}")
    return text + "."


def yearend_contrast_sentence(usd_mean: float, usd_share_up: float, usd_n: int,
                              eur_mean: float, eur_share_up: float, eur_n: int) -> str:
    """Direction and size of the year-end turn in each currency."""
    def one(name: str, mean: float, share: float, n: int) -> str:
        direction = rose_or_fell(mean)
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
                    usd_mean: float, eur_mean: float, test_start: str = "2023",
                    calibration: dict | None = None) -> tuple[str, str]:
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
    beat = " and ".join(beaten) if beaten else "neither currency"
    sig = " and ".join(significant) if significant else "neither"
    text = (f"On the test period from {test_start}, a quantile model with calendar and state variables beat "
            f"the naive same-as-last-turn rule on turn days in {beat} (significantly in {sig}, after a Holm "
            f"correction across the six model comparisons). Across every year-end in the data, {direction} "
            f"({signed_bp(usd_mean)} and {signed_bp(eur_mean)} on an average year-end).")
    if calibration:
        parts = [f"{c} {v}" for c, v in calibration.items()]
        text += f" Calibration of the 5-95% ranges on the test period: {', '.join(parts)}."
    return answer, text


# --------------------------------------------------------------------------- #
# Chapter II: three corridors
# --------------------------------------------------------------------------- #
CURRENCY_NAMES = {"EUR": "the ECB", "USD": "the Fed", "JPY": "the BoJ"}
MARKET_NAMES = {"EUR": "€STR", "USD": "SOFR", "JPY": "TONA"}


def corridor_sentence(currency: str, inside_share: float, below_share: float, median_bp: float, iqr_bp: float,
                      start: str) -> str:
    """How often the market rate stayed inside the corridor and how tightly over the past year."""
    tight = "tightly" if iqr_bp <= 3 else "loosely"
    where = (f"{MARKET_NAMES[currency]} stayed inside {CURRENCY_NAMES[currency]}'s corridor on {inside_share:.1%} of "
             "days"
             if below_share < 0.5 else
             f"{MARKET_NAMES[currency]} traded below {CURRENCY_NAMES[currency]}'s floor on {below_share:.1%} of days, "
             "as expected in a floor system: its lenders include institutions that cannot deposit at the central "
             "bank, so they accept less than the floor")
    return (f"Since {start[:4]}, {where}. Over the past year it sat {bp(median_bp)} {above_or_below(median_bp)} the "
            f"policy rate, held {tight} (interquartile range {bp(iqr_bp)}).")


def markov_sentence(currency: str, calm_mean: float, stressed_mean: float, stressed_sd: float, calm_sd: float,
                    test_ll: float, normal_ll: float, share_test: float) -> str:
    """The two Markov regimes and whether the model travels out of sample."""
    better = test_ll > normal_ll
    fit = ("fitted the test period better than a single normal distribution" if better
           else "fitted the test period worse than a single normal distribution, so it does not travel out of sample")
    meaning = ("the volatile regime is also the expensive one, so it reads as funding stress"
               if stressed_mean > calm_mean else
               "the volatile regime is the one further below the policy rate, so the regimes describe how deep the "
               "floor sits rather than stress")
    return (f"For {MARKET_NAMES[currency]}, the two regimes average {signed_bp(calm_mean)} (sd {bp(calm_sd)}) and "
            f"{signed_bp(stressed_mean)} (sd {bp(stressed_sd)}); {meaning}. Estimated on 2022 and earlier, the model "
            f"{fit}, and it placed {share_test:.0%} of test days in the volatile regime.")


def reserves_sentence(currency: str, winner: str, slope: float, point: float, band: list, latest: float,
                      unit: str, identified: bool = True, edge_share: float | None = None) -> str:
    """Slope of the spread on liquidity, and where pressure starts only if the kink is identified (U0)."""
    move = "rises" if slope < 0 else "falls"
    head = (f"Out of sample, the best description of the link between {unit} and the spread is {winner}: "
            f"the spread {move} by about {bp(slope)} for each 1 trillion less.")
    if point != point:
        return head
    if not identified:
        share = (f" ({edge_share:.0%} of bootstrap estimates sit at the edge of the search range)"
                 if edge_share is not None else "")
        return (f"{head} The point where pressure starts is not identified: the estimated kink lies at the edge of "
                f"the range searched{share}, so the data cannot place it.")
    where = ("below" if latest < band[0] else "inside" if latest <= band[1] else "above")
    caveat = "" if winner != "linear" else " (a reference only: the threshold model did not win out of sample)"
    return (f"{head} The estimated point where pressure starts is {point:.2f} trillion{caveat}, with a 95% band of "
            f"{band[0]:.2f} to {band[1]:.2f}; the latest level, {latest:.2f}, is {where} that band.")


def case_sentence(case: str, currency: str, peak: float, peak_date: str, before: float) -> str:
    """Peak of an episode against the level of the two weeks before."""
    jump = peak - before
    return (f"{case}: {MARKET_NAMES[currency]} peaked at {signed_bp(peak)} against the policy rate on "
            f"{pd_day(peak_date)}, {bp(jump)} {'above' if jump > 0 else 'below'} its level in the two weeks before.")


def pd_day(iso: str) -> str:
    """An ISO date as '3 November 2026'."""
    import pandas as pd
    ts = pd.Timestamp(iso)
    return f"{ts.day} {ts:%B %Y}"


def corridors_answer(stats: dict, reserves: dict, slope_ci: dict | None = None) -> tuple[str, str]:
    """(answer, explanation) for chapter II: held tightly over the past year, and the balance-sheet effect."""
    tight = [c for c, s in stats.items() if s["recent_iqr_bp"] <= 3]
    answer = ("Yes, within a few basis points" if len(tight) == len(stats) else
              f"Mostly: {share_words(len(tight), len(stats))} held tightly")
    usd = reserves.get("USD", {})
    slope = usd.get("slope_per_unit", 0)
    ci = ""
    if slope_ci and slope_ci.get("lower") is not None:
        # The interval is for the slope (negative = the spread rises as reserves fall); shown as a magnitude.
        if slope_ci["upper"] < 0:
            ci = f" (95% CI {abs(slope_ci['upper']):.1f} to {abs(slope_ci['lower']):.1f} bp)"
        else:
            ci = f" ({ci_text(slope_ci['lower'], slope_ci['upper'])} for the slope)"
    tail = (f"As balance sheets shrink, SOFR has drifted up relative to the Fed's interest on reserves, about "
            f"{bp(slope)} per trillion of reserves lost{ci}" if slope < 0 else
            "Shrinking reserves have not pushed SOFR up relative to interest on reserves")
    spreads = ", ".join(f"{MARKET_NAMES[c]} {signed_bp(s['recent_median_bp'])} (IQR {bp(s['recent_iqr_bp'])})"
                        for c, s in stats.items())
    return answer, f"Past-year median spread to the policy rate: {spreads}. {tail}."


# --------------------------------------------------------------------------- #
# Chapter III: credit or scarcity
# --------------------------------------------------------------------------- #
COUNTRY_NAMES = {"IT": "Italian", "FR": "French", "ES": "Spanish", "DE": "German"}


def verdict_phrase(verdict: str) -> str:
    """Plain words for a chapter III verdict."""
    return {"credit": "mainly credit risk", "scarcity": "mainly scarcity of German collateral",
            "both / unclear": "neither clearly credit nor scarcity",
            "too close to call": "too close to call between credit and scarcity"}[verdict]


def final_verdict(verdict: str, too_close: bool | None) -> str:
    """U2 rule: if the interval of the credit-scarcity difference includes zero, 'too close to call'."""
    return "too close to call" if too_close else verdict


def credit_scarcity_ci_sentence(country: str, diff: float, lower: float, upper: float) -> str:
    """The interval of |credit| - (|liquidity| + |holdings|) in standardised bp and what it means."""
    if not excludes_zero(lower, upper):
        meaning = "it includes zero, so the data cannot say which channel is larger: too close to call"
    elif upper < 0:
        meaning = "it lies below zero, so the scarcity effects are larger than the credit effect"
    else:
        meaning = "it lies above zero, so the credit effect is larger than the scarcity effects"
    return (f"For {COUNTRY_NAMES[country]} collateral the credit effect minus the scarcity effects is "
            f"{signed_bp(diff)} ({ci_text(lower, upper)}); {meaning}.")


def collateral_sentence(country: str, verdict: str, credit_effect: float, scarcity_effect: float, r2: float,
                        mean_spread: float, latest: float) -> str:
    """Average collateral premium, fit and the standardised credit and scarcity effects."""
    return (f"{COUNTRY_NAMES[country]} collateral cost {bp(mean_spread)} {more_or_less(mean_spread)} than German "
            f"collateral in repo on "
            f"average (latest {signed_bp(latest)}). The regression explains {r2:.0%} of the variation and reads as "
            f"{verdict_phrase(verdict)}: a one-standard-deviation move in the yield spread is worth "
            f"{signed_bp(credit_effect)}, the two scarcity measures together {bp(scarcity_effect)}.")


def qt_break_sentence(country: str, p_value: float, before: str | None, after: str | None,
                      adjusted: bool = False) -> str:
    """Chow break at the start of QT, with the sub-period verdicts."""
    changed = p_value < 0.05
    head = (f"The relationship for {COUNTRY_NAMES[country]} collateral changed at the start of quantitative "
            f"tightening; the break is {significance_phrase(p_value, adjusted=adjusted)}" if changed else
            f"There is no significant break for {COUNTRY_NAMES[country]} collateral at the start of quantitative "
            f"tightening; the test is {significance_phrase(p_value, adjusted=adjusted)}")
    if before and after:
        if before == after:
            return head + f"; it reads as {verdict_phrase(before)} both before and after."
        return head + f": {verdict_phrase(before)} before, {verdict_phrase(after)} after."
    return head + "."


def collateral_answer(it_verdict: str, fr_verdict: str, it_break_p: float, fr_break_p: float,
                      ci_lines: list[str] | None = None) -> tuple[str, str]:
    """(answer, explanation) for chapter III; verdicts already include the 'too close to call' rule."""
    verdicts = (it_verdict, fr_verdict)
    unclear = ("both / unclear", "too close to call")
    if all(v in unclear for v in verdicts):
        answer = ("Too close to call" if "too close to call" in verdicts else "Neither clearly")
        breaks = sum(p < 0.05 for p in (it_break_p, fr_break_p))
        which = {0: "neither country", 1: "one of the two countries", 2: "both countries"}[breaks]
        return answer, (f"Italian collateral: {verdict_phrase(it_verdict)}; French collateral: "
                        f"{verdict_phrase(fr_verdict)}. " + (" ".join(ci_lines) + " " if ci_lines else "") +
                        f"The relationship broke at the start of quantitative tightening for {which} (Holm-adjusted).")
    if it_verdict == fr_verdict and it_verdict != "both / unclear":
        answer = "Mostly " + ("credit risk" if it_verdict == "credit" else "scarcity")
    elif "scarcity" in verdicts and "credit" not in verdicts:
        answer = ("Scarcity for Italy; no clear driver for France" if it_verdict == "scarcity"
                  else "Scarcity for France; no clear driver for Italy")
    elif "credit" in verdicts and "scarcity" not in verdicts:
        answer = ("Credit for Italy; no clear driver for France" if it_verdict == "credit"
                  else "Credit for France; no clear driver for Italy")
    elif it_verdict == fr_verdict:
        answer = "Neither clearly"
    else:
        answer = "Both, in different places"
    breaks = sum(p < 0.05 for p in (it_break_p, fr_break_p))
    which = {0: "neither country", 1: "one of the two countries", 2: "both countries"}[breaks]
    return answer, (f"Italian collateral: {verdict_phrase(it_verdict)}; French collateral: "
                    f"{verdict_phrase(fr_verdict)}. "
                    + (" ".join(ci_lines) + " " if ci_lines else "") +
                    f"The relationship broke at the start of quantitative tightening for {which} (Holm-adjusted).")


# --------------------------------------------------------------------------- #
# Chapter IV: Italy then, France now
# --------------------------------------------------------------------------- #
def decomposition_sentence(base_month: str, last_month: str, spread_base: float, spread_last: float,
                           oat_leg: float, bund_contribution: float) -> str:
    """oat_leg = change in the OAT yield; bund_contribution = minus the change in the Bund yield (bp)."""
    bund_move = "fell" if bund_contribution > 0 else "rose"
    widened = spread_last > spread_base
    if oat_leg * bund_contribution > 0:
        source = "both legs"
    elif abs(oat_leg) > abs(bund_contribution):
        source = "the OAT leg, partly offset by the Bund leg"
    else:
        source = "the Bund leg, partly offset by the OAT leg"
    return (f"From {base_month} to {last_month} the OAT-Bund spread went from {bp(spread_base, 0)} to "
            f"{bp(spread_last, 0)}. OAT yields {rose_or_fell(oat_leg)} by {bp(oat_leg, 0)} and Bund yields "
            f"{bund_move} by {bp(bund_contribution, 0)}, so the {'widening' if widened else 'tightening'} came from "
            f"{source}.")


def france_specific_sentence(since: str, cum_change: float, euro_wide: float, france_specific: float,
                             ci_france: dict | None = None, ci_euro: dict | None = None) -> str:
    """Euro-wide vs France-specific parts of the widening, with bootstrap intervals when available."""
    share = france_specific / cum_change if cum_change else float("nan")
    own = "France-specific" if abs(france_specific) > abs(euro_wide) else "euro-wide"
    cf = f", {ci_text(ci_france['lower'], ci_france['upper'], ' bp', 0)}" if ci_france else ""
    ce = f", {ci_text(ci_euro['lower'], ci_euro['upper'], ' bp', 0)}" if ci_euro else ""
    text = (f"Since {since} the French spread moved {signed_bp(cum_change)}: {signed_bp(euro_wide)} is what Italian "
            f"and Spanish spreads would have implied (euro-wide{ce}), {signed_bp(france_specific)} is France-specific "
            f"({share:.0%} of the move{cf}). The move has been mainly {own}")
    if ci_france and excludes_zero(ci_france["lower"], ci_france["upper"]) and ci_france["lower"] > 0:
        text += ", and the France-specific part is clearly above zero"
    return text + "."


def survival_sentence(n: int, n_countries: int, median: float, s12: float, s12_lo: float, s12_hi: float,
                      threshold: float) -> str:
    """Base rates of blowout recoveries from the Kaplan-Meier curve."""
    return (f"Across {n} blowouts of {bp(threshold, 0)} or more in {n_countries} euro countries since 2008, the "
            f"median time to retrace half the widening was {median:.0f} months; {1 - s12:.0%} had done so within a "
            f"year (95% band {1 - s12_hi:.0%} to {1 - s12_lo:.0%}). The sample is small and the episodes overlap in "
            "time, so these are base rates, not forecasts.")


def france_status_sentence(in_episode: bool, spread_now: float, baseline: float | None, gap: float | None,
                           threshold: float, sens_threshold: float | None = None, sens_start: str | None = None,
                           sens_p12: float | None = None) -> str:
    """France's status under the monthly blowout rule (and the 20 bp sensitivity)."""
    if in_episode:
        return f"By the {bp(threshold, 0)} rule France is in a blowout episode, with the spread at {bp(spread_now, 0)}."
    text = (f"By the {bp(threshold, 0)} rule France is not in a blowout: at {bp(spread_now, 0)} the spread is "
            f"{bp(gap, 1)} short of its trailing one-year average ({bp(baseline, 0)}) plus {bp(threshold, 0)}. The "
            "widening since 2024 has been a steady grind rather than a jump, so the trailing average has risen with "
            "it.")
    if sens_threshold is not None and sens_start is not None:
        text += (f" With the looser {bp(sens_threshold, 0)} rule an episode starts in {sens_start}; for episodes of "
                 f"that kind the chance of retracing half the widening within 12 months was {sens_p12:.0%}.")
    return text


def repo_treatment_sentence(fr_before: float, fr_after: float, it_before: float, it_after: float,
                            pos_before: float, pos_after: float, p_gap: float, latest_fr: float,
                            latest_it: float, adjusted: bool = False) -> str:
    """Whether French collateral moved towards Italian pricing after June 2024."""
    closer = pos_after > pos_before
    text = (f"In repo, French collateral moved {'closer to Italian' if closer else 'away from Italian'} pricing after "
            f"June 2024: its spread to German collateral went from {signed_bp(fr_before)} to {signed_bp(fr_after)}, "
            "the "
            f"Italian spread from {signed_bp(it_before)} to {signed_bp(it_after)}, and France's position between "
            "Germany "
            f"(0) and Italy (1) "
            f"from {pos_before:.2f} to {pos_after:.2f}. The change in the Italy-France gap is "
            f"{significance_phrase(p_gap, adjusted=adjusted)}.")
    if latest_fr > latest_it:
        text += (f" In the latest period French collateral cost more than Italian ({signed_bp(latest_fr)} against "
                 f"{signed_bp(latest_it)}).")
    return text


def event_sentence(event: str, month: str, change: float, percentile: float) -> str:
    """Monthly change in the spread in an event month and how unusual it was."""
    size = ("an unusually large" if percentile >= 0.9 else "a larger than typical" if percentile >= 0.5
            else "a smaller than typical")
    move = "widened" if change > 0 else "narrowed" if change < 0 else "was unchanged"
    return (f"{event} ({month}): the OAT-Bund spread {move} by {bp(change)} that month, {size} move "
            f"({percentile:.0%} of months since 2010 saw a smaller change).")


def daily_status_phrase(in_blowout: bool, start: str | None, spread: float, day: str, in_gradual: bool,
                        monthly_in_episode: bool) -> str:
    """France's status by the daily rules (U1), with the monthly rule as the robustness check."""
    if in_blowout:
        head = (f"By the daily rule France has been in a blowout episode since {pd_day(start)}, with the OAT-Bund "
                f"spread at {bp(spread, 0)} on {pd_day(day)}")
    else:
        head = f"By the daily rule France is not in a blowout (spread {bp(spread, 0)} on {pd_day(day)})"
    tail = f"; it {'meets' if in_gradual else 'does not meet'} the gradual-deterioration rule"
    agree = ("the monthly rule agrees" if monthly_in_episode == in_blowout else
             "the monthly rule, whose data end earlier, does not yet show it" if in_blowout else
             "the monthly rule disagrees")
    return f"{head}{tail}; {agree}"


def oat_answer(in_episode: bool, median_months: float, p_half_12: float, share_cut: float, share_peers: float,
               share_buying: float | None, now_cut: bool, now_peers: bool, now_buying: bool | None,
               france_specific_share: float, status_text: str | None = None,
               p_next_12: float | None = None) -> tuple[str, str]:
    """Will French OATs bounce back? Base rates and conditions only; never a political prediction."""
    met = [name for name, ok in (("ECB easing", now_cut), ("other spreads tightening", now_peers),
                                 ("Eurosystem buying", bool(now_buying))) if ok]
    if len(met) >= 2:
        answer = "Possibly: most of the conditions that preceded past recoveries are in place"
    elif len(met) == 1:
        answer = "Not yet: only one of the three conditions that preceded past recoveries is in place"
    else:
        answer = "Not yet: none of the conditions that preceded past recoveries is in place"
    status = status_text or ("France is in a blowout episode by the main rule" if in_episode else
                             "By the main rule France is not in a blowout: its spread has widened steadily rather "
                             "than jumped")
    if in_episode and p_next_12 is not None:
        status += (f". For a blowout of its current age, {p_next_12:.0%} of past euro episodes retraced half the "
                   "widening within the next 12 months")
    buying = f", and the Eurosystem was a net buyer in {share_buying:.0%}" if share_buying is not None else ""
    explanation = (f"{status}. Historically the median euro blowout retraced half its widening in {median_months:.0f} "
                   f"months and {p_half_12:.0%} did so within a year. Before those recoveries the ECB had cut rates in "
                   f"{share_cut:.0%} of cases, other countries' spreads were tightening in {share_peers:.0%}{buying}. "
                   f"Now: {', '.join(met) if met else 'none of these'}. With {france_specific_share:.0%} of the "
                   "widening France-specific, what would help most is a France-specific improvement in the fiscal "
                   "outlook; the data cannot say whether that will happen.")
    return answer, explanation


# --------------------------------------------------------------------------- #
# Chapter VI: Japan
# --------------------------------------------------------------------------- #
def _days_ci(ci: dict | None) -> str:
    """' (95% CI 0.3 to 0.6)' for a half-life interval, or ''."""
    if not ci or ci.get("lower") is None or ci["lower"] != ci["lower"]:
        return ""
    return f" (95% CI {ci['lower']:.1f} to {ci['upper']:.1f})"


def japan_change_sentence(date: str, change_bp: float, days: int | None, pass_20d: float) -> str:
    """How fast TONA closed the gap after one BoJ policy change."""
    direction = "rise" if change_bp > 0 else "cut"
    speed = ("on the effective day" if days == 0 else f"after {days} business days" if days is not None
             else "not within 60 business days")
    return (f"{pd_day(date)}, a {bp(change_bp, 0)} {direction}: TONA closed half the gap {speed} and moved "
            f"{pass_20d:.0%} of the change on average over the first 20 business days.")


def japan_answer(n_changes: int, n_same_day: int, exit_half_life: float, negative_half_life: float,
                 latest_gap_bp: float, exit_ci: dict | None = None, negative_ci: dict | None = None) -> tuple[str, str]:
    """(answer, explanation) for chapter VI."""
    if n_same_day == n_changes:
        answer = "Yes, immediately"
    elif n_same_day >= n_changes / 2:
        answer = "Yes, since the exit; the regime changes passed through more slowly"
    else:
        answer = "Only partly"
    return answer, (f"{n_same_day} of {n_changes} BoJ policy changes since 2016 reached TONA on the effective day. "
                    f"After the exit, a gap between TONA and the policy rate halves in {exit_half_life:.1f} business "
                    f"days{_days_ci(exit_ci)}, against {negative_half_life:.1f}{_days_ci(negative_ci)} under negative "
                    f"rates. TONA now sits "
                    f"{bp(latest_gap_bp)} {above_or_below(latest_gap_bp)} the policy rate.")


# --------------------------------------------------------------------------- #
# Chapter I and VII
# --------------------------------------------------------------------------- #
def story_answer(it_mean: float, it_latest: float, fr_latest: float, it_latest_2: float) -> tuple[str, str]:
    """Repo in one line, and the collateral effect in numbers."""
    ranking = ("French collateral now costs more than Italian" if fr_latest > it_latest_2 else
               "French collateral still costs less than Italian")
    return ("A secured overnight loan, and the bond changes the price",
            f"Repo is borrowing cash against a government bond, like a pawn shop for bonds. Lending against Italian "
            f"bonds has paid {bp(it_mean)} {more_or_less(it_mean)} than lending against German bonds on average since "
            "2018 "
            f"(latest {signed_bp(it_latest)}); {ranking} ({signed_bp(fr_latest)}).")


def term_out_line(currency: str, excess_bp: float, premium_bp: float | None, threshold_bp: float,
                  turn_median_bp: float | None = None) -> tuple[bool, str]:
    """(term out?, sentence) for one currency (rule in METHODOLOGY.md, Phase 6, corrected in U0).

    Term out iff the expected night-weighted excess overnight cost exceeds the hurdle: the term premium
    (term minus overnight; negative = term is cheaper) or, without a usable premium, a fixed hurdle.
    """
    hurdle = premium_bp if premium_bp is not None else threshold_bp
    lock = excess_bp > hurdle
    if premium_bp is None:
        what = f"a {bp(threshold_bp, 0)} hurdle (no usable term rate)"
    elif premium_bp < 0:
        what = f"the term premium ({signed_bp(premium_bp)}: term funding is {bp(premium_bp)} cheaper than overnight)"
    elif premium_bp > 0:
        what = f"the term premium ({signed_bp(premium_bp)}: term funding costs {bp(premium_bp)} more than overnight)"
    else:
        what = "the term premium (zero: term and overnight cost the same)"
    verdict = "Term out" if lock else "Stay overnight"
    turn = f"the 31 December median is {signed_bp(turn_median_bp)}, and " if turn_median_bp is not None else ""
    return lock, (f"{currency}: {verdict}. Over the 14 nights from 7 business days before the turn, {turn}the forecast "
                  f"puts overnight funding {signed_bp(excess_bp)} away from today's level on average (weighted by "
                  f"nights), {above_or_below(excess_bp - hurdle)} {what}.")


def term_freshness_sentence(term_date: str, age_bd: int, stale: bool, limit_bd: int) -> str:
    """Always-shown status of the OFR term rate used for the term premium."""
    state = ("stale, so the 1 bp hurdle replaces the premium" if stale else
             "recent enough to use (the limit is " + str(limit_bd) + " business days)")
    return (f"Term premium input: the latest published OFR term repo rate is from {pd_day(term_date)}, {age_bd} "
            f"business day{'s' if age_bd != 1 else ''} before the data's as-of date: {state}.")


def term_staleness_sentence(term_date: str | None, age_bd: int | None, stale: bool, limit_bd: int) -> str:
    """Empty when the term rate is fresh; otherwise says it is stale and that the hurdle replaced it."""
    if not stale or term_date is None:
        return ""
    return (f"The latest published term rate is from {pd_day(term_date)}, {age_bd} business days old (more than "
            f"{limit_bd}), so the term premium is treated as stale and the 1 bp hurdle is used instead.")


def client_verdict(usd_lock: bool, eur_lock: bool, usd_premium_bp: float | None = None) -> tuple[str, str]:
    """'Yes' / 'Partly' / 'No' and the sentence, from the two currencies' term-out decisions."""
    n = int(usd_lock) + int(eur_lock)
    verdict = {2: "Yes", 1: "Partly", 0: "No"}[n]
    if n == 2:
        sentence = ("Both the dollar and the euro forecasts imply that locking in term funding across 31 December "
                    "2026 should cost less than rolling overnight.")
    elif usd_lock:
        sentence = ("Term out the dollar leg, where the expected cost of rolling overnight over the turn exceeds the "
                    "term rate; keep euro funding overnight, where the expected excess cost is below the hurdle.")
    elif eur_lock:
        sentence = "Term out the euro leg only; the dollar forecast does not exceed the term premium."
    elif usd_premium_bp is not None and usd_premium_bp < 0:
        sentence = ("Stay overnight in both currencies. Dollar term funding is currently cheaper than overnight, but "
                    "the forecast expects overnight funding over the turn window to fall by more than that discount; "
                    "in euros the expected excess cost is below the hurdle. The upper tail is the risk to manage.")
    else:
        sentence = ("Stay overnight in both currencies: the expected excess cost of rolling overnight over the turn "
                    "is below the hurdle in each, with the upper tail as the risk to manage.")
    return verdict, sentence


def calibration_sentence(currency: str, model_label: str, coverage: float, lower: float, upper: float,
                         verdict: str, n: int) -> str:
    """Plain-English calibration verdict of the 5-95% range on the test period (U2 rule)."""
    meaning = {"well calibrated": "consistent with the nominal 90%",
               "too narrow": "below the nominal 90%: the ranges are too narrow",
               "too wide": "above the nominal 90%: the ranges are too wide"}[verdict]
    return (f"{currency} ({model_label.lower()}): the 5-95% range contained the outcome on {coverage:.1%} of "
            f"{n} test days (exact 95% CI {lower:.1%} to {upper:.1%}), {meaning}. Verdict: {verdict}.")


def robustness_badge_text(holds: int, n: int, not_computable: int = 0) -> str:
    """'Holds in 4 of 5 robustness checks' (and how many alternatives could not be computed)."""
    text = (f"Holds in all {n} robustness checks" if holds == n and n > 1 else
            f"Holds in {holds} of {n} robustness check{'s' if n != 1 else ''}")
    if not_computable:
        text += f" ({not_computable} not computable)"
    return text


def v1_v2_sentence(currency: str, m1: float, lo1: float, q90_1: float, hi1: float, m2: float, lo2: float,
                   q90_2: float, hi2: float, n_ye: int | None) -> str:
    """v1 (pre-registered) against v2 (challenger) on 31 December 2026."""
    wider = (hi2 - lo2) - (hi1 - lo1)
    return (f"{currency} on 31 December 2026: v1 median {signed_bp(m1)}, 5-95% {signed_bp(lo1)} to {signed_bp(hi1)}; "
            f"v2 median {signed_bp(m2)}, 5-95% {signed_bp(lo2)} to {signed_bp(hi2)}. The v2 range is "
            f"{bp(wider)} {wider_or_narrower(wider)}, and its 90th and 95th percentiles ({signed_bp(q90_2)}, "
            f"{signed_bp(hi2)}) are {'separated' if hi2 - q90_2 >= 0.5 else 'still close together'}"
            + (f"; its year-end distribution rests on {n_ye} past year-ends." if n_ye else "."))


def v2_test_sentence(currency: str, cqr_turn: float, v1_turn: float, base_turn: float, cqr_cov: float,
                     cqr_verdict: str, v1_cov: float, analogue_inside: int, analogue_n: int) -> str:
    """v2's test-period results, always with the caveat that they are not a clean out-of-sample claim."""
    better = "lower" if cqr_turn < v1_turn else "higher"
    return (f"{currency} (not a clean out-of-sample test: v2 was designed after seeing v1's test results): the CQR "
            f"turn-day pinball loss was {cqr_turn:.2f}, {better} than v1's {v1_turn:.2f} (baseline {base_turn:.2f}); "
            f"its 5-95% range covered {cqr_cov:.1%} of test days ({cqr_verdict}; v1 {v1_cov:.1%}). The year-end "
            f"analogue's range contained {share_words(analogue_inside, analogue_n)} of the 2023-2025 year-ends.")


def tail_sentence(currency: str, q90: float, q95: float, raw90: float, raw95: float, n_year_ends: int,
                  pins: list[str], same_pins: bool) -> str:
    """Why the frozen 90th and 95th percentiles on 31 December are (nearly) the same (U0 diagnosis)."""
    crossed = raw90 > raw95
    order = (f"before sorting the 90th percentile ({signed_bp(raw90, 2)}) was above the 95th ({signed_bp(raw95, 2)}), "
             "so the two were swapped" if crossed else
             f"before sorting the 90th and 95th percentiles were {signed_bp(raw90, 2)} and {signed_bp(raw95, 2)}")
    pinned = (f"both pass exactly through the same {share_words(len(pins), len(pins)) if len(pins) > 1 else 'one'} "
              f"year-end{'s' if len(pins) > 1 else ''} ({', '.join(pd_day(d) for d in pins)})" if same_pins and pins
              else "they pass through different year-ends")
    return (f"{currency}: the frozen 90th and 95th percentiles ({signed_bp(q90)} and {signed_bp(q95)}) are not "
            f"separately identified. The year-end effect is fitted on only {n_year_ends} year-ends with two "
            f"year-end parameters; at the 90th and 95th percentiles {pinned}, and {order}. With {n_year_ends} "
            f"year-ends, any quantile above {(n_year_ends - 1) / n_year_ends:.0%} leaves no year-end above the "
            "fit, so the upper tail rests on the single largest past turns.")


def daily_rules_sentence(day: str, spread: float, smoothed: float, baseline: float, in_blowout: bool,
                         start: str | None, peak: float | None, half_level: float | None, p_next_12: float | None,
                         in_gradual: bool, monthly_in_episode: bool) -> str:
    """Chapter IV, daily: where the spread stands against both pre-registered rules (U1)."""
    excess = smoothed - baseline
    head = (f"On {pd_day(day)} the OAT-Bund spread was {bp(spread, 0)}; its five-day average, {bp(smoothed, 0)}, "
            f"was {bp(excess, 0)} {above_or_below(excess)} its trailing one-year average ({bp(baseline, 0)}).")
    if in_blowout:
        rule1 = (f" By the daily blowout rule (30 bp) France has been in an episode since {pd_day(start)}; the "
                 f"peak so far is {bp(peak, 0)}, so half the widening is retraced at {bp(half_level, 0)}.")
        if p_next_12 is not None:
            rule1 += (f" Of past euro blowouts that had lasted this long, {p_next_12:.0%} retraced half the widening "
                      "within the following 12 months (monthly 10-country base rate).")
    else:
        rule1 = " By the daily blowout rule (30 bp) France is not in an episode."
    rule2 = (" It also meets the gradual-deterioration rule (15 bp for six months)." if in_gradual else
             " It does not meet the gradual-deterioration rule (15 bp above the trailing average for six months): "
             "the excess built up within weeks, not over half a year.")
    monthly = (" The monthly rule agrees." if monthly_in_episode == in_blowout else
               " The monthly rule, whose data end earlier, does not yet show the episode." if in_blowout else
               " The monthly rule disagrees.")
    return head + rule1 + rule2 + monthly


def gradual_base_rate_sentence(n: int, n_countries: int, median_months: float, s12: float) -> str:
    """Monthly base rates of gradual-deterioration episodes (Rule 2) in the euro panel."""
    return (f"Gradual deteriorations are common: {n} episodes in {n_countries} euro countries since 2008 by the "
            f"same rule on monthly data; the median retraced half its widening in {median_months:.0f} months and "
            f"{1 - s12:.0%} within a year.")


def daily_event_sentence(event: str, day: str, change: float, percentile: float) -> str:
    """Two-day change in the daily OAT-Bund spread around an event, against every two-day window since 2010."""
    size = ("an unusually large" if percentile >= 0.9 else "a larger than typical" if percentile >= 0.5
            else "a smaller than typical")
    move = "widened" if change > 0 else "narrowed" if change < 0 else "was unchanged"
    return (f"{event} ({pd_day(day)}): over the two days around it the OAT-Bund spread {move} by {bp(change)}, "
            f"{size} move ({percentile:.0%} of two-day windows since 2010 saw a smaller change).")


def event_study_summary_sentence(n: int, n_unusual: int, mean_change: float, n_widened: int) -> str:
    """Overall result of the daily event study."""
    return (f"Across the {n} verified events, the spread widened in {share_words(n_widened, n)} two-day windows "
            f"(average change {signed_bp(mean_change)}); {share_words(n_unusual, n)} "
            f"{'was' if n_unusual == 1 else 'were'} unusually large (90th percentile of all two-day changes or above).")


# --------------------------------------------------------------------------- #
# Desk upgrade D0: the two constructions in the daily OAT-Bund spread
# --------------------------------------------------------------------------- #
def construction_sentence(mean_gap: float, recent_gap: float, latest_spread: float, latest_spread_cm: float,
                          small: bool, threshold: float, n_days: int) -> str:
    """Caveat on the daily spread: current Bund vs constant-maturity Bund (gap = current - constant maturity)."""
    side = "below" if mean_gap < 0 else "above" if mean_gap > 0 else "level with"
    effect = "wider" if mean_gap < 0 else "narrower" if mean_gap > 0 else "the same"
    size = (f"small (at most {threshold:.0f} bp)" if small else
            f"material (more than {threshold:.0f} bp)")
    return (f"The French leg is a constant-maturity 10-year yield (TEC10) but the German leg is the current 10-year "
            f"Bund, a single bond. Over {n_days:,} common days the current Bund yielded on average {bp(mean_gap)} "
            f"{side} the Bundesbank's constant-maturity 10-year yield ({signed_bp(recent_gap)} over the last 250 "
            f"days), so the daily spread reads {effect} than a like-for-like spread by about that much: "
            f"{latest_spread:.1f} bp against {latest_spread_cm:.1f} bp on the latest day. The difference is {size}; "
            "the episode rules compare the spread with its own trailing average, so a steady gap largely cancels "
            "out of them.")


def construction_monthly_sentence(oat_irs: float, bund_irs: float, bund_cm_irs: float, n_months: int) -> str:
    """How each daily series compares with the ECB monthly 10-year yields (mean differences, bp)."""
    return (f"Against the ECB's monthly 10-year yields ({n_months} months since 2010), the monthly mean of the "
            f"TEC10 differs by {signed_bp(oat_irs)}, the current Bund by {signed_bp(bund_irs)} and the "
            f"constant-maturity Bund by {signed_bp(bund_cm_irs)} on average.")


# --------------------------------------------------------------------------- #
# Desk upgrade D1: the euro runway
# --------------------------------------------------------------------------- #
def eur_bn(x: float) -> str:
    """2242.6 -> 'EUR 2,243 bn' (absolute value; the sentence carries the sign)."""
    return f"EUR {abs(x):,.1f} bn" if abs(x) < 100 else f"EUR {abs(x):,.0f} bn"


def runway_distance_sentence(latest_bn: float, latest_date: str, bounds: dict, dist: dict | None) -> str:
    """Where euro liquidity stands against chapter II's pressure point and its band."""
    if dist is None:
        return (f"Euro liquidity is {eur_bn(latest_bn)} ({latest_date}); chapter II could not place a pressure "
                "point, so no distance is quoted.")
    def part(name: str, label: str) -> str:
        d = dist[name]
        return f"{eur_bn(d)} {'above' if d > 0 else 'below'} {label} ({eur_bn(bounds[name])})"
    n_below = sum(v <= 0 for v in dist.values())
    if n_below == 3:
        lead = "Euro liquidity is already below the whole pressure band identified in chapter II"
    elif n_below == 0:
        lead = "Euro liquidity is still above the whole pressure band identified in chapter II"
    else:
        lead = "Euro liquidity is inside the pressure band identified in chapter II"
    return (f"{lead}: {eur_bn(latest_bn)} on {latest_date}, {part('upper', 'the band upper end')}, "
            f"{part('kink', 'the kink')} and {part('lower', 'the band lower end')}.")


def runway_drift_sentence(liq_week: float, sec_week: float) -> str:
    """The trailing-year drain of liquidity and of the monetary-policy portfolio (EUR bn per week)."""
    def move(x: float) -> str:
        return f"{'fell' if x < 0 else 'rose' if x > 0 else 'was unchanged'} by {eur_bn(x)} a week"
    if liq_week < 0 and sec_week < 0:
        share = ("more than accounts for" if sec_week < liq_week else "accounts for most of" if sec_week < liq_week / 2
                 else "accounts for less than half of")
        tail = f"so the portfolio run-off {share} the drain."
    else:
        tail = "so the portfolio run-off is not what moved liquidity."
    return (f"Over the last 52 weeks euro liquidity {move(liq_week)} on average and the Eurosystem's APP and PEPP "
            f"holdings {move(sec_week)}, {tail}")


def runway_scenario_sentence(scenarios: dict | None) -> str:
    """When each mechanical scenario reaches the pressure band. Always labelled as scenarios, not forecasts."""
    if not scenarios:
        return "No scenario is shown because the pressure point is not identified."
    base = scenarios["base"]["crossings"]
    statuses = {v["status"] for s in scenarios.values() for v in s["crossings"].values()}
    lead = ("These are scenarios, not forecasts: straight-line extensions of the last year's drain at half, the same "
            "and one and a half times its pace, with no view on policy.")
    if statuses == {"already crossed"}:
        when = (f"Every scenario starts below the band, so there is no date to reach it: liquidity fell below the band "
                f"upper end on {pd_day(base['upper']['date'])}, below the kink on {pd_day(base['kink']['date'])} "
                f"and below the lower end on {pd_day(base['lower']['date'])}.")
    else:
        bits = []
        for name in ("slow", "base", "fast"):
            c = scenarios[name]["crossings"]
            def show(x: dict) -> str:
                return pd_day(x["date"]) if x["date"] else x["status"]
            bits.append(f"{name} {show(c['upper'])} to {show(c['lower'])}")
        when = "Dates at which liquidity enters and leaves the band: " + "; ".join(bits) + "."
    lv = {k: v["levels_bn"] for k, v in scenarios.items()}
    levels = (f"On 31 December 2027 the paths stand at {eur_bn(lv['slow']['2027-12-31'])} (slow), "
              f"{eur_bn(lv['base']['2027-12-31'])} (base) and {eur_bn(lv['fast']['2027-12-31'])} (fast).")
    return f"{lead} {when} {levels}"


def spread_trend_sentence(slope: float, lo: float, hi: float, p_value: float, verdict: str, first: float,
                          last: float, sens_verdict: str) -> str:
    """Whether €STR minus the DFR has drifted over the last 12 months (HAC trend test)."""
    sig = significance_phrase(p_value)
    head = {"drifting up": "€STR minus the DFR has started drifting up",
            "drifting down": "€STR minus the DFR has been drifting down",
            "no significant trend": "€STR minus the DFR shows no significant trend"}[verdict]
    same = ("the same holds without month-end turn days" if sens_verdict == verdict else
            f"without month-end turn days the result reads '{sens_verdict}'")
    return (f"{head} over the last 12 months: a slope of {slope:+.2f} bp a year ({ci_text(lo, hi, ' bp', 2)}), "
            f"{sig}, from {first:+.1f} bp to {last:+.1f} bp (20-day averages); {same}.")


# --------------------------------------------------------------------------- #
# Desk upgrade D2: Treasury cash and overnight funding
# --------------------------------------------------------------------------- #
CASH_LABEL = {"EUR": ("euro", "government and other non-bank deposits at the Eurosystem", "€STR minus the DFR",
                     "liquidity"),
              "USD": ("dollar", "the Treasury General Account", "SOFR minus IORB", "reserves")}


def treasury_cash_sentence(currency: str, coef: float, lo: float, hi: float, p_holm: float, r2_oos: float,
                           liq_coef: float, liq_lo: float, liq_hi: float, verdict: str) -> str:
    """What the weekly regression says about Treasury cash and the overnight spread in one currency."""
    name, cash, spread, liq = CASH_LABEL[currency]
    unit = f"{currency} 100 bn"
    direction = ("rises" if coef > 0 else "falls") + " when Treasury cash rises"
    ci_side = "excludes zero" if excludes_zero(lo, hi) else "includes zero"
    oos = ("beats" if r2_oos > 0 else "does not beat") + f" a no-change rule out of sample (R² {r2_oos:+.2f}, 2023 on)"
    head = {"matters": f"In the {name} market, swings in {cash} matter for overnight funding",
            "some evidence": f"In the {name} market there is some evidence that changes in {cash} move overnight "
                             "funding",
            "no clear effect": f"In the {name} market changes in {cash} have no clear effect on overnight "
                               "funding"}[verdict]
    liq_part = (f"; the {liq} term is {liq_coef:+.2f} bp per {unit} ({ci_text(liq_lo, liq_hi, ' bp', 2)})")
    return (f"{head}: holding {liq} fixed, {spread} {direction} ({coef:+.2f} bp per {unit} in a week, "
            f"{ci_text(lo, hi, ' bp', 2)}, which {ci_side}){liq_part}. The Treasury-cash coefficient is "
            f"{significance_phrase(p_holm, adjusted=True)}, and the weekly model {oos}.")


def treasury_cash_answer(eur_verdict: str, usd_verdict: str) -> str:
    """One line: do Treasury cash swings matter for overnight funding, by currency."""
    words = {"matters": "matter", "some evidence": "matter only partly", "no clear effect": "do not clearly matter"}
    if eur_verdict == usd_verdict:
        return f"Treasury cash swings {words[eur_verdict]} for overnight funding in both currencies."
    return (f"Treasury cash swings {words[eur_verdict]} for euro overnight funding and {words[usd_verdict]} for "
            "dollar overnight funding.")


# --------------------------------------------------------------------------- #
# Desk upgrade D3: the Fed's year-end toolkit
# --------------------------------------------------------------------------- #
def usd_bn(x: float, decimals: int = 1) -> str:
    """74.6 -> 'USD 74.6 bn' (absolute value)."""
    return f"USD {abs(x):,.{decimals}f} bn"


def toolkit_pattern_sentence(p: dict) -> str:
    """How the Fed's repo backstop has been used around quarter-ends and year-ends since 2018."""
    if p["n_used"] == 0:
        return (f"Fed repo operations were not used (at least {usd_bn(p['min_bn'], 0)}) on any of the "
                f"{p['n_turns']} quarter-end turns since mid-2018.")
    early = f"{share_words(p['n_used_early'], p['n_early'])} turns before {p['split_year']}"
    late = f"{share_words(p['n_used_late'], p['n_late'])} from {p['split_year']}"
    trend = ("more often" if p["n_used_late"] / max(p["n_late"], 1) > p["n_used_early"] / max(p["n_early"], 1)
             else "less often" if p["n_used_late"] / max(p["n_late"], 1) < p["n_used_early"] / max(p["n_early"], 1)
             else "as often")
    shape = ""
    if p["mean_at_used"] is not None and p["mean_before_used"] is not None:
        peak = "peaks on the turn itself" if p["mean_at_used"] > max(p["mean_before_used"],
                                                                     p["mean_after_used"] or 0) else \
            "does not peak on the turn itself"
        shape = (f" When it is used, take-up {peak}: {usd_bn(p['mean_before_used'])} a day in the week before, "
                 f"{usd_bn(p['mean_at_used'])} on the day and {usd_bn(p['mean_after_used'] or 0)} a day in the week "
                 "after, on average.")
    rho = p["spearman_spread_usage"]
    link = ("Turns with more take-up also had a higher SOFR minus IOR" if rho > 0 else
            "Turns with more take-up did not have a higher SOFR minus IOR")
    return (f"The Fed's repo operations (the standing repo facility from July 2021) were used, at least "
            f"{usd_bn(p['min_bn'], 0)}, on {p['n_used']} of {p['n_turns']} quarter-end turns since mid-2018: {early} "
            f"and {late}, so the backstop has been used {trend} since {p['split_year']}. The largest take-up was "
            f"{usd_bn(p['max_at'])} on {pd_day(p['max_at_date'])}.{shape} {link} (rank correlation {rho:+.2f}, "
            "descriptive).")


def backstop_line(s: dict) -> str:
    """Chapter VII: the latest state of the Fed's backstop and reserve-management purchases."""
    used = ("was used" if s["repo_30d_days_used"] else "was not used (at least USD 1 bn)")
    bills = ""
    if s.get("bills_13w_change_bn") is not None:
        bills = (f" Fed bill holdings are {usd_bn(s['bills_bn'], 0)} ({pd_day(s['bills_date'])}), "
                 f"{'up' if s['bills_13w_change_bn'] > 0 else 'down' if s['bills_13w_change_bn'] < 0 else 'unchanged'}"
                 f" {usd_bn(s['bills_13w_change_bn'], 0)} over 13 weeks.")
    return (f"Backstop: the standing repo facility {used} in the last 30 days (latest {usd_bn(s['repo_bn'], 2)} on "
            f"{pd_day(s['repo_date'])}); at the last quarter-end ({pd_day(s['last_turn'])}) it lent "
            f"{usd_bn(s['last_turn_repo_bn'])} with SOFR minus IOR at {signed_bp(s['last_turn_spread_bp'], 0)}. "
            f"ON RRP take-up is {usd_bn(s['rrp_bn'])}.{bills}")
