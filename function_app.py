"""Azure Functions app (Python v2 model): two timers and a manual HTTP trigger.

Timers run in UTC; the code checks Amsterdam time itself so that daylight
saving time is handled automatically.
"""
import json
import logging
from datetime import datetime

import azure.functions as func

import logic
from clients import make_first_event_getter, ns_get_trips, slack_post
from config import TZ, Settings
from store import OverlayStore, Store

app = func.FunctionApp()


# 18:00 and 19:00 UTC cover 20:00 local time in summer and winter; only run at 20:00 local.
@app.timer_trigger(schedule="0 0 18,19 * * *", arg_name="timer", run_on_startup=False)
def evening_plan(timer: func.TimerRequest) -> None:
    now = datetime.now(TZ)
    if now.hour != 20:
        return
    store = Store()
    plan = logic.run_evening(
        Settings.load(), store, ns_get_trips, make_first_event_getter(store), slack_post, now
    )
    logging.info("Evening plan: %s", plan)


# Every 2 minutes between 03:00 and 08:59 UTC; run_morning ignores anything outside the monitoring window.
@app.timer_trigger(schedule="0 */2 3-8 * * *", arg_name="timer", run_on_startup=False)
def morning_monitor(timer: func.TimerRequest) -> None:
    now = datetime.now(TZ)
    result = logic.run_morning(Settings.load(), Store(), ns_get_trips, slack_post, now)
    logging.info("Morning check: %s", result)


# Manual trigger for testing: GET/POST /api/run/evening or /api/run/morning (requires a function key).
#   ?dry_run=1            do not send Slack messages or change stored state; return the messages instead
#   ?now=2026-11-10T07:00 pretend it is this (Amsterdam) time, e.g. to test the morning check
@app.route(route="run/{job}", methods=["GET", "POST"], auth_level=func.AuthLevel.FUNCTION)
def run_now(req: func.HttpRequest) -> func.HttpResponse:
    def reply(status: int, body: dict) -> func.HttpResponse:
        return func.HttpResponse(json.dumps(body, default=str, indent=2), status_code=status,
                                 mimetype="application/json")

    job = req.route_params.get("job")
    if job not in ("evening", "morning"):
        return reply(400, {"error": "job must be 'evening' or 'morning'"})

    dry_run = req.params.get("dry_run", "").lower() in ("1", "true", "yes")
    try:
        now = datetime.fromisoformat(req.params["now"]) if "now" in req.params else datetime.now(TZ)
        now = now.replace(tzinfo=TZ) if now.tzinfo is None else now.astimezone(TZ)
    except ValueError:
        return reply(400, {"error": "now must be an ISO datetime, e.g. 2026-11-10T07:00"})

    real = Store()
    store = OverlayStore(real) if dry_run else real
    messages = []

    def post(text: str) -> None:
        messages.append(text)
        if not dry_run:
            slack_post(text)

    try:
        settings = Settings.load()
        if job == "evening":
            # The calendar client always uses the real store so a rotated refresh token is kept.
            result = logic.run_evening(settings, store, ns_get_trips,
                                       make_first_event_getter(real), post, now)
        else:
            result = logic.run_morning(settings, store, ns_get_trips, post, now)
    except Exception as exc:  # report the failure to the caller instead of a bare 500
        logging.exception("Manual run of %s failed", job)
        return reply(500, {"job": job, "error": f"{type(exc).__name__}: {exc}"})

    return reply(200, {"job": job, "now": now.isoformat(), "dry_run": dry_run,
                       "result": result, "messages": messages})
