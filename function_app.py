"""Azure Functions app (Python v2 model) with two timers.

Timers run in UTC; the code checks Amsterdam time itself so that daylight
saving time is handled automatically.
"""
import logging
from datetime import datetime

import azure.functions as func

import logic
from clients import make_first_event_getter, ns_get_trips, slack_post
from config import TZ, Settings
from store import Store

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
