"""Azure Functions-app (Python v2-model) met twee timers.

Timers draaien in UTC; de code controleert zelf de Amsterdamse tijd, zodat
winter-/zomertijd vanzelf goed gaat.
"""
import logging
from datetime import datetime

import azure.functions as func

import logic
from clients import make_first_event_getter, ns_get_trips, slack_post
from config import TZ, Settings
from store import Store

app = func.FunctionApp()


# 18:00 en 19:00 UTC = 20:00 lokale tijd in zomer resp. winter; we sturen alleen om 20 uur lokaal.
@app.timer_trigger(schedule="0 0 18,19 * * *", arg_name="timer", run_on_startup=False)
def avondplanning(timer: func.TimerRequest) -> None:
    now = datetime.now(TZ)
    if now.hour != 20:
        return
    store = Store()
    plan = logic.run_evening(
        Settings.load(), store, ns_get_trips, make_first_event_getter(store), slack_post, now
    )
    logging.info("Avondplan: %s", plan)


# Elke 2 minuten tussen 03:00 en 08:59 UTC; run_morning negeert alles buiten het monitorvenster.
@app.timer_trigger(schedule="0 */2 3-8 * * *", arg_name="timer", run_on_startup=False)
def ochtendmonitor(timer: func.TimerRequest) -> None:
    now = datetime.now(TZ)
    result = logic.run_morning(Settings.load(), Store(), ns_get_trips, slack_post, now)
    logging.info("Ochtendcheck: %s", result)
