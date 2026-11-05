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


def more_or_less(x: float) -> str:
    """'more' for a positive difference, 'less' for a negative one (the number is printed as a magnitude)."""
    return "more" if x >= 0 else "less"


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
    beat = " and ".join(beaten) if beaten else "neither currency"
    sig = " and ".join(significant) if significant else "neither"
    return answer, (f"On the test period from {test_start}, a quantile model with calendar and state variables beat "
                    f"the naive same-as-last-turn rule on turn days in {beat} (significantly in {sig}). "
                    f"Across every year-end in the data, {direction} "
                    f"({signed_bp(usd_mean)} and {signed_bp(eur_mean)} on an average year-end).")


# --------------------------------------------------------------------------- #
# Chapter II: three corridors
# --------------------------------------------------------------------------- #
CURRENCY_NAMES = {"EUR": "the ECB", "USD": "the Fed", "JPY": "the BoJ"}
MARKET_NAMES = {"EUR": "€STR", "USD": "SOFR", "JPY": "TONA"}


def corridor_sentence(currency: str, inside_share: float, below_share: float, median_bp: float, iqr_bp: float,
                      start: str) -> str:
    tight = "tightly" if iqr_bp <= 3 else "loosely"
    where = (f"{MARKET_NAMES[currency]} stayed inside {CURRENCY_NAMES[currency]}'s corridor on {inside_share:.1%} of days"
             if below_share < 0.5 else
             f"{MARKET_NAMES[currency]} traded below {CURRENCY_NAMES[currency]}'s floor on {below_share:.1%} of days, "
             "as expected in a floor system: its lenders include institutions that cannot deposit at the central "
             "bank, so they accept less than the floor")
    return (f"Since {start[:4]}, {where}. Over the past year it sat {bp(median_bp)} {above_or_below(median_bp)} the "
            f"policy rate, held {tight} (interquartile range {bp(iqr_bp)}).")


def markov_sentence(currency: str, calm_mean: float, stressed_mean: float, stressed_sd: float, calm_sd: float,
                    test_ll: float, normal_ll: float, share_test: float) -> str:
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
        share = f" ({edge_share:.0%} of bootstrap estimates sit at the edge of the search range)"             if edge_share is not None else ""
        return (f"{head} The point where pressure starts is not identified: the estimated kink lies at the edge of "
                f"the range searched{share}, so the data cannot place it.")
    where = ("below" if latest < band[0] else "inside" if latest <= band[1] else "above")
    caveat = "" if winner != "linear" else " (a reference only: the threshold model did not win out of sample)"
    return (f"{head} The estimated point where pressure starts is {point:.2f} trillion{caveat}, with a 95% band of "
            f"{band[0]:.2f} to {band[1]:.2f}; the latest level, {latest:.2f}, is {where} that band.")


def case_sentence(case: str, currency: str, peak: float, peak_date: str, before: float) -> str:
    jump = peak - before
    return (f"{case}: {MARKET_NAMES[currency]} peaked at {signed_bp(peak)} against the policy rate on "
            f"{pd_day(peak_date)}, {bp(jump)} {'above' if jump > 0 else 'below'} its level in the two weeks before.")


def pd_day(iso: str) -> str:
    import pandas as pd
    ts = pd.Timestamp(iso)
    return f"{ts.day} {ts:%B %Y}"


def corridors_answer(stats: dict, reserves: dict) -> tuple[str, str]:
    """(answer, explanation) for chapter II: held tightly over the past year, and the balance-sheet effect."""
    tight = [c for c, s in stats.items() if s["recent_iqr_bp"] <= 3]
    answer = ("Yes, within a few basis points" if len(tight) == len(stats) else
              f"Mostly: {share_words(len(tight), len(stats))} held tightly")
    usd = reserves.get("USD", {})
    slope = usd.get("slope_per_unit", 0)
    tail = (f"As balance sheets shrink, SOFR has drifted up relative to the Fed's interest on reserves, about "
            f"{bp(slope)} per trillion of reserves lost" if slope < 0 else
            "Shrinking reserves have not pushed SOFR up relative to interest on reserves")
    spreads = ", ".join(f"{MARKET_NAMES[c]} {signed_bp(s['recent_median_bp'])} (IQR {bp(s['recent_iqr_bp'])})"
                        for c, s in stats.items())
    return answer, f"Past-year median spread to the policy rate: {spreads}. {tail}."


# --------------------------------------------------------------------------- #
# Chapter III: credit or scarcity
# --------------------------------------------------------------------------- #
COUNTRY_NAMES = {"IT": "Italian", "FR": "French", "ES": "Spanish", "DE": "German"}


def verdict_phrase(verdict: str) -> str:
    return {"credit": "mainly credit risk", "scarcity": "mainly scarcity of German collateral",
            "both / unclear": "neither clearly credit nor scarcity"}[verdict]


def collateral_sentence(country: str, verdict: str, credit_effect: float, scarcity_effect: float, r2: float,
                        mean_spread: float, latest: float) -> str:
    return (f"{COUNTRY_NAMES[country]} collateral cost {bp(mean_spread)} {more_or_less(mean_spread)} than German "
            f"collateral in repo on "
            f"average (latest {signed_bp(latest)}). The regression explains {r2:.0%} of the variation and reads as "
            f"{verdict_phrase(verdict)}: a one-standard-deviation move in the yield spread is worth "
            f"{signed_bp(credit_effect)}, the two scarcity measures together {bp(scarcity_effect)}.")


