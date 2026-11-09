"""Run once locally to obtain a Microsoft refresh token for your calendar.

    MS_CLIENT_ID=<app-id> python get_refresh_token.py

Open the URL it prints, enter the code and sign in with your Outlook account.
"""
import os
import sys
import time

import requests

tenant = os.environ.get("MS_TENANT", "organizations")
client_id = os.environ["MS_CLIENT_ID"]
base = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"

# Device code flow: the user signs in in a browser while this script polls for the token.
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
        sys.exit(f"Failed: {r}")
sys.exit("Code expired, please try again.")
