"""Test van de logica met nepdata. Draaien: python test_logic.py"""
from datetime import datetime, timedelta

from config import TZ, Settings
import logic


def leg(dep, arr, num, hsl, track="4", dep_actual=None, arr_actual=None, cancelled=False):
    f = lambda d: d.strftime("%Y-%m-%dT%H:%M:%S%z")
    return {
        "cancelled": cancelled,
        "product": {"number": num, "longCategoryName": "Intercity direct" if hsl else "Intercity",
                    "shortCategoryName": "ICD" if hsl else "IC"},
        "origin": {"plannedDateTime": f(dep), "plannedTrack": track,
                   **({"actualDateTime": f(dep_actual)} if dep_actual else {})},
        "destination": {"plannedDateTime": f(arr),
                        **({"actualDateTime": f(arr_actual)} if arr_actual else {})},
    }


def trip(*legs, status="NORMAL"):
    return {"status": status, "legs": list(legs)}


class FakeStore:
    def __init__(self): self.d = {}
    def get(self, k): return self.d.get(k)
    def set(self, k, v): self.d[k] = v
    def delete(self, k): self.d.pop(k, None)


tomorrow = datetime(2026, 11, 10, tzinfo=TZ)
t = lambda h, m: tomorrow.replace(hour=h, minute=m)
S = Settings(from_station="ASD", to_station="RTD")
event = {"subject": "Klantafspraak", "start": t(9, 0)}  # deadline 08:45

HSL = leg(t(7, 12), t(7, 47), "1234", True)
direct_list = [
    trip(leg(t(7, 42), t(8, 17), "9999", True)),      # te laat? nee, arriveert 08:17 -> beter
    trip(leg(t(8, 12), t(8, 47), "5555", True)),      # arriveert na deadline 08:45 -> afvallen
    trip(HSL),
]
alt_list = [
    trip(leg(t(7, 36), t(8, 8), "111", False), leg(t(8, 14), t(8, 40), "222", False)),
    trip(leg(t(6, 54), t(7, 25), "333", False), leg(t(7, 31), t(7, 55), "444", False)),
]


def get_trips(frm, to, when, arrival, via):
    return alt_list if via else direct_list


posts = []
store = FakeStore()
plan = logic.run_evening(S, store, get_trips, lambda d: event, posts.append, datetime(2026, 11, 9, 20, 0, tzinfo=TZ))
assert plan, "plan verwacht"
# Beste HSL = laatste die op tijd is: 07:42 (arr 08:17); alt = laatste niet-HSL op tijd: 07:36
assert plan["primary"]["numbers"] == ["9999"], plan["primary"]
assert plan["alt"]["dep_planned"].startswith("2026-11-10T07:36"), plan["alt"]
assert plan["extra_min"] == 6, plan["extra_min"]
print(posts[0], "\n")

# Ochtend. Bepaal huidige NS-lijst met verschillende situaties.
def morning(now, raw, expect_posts):
    n0 = len(posts)
    res = logic.run_morning(S, store, lambda *a: raw, posts.append, now)
    assert len(posts) - n0 == expect_posts, (res, posts[n0:])
    return res

ok = [trip(leg(t(7, 42), t(8, 17), "9999", True))]
delayed = [trip(leg(t(7, 42), t(8, 17), "9999", True, dep_actual=t(7, 50), arr_actual=t(8, 26)))]
delayed2 = [trip(leg(t(7, 42), t(8, 17), "9999", True, dep_actual=t(7, 58), arr_actual=t(8, 33)))]
cancelled = [trip(leg(t(7, 42), t(8, 17), "9999", True, cancelled=True), status="CANCELLED")]

assert morning(t(5, 0), ok, 0) == "buiten monitorvenster"     # te vroeg (venster start 06:06)
assert morning(t(6, 30), ok, 0) == "ok"                       # geen melding
assert morning(t(7, 0), delayed, 1) == "delay"                # 8 min vertraging -> melding
assert morning(t(7, 2), delayed, 0) == "delay"                # zelfde situatie -> geen spam
assert morning(t(7, 5), delayed2, 1) == "delay"               # vertraging +8 -> nieuwe melding
assert morning(t(7, 8), cancelled, 1) == "cancelled"          # uitval -> melding
assert morning(t(7, 10), ok, 1) == "ok"                       # hersteld -> bericht
assert morning(t(9, 30), ok, 0) == "buiten monitorvenster"    # na vertrek
for p in posts[1:]:
    print(p, "\n")
print("Alle tests geslaagd.")
