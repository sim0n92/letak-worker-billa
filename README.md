# letak-worker-billa

Process Class (spec v1.0, type `stdin`) that checks the BILLA Slovakia leaflet
page for new leaflets and returns their metadata + URLs. It does not download
anything and keeps no state between runs.

- Leaflet page: https://www.billa.sk/letaky-a-akcie
- Protocol spec: `0ics-srls/ProcessMonitor` → `docs/process-class-specification-v1.md`

## How it works

1. Fetch the listing page and parse each leaflet teaser: type, human validity
   date range (`platí od ... do ...`), and a link to its detail page.
2. Fetch each detail page and parse the server-rendered PDF download link.
3. Build a novelty key per leaflet: `type|validFrom|validTo` (deliberately not
   the PDF URL, since its UUID changes on re-upload even for the same leaflet).
4. Return only leaflets whose key is not already in the caller-supplied
   `knownLeaflets`, optionally filtered by `types`.

The worker is stateless: the caller (ProcessMonitor) is responsible for
persisting `knownLeaflets` between runs.

## Input (`execute`)

```json
{
  "outputPath": "/abs/path/result.json",
  "knownLeaflets": ["Aktuálny leták|2026-06-24|2026-06-30"],
  "types": [],
  "pageUrl": "https://www.billa.sk/letaky-a-akcie"
}
```

## Output

```json
{
  "outputPath": "...",
  "count": 1,
  "hasNew": true,
  "leaflets": [
    {"type": "Aktuálny leták", "from": "2026-07-01", "to": "2026-07-07", "url": "https://letak.billa.sk/.../....pdf"}
  ],
  "fileSize": 123
}
```

## Layout

- `src/billa.py` — pure parsing functions (`fetch`, `parse_leaflet_list`,
  `parse_pdf_url`, `parse_leaflets`, `leaflet_key`), testable offline.
- `src/main.py` — `ProcessClass` protocol wrapper (stdin/stdout JSON Lines,
  exit codes, `--version`, terminate) + `BillaWorker.execute()`.
- `manifest.json` — Process Class manifest.
- `tests/fixtures/*.html` — saved snapshots of the listing and a detail page.
- `tests/test_parser.py` — offline parser tests against the fixtures.
- `tests/test_protocol.py` — runs `main.py` as a subprocess against local
  `file://` fixtures and checks the protocol contract (exit codes, JSON
  Lines shape, `--version`, novelty filtering).

## Running tests locally

```bash
python tests/test_parser.py
python tests/test_protocol.py
```

## Running the worker manually

```bash
echo '{"_action":"execute","outputPath":"/tmp/result.json","knownLeaflets":[],"_meta":{"executionId":"local"}}' | python src/main.py
```
