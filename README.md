# Madden CFM Exporter

Self-hosted replacement for the old Heroku listener. Runs as a single Docker
container on a Synology NAS (or anywhere) and gets Madden franchise data into
Firebase two ways:

1. **EA pull (primary)** — connects to EA with your EA account using the
   Companion App's own API (protocol documented by
   [snallabot](https://github.com/snallabot/snallabot-service), MIT) and pulls
   teams, standings, weekly stats, rosters and free agents on demand or on a
   schedule. Outbound HTTPS only: no port forwarding, no public URL, no phone.
2. **Companion App push (fallback)** — the same POST routes as the original
   Heroku app, so the Madden Companion App can still export to this server if
   you expose it (LAN or DDNS).

Supports **multiple leagues**, each writing to its **own Firebase project**
(separate service-account key + database URL per league). Database paths are
identical to the original listener, so existing consumers keep working.

## Setup (Synology)

1. Clone this repo somewhere on the NAS (e.g. `/volume1/docker/cfm-exporter`).
2. `mkdir config data` inside it. Drop each league's Firebase service-account
   key into `config/` as `<something>.json`.
   *Generate fresh keys* (Firebase console → Project settings → Service
   accounts → Generate new private key) — do not reuse a key that was ever
   committed to a repo.
3. `cp .env.example .env` and set at least `ADMIN_PASSWORD`.
4. In Container Manager create the project from `docker-compose.yml` (or:
   `docker compose up -d --build`).
5. Open `http://<nas-ip>:5000/admin`:
   - **Connect EA**: follow the login link, sign in with the EA account that
     owns Madden, then paste the `http://127.0.0.1/success?code=...` URL the
     browser lands on. Pick your console persona.
   - **Add league**: choose the EA league, pick its key file, enter its
     database URL (`https://<project>-default-rtdb.firebaseio.com/`). The
     connection is verified before saving.
   - **Export**: current week or all weeks, optionally rosters + free agents.

Tokens and league config persist in `data/ea_state.json`; the EA refresh token
keeps the connection alive without re-logging in.

## Scheduled exports

Either set `AUTO_EXPORT_MINUTES` in `.env`, or use Synology Task Scheduler:

```sh
curl -u admin:<ADMIN_PASSWORD> -X POST \
  -d weeks=current http://localhost:5000/admin/league/<leagueId>/export
```

## When a new Madden releases

EA rotates API constants each year. Grab the new values from snallabot's
[`ea_constants.ts`](https://github.com/snallabot/snallabot-service/blob/main/src/dashboard/ea_constants.ts)
and set them in `.env` (see `.env.example`) — no code changes needed. For a
league still on Madden 26 set `EA_BLAZE_YEAR=2026` and
`EA_COMPONENT_NAME=careermode`.

## Companion App push (fallback)

Export URL in the app: `http://<host>:5000` (the app appends
`/{platform}/{leagueId}/...`). Only league IDs configured in the admin UI are
accepted; everything else gets a 404. There is no `/delete` route anymore.

## Development

```sh
uv sync
uv run pytest
```

The EA request-signing is verified against test vectors generated from
snallabot's JavaScript implementation (`tests/test_ea_client.py`).
