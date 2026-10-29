"""Offline tests for src/billa.py against saved HTML fixtures. No network access."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

import billa  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class ParseLeafletListTests(unittest.TestCase):
    def setUp(self):
        self.html = _read_fixture("billa.html")
        self.stubs = billa.parse_leaflet_list(self.html)

    def test_finds_all_teasers(self):
        self.assertEqual(len(self.stubs), 7)

    def test_types_are_extracted(self):
        types = {s["type"] for s in self.stubs}
        self.assertEqual(
            types,
            {
                "Aktuálny leták",
                "BILLA Bonus leták",
                "Katalóg Futbal",
                "Katalóg Letné dni",
                "Katalóg Upratovanie",
                "Leták BILLA Trnava",
                "Leták BILLA Záhorská Bystrica",
            },
        )

    def test_dates_parsed_with_year_rollover_handling(self):
        by_type = {s["type"]: s for s in self.stubs}
        self.assertEqual(by_type["Aktuálny leták"]["validFrom"], "2026-07-01")
        self.assertEqual(by_type["Aktuálny leták"]["validTo"], "2026-07-07")
        self.assertEqual(by_type["Katalóg Futbal"]["validFrom"], "2026-06-10")
        self.assertEqual(by_type["Katalóg Futbal"]["validTo"], "2026-07-21")

    def test_detail_url_is_absolute(self):
        by_type = {s["type"]: s for s in self.stubs}
        self.assertEqual(
            by_type["Aktuálny leták"]["detailUrl"],
            "https://www.billa.sk/letaky-a-akcie/letaky",
        )

    def test_no_teasers_found_in_empty_html(self):
        self.assertEqual(billa.parse_leaflet_list("<html><body>nothing here</body></html>"), [])


class ParsePdfUrlTests(unittest.TestCase):
    def test_extracts_pdf_link_from_detail_page(self):
        html = _read_fixture("billa_detail.html")
        pdf_url = billa.parse_pdf_url(html)
        self.assertIsNotNone(pdf_url)
        self.assertTrue(pdf_url.startswith("https://letak.billa.sk/"))
        self.assertIn(".pdf", pdf_url)

    def test_extracts_publitas_pdf_link_with_attributes_before_href(self):
        # 2026-10: the PDF moved to view.publitas.com and the <a> carries style/class before href
        pdf_url = billa.parse_pdf_url(_read_fixture("billa_detail_publitas.html"))
        self.assertIsNotNone(pdf_url)
        self.assertTrue(pdf_url.startswith("https://view.publitas.com/"))
        self.assertIn(".pdf", pdf_url)

    def test_returns_none_when_no_pdf_link_present(self):
        self.assertIsNone(billa.parse_pdf_url("<html><body>no pdf here</body></html>"))


class ParseLeafletsTests(unittest.TestCase):
    def test_combines_listing_and_detail_pages(self):
        listing_html = _read_fixture("billa.html")
        detail_html = _read_fixture("billa_detail.html")
        stubs = billa.parse_leaflet_list(listing_html)
        current = next(s for s in stubs if s["type"] == "Aktuálny leták")

        leaflets = billa.parse_leaflets(listing_html, {current["detailUrl"]: detail_html})

        current_leaflet = next(lf for lf in leaflets if lf["type"] == "Aktuálny leták")
        self.assertIsNotNone(current_leaflet["pdfUrl"])
        self.assertTrue(current_leaflet["pdfUrl"].startswith("https://letak.billa.sk/"))
        self.assertEqual(current_leaflet["viewerUrl"], current["detailUrl"])

        others = [lf for lf in leaflets if lf["type"] != "Aktuálny leták"]
        self.assertTrue(all(lf["pdfUrl"] is None for lf in others))


class LeafletKeyTests(unittest.TestCase):
    def test_key_format(self):
        self.assertEqual(
            billa.leaflet_key("Aktuálny leták", "2026-07-01", "2026-07-07"),
            "Aktuálny leták|2026-07-01|2026-07-07",
        )

    def test_different_types_same_dates_produce_different_keys(self):
        k1 = billa.leaflet_key("Leták A", "2026-01-01", "2026-01-07")
        k2 = billa.leaflet_key("Leták B", "2026-01-01", "2026-01-07")
        self.assertNotEqual(k1, k2)


if __name__ == "__main__":
    unittest.main()
