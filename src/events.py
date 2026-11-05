"""French political and rating events for the event study (chapter IV), each confirmed by two sources.

Rule (docs/METHODOLOGY.md, U5): an event is included if at least two independent reputable sources confirm
it and its date (official sites, Reuters, Bloomberg, Financial Times, CNBC, Les Echos, Le Monde). Checked
on 2026-11-05. Reuters, the Financial Times, Le Monde, Les Echos and fitchratings.com refuse the search
tool's user agent, so in practice the sources are Bloomberg, CNBC and official sites. Methods:
- "fetched": the page was downloaded and returned HTTP 200 (the Assemblée nationale records, 2026-11-04);
- "search listing": the outlet's own article appeared in a web search with its title and dated URL, and the
  listing stated the action and date (the article body was not downloaded; Bloomberg is paywalled).
Anything with fewer than two independent listed sources is excluded, with the reason (never added from memory).
"""

from __future__ import annotations

CHECKED_ON = "2026-11-05"
LISTING = "search listing (title and dated URL)"


def _src(outlet: str, url: str, title: str, method: str = LISTING, accessed: str = CHECKED_ON) -> dict:
    return {"outlet": outlet, "url": url, "title": title, "method": method, "accessed": accessed}


AN = "https://questions.assemblee-nationale.fr/dyn/17/comptes-rendus/seance/"
EVENTS = [
    {"date": "2024-06-09", "kind": "political", "event": "President Macron dissolves the National Assembly",
     "sources": [
         _src("CNBC", "https://www.cnbc.com/2024/06/09/french-president-macron-calls-for-snap-election-after-heavy-"
                      "defeat-in-eu-vote-.html", "France's Macron calls for snap election after losing big to the far right in EU vote"),
         _src("Bloomberg", "https://www.bloomberg.com/news/articles/2024-06-18/macron-says-snap-election-was-needed-to-"
                           "avoid-chaos-in-france", "Macron Says Snap Election Was Needed to Avoid Chaos")]},
    {"date": "2024-10-25", "kind": "rating", "event": "Moody's moves France's Aa2 outlook to negative",
     "sources": [
         _src("Bloomberg", "https://www.bloomberg.com/news/articles/2024-10-25/france-rating-outlook-cut-to-negative-by-"
                           "moody-s-on-deficit-woes", "France's Credit Rating Put on Negative Outlook by Moody's on Deficit Woes"),
         _src("CNBC", "https://www.cnbc.com/video/2024/10/28/moodys-downgrades-frances-outlook.html",
              "Moody's downgrades France's outlook")]},
    {"date": "2024-12-04", "kind": "political",
     "event": "The National Assembly adopts a motion of censure; the Barnier government falls",
     "sources": [
         _src("Assemblée nationale", AN + "session-ordinaire-de-2024-2025/seance-du-mercredi-04-decembre-2024.pdf",
              "Compte rendu intégral, séance du mercredi 4 décembre 2024", "fetched (HTTP 200)", "2026-11-04"),
         _src("CNBC", "https://www.cnbc.com/2024/12/04/french-government-toppled-in-no-confidence-vote-brought-by-"
                      "opposition.html", "French government toppled in no-confidence vote brought by opposition"),
         _src("Bloomberg", "https://www.bloomberg.com/news/articles/2024-12-04/french-far-right-joins-forces-with-left-"
                           "to-topple-government", "Le Pen, Left Wing Topple French Government")]},
    {"date": "2024-12-13", "kind": "rating", "event": "Moody's downgrades France to Aa3 (Friday evening)",
     "sources": [
         _src("Bloomberg", "https://www.bloomberg.com/news/articles/2024-12-13/france-downgraded-by-moody-s-after-le-pen-"
                           "derails-deficit-push", "French Credit Rating Cut on Crisis That Imperils Finances"),
         _src("Moody's (official)", "https://ratings.moodys.com/ratings-news/434553", "Rating Action")]},
    {"date": "2025-09-08", "kind": "political",
     "event": "The National Assembly refuses its confidence to the Bayrou government (article 49, paragraph 1)",
     "sources": [
         _src("Assemblée nationale", AN + "2e-session-extraordinaire-de-2024-2025/seance-du-lundi-08-septembre-2025.pdf",
              "Compte rendu intégral, séance du lundi 8 septembre 2025", "fetched (HTTP 200)", "2026-11-04"),
         _src("CNBC", "https://www.cnbc.com/2025/09/08/french-prime-minister-francois-bayrou-ousted-in-confidence-vote.html",
              "French prime minister Francois Bayrou ousted in confidence vote")]},
    {"date": "2025-09-12", "kind": "rating", "event": "Fitch downgrades France to A+ (Friday evening)",
     "sources": [
         _src("Bloomberg", "https://www.bloomberg.com/news/articles/2025-09-12/france-s-debt-woes-mount-as-fitch-"
                           "downgrades-credit-rating", "France's Debt Woes Mount as Fitch Downgrades Credit Rating"),
         _src("CNBC", "https://www.cnbc.com/2025/09/15/frances-borrowing-costs-rise-after-fitch-downgrade-.html",
              "France's borrowing costs rise after Fitch downgrade")]},
    {"date": "2025-10-06", "kind": "political", "event": "Prime Minister Lecornu resigns; his first government falls",
     "sources": [
         _src("CNBC", "https://www.cnbc.com/2025/10/06/frances-new-pm-resigns-as-political-chaos-continues.html",
              "French PM resigns after 27 days, sparking fresh political chaos"),
         _src("Bloomberg", "https://www.bloomberg.com/news/articles/2025-10-06/french-prime-minister-lecornu-has-"
                           "resigned-after-cabinet-panned", "French Premier Lecornu Resigns After Cabinet Criticized")]},
    {"date": "2025-10-17", "kind": "rating", "event": "S&P downgrades France to A+ (Friday evening, unscheduled)",
     "sources": [
         _src("Bloomberg", "https://www.bloomberg.com/news/articles/2025-10-17/france-s-gets-debt-warning-as-s-p-"
                           "downgrades-in-unscheduled-move", "France Gets Debt Warning as S&P Downgrades in Unscheduled Move"),
         _src("CNBC", "https://www.cnbc.com/video/2025/10/20/sp-downgrades-france-as-political-uncertainty-takes-its-"
                      "toll.html", "S&P downgrades France as political uncertainty takes its toll")]},
    {"date": "2025-10-24", "kind": "rating", "event": "Moody's moves France's Aa3 outlook to negative",
     "sources": [
         _src("Bloomberg", "https://www.bloomberg.com/news/articles/2025-10-24/france-gets-fresh-warning-on-finances-as-"
                           "moody-s-turns-negative", "France Gets Fresh Warning on Debt as Moody's Turns Negative"),
         _src("CNBC", "https://www.cnbc.com/video/2025/10/27/moodys-negative-france-outlook-shows-markets-fear-more-"
                      "budget-chaos.html", "Moody's negative France outlook shows markets fear more budget chaos")]},
    {"date": "2026-10-23", "kind": "rating review",
     "event": "Moody's periodic review keeps France at Aa3, outlook negative (no rating action)",
     "sources": [
         _src("CNBC", "https://www.cnbc.com/2026/10/23/moodys-holds-steady-on-frances-credit-rating-as-country-"
                      "grapples-with-turmoil-and-higher-yields.html", "Moody's holds steady on France's credit rating"),
         _src("Bloomberg", "https://www.bloomberg.com/news/articles/2026-10-23/france-avoids-moody-s-downgrade-in-"
                           "reprieve-after-week-of-crisis", "France Avoids Moody's Downgrade in Reprieve After Week of Crisis")]},
    {"date": "2026-10-30", "kind": "rating", "event": "Fitch moves France's A+ outlook to negative (unscheduled)",
     "sources": [
         _src("Bloomberg", "https://www.bloomberg.com/news/articles/2026-10-30/france-gets-budget-warning-as-fitch-turns-"
                           "negative-on-rating", "France Gets Budget Warning as Fitch Turns Negative on Rating"),
         _src("CNBC", "https://www.cnbc.com/video/2026/11/02/fitch-downgrades-outlook-for-france-in-a-surprise-update.html",
              "Fitch downgrades outlook for France in a surprise update"),
         _src("Agence France Trésor (official)", "https://www.aft.gouv.fr/en/frances-credit-ratings",
              "France's credit ratings (Fitch A+, negative, 30 October 2026)")]},
]

