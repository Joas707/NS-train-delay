"""Instellingen, gelezen uit omgevingsvariabelen (Azure: Application settings)."""
import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Amsterdam")


@dataclass
class Settings:
    from_station: str            # NS-stationscode van je vertrekstation, bijv. "ASD"
    to_station: str              # NS-stationscode van je bestemming, bijv. "RTD"
    via_station: str = "UT"      # route voor het alternatief (Utrecht Centraal)
    arrival_buffer_min: int = 15 # minuten tussen aankomst op station en start afspraak
    delay_threshold_min: int = 5 # vanaf hoeveel minuten vertraging je een bericht krijgt
    realert_step_min: int = 3    # nieuw bericht als de vertraging met zoveel minuten verandert
    prewindow_min: int = 90      # begin met monitoren zoveel minuten voor het alternatief

    @staticmethod
    def load() -> "Settings":
        def need(name):
            v = os.environ.get(name)
            if not v:
                raise RuntimeError(f"Omgevingsvariabele {name} ontbreekt")
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
