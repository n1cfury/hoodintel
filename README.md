# House Intel Report Generator

A local-first Python tool for generating a property and neighborhood intelligence report from a single address.

The goal of this project is to make home-buying due diligence faster, more repeatable, and less dependent on manually jumping between a dozen tabs, maps, and public records sites. Given an address, the tool gathers publicly available information, analyzes the surrounding area, and produces a clean PDF report that helps a buyer quickly assess the property, neighborhood, risk factors, and nearby essentials.

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
- exports a PDF report

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
- **Readable output:** the PDF should be useful to a normal human, not just a data nerd
- **Modular inputs:** data sources should be swappable as APIs change
- **Decision support, not false certainty:** surface useful signals without pretending the tool can predict everything

## Current workflow

1. You provide a property address.
2. The script gathers data from configured sources.
3. The findings are normalized and organized into report sections.
4. A PDF is generated for review and comparison.

## Usage

### Basic example

```bash
python main.py "1234 Example St, San Diego, CA 92101"
