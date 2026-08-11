"""
PDMA Schema Validation

Validates:

1. Daily Report
2. Rainfall Report
3. Gauge Report
"""


def validate_schema(data):

    errors = []

    report_type = data.get("report_type")

    # ==========================================================
    # DAILY REPORT
    # ==========================================================

    if report_type == "daily":
        required = [

            "report_date",
            "report_time",
            "forecast",
            "weather_alert",
            "temperature",
            "rainfall",
            "dams",
        ]

        for field in required:

            if field not in data:

                errors.append(f"Missing field : {field}")

        if not data.get("report_date"):

            errors.append("Empty report_date")

        if not data.get("forecast"):

            errors.append("Forecast is empty")

        if not isinstance(data.get("temperature"), dict):

            errors.append("Temperature should be dictionary")

        if not isinstance(data.get("rainfall"), dict):

            errors.append("Rainfall should be dictionary")

        if not isinstance(data.get("dams"), list):
            errors.append("Dams should be list")

    # ==========================================================
    # RAINFALL REPORT
    # ==========================================================

    elif report_type == "rainfall":

        required = [

            "report_date",
            "stations",

        ]

        for field in required:

            if field not in data:

                errors.append(f"Missing field : {field}")

        stations = data.get("stations", [])

        if len(stations) == 0:

            errors.append("No rainfall stations found")

        for i, station in enumerate(stations):

            if "station" not in station:

                errors.append(f"Station {i} missing station")

            if "rainfall_mm" not in station:

                errors.append(f"Station {i} missing rainfall_mm")

    # ==========================================================
    # GAUGE REPORT
    # ==========================================================

    elif report_type == "gauge":

        required = [

            "report_datetime",
            "gauges",

        ]

        for field in required:

            if field not in data:

                errors.append(f"Missing field : {field}")

        gauges = data.get("gauges", [])

        if len(gauges) == 0:

            errors.append("No gauge stations found")

        for i, gauge in enumerate(gauges):

            if "station" not in gauge:

                errors.append(f"Gauge {i} missing station")

            if "river" not in gauge:

                errors.append(f"Gauge {i} missing river")

            if "flow_status" not in gauge:

                errors.append(f"Gauge {i} missing flow_status")

    # ==========================================================
    # UNKNOWN REPORT
    # ==========================================================

    else:

        errors.append(f"Unknown report type : {report_type}")

    # ==========================================================

    return len(errors) == 0, errors