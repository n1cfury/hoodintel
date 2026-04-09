from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..models import POIResult, ReportData
from ..utils import escape_text


def format_currency(value: int | float | None) -> str:
    if value is None:
        return "N/A"
    return f"${value:,.0f}"


def poi_to_lines(poi: POIResult | None) -> list[str]:
    if not poi:
        return ["No result found."]
    lines = [
        f"Name: {poi.name}",
        f"Distance: {poi.distance_miles} miles",
        f"Coordinates: {poi.latitude}, {poi.longitude}",
    ]
    if poi.address:
        lines.append(f"Address: {poi.address}")
    if poi.phone:
        lines.append(f"Phone: {poi.phone}")
    if poi.website:
        lines.append(f"Website: {poi.website}")
    return lines


def make_table(rows: list[list[str]]) -> Table:
    table = Table(rows, colWidths=[2.2 * inch, 4.8 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.75, colors.black),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("LEADING", (0, 0), (-1, -1), 11),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
            ]
        )
    )
    return table


def build_pdf(report: ReportData, output_path: Path, include_debug_snapshot: bool = False) -> None:
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.7 * inch,
        leftMargin=0.7 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title="Neighborhood OSINT Report",
        author="HoodIntel",
    )

    styles = getSampleStyleSheet()
    body_style = styles["BodyText"]
    body_style.leading = 14
    mono_style = ParagraphStyle(
        "MonoSmall",
        parent=body_style,
        fontName="Courier",
        fontSize=8.5,
        leading=10,
    )

    story: list[Any] = []
    subject = report.subject

    story.append(Paragraph("Neighborhood OSINT Report", styles["Title"]))
    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph(f"Generated: {report.generated_at_utc}", body_style))
    story.append(Spacer(1, 0.15 * inch))

    if report.executive_summary:
        story.append(Paragraph("Executive Summary", styles["Heading2"]))
        for line in report.executive_summary:
            story.append(Paragraph(f"• {escape_text(line)}", body_style))
        story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph("Subject Property", styles["Heading2"]))
    story.append(
        make_table(
            [
                ["Input Address", subject.input_address],
                ["Matched Address", subject.matched_address],
                ["Latitude", str(subject.latitude)],
                ["Longitude", str(subject.longitude)],
                ["ZIP Code", subject.zip_code or "N/A"],
                ["City", subject.city or "N/A"],
                ["State", subject.state or "N/A"],
                ["County", subject.county or "N/A"],
            ]
        )
    )
    story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph("Important Landmarks", styles["Heading2"]))
    for line in poi_to_lines(report.important_landmarks.get("closest_gas_station")):
        story.append(Paragraph(escape_text(line), body_style))
    story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph("Emergency Services", styles["Heading2"]))
    for label, key in [
        ("Closest Hospital", "closest_hospital"),
        ("Closest Urgent Care", "closest_urgent_care"),
        ("Closest Veterinary Clinic", "closest_veterinary_clinic"),
    ]:
        story.append(Paragraph(label, styles["Heading3"]))
        for line in poi_to_lines(report.emergency_services.get(key)):
            story.append(Paragraph(escape_text(line), body_style))
        story.append(Spacer(1, 0.08 * inch))

    story.append(Paragraph("Real Estate Metrics", styles["Heading2"]))
    if report.real_estate_metrics:
        metrics = report.real_estate_metrics
        story.append(
            make_table(
                [
                    ["Data Source", metrics.source],
                    ["Geography", metrics.label or "N/A"],
                    ["Median Owner-Occupied Home Value", format_currency(metrics.median_owner_occupied_home_value_usd)],
                ]
            )
        )
        story.append(Spacer(1, 0.08 * inch))
        story.append(Paragraph(escape_text(metrics.note), body_style))
    else:
        story.append(Paragraph("No real estate metrics available.", body_style))
    story.append(Spacer(1, 0.15 * inch))

    if report.hardening_plan:
        story.append(Paragraph("Basic Hardening Plan", styles["Heading2"]))
        rows = [["Item", "Qty / Deploy / Why"]]
        for rec in report.hardening_plan:
            rows.append([rec.item, f"{rec.quantity} | {rec.deploy_where} | {rec.rationale}"])
        story.append(make_table(rows))
        story.append(Spacer(1, 0.15 * inch))

    if report.operating_rules:
        story.append(Paragraph("Operating Rules", styles["Heading2"]))
        for rule in report.operating_rules:
            story.append(Paragraph(f"• {escape_text(rule)}", body_style))
        story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph("Sources Used", styles["Heading2"]))
    for source in report.sources:
        story.append(Paragraph(f"• {escape_text(source)}", body_style))
    story.append(Spacer(1, 0.15 * inch))

    if report.warnings:
        story.append(Paragraph("Lookup Warnings / Failures", styles["Heading2"]))
        for warning in report.warnings:
            story.append(Paragraph(f"• {escape_text(warning.source)}: {escape_text(warning.message)}", body_style))
        story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph("Raw Notes", styles["Heading2"]))
    story.append(
        Paragraph(
            "This report uses publicly available information only. It is intended as a lightweight neighborhood "
            "and logistics brief, not legal, medical, insurance, appraisal, or investment advice.",
            body_style,
        )
    )
    story.append(Spacer(1, 0.08 * inch))
    story.append(
        Paragraph(
            "The real estate metric shown here is Census-based and lagging by design. It is useful as a baseline, "
            "not a crystal ball.",
            body_style,
        )
    )

    if include_debug_snapshot and report.debug_snapshot:
        story.append(Spacer(1, 0.15 * inch))
        story.append(Paragraph("Debug Snapshot", styles["Heading2"]))
        compact_json = json.dumps(report.debug_snapshot, indent=2)[:4000]
        for line in compact_json.splitlines():
            story.append(Paragraph(escape_text(line), mono_style))

    doc.build(story)
