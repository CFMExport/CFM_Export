import os
import threading
import time

from flask import Flask, request, abort

from cfm import store as fb
from cfm.tokens import store as token_store
from cfm import exporter
from cfm.admin import admin

app = Flask(__name__)
app.register_blueprint(admin, url_prefix="/admin")


def league_for(league_id) -> dict | None:
    state = token_store.load() or {}
    return state.get("leagues", {}).get(str(league_id))


def _require_league(league_id) -> dict:
    league = league_for(league_id)
    if not league:
        abort(404, description=f"League {league_id} is not configured on this server")
    return league


@app.route("/")
def index():
    return "Madden CFM Exporter V2.0"


# ---------------------------------------------------------------------------
# Madden Companion App push routes — identical URLs to the original listener,
# still fully supported as a fallback alongside the EA pull exporter.
# ---------------------------------------------------------------------------

@app.route("/<system>/<leagueId>/leagueteams", methods=["POST"])
def teams(system, leagueId):
    fb.store_league_teams(_require_league(leagueId), system, leagueId, request.json)
    return "OK", 200


@app.route("/<system>/<leagueId>/standings", methods=["POST"])
def standings(system, leagueId):
    fb.store_standings(_require_league(leagueId), system, leagueId, request.json)
    return "OK", 200


@app.route("/<system>/<leagueId>/freeagents/roster", methods=["POST"])
def freeagents(system, leagueId):
    fb.store_free_agents(_require_league(leagueId), system, leagueId, request.json)
    return "OK", 200


@app.route("/<system>/<leagueId>/team/<teamId>/roster", methods=["POST"])
def roster(system, leagueId, teamId):
    fb.store_team_roster(_require_league(leagueId), system, leagueId, teamId, request.json)
    return "OK", 200


@app.route("/<system>/<leagueId>/week/<weekType>/<weekNumber>/<dataType>", methods=["POST"])
def stats(system, leagueId, weekType, weekNumber, dataType):
    fb.store_weekly(
        _require_league(leagueId), system, leagueId, weekType, weekNumber,
        dataType, request.json,
    )
    return "OK", 200


# ---------------------------------------------------------------------------
# Optional scheduled auto-export (set AUTO_EXPORT_MINUTES to enable).
# Alternatively leave it unset and trigger exports from Synology Task Scheduler:
#   curl -X POST http://localhost:5000/admin/league/<leagueId>/export -d weeks=current
# ---------------------------------------------------------------------------

def _auto_export_loop(interval_minutes: int):
    while True:
        time.sleep(interval_minutes * 60)
        state = token_store.load() or {}
        if "token" not in state:
            continue
        for league in state.get("leagues", {}).values():
            exporter.run_export(
                league,
                weeks="current",
                rosters=os.environ.get("AUTO_EXPORT_ROSTERS") == "true",
            )


_interval = os.environ.get("AUTO_EXPORT_MINUTES")
if _interval and not os.environ.get("CFM_DISABLE_SCHEDULER"):
    threading.Thread(
        target=_auto_export_loop, args=(int(_interval),), daemon=True
    ).start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
