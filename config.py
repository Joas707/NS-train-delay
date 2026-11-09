"""Settings, read from environment variables (Azure: Application settings)."""
import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Amsterdam")


@dataclass
class Settings:
    from_station: str             # NS station code of your departure station, e.g. "ASD"
    to_station: str               # NS station code of your destination, e.g. "RTD"
    via_station: str = "UT"       # via station for the fallback route (Utrecht Centraal)
    arrival_buffer_min: int = 15  # minutes between arriving at the station and the event start
    delay_threshold_min: int = 5  # alert once the delay reaches this many minutes
    realert_step_min: int = 3     # send a new alert when the delay changes by this many minutes
    prewindow_min: int = 90       # start monitoring this many minutes before the fallback train

    @staticmethod
    def load() -> "Settings":
        def need(name):
            v = os.environ.get(name)
            if not v:
                raise RuntimeError(f"Environment variable {name} is missing")
            return v

        return Settings(
            from_station=need("FROM_STATION"),
            to_station=need("TO_STATION"),
            via_station=os.environ.get("VIA_STATION", "UT"),
            arrival_buffer_min=int(os.environ.get("ARRIVAL_BUFFER_MIN", 15)),
            delay_threshold_min=int(os.environ.get("DELAY_THRESHOLD_MIN", 5)),
            realert_step_min=int(os.environ.get("REALERT_STEP_MIN", 3)),
            prewindow_min=int(os.environ.get("PREWINDOW_MIN", 90)),
        )
