# Trein-assistent (Slack + Outlook + NS)

Elke avond om 20:00 kijkt de app in je Outlook-agenda naar je eerste afspraak van morgen,
kiest de laatste HSL-trein (Intercity direct) die op tijd aankomt en een alternatief via Utrecht,
en stuurt je dat in Slack. Morgenochtend controleert hij elke 2 minuten of die HSL rijdt en meldt
zich bij uitval of vertraging (standaard vanaf 5 minuten, of als je te laat zou aankomen), met
plan B en hoeveel minuten eerder je op het station moet zijn.

## Opzet

1. **NS API-sleutel**: maak een account op https://apiportal.ns.nl, abonneer je op het product met
   de *Reisinformatie API* en kopieer de sleutel (`NS_API_KEY`).
2. **Stationscodes**: zet `FROM_STATION` en `TO_STATION` (bijv. `ASD`, `RTD`, `UT`).
3. **Slack**: maak op https://api.slack.com/apps een app, geef de bot scope `chat:write`, installeer
   hem en kopieer de Bot Token (`SLACK_BOT_TOKEN`). Je eigen member-ID (profiel, drie puntjes,
   *Copy member ID*) is `SLACK_USER_ID`; de bot stuurt je een DM.
4. **Outlook**: registreer in Microsoft Entra een app (*Accounts in any organizational directory*),
   zet *Allow public client flows* aan en voeg de delegated permissions `Calendars.Read` en
   `offline_access` toe. Is een beheerder-goedkeuring nodig in jullie tenant, vraag die dan aan.
   Draai daarna lokaal eenmalig:
   `MS_CLIENT_ID=<app-id> python get_refresh_token.py` en zet de uitkomst in `MS_REFRESH_TOKEN`.
5. **Azure**: maak een Function App (Python 3.11+, Flex Consumption of Consumption, Linux) met een
   opslagaccount. Zet alle waarden uit `local.settings.example.json` als Application settings en
   publiceer met `func azure functionapp publish <naam>`.

## Lokaal testen

`python test_logic.py` draait de logica met nepdata, zonder sleutels of netwerk.

## Instellingen

| Naam | Standaard | Betekenis |
|---|---|---|
| `ARRIVAL_BUFFER_MIN` | 15 | minuten tussen aankomst en afspraakstart |
| `DELAY_THRESHOLD_MIN` | 5 | melden vanaf zoveel minuten vertraging |
| `REALERT_STEP_MIN` | 3 | nieuw bericht als de vertraging zoveel verandert |
| `PREWINDOW_MIN` | 90 | start met monitoren zoveel minuten voor plan B |
| `VIA_STATION` | UT | tussenstation voor het alternatief |

## Let op

- De veldnamen van de NS-API zijn geschreven volgens de documentatie maar nog niet met een echte
  sleutel getest. Controleer bij de eerste run in de logs dat HSL-detectie en trein-matching kloppen
  (`logic.py`: `_is_hsl` en `assess`).
- Als je geen afspraak hebt (of alleen een hele-dag-afspraak) krijg je geen bericht.
- Het gratis tegoed van Azure Functions geldt voor een pay-as-you-go-abonnement.

## Deployen met GitHub Actions

Bij elke push naar `main` draait `.github/workflows/deploy.yml`: eerst `test_logic.py`, daarna
publiceren naar Azure. Inloggen gaat via OIDC (geen wachtwoorden in GitHub), dat werkt ook voor het
Flex Consumption-plan.

1. Maak in Entra een app-registratie (of gebruik `az ad sp create-for-rbac`) en geef die de rol
   *Contributor* op de Function App (of de resourcegroep).
2. Voeg bij die app onder *Certificates & secrets, Federated credentials* een credential toe voor
   je GitHub-repo, met entiteit *Environment* en naam `production`.
3. Zet in GitHub (Settings, Secrets and variables, Actions) de **secrets** `AZURE_CLIENT_ID`,
   `AZURE_TENANT_ID` en `AZURE_SUBSCRIPTION_ID`, en de **variable** `AZURE_FUNCTIONAPP_NAME`.
4. De app-instellingen (NS-sleutel, Slack-token enz.) zet je in Azure bij de Function App, niet
   in GitHub.
