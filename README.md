# Train assistant (Slack + Outlook + NS)

Every evening at 20:00 the app looks at your Outlook calendar for tomorrow's first event, picks the
latest high-speed train (Intercity direct) that gets you there in time plus a fallback via Utrecht,
and sends you that in Slack. The next morning it checks every 2 minutes whether that HSL is running
and alerts you on cancellation or delay (by default from 5 minutes, or if you would arrive late),
including plan B and how many minutes earlier you need to be at the station.

Note: the Slack messages are in Dutch.

## Setup

1. **NS API key**: create an account at https://apiportal.ns.nl, subscribe to the product that
   includes the *Reisinformatie API* and copy the key (`NS_API_KEY`).
2. **Station codes**: set `FROM_STATION` and `TO_STATION` (e.g. `ASD`, `RTD`, `UT`).
3. **Slack**: create an app at https://api.slack.com/apps, give the bot the `chat:write` scope,
   install it and copy the Bot Token (`SLACK_BOT_TOKEN`). Your own member ID (profile, three dots,
   *Copy member ID*) is `SLACK_USER_ID`; the bot sends you a DM.
4. **Outlook**: register an app in Microsoft Entra (*Accounts in any organizational directory*),
   enable *Allow public client flows* and add the delegated permissions `Calendars.Read` and
   `offline_access`. If your tenant requires admin consent, request it.
   Then run once locally:
   `MS_CLIENT_ID=<app-id> python get_refresh_token.py` and put the result in `MS_REFRESH_TOKEN`.
5. **Azure**: create a Function App (Python 3.11+, Flex Consumption or Consumption, Linux) with a
   storage account. Set all values from `local.settings.example.json` as Application settings
   (see also the GitHub Actions section below for deploying). Also add `STATE_STORAGE_CONNECTION`
   with the connection string of the storage account (Storage account, Security + networking,
   Access keys): Flex Consumption has no `AzureWebJobsStorage` connection string, and the app needs
   one to keep its state between the evening and morning runs.

## Testing locally

`python test_logic.py` runs the logic against fake data, with no keys or network needed.

## Settings

| Name | Default | Meaning |
|---|---|---|
| `ARRIVAL_BUFFER_MIN` | 15 | minutes between arrival and event start |
| `DELAY_THRESHOLD_MIN` | 5 | alert from this many minutes of delay |
| `REALERT_STEP_MIN` | 3 | send a new alert when the delay changes by this much |
| `PREWINDOW_MIN` | 90 | start monitoring this many minutes before plan B |
| `VIA_STATION` | UT | via station for the fallback route |

## Notes

- The NS API field names are written from the documentation but have not been tested with a real
  key. On the first run, check in the logs that HSL detection and train matching work
  (`logic.py`: `_is_hsl` and `assess`).
- If you have no event (or only an all-day event) you get no message.
- The Azure Functions free grant applies to a pay-as-you-go subscription.

## Deploying with GitHub Actions

On every push to `main`, `.github/workflows/deploy.yml` runs: first `test_logic.py`, then it
publishes to Azure. Sign-in uses OIDC (no passwords stored in GitHub), which also works for the
Flex Consumption plan.

1. In Entra, create an app registration (or use `az ad sp create-for-rbac`) and give it the
   *Contributor* role on the Function App (or its resource group).
2. On that app, under *Certificates & secrets, Federated credentials*, add a credential for your
   GitHub repo with entity type *Environment* and name `production`.
3. In GitHub (Settings, Secrets and variables, Actions) set the **secrets** `AZURE_CLIENT_ID`,
   `AZURE_TENANT_ID` and `AZURE_SUBSCRIPTION_ID`, and the **variable** `AZURE_FUNCTIONAPP_NAME`.
4. Set the app settings (NS key, Slack token, etc.) in Azure on the Function App, not in GitHub.
