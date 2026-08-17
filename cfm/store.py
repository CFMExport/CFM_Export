"""Firebase Realtime Database writers — one Firebase project per league.

Database paths are byte-for-byte the same as the original Heroku listener, so
existing consumers of each league's database keep working unchanged:

    data/{system}/{leagueId}/leagueteams
    data/{system}/{leagueId}/standings
    data/{system}/{leagueId}/freeagents
    data/{system}/{leagueId}/team/{teamId}
    data/{system}/{leagueId}/week/{weekType}/{weekNumber}/{dataType}/{statName}
"""
import json
import threading

import firebase_admin
from firebase_admin import credentials, db

_lock = threading.Lock()


def _app_for(league: dict) -> firebase_admin.App:
    """Get or lazily create the firebase app for one league's project."""
    name = f"league-{league['leagueId']}"
    with _lock:
        try:
            return firebase_admin.get_app(name)
        except ValueError:
            with open(league["keyFile"]) as f:
                cred = credentials.Certificate(json.load(f))
            return firebase_admin.initialize_app(
                cred, {"databaseURL": league["databaseURL"]}, name=name
            )


def drop_app(league_id) -> None:
    """Forget a league's firebase app (after config changes)."""
    with _lock:
        try:
            firebase_admin.delete_app(firebase_admin.get_app(f"league-{league_id}"))
        except ValueError:
            pass


def write(league: dict, path: str, data) -> None:
    db.reference(path, app=_app_for(league)).set(data)


def check_connection(league: dict) -> None:
    """Cheap read to verify the key/URL pair actually works."""
    db.reference("data", app=_app_for(league)).get(shallow=True)


def extract_stat_list(payload: dict) -> tuple[str, list]:
    """Weekly exports wrap the stats in a single '...List' key; store just that
    list under its key name, exactly as the original listener did."""
    stat_name = next(k for k in payload if "List" in k)
    return stat_name, payload[stat_name]


def store_league_teams(league: dict, system: str, league_id: str, payload: dict):
    write(league, f"data/{system}/{league_id}/leagueteams", payload)


def store_standings(league: dict, system: str, league_id: str, payload: dict):
    write(league, f"data/{system}/{league_id}/standings", payload)


def store_free_agents(league: dict, system: str, league_id: str, payload: dict):
    write(league, f"data/{system}/{league_id}/freeagents", payload)


def store_team_roster(league: dict, system: str, league_id: str, team_id: str, payload: dict):
    write(league, f"data/{system}/{league_id}/team/{team_id}", payload)


def store_weekly(league: dict, system: str, league_id: str, week_type: str,
                 week_number, data_type: str, payload: dict):
    stat_name, stats = extract_stat_list(payload)
    write(
        league,
        f"data/{system}/{league_id}/week/{week_type}/{week_number}/{data_type}/{stat_name}",
        stats,
    )
