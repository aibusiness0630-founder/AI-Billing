"""
India time (IST) helpers.

The database stores datetimes in UTC (datetime.utcnow). Servers like Render
also run in UTC, so we convert to IST only when we SHOW a time.
"""
from datetime import datetime, timedelta
from flask.templating import Environment

IST_OFFSET = timedelta(hours=5, minutes=30)


def to_ist(dt):
    """UTC (naive) datetime -> IST datetime. Other values are returned as is."""
    if isinstance(dt, datetime) and dt.tzinfo is None:
        return dt + IST_OFFSET
    return dt


class IstEnvironment(Environment):
    """Jinja environment: any `some_datetime.strftime(...)` in a template
    prints India time, so no template needs to be edited one by one."""

    def getattr(self, obj, attribute):
        if attribute == "strftime" and isinstance(obj, datetime):
            return to_ist(obj).strftime
        return super().getattr(obj, attribute)