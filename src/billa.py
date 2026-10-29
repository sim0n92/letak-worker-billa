"""Pure parsing functions for the BILLA Slovakia leaflet listing page.

billa.sk renders the leaflet list server-side (Nuxt/Kontent.ai), so both the
listing page and each leaflet's detail page can be parsed with plain regex
over the raw HTML - no JS execution needed.

Two-stage layout:
  - the listing page (DEFAULT_URL) has one teaser card per leaflet with its
    type, human validity date range, and a link to a detail page
  - each detail page embeds the actual PDF download link server-side

Both stages are exposed separately (parse_leaflet_list / parse_pdf_url) so
each can be unit-tested offline against a saved HTML fixture. parse_leaflets
combines already-fetched HTML for both stages into full leaflet records.
"""
from __future__ import annotations

import re
import urllib.parse
import urllib.request

DEFAULT_URL = "https://www.billa.sk/letaky-a-akcie"
DEFAULT_TIMEOUT = 15  # seconds per request; keeps N detail fetches within manifest execution.timeout

_USER_AGENT = "Mozilla/5.0 (compatible; letak-worker-billa/1.0; +https://github.com/sim0n92/letak-worker-billa)"

_TEASER_RE = re.compile(
    r'<a href="(?P<href>[^"]+)"[^>]*data-teaser-name="(?P<type>[^"]*)"'
    r'.*?<div class="text-base-color[^"]*">(?P<daterange>.*?)</div>',
    re.S,
)

_DATE_RANGE_RE = re.compile(
    r"od\s+\S+\s+(\d{1,2})\.\s*(\d{1,2})\.\s+do\s+\S+\s+(\d{1,2})\.\s*(\d{1,2})\.\s+(\d{4})"
)

# the "Stiahnuť PDF" button; any host (letak.billa.sk until 2026-10, view.publitas.com since) and any
# attributes before the href (style/class)
_PDF_RE = re.compile(
    r'<a\b[^>]*?\bhref="(?P<pdf>https://[^"]+?\.pdf[^"]*)"[^>]*aria-label="Stiahnu[^"]*PDF"'
)


def fetch(url: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Fetch a page and return its HTML as text. Not pure - performs I/O."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _normalize_whitespace(text: str) -> str:
    return text.replace("&nbsp;", " ").replace("\xa0", " ")


def _parse_date_range(text: str) -> tuple[str, str] | None:
    """Parse "platí od stredy 1. 7. do utorka 7. 7. 2026" -> ("2026-07-01", "2026-07-07").

    Only the end year is present in the source text; the start year rolls back
    one year when the start month is after the end month (December -> January).
    """
    m = _DATE_RANGE_RE.search(_normalize_whitespace(text))
    if not m:
        return None
    from_day, from_month, to_day, to_month, to_year = (int(g) for g in m.groups())
    from_year = to_year - 1 if from_month > to_month else to_year
    valid_from = f"{from_year:04d}-{from_month:02d}-{from_day:02d}"
    valid_to = f"{to_year:04d}-{to_month:02d}-{to_day:02d}"
    return valid_from, valid_to


def parse_leaflet_list(html: str, base_url: str = DEFAULT_URL) -> list[dict]:
    """Parse the listing page into leaflet stubs (type, dates, detail page URL).

    base_url resolves relative hrefs (urljoin) - defaults to the production
    listing URL, but tests can pass a file:// base to resolve against local
    fixtures instead.
    """
    items = []
    for m in _TEASER_RE.finditer(html):
        date_range = _parse_date_range(m.group("daterange"))
        if not date_range:
            continue
        valid_from, valid_to = date_range
        leaflet_type = m.group("type").strip()
        items.append(
            {
                "type": leaflet_type,
                "title": leaflet_type,
                "validFrom": valid_from,
                "validTo": valid_to,
                "detailUrl": urllib.parse.urljoin(base_url, m.group("href")),
            }
        )
    return items


def parse_pdf_url(html: str) -> str | None:
    """Parse a leaflet detail page for the direct PDF download link."""
    m = _PDF_RE.search(html)
    return m.group("pdf") if m else None


def parse_leaflets(
    listing_html: str, detail_html_by_url: dict[str, str], base_url: str = DEFAULT_URL
) -> list[dict]:
    """Combine the listing page with already-fetched detail pages into full records.

    detail_html_by_url maps each stub's detailUrl to that page's HTML (fetched
    by the caller, since this module only parses - it does not orchestrate I/O).
    """
    leaflets = []
    for item in parse_leaflet_list(listing_html, base_url):
        detail_html = detail_html_by_url.get(item["detailUrl"])
        pdf_url = parse_pdf_url(detail_html) if detail_html else None
        leaflets.append(
            {
                "type": item["type"],
                "title": item["title"],
                "validFrom": item["validFrom"],
                "validTo": item["validTo"],
                "viewerUrl": item["detailUrl"],
                "pdfUrl": pdf_url,
            }
        )
    return leaflets


def leaflet_key(leaflet_type: str, valid_from: str, valid_to: str) -> str:
    return f"{leaflet_type}|{valid_from}|{valid_to}"
