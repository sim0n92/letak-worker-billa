# letak-worker-billa

Process Class (stdin, spec v1.0) for detecting new leaflets on
https://www.billa.sk/letaky-a-akcie. Sibling workers for other chains
(lidl, tesco, kaufland, ...) live in separate repos under the same
`sim0n92` account and share this exact protocol — see kaufland's repo for
the reference `ProcessClass` implementation if the wrapper protocol itself
needs changing.

## Key design points

- billa.sk is server-rendered (Nuxt + Kontent.ai), so plain regex over the
  raw HTML is enough — no headless browser needed at runtime.
- Two-stage fetch: the listing page has type + dates + a link to a detail
  page; the actual PDF link only exists on the detail page. `src/billa.py`
  keeps both stages as separate pure functions (`parse_leaflet_list`,
  `parse_pdf_url`) so each can be unit-tested against a fixture without
  hitting the network. `src/main.py` does the two-stage I/O and combines
  them via `billa.parse_leaflets`.
- Novelty key is `type|validFrom|validTo`, never the PDF URL — the PDF's
  UUID changes on re-upload even when the leaflet itself hasn't changed.
- Dates come from the listing page's "platí od ... do ..." text, which only
  gives the end year; the start year is inferred (rolls back one year if
  the start month is after the end month, for December→January leaflets).

## Tests

`tests/test_protocol.py` spawns `src/main.py` as a real subprocess and
points `pageUrl` at local `file://` fixtures (a synthetic listing+detail
pair, not the saved `tests/fixtures/*.html` snapshots) so it can exercise
the full two-hop fetch without network access.
