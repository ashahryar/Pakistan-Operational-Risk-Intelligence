"""
PDMA Completeness Checker

Calculates completeness percentage for

1. Daily Reports
2. Rainfall Reports
3. Gauge Reports
"""

from typing import Dict


# ==========================================================
# DAILY
# ==========================================================

def daily_score(report: Dict):

    score = 0
    total = 8

    if report.get("report_date"):
        score += 1

    if report.get("report_time"):
        score += 1

    if report.get("forecast"):
        score += 1

    if report.get("weather_alert"):
        score += 1

    if report.get("temperature"):
        score += 1

    if report.get("rainfall"):
        score += 1

    if report.get("dams"):
        score += 1

    if report.get("source_file"):
        score += 1

    percentage = round(score / total * 100, 2)

    return {
        "score": percentage,
        "passed": percentage >= 70
    }


# ==========================================================
# RAINFALL
# ==========================================================

def rainfall_score(report: Dict):

    score = 0
    total = 5

    if report.get("report_date"):
        score += 1

    if report.get("station_count", 0) > 0:
        score += 1

    if report.get("stations"):
        score += 1

    if report.get("report_year"):
        score += 1

    if report.get("source_file"):
        score += 1

    percentage = round(score / total * 100, 2)

    return {
        "score": percentage,
        "passed": percentage >= 80
    }


# ==========================================================
# GAUGE
# ==========================================================

def gauge_score(report: Dict):

    score = 0
    total = 5

    if report.get("report_datetime"):
        score += 1

    if report.get("gauge_count", 0) > 0:
        score += 1

    if report.get("gauges"):
        score += 1

    if report.get("source_file"):
        score += 1

    if report.get("report_type"):
        score += 1

    percentage = round(score / total * 100, 2)

    return {
        "score": percentage,
        "passed": percentage >= 80
    }


# ==========================================================
# AUTO
# ==========================================================

def completeness_score(report: Dict):

    report_type = report.get("report_type")

    if report_type == "daily":
        return daily_score(report)

    if report_type == "rainfall":
        return rainfall_score(report)

    if report_type == "gauge":
        return gauge_score(report)

    return {
        "score": 0,
        "passed": False
    }