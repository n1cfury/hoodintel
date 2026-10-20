"""Offline tests. Run: python -m unittest discover -s tests

No network: the pipeline is patched with a synthetic report that includes
hostile OSM tag values to check escaping and link filtering.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hoodintel  # noqa: E402
from src import web  # noqa: E402
from src.exceptions import NeighborhoodReportError  # noqa: E402
from src.models import GeocodeResult, LookupWarning, POIResult, RealEstateMetrics, ReportData  # noqa: E402
from src import http as hood_http  # noqa: E402
from src.collectors import census, geocode, pois  # noqa: E402
from src.config import AppConfig  # noqa: E402
from src.renderers.html import _safe_url, render_report  # noqa: E402

hood_http.MIN_INTERVAL = {}          # no Nominatim throttling in tests
pois.OVERPASS_BACKOFF_SECONDS = [0, 0]

ADDRESS = "1234 Example St, San Diego, CA 92101"
NOMINATIM = "https://nominatim.openstreetmap.org/search"


def poi(category, name, miles, **kw):
    return POIResult(category=category, name=name, latitude=32.71, longitude=-117.16,
                     distance_miles=miles, osm_type="node", osm_id=42, **kw)


def sample_report(**overrides):
    r = ReportData(
        generated_at_utc="2026-10-20T00:00:00+00:00",
        sources=["U.S. Census Geocoder", "OpenStreetMap / Overpass API"],
        subject=GeocodeResult(ADDRESS, "1234 EXAMPLE ST, SAN DIEGO, CA, 92101",
                              32.715736, -117.161087, "92101", "SAN DIEGO", "CA"),
        important_landmarks={"closest_gas_station": poi("Closest Gas Station", "Fuel <b>Stop</b>", 0.4,
                                                        website="javascript:alert(1)")},
        emergency_services={
            "closest_hospital": poi("Closest Hospital", "General Hospital", 1.25,
                                    phone="+1 555 0100", website="http://hospital.example"),
            "closest_urgent_care": None,
            "closest_veterinary_clinic": poi("Closest Veterinary Clinic", "Vet", 2.0),
        },
        real_estate_metrics=RealEstateMetrics("U.S. Census ACS 2023 5-year", "92101",
                                              "ZCTA5 92101", 750000, "Median value note."),
        executive_summary=["Target property: <script>x</script>."],
        warnings=[LookupWarning("Closest Urgent Care", "timeout")],
    )
    for k, v in overrides.items():
        setattr(r, k, v)
    return r


class RenderTests(unittest.TestCase):
    def test_report_content_and_escaping(self):
        html = render_report(sample_report())
        self.assertIn("1234 EXAMPLE ST, SAN DIEGO, CA, 92101", html)
        self.assertIn("$750,000", html)
        self.assertIn("1.25 mi", html)
        self.assertIn("https://www.openstreetmap.org/node/42", html)
        self.assertIn('href="http://hospital.example"', html)
        self.assertNotIn("<script>x", html)
        self.assertNotIn("<b>Stop", html)
        self.assertNotIn('href="javascript:', html)
        self.assertIn("Closest Urgent Care", html)          # None POI still gets a row
        self.assertIn("⚠ Closest Urgent Care: timeout", html)
        self.assertIn("form-action 'none'", html)
        self.assertNotIn("Download HTML", html)

    def test_web_mode_adds_toolbar(self):
        html = render_report(sample_report(), web=True)
        self.assertIn("Download HTML", html)
        self.assertIn("form-action 'self'", html)

    def test_missing_metrics(self):
        html = render_report(sample_report(real_estate_metrics=None))
        self.assertIn("No real estate metrics available", html)

    def test_safe_url(self):
        self.assertEqual(_safe_url("https://a.example/x"), "https://a.example/x")
        self.assertEqual(_safe_url("http://a.example"), "http://a.example")
        self.assertIsNone(_safe_url("javascript:alert(1)"))
        self.assertIsNone(_safe_url("data:text/html,x"))
        self.assertIsNone(_safe_url("//a.example"))
        self.assertIsNone(_safe_url(None))


def resp(status=200, payload=None, headers=None):
    r = requests.Response()
    r.status_code = status
    r._content = json.dumps(payload).encode() if payload is not None else b""
    r.headers.update(headers or {})
    r.url = "https://example.test/"
    return r


def nominatim_item(name, lat, lon, cat="amenity", typ="fuel", osm_id=1):
    return {"name": name, "lat": str(lat), "lon": str(lon), "category": cat, "type": typ,
            "osm_type": "node", "osm_id": osm_id, "extratags": {"phone": "+1 555 0101"},
            "address": {"house_number": "1", "road": "Main St", "city": "Town",
                        "ISO3166-2-lvl4": "US-CA", "postcode": "92101"}}


class CollectorTests(unittest.TestCase):
    LAT, LON = 32.7168, -117.1628

    def test_nominatim_closest_trusts_small_box(self):
        session = mock.Mock()
        session.get.return_value = resp(payload=[
            nominatim_item("Far", self.LAT + 0.012, self.LON, osm_id=2),
            nominatim_item("Near", self.LAT + 0.002, self.LON),
        ])
        poi = pois.nominatim_closest(session, pois.POI_CATEGORIES[0], self.LAT, self.LON, AppConfig())
        self.assertEqual((poi.name, poi.phone, poi.address), ("Near", "+1 555 0101", "1 Main St, Town, CA, 92101"))
        self.assertEqual(session.get.call_count, 1)

    def test_nominatim_widens_when_hit_outside_inscribed_circle(self):
        session = mock.Mock()
        corner = nominatim_item("Corner", self.LAT + 0.017, self.LON + 0.02)   # in the 2 km box, > 2 km away
        session.get.side_effect = [resp(payload=[corner]), resp(payload=[corner, nominatim_item("Mid", self.LAT + 0.015, self.LON)])]
        poi = pois.nominatim_closest(session, pois.POI_CATEGORIES[0], self.LAT, self.LON, AppConfig())
        self.assertEqual(poi.name, "Mid")
        self.assertEqual(session.get.call_count, 2)

    def test_urgent_care_matcher(self):
        self.assertTrue(pois._is_urgent_care({"amenity": "clinic", "name": "AFC Urgent Care"}))
        self.assertFalse(pois._is_urgent_care({"amenity": "cafe", "name": "Urgent Coffee"}))
        self.assertFalse(pois._is_urgent_care({"amenity": "clinic", "name": "Family Dental"}))

    def test_overpass_fallback_for_missing_categories(self):
        session = mock.Mock()
        session.get.side_effect = requests.ConnectionError("nominatim down")
        session.post.side_effect = [
            resp(502),                                                  # first endpoint busy
            resp(payload={"elements": [{"type": "node", "id": 9, "lat": self.LAT, "lon": self.LON,
                                        "tags": {"amenity": "fuel", "name": "Gas"}}]}),
        ]
        found, errors = pois.find_closest_pois(session, lat=self.LAT, lon=self.LON,
                                               categories=pois.POI_CATEGORIES[:1],
                                               config=AppConfig(search_radii_meters=[8000]))
        self.assertEqual(found["Closest Gas Station"].name, "Gas")
        self.assertIn("Nominatim search", errors[0])

    def test_overpass_all_failing_is_a_warning_not_a_crash(self):
        session = mock.Mock()
        session.get.return_value = resp(payload=[])
        session.post.return_value = resp(504)
        found, errors = pois.find_closest_pois(session, lat=self.LAT, lon=self.LON,
                                               categories=pois.POI_CATEGORIES[:1],
                                               config=AppConfig(search_radii_meters=[8000]))
        self.assertIsNone(found["Closest Gas Station"])
        self.assertIn("Overpass lookup within 8 km failed", errors[0])

    def test_geocode_falls_back_to_nominatim(self):
        session = mock.Mock()
        session.get.side_effect = [
            resp(payload={"result": {"addressMatches": []}}),
            resp(payload=[{"lat": "34.47", "lon": "-81.88", "display_name": "Clinton, SC",
                           "addresstype": "road", "address": {"town": "Clinton", "ISO3166-2-lvl4": "US-SC",
                                                               "postcode": "29325"}}]),
        ]
        g = geocode.geocode_address(session, "1 Somewhere Rd, Clinton, SC")
        self.assertEqual((g.source, g.state, g.zip_code, g.city), ("OpenStreetMap Nominatim", "SC", "29325", "Clinton"))
        self.assertEqual(g.precision, "approximate (road level)")

    def test_geocode_no_match_anywhere(self):
        session = mock.Mock()
        session.get.side_effect = [resp(payload={"result": {"addressMatches": []}}), resp(payload=[])]
        with self.assertRaises(NeighborhoodReportError):
            geocode.geocode_address(session, "nowhere")

    def test_acs_missing_key_message(self):
        session = mock.Mock()
        session.get.return_value = resp(302, headers={"Location": "https://api.census.gov/data/missing_key.html"})
        with self.assertRaisesRegex(NeighborhoodReportError, "CENSUS_API_KEY"):
            census.get_real_estate_metrics(session, "92101", 2023)


class CliTests(unittest.TestCase):
    def test_writes_html_and_json(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(hoodintel, "generate_report_data", return_value=sample_report()):
            out, js = Path(d) / "r.html", Path(d) / "r.json"
            rc = hoodintel.main([ADDRESS, "--output", str(out), "--json-out", str(js)])
            self.assertEqual(rc, 0)
            self.assertIn("<!doctype html>", out.read_text())
            self.assertEqual(json.loads(js.read_text())["subject"]["zip_code"], "92101")

    def test_no_geocode_match(self):
        err = NeighborhoodReportError("No Census geocoder match found")
        with mock.patch.object(hoodintel, "generate_report_data", side_effect=err):
            self.assertEqual(hoodintel.main(["nowhere", "--output", "/dev/null"]), 4)

    def test_address_required_without_serve(self):
        with self.assertRaises(SystemExit):
            hoodintel.parse_args([])
        self.assertTrue(hoodintel.parse_args(["--serve"]).serve)


class WebTests(unittest.TestCase):
    def setUp(self):
        web._cache.clear()
        self.client = web.app.test_client()

    def test_index_and_health(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Generate report", r.data)
        self.assertEqual(self.client.get("/healthz").data, b"ok")
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")

    def test_report_html_json_download_and_cache(self):
        with mock.patch.object(web, "generate_report_data", return_value=sample_report()) as gen:
            r = self.client.post("/report", data={"address": ADDRESS})
            self.assertEqual(r.status_code, 200)
            self.assertIn(b"Download JSON", r.data)

            r = self.client.post("/report", data={"address": ADDRESS.lower(), "format": "json", "download": "1"})
            self.assertEqual(r.json["subject"]["city"], "SAN DIEGO")
            self.assertIn('filename="1234_example_st_san_diego_ca_92101.json"', r.headers["Content-Disposition"])

            r = self.client.post("/report", data={"address": ADDRESS, "download": "1"})
            self.assertNotIn(b"Download JSON", r.data)       # standalone file: no toolbar
            self.assertEqual(gen.call_count, 1)                # cached across all three

    def test_bad_input(self):
        self.assertEqual(self.client.post("/report", data={"address": "  "}).status_code, 400)
        self.assertEqual(self.client.post("/report", data={"address": "x" * 500}).status_code, 400)
        self.assertEqual(self.client.post("/report", data={"address": "a", "format": "pdf"}).status_code, 400)

    def test_upstream_errors(self):
        with mock.patch.object(web, "generate_report_data",
                               side_effect=NeighborhoodReportError("No Census geocoder match found for: <x>")):
            r = self.client.post("/report", data={"address": "<x>"})
            self.assertEqual(r.status_code, 422)
            self.assertIn(b"No Census geocoder match", r.data)
            self.assertNotIn(b"<x>", r.data)
        with mock.patch.object(web, "generate_report_data", side_effect=requests.ConnectionError("boom")):
            self.assertEqual(self.client.post("/report", data={"address": "y"}).status_code, 502)


if __name__ == "__main__":
    unittest.main()
