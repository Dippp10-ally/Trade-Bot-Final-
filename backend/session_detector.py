from datetime import datetime, timezone


def detect_market_session(now: datetime | None = None) -> str:
    now = now or datetime.now(tz=timezone.utc)
    hour = now.hour
    if 0 <= hour < 8:
        return "Asia"
    if 8 <= hour < 13:
        return "London"
    if 13 <= hour < 22:
        return "New York"
    return "Asia"