EXCLUDED = [
    {"date": "2024-05-31", "event": "S&P downgrades France to AA-",
     "reason": "only one listed source reachable (Bloomberg, 31 May 2024); other confirming outlets are not on the list"},
    {"date": "2024-10-11", "event": "Fitch moves France's AA- outlook to negative",
     "reason": "only one listed source reachable (Bloomberg, 11 Oct 2024); fitchratings.com refuses the search tool"},
    {"date": "2025-02-28", "event": "S&P moves France's AA- outlook to negative",
     "reason": "only one listed source reachable (Bloomberg, 28 Feb 2025)"},
    {"date": "2024-11-29, 2026-05-29, 2026-08-28", "event": "S&P and Fitch affirmations with no change",
     "reason": "affirmations are not rating actions (the candidate list is downgrades and outlook changes)"},
    {"date": "2024-2026", "event": "Scope and Morningstar DBRS actions",
     "reason": "not among the three agencies in the pre-registered candidate list"},
    {"date": "2026", "event": "A fall of a French government in 2026",
     "reason": "none found: the Lecornu government survived every censure vote reported (Bloomberg, Jan-Feb 2026)"},
]


def first_source(ev: dict) -> dict:
    """The first recorded source of an event (for one-line citations)."""
    return ev["sources"][0]
