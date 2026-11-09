"""Thin wrappers around the NS API, Microsoft Graph (Outlook) and Slack."""
import os
from datetime import datetime, timedelta

import requests

from config import TZ

NS_URL = "https://gateway.apiportal.ns.nl/reisinformatie-api/api/v3/trips"


def ns_get_trips(from_st, to_st, when: datetime, arrival: bool, via: str | None) -> list:
    params = {
        "fromStation": from_st,
        "toStation": to_st,
        "dateTime": when.astimezone(TZ).strftime("%Y-%m-%dT%H:%M:%S%z"),
        "searchForArrival": str(arrival).lower(),
    }
    if via:
        params["viaStation"] = via
    r = requests.get(
        NS_URL,
        params=params,
        headers={"Ocp-Apim-Subscription-Key": os.environ["NS_API_KEY"]},
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get("trips", [])


# ---------------------------------------------------------------- Graph

def _graph_token(store) -> str:
    tenant = os.environ.get("MS_TENANT", "organizations")
    refresh = store.get("graph_refresh_token") or os.environ["MS_REFRESH_TOKEN"]
    data = {
        "client_id": os.environ["MS_CLIENT_ID"],
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "scope": "Calendars.Read offline_access",
    }
    if os.environ.get("MS_CLIENT_SECRET"):
        data["client_secret"] = os.environ["MS_CLIENT_SECRET"]
    r = requests.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token", data=data, timeout=15
    )
    r.raise_for_status()
    tok = r.json()
    if tok.get("refresh_token"):  # Microsoft rotates refresh tokens
        store.set("graph_refresh_token", tok["refresh_token"])
    return tok["access_token"]


def _parse_graph_dt(s: str) -> datetime:
    # Graph returns naive local times like "2026-11-10T09:00:00.0000000".
    return datetime.fromisoformat(s.split(".")[0]).replace(tzinfo=TZ)


def make_first_event_getter(store):
    def get_first_event(day):
        start = datetime(day.year, day.month, day.day, tzinfo=TZ)
        end = start + timedelta(days=1)
        r = requests.get(
            "https://graph.microsoft.com/v1.0/me/calendarView",
            params={
                "startDateTime": start.isoformat(),
                "endDateTime": end.isoformat(),
                "$orderby": "start/dateTime",
                "$select": "subject,start,isAllDay,isCancelled,responseStatus,showAs",
                "$top": "25",
            },
            headers={
                "Authorization": f"Bearer {_graph_token(store)}",
                "Prefer": 'outlook.timezone="W. Europe Standard Time"',
            },
            timeout=15,
        )
        r.raise_for_status()
        # First event that is a real commitment: skip all-day, cancelled, declined and "free" events.
        for ev in r.json().get("value", []):
            if ev.get("isAllDay") or ev.get("isCancelled"):
                continue
            if (ev.get("responseStatus") or {}).get("response") == "declined":
                continue
            if ev.get("showAs") == "free":
                continue
            return {"subject": ev.get("subject") or "(zonder titel)",
                    "start": _parse_graph_dt(ev["start"]["dateTime"])}
        return None

    return get_first_event


# ---------------------------------------------------------------- Slack

def slack_post(text: str) -> None:
    r = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {os.environ['SLACK_BOT_TOKEN']}"},
        json={"channel": os.environ["SLACK_USER_ID"], "text": text},  # posting to a user ID sends a DM
        timeout=15,
    )
    r.raise_for_status()
    if not r.json().get("ok"):
        raise RuntimeError(f"Slack error: {r.json().get('error')}")
