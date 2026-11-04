"""French political and rating events for the event study (chapter IV), each with an official source URL.

Rule (docs/METHODOLOGY.md, Phase 4 IV(d)): an event is included only if its official source was
reachable when checked. Checked on 2026-11-04 with plain HTTP requests:

Included: the Assemblée nationale's verbatim record (compte rendu intégral) of the sitting at which the
vote took place. Each returned HTTP 200 as a PDF dated in its URL; the vote itself is corroborated by
independent reporting found in a web search (LCP, the Assemblée's own channel, for 8 Sep 2025).

Excluded, with the reason (never added from memory):
- Dissolution of the National Assembly, 9 Jun 2024: the Élysée page returned no text about the dissolution
  and then reset the connection; Légifrance returned HTTP 403. Not verifiable.
- Rating actions on France by S&P, Moody's and Fitch (2024-2026): the agencies' press releases were not
  found, and the French Treasury's ratings page (aft.gouv.fr) returns HTTP 403 to scripts. Not verifiable.
"""

from __future__ import annotations

CHECKED_ON = "2026-11-04"

EVENTS = [
    {"date": "2024-12-04", "kind": "political",
     "event": "The National Assembly adopts a motion of censure; the Barnier government falls",
     "source": "Assemblée nationale, compte rendu intégral, séance du mercredi 4 décembre 2024",
     "url": "https://questions.assemblee-nationale.fr/dyn/17/comptes-rendus/seance/session-ordinaire-de-2024-2025/"
            "seance-du-mercredi-04-decembre-2024.pdf",
     "http_status": 200},
    {"date": "2025-09-08", "kind": "political",
     "event": "The National Assembly refuses its confidence to the Bayrou government (article 49, paragraph 1)",
     "source": "Assemblée nationale, compte rendu intégral, séance du lundi 8 septembre 2025",
     "url": "https://questions.assemblee-nationale.fr/dyn/17/comptes-rendus/seance/2e-session-extraordinaire-de-2024-2025/"
            "seance-du-lundi-08-septembre-2025.pdf",
     "http_status": 200},
]

EXCLUDED = [
    {"date": "2024-06-09", "event": "Dissolution of the National Assembly",
     "reason": "Élysée page did not contain the announcement when fetched and then reset the connection; Légifrance HTTP 403"},
    {"date": "2024-2026", "event": "Sovereign rating actions on France (S&P, Moody's, Fitch)",
     "reason": "agency press releases not found; aft.gouv.fr ratings page HTTP 403 to scripts"},
]
