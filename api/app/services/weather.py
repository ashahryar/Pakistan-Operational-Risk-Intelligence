from __future__ import annotations

from api.app.db import fetch_all


def list_latest_weather(city: str | None = None, limit: int = 200) -> list[dict]:
    """
    Returns the most recent PMD daily-forecast reading per city
    (pmd_daily_forecast -- the real, DAG-populated table; see
    dashboard/db.py::get_latest_weather() for the equivalent dashboard
    query, which this mirrors rather than duplicating a third time).
    """
    if city:
        query = """
            SELECT DISTINCT ON (city)
                city, district, province, temperature, humidity,
                forecast_day_1, forecast_day_2, forecast_day_3, category, scraped_at
            FROM pmd_daily_forecast
            WHERE LOWER(city) = LOWER(:city)
            ORDER BY city, scraped_at DESC
        """
        return fetch_all(query, {"city": city})

    query = """
        SELECT DISTINCT ON (city)
            city, district, province, temperature, humidity,
            forecast_day_1, forecast_day_2, forecast_day_3, category, scraped_at
        FROM pmd_daily_forecast
        ORDER BY city, scraped_at DESC
        LIMIT :limit
    """
    return fetch_all(query, {"limit": limit})
