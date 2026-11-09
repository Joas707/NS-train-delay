"""Core logic: evening planning and morning monitoring.

Everything here is pure (no network): NS, the calendar, Slack and storage are
passed in as functions, which keeps it easy to test.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from config import TZ, Settings


def _dt(s: str) -> datetime:
    # NS returns e.g. "2026-11-10T07:12:00+0100"; Python >= 3.11 parses that.
    return datetime.fromisoformat(s).astimezone(TZ)


def _is_hsl(leg: dict) -> bool:
    """True if the leg is a high-speed train (Intercity direct)."""
    p = leg.get("product") or {}
    name = (p.get("longCategoryName") or "").lower()
    return "direct" in name or p.get("shortCategoryName") == "ICD" or p.get("categoryCode") == "ICD"


@dataclass
class Trip:
    dep_planned: datetime
    dep_actual: datetime
    arr_planned: datetime
    arr_actual: datetime
    cancelled: bool
    hsl: bool
    numbers: tuple
    track: str

    @property
    def delay_min(self) -> int:
        d = max(self.dep_actual - self.dep_planned, self.arr_actual - self.arr_planned)
        return max(0, int(d.total_seconds() // 60))


def parse_trip(raw: dict) -> Trip:
    legs = raw["legs"]
    o, d = legs[0]["origin"], legs[-1]["destination"]
    return Trip(
        dep_planned=_dt(o["plannedDateTime"]),
        dep_actual=_dt(o.get("actualDateTime") or o["plannedDateTime"]),
        arr_planned=_dt(d["plannedDateTime"]),
        arr_actual=_dt(d.get("actualDateTime") or d["plannedDateTime"]),
        cancelled=raw.get("status") == "CANCELLED" or any(l.get("cancelled") for l in legs),
        hsl=any(_is_hsl(l) for l in legs),
        numbers=tuple(str((l.get("product") or {}).get("number", "")) for l in legs),
        track=str(o.get("plannedTrack") or "?"),
    )


def _trip_dict(t: Trip) -> dict:
    return {
        "dep_planned": t.dep_planned.isoformat(),
        "arr_planned": t.arr_planned.isoformat(),
        "numbers": list(t.numbers),
        "track": t.track,
        "hsl": t.hsl,
    }


def _hhmm(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(TZ).strftime("%H:%M")


# --------------------------------------------------------------- evening

def plan_evening(s: Settings, get_trips, event: dict) -> dict | None:
    """Pick the HSL train and a fallback via Utrecht for tomorrow's first event.

    get_trips(from, to, when, arrival, via) -> list of raw NS trips.
    event = {"subject": str, "start": datetime}
    """
    deadline = event["start"] - timedelta(minutes=s.arrival_buffer_min)

    def usable(raw_list, want_hsl):
        trips = [parse_trip(r) for r in raw_list]
        trips = [t for t in trips if not t.cancelled and t.arr_planned <= deadline]
        if want_hsl is not None:
            trips = [t for t in trips if t.hsl == want_hsl]
        return max(trips, key=lambda t: t.dep_planned, default=None)

    direct_raw = get_trips(s.from_station, s.to_station, deadline, True, None)
    alt_raw = get_trips(s.from_station, s.to_station, deadline, True, s.via_station)

    # Prefer the HSL; if none arrives in time, fall back to any train.
    primary = usable(direct_raw, True) or usable(direct_raw, None)
    if primary is None:
        return None
    alt = usable(alt_raw, False)
    extra = 0
    if alt is not None:
        extra = max(0, int((primary.dep_planned - alt.dep_planned).total_seconds() // 60))

    return {
        "date": primary.dep_planned.date().isoformat(),
        "event_subject": event["subject"],
        "event_start": event["start"].isoformat(),
        "deadline": deadline.isoformat(),
        "primary": _trip_dict(primary),
        "alt": _trip_dict(alt) if alt else None,
        "extra_min": extra,
    }


def evening_message(plan: dict) -> str:
    # Slack messages are intentionally in Dutch (the user reads them).
    p, a = plan["primary"], plan["alt"]
    kind = "HSL (Intercity direct)" if p["hsl"] else "trein"
    lines = [
        f":bullettrain_front: *Morgen: {plan['event_subject']}* om {_hhmm(plan['event_start'])}",
        f"Je {kind}: vertrek *{_hhmm(p['dep_planned'])}* spoor {p['track']}, aankomst {_hhmm(p['arr_planned'])}.",
    ]
    if a:
        lines.append(
            f"Plan B via Utrecht: vertrek {_hhmm(a['dep_planned'])} spoor {a['track']} "
            f"({plan['extra_min']} min eerder op het station dan de HSL)."
        )
    else:
        lines.append("Er is geen geschikt alternatief via Utrecht gevonden.")
    lines.append("Ik houd morgenochtend de HSL in de gaten en meld me bij vertraging of uitval.")
    return "\n".join(lines)


def run_evening(s, store, get_trips, get_first_event, post, now):
    event = get_first_event(now.date() + timedelta(days=1))
    if event is None:
        return None
    plan = plan_evening(s, get_trips, event)
    if plan is None:
        post(f":warning: Morgen {event['subject']} om {event['start'].astimezone(TZ):%H:%M}, "
             "maar ik vond geen trein die op tijd aankomt. Kijk zelf even in de NS-app.")
        return None
    store.set("plan", plan)
    store.delete("alert")  # reset the alert state for the new day
    post(evening_message(plan))
    return plan


# --------------------------------------------------------------- morning

def assess(s: Settings, plan: dict, raw_trips: list) -> dict | None:
    """Find the planned train in the live travel info and judge its status."""
    want_dep = datetime.fromisoformat(plan["primary"]["dep_planned"])
    want_nums = tuple(plan["primary"]["numbers"])
    deadline = datetime.fromisoformat(plan["deadline"])
    for raw in raw_trips:
        t = parse_trip(raw)
        if t.dep_planned == want_dep and t.numbers == want_nums:
            if t.cancelled:
                return {"level": "cancelled", "delay": 0, "arr": t.arr_actual}
            late = t.arr_actual > deadline
            if t.delay_min >= s.delay_threshold_min or late:
                return {"level": "delay", "delay": t.delay_min, "arr": t.arr_actual}
            return {"level": "ok", "delay": t.delay_min, "arr": t.arr_actual}
    return None  # not found: no alarm


def alert_message(plan: dict, st: dict, now: datetime) -> str:
    p, a = plan["primary"], plan["alt"]
    dep = _hhmm(p["dep_planned"])
    if st["level"] == "cancelled":
        head = f":rotating_light: *De trein van {dep} rijdt niet.*"
    else:
        head = (f":warning: *De trein van {dep} heeft {st['delay']} min vertraging* "
                f"(aankomst {st['arr']:%H:%M}, afspraak {_hhmm(plan['event_start'])}).")
    if not a:
        return head + "\nGeen alternatief via Utrecht gevonden, kijk in de NS-app."
    left = int((datetime.fromisoformat(a["dep_planned"]) - now).total_seconds() // 60)
    when = (f"over {left} min" if left > 0 else "die is al vertrokken, kijk in de NS-app")
    return (f"{head}\nNeem plan B via Utrecht: vertrek *{_hhmm(a['dep_planned'])}* spoor {a['track']} "
            f"({plan['extra_min']} min eerder dan de HSL), {when}.")


def run_morning(s, store, get_trips, post, now):
    plan = store.get("plan")
    if not plan or plan["date"] != now.date().isoformat():
        return "no plan for today"

    dep = datetime.fromisoformat(plan["primary"]["dep_planned"])
    first = datetime.fromisoformat(plan["alt"]["dep_planned"]) if plan["alt"] else dep
    first = min(first, dep)
    if not (first - timedelta(minutes=s.prewindow_min) <= now <= dep + timedelta(minutes=3)):
        return "outside monitoring window"

    raw = get_trips(s.from_station, s.to_station, dep - timedelta(minutes=10), False, None)
    st = assess(s, plan, raw)
    if st is None:
        return "train not found in travel info"

    prev = store.get("alert")
    prev = prev if prev and prev.get("date") == plan["date"] else None

    if st["level"] == "ok":
        if prev and prev["level"] != "ok":
            post(f":white_check_mark: De trein van {_hhmm(plan['primary']['dep_planned'])} "
                 f"rijdt weer op schema ({st['delay']} min vertraging).")
            store.set("alert", {"date": plan["date"], "level": "ok", "delay": st["delay"]})
        return "ok"

    # Only alert on a change, to avoid spamming every 2 minutes.
    changed = (prev is None or prev["level"] != st["level"]
               or abs(prev["delay"] - st["delay"]) >= s.realert_step_min)
    if changed:
        post(alert_message(plan, st, now))
        store.set("alert", {"date": plan["date"], "level": st["level"], "delay": st["delay"]})
    return st["level"]
