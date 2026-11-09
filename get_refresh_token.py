"""Eenmalig lokaal draaien om een Microsoft refresh token voor je agenda te krijgen.

    MS_CLIENT_ID=<app-id> python get_refresh_token.py

Je opent de getoonde URL, voert de code in en logt in met je Outlook-account.
"""
import os
import sys
import time

import requests

tenant = os.environ.get("MS_TENANT", "organizations")
client_id = os.environ["MS_CLIENT_ID"]
base = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"

dc = requests.post(
    f"{base}/devicecode",
    data={"client_id": client_id, "scope": "Calendars.Read offline_access"},
    timeout=15,
).json()
print(dc["message"])

deadline = time.time() + dc["expires_in"]
while time.time() < deadline:
    time.sleep(dc.get("interval", 5))
    r = requests.post(
        f"{base}/token",
        data={
            "client_id": client_id,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": dc["device_code"],
        },
        timeout=15,
    ).json()
    if "refresh_token" in r:
        print("\nMS_REFRESH_TOKEN =", r["refresh_token"])
        sys.exit(0)
    if r.get("error") not in ("authorization_pending", "slow_down"):
        sys.exit(f"Mislukt: {r}")
sys.exit("Code verlopen, probeer opnieuw.")