def qt_break_sentence(country: str, p_value: float, before: str | None, after: str | None) -> str:
    changed = p_value < 0.05
    head = (f"The relationship for {COUNTRY_NAMES[country]} collateral changed at the start of quantitative "
            f"tightening; the break is {significance_phrase(p_value)}" if changed else
            f"There is no significant break for {COUNTRY_NAMES[country]} collateral at the start of quantitative "
            f"tightening; the test is {significance_phrase(p_value)}")
    if before and after:
        if before == after:
            return head + f"; it reads as {verdict_phrase(before)} both before and after."
        return head + f": {verdict_phrase(before)} before, {verdict_phrase(after)} after."
    return head + "."


def collateral_answer(it_verdict: str, fr_verdict: str, it_break_p: float, fr_break_p: float) -> tuple[str, str]:
    verdicts = (it_verdict, fr_verdict)
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
    return answer, (f"Italian collateral: {verdict_phrase(it_verdict)}; French collateral: {verdict_phrase(fr_verdict)}. "
                    f"The relationship broke at the start of quantitative tightening for {which}.")


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


def france_specific_sentence(since: str, cum_change: float, euro_wide: float, france_specific: float) -> str:
    share = france_specific / cum_change if cum_change else float("nan")
    own = "France-specific" if abs(france_specific) > abs(euro_wide) else "euro-wide"
    return (f"Since {since} the French spread moved {signed_bp(cum_change)}: {signed_bp(euro_wide)} is what Italian "
            f"and Spanish spreads would have implied (euro-wide), {signed_bp(france_specific)} is France-specific "
            f"({share:.0%} of the move). The move has been mainly {own}.")


def survival_sentence(n: int, n_countries: int, median: float, s12: float, s12_lo: float, s12_hi: float,
                      threshold: float) -> str:
    return (f"Across {n} blowouts of {bp(threshold, 0)} or more in {n_countries} euro countries since 2008, the "
            f"median time to retrace half the widening was {median:.0f} months; {1 - s12:.0%} had done so within a "
            f"year (95% band {1 - s12_hi:.0%} to {1 - s12_lo:.0%}). The sample is small and the episodes overlap in "
            "time, so these are base rates, not forecasts.")


def france_status_sentence(in_episode: bool, spread_now: float, baseline: float | None, gap: float | None,
                           threshold: float, sens_threshold: float | None = None, sens_start: str | None = None,
                           sens_p12: float | None = None) -> str:
    if in_episode:
        return f"By the {bp(threshold, 0)} rule France is in a blowout episode, with the spread at {bp(spread_now, 0)}."
    text = (f"By the {bp(threshold, 0)} rule France is not in a blowout: at {bp(spread_now, 0)} the spread is "
            f"{bp(gap, 1)} short of its trailing one-year average ({bp(baseline, 0)}) plus {bp(threshold, 0)}. The "
            "widening since 2024 has been a steady grind rather than a jump, so the trailing average has risen with it.")
    if sens_threshold is not None and sens_start is not None:
        text += (f" With the looser {bp(sens_threshold, 0)} rule an episode starts in {sens_start}; for episodes of "
                 f"that kind the chance of retracing half the widening within 12 months was {sens_p12:.0%}.")
    return text


def repo_treatment_sentence(fr_before: float, fr_after: float, it_before: float, it_after: float,
                            pos_before: float, pos_after: float, p_gap: float, latest_fr: float,
                            latest_it: float) -> str:
    closer = pos_after > pos_before
    text = (f"In repo, French collateral moved {'closer to Italian' if closer else 'away from Italian'} pricing after "
            f"June 2024: its spread to German collateral went from {signed_bp(fr_before)} to {signed_bp(fr_after)}, the "
            f"Italian spread from {signed_bp(it_before)} to {signed_bp(it_after)}, and France's position between Germany "
            f"(0) and Italy (1) "
            f"from {pos_before:.2f} to {pos_after:.2f}. The change in the Italy-France gap is "
            f"{significance_phrase(p_gap)}.")
    if latest_fr > latest_it:
        text += (f" In the latest period French collateral cost more than Italian ({signed_bp(latest_fr)} against "
                 f"{signed_bp(latest_it)}).")
    return text


def event_sentence(event: str, month: str, change: float, percentile: float) -> str:
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
def japan_change_sentence(date: str, change_bp: float, days: int | None, pass_20d: float) -> str:
    direction = "rise" if change_bp > 0 else "cut"
    speed = ("on the effective day" if days == 0 else f"after {days} business days" if days is not None
             else "not within 60 business days")
    return (f"{pd_day(date)}, a {bp(change_bp, 0)} {direction}: TONA closed half the gap {speed} and moved "
            f"{pass_20d:.0%} of the change on average over the first 20 business days.")


def japan_answer(n_changes: int, n_same_day: int, exit_half_life: float, negative_half_life: float,
                 latest_gap_bp: float) -> tuple[str, str]:
    if n_same_day == n_changes:
        answer = "Yes, immediately"
    elif n_same_day >= n_changes / 2:
        answer = "Yes, since the exit; the regime changes passed through more slowly"
    else:
        answer = "Only partly"
    return answer, (f"{n_same_day} of {n_changes} BoJ policy changes since 2016 reached TONA on the effective day. "
                    f"After the exit, a gap between TONA and the policy rate halves in {exit_half_life:.1f} business "
                    f"days (against {negative_half_life:.1f} under negative rates). TONA now sits "
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
            f"bonds has paid {bp(it_mean)} {more_or_less(it_mean)} than lending against German bonds on average since 2018 "
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
