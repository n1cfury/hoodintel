# House Intel Report Generator

A local-first Python tool for generating a property and neighborhood intelligence report from a single address.

The goal of this project is to make home-buying due diligence faster, more repeatable, and less dependent on manually jumping between a dozen tabs, maps, and public records sites. Given an address, the tool gathers publicly available information, analyzes the surrounding area, and produces a clean HTML report you can read in a browser that helps a buyer quickly assess the property, neighborhood, risk factors, and nearby essentials.

This started as a way to reproduce the kind of property and neighborhood threat-intel reports I was manually building during house hunting. The end goal is a tool that can be run locally or eventually deployed as a web app, while staying focused on one job: turning public data into a useful decision-support report for real estate research.

## What the tool does

Given a street address, the tool pulls together OSINT-style housing intelligence and packages it into a readable report. Depending on the configured data sources and API keys, the report can include things like:

- Neighborhood and area context
- Nearby emergency services
- Closest hospitals, ERs, pet clinics, and fire stations
- Important landmarks such as gas stations and grocery stores
- Crime and safety-related context
- Geographic and environmental details
- Elevation / feet and meters above sea level
- Local infrastructure observations
- Walkability and practical livability notes
- Property-adjacent risk indicators worth reviewing further

The output is designed to help with initial screening and deeper due diligence. It is not meant to replace inspections, title review, disclosures, or legal advice.

## Why this exists

Buying a house is one part finance, one part emotion, and one part detective work. Most people do the detective work by hand: checking maps, searching public records, reading neighborhood threads, scanning nearby services, and trying to mentally stitch it all together.

That process is slow and inconsistent.

This project exists to make that process faster and more structured by:

- using publicly available information only
- generating a repeatable report format
- keeping the workflow local-first
- making it easier to compare one property against another
- building toward a tool that can eventually scale into a browser-based app

## End goal

The long-term vision is a real estate intelligence tool that can take an address and generate a polished, decision-ready report with minimal manual effort.

### Near-term goal
A reliable local Python script that:
- accepts an address as input
- queries selected public/open data sources and APIs
- organizes the results into a clear narrative + structured findings
- exports a standalone HTML report

### Long-term goal
A web application that:
- runs the same workflow in a browser
- supports user accounts and saved reports
- stores reusable configuration for APIs and preferences
- compares multiple properties side-by-side
- supports more advanced mapping, scoring, and automation

## Design principles

This project is built around a few rules:

- **Local-first:** run it on your own machine before worrying about deployment
- **Public-data only:** use OSINT and legitimate public or licensed APIs
- **Readable output:** the report should be useful to a normal human, not just a data nerd
- **Modular inputs:** data sources should be swappable as APIs change
- **Decision support, not false certainty:** surface useful signals without pretending the tool can predict everything

## Current workflow

1. You provide a property address, in the browser or on the command line.
2. The address is geocoded, and nearby services and housing data are gathered from public sources.
3. The findings are normalized and organized into report sections.
4. The report is shown in the browser, or written as a standalone HTML file (plus optional JSON).

## Setup

Python 3.10 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export CENSUS_API_KEY="<your key>"    # optional; free at https://api.census.gov/data/key_signup.html
```

Without `CENSUS_API_KEY` the report still runs; the real estate section says the key is missing.

## Usage

### In the browser

```bash
python hoodintel.py --serve
```

Open http://127.0.0.1:8000, enter an address, and the report opens in the browser. It has buttons to
download it as a standalone HTML file or as JSON. A report usually takes 5–15 seconds.

`--host` and `--port` change where it listens. It listens on 127.0.0.1 only by default. The built-in
server is for local use; for a shared server, run it under a WSGI server, e.g.
`gunicorn -b 0.0.0.0:8000 --threads 8 --timeout 180 src.web:app`.

### On the command line

```bash
python hoodintel.py "1234 Example St, San Diego, CA 92101"
# -> 1234_example_st_san_diego_ca_92101.html in the current folder
```

| Option | Purpose |
|---|---|
| `--output PATH` | HTML output path (default: derived from the address) |
| `--json-out PATH` | Also write the raw results as JSON |
| `--acs-year YEAR` | Census ACS year (default: 2023) |
| `--debug` | Include a debug snapshot in the report |
| `--update-data` | Download or refresh the Zillow home value cache now, then exit |
| `--serve` | Run the browser UI instead (`--host`, `--port`) |

The HTML report is a single self-contained file: no external requests, and only one small inline
script, the light/dark toggle (allowed by hash in the page's Content-Security-Policy). With no
choice saved it follows the system setting. It prints cleanly (use the browser's Print → Save as PDF if you need a PDF).

## Data sources

| Source | Used for |
|---|---|
| U.S. Census Geocoder | Address → coordinates, city, state, ZIP, county |
| OpenStreetMap Nominatim | Fallback geocoder for addresses Census doesn't have (common for rural and new addresses; flagged as approximate when not house-level). Primary source for nearby POIs |
| OpenStreetMap Overpass API | Fallback POI source for categories Nominatim misses. Public servers are often at capacity, so it's tried second |
| USGS 3DEP Elevation Point Query Service | Ground elevation (ft and m) at the address. Green above sea level, red below |
| OurAirports | Closest regional or international airport: U.S. large and medium airports with scheduled passenger service. Bundled as `src/data/us_airports.csv` (public domain); refresh with `python scripts/update_airports.py` |
| iNaturalist | Environmental section: common plants and trees, venomous snakes and spiders, problem wildlife (coyotes, deer, wild hogs, bears, raccoons, ...), and species introduced to the state. From research-grade observations within 15 km, ranked by observation count |
| Zillow Home Value Index (ZHVI) | ZIP-level typical home value (average value of mid-priced homes, the 35th–65th percentile) and its 1-year change |
| U.S. Census ACS 5-year | ZIP-level (ZCTA) average and median owner-occupied home value. Needs `CENSUS_API_KEY` |

- **Every lookup after geocoding is optional.** A failed source becomes a warning in the report, and the
  rest still renders.
- **Nearby POIs** (hospital, urgent care, fire station, veterinary clinic, grocery store, school, gas station): Nominatim is searched in a
  2 km box around the address, widening to 8 and 25 km only when needed. Distances are straight-line.
- **Zillow cache:** Zillow publishes ZHVI as one ~120 MB CSV for every ZIP. It's downloaded the first
  time it's needed (about 20 s), reduced to a ~2 MB per-ZIP file, and refreshed after 30 days. The web
  UI downloads it in the background at startup. The cache lives in `$HOODINTEL_CACHE_DIR`, or
  `~/.cache/hoodintel` by default. If a refresh fails, the old cache keeps being used.
- **Environmental:** venomous groups are vipers and elapids (snakes) and widow and recluse spiders.
  Species iNaturalist lists as introduced in the state are tagged "introduced" in every list.
  iNaturalist runs at the same time as the OpenStreetMap lookups, so it adds little time.
- **Usage policies:** iNaturalist requests are spaced 1 s apart. Nominatim requests are spaced at least 1.1 s apart (shared across concurrent web
  requests), and Overpass is retried with backoff when busy. The web UI caches each report for an hour,
  so the download buttons don't repeat the lookups. These public services aren't meant for heavy
  traffic; a busy shared deployment should run its own instances.

## Tests

```bash
python -m unittest discover -s tests
```

Offline: every network call is mocked.

## Roadmap

- Container image (Dockerfile) for running on a web server
- More sources from `src/config.py` (AirNow air quality, FCC broadband, Walk Score, crime data)
- Map view, saved reports, side-by-side comparison
