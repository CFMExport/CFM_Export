"""Pulls league data from EA and writes it to that league's Firebase project.

Produces the same database layout as a full Madden Companion App export, plus
free agents (which the companion app never sends).
"""
import threading
import traceback
from datetime import datetime, timezone

from . import constants as C
from . import store as fb
from .ea_client import EAClient
from .tokens import store as token_store

# league_id (str) -> progress dict; in-memory, shown on the admin page
JOBS: dict = {}
_running: set = set()
_lock = threading.Lock()


def job_status(league_id: str) -> dict | None:
    return JOBS.get(str(league_id))


def _set(league_id: str, **fields):
    JOBS.setdefault(str(league_id), {}).update(fields)


def stage_to_path(stage: int) -> str:
    return "pre" if stage == C.STAGE_PRESEASON else "reg"


def select_weeks(league_info: dict, which: str) -> list[tuple[int, int]]:
    """Return (stageIndex, weekIndex) pairs to export."""
    season = league_info["careerHubInfo"]["seasonInfo"]
    if which == "current":
        return [(season["seasonWeekType"], season["seasonWeek"])]
    available = league_info.get("availableWeekInfoList", [])
    played = [
        (w["stageIndex"], w["weekIndex"])
        for w in available
        if w.get("gameTotalCount", 0) > 0
    ]
    if which == "all":
        return played
    raise ValueError(f"Unknown week selection: {which}")


def run_export(league_cfg: dict, weeks: str = "current",
               rosters: bool = False, league_info_data: bool = True) -> bool:
    """Start an export in a background thread. Returns False if one is already
    running for this league."""
    league_id = str(league_cfg["leagueId"])
    with _lock:
        if league_id in _running:
            return False
        _running.add(league_id)
    JOBS[league_id] = {
        "status": "running",
        "detail": "starting",
        "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "finished": None,
        "error": None,
    }
    threading.Thread(
        target=_export_worker,
        args=(league_cfg, weeks, rosters, league_info_data),
        daemon=True,
    ).start()
    return True


def _export_worker(league_cfg: dict, weeks: str, rosters: bool, league_info_data: bool):
    league_id = str(league_cfg["leagueId"])
    try:
        client = EAClient(token_store)
        system = client.console
        lid = int(league_id)

        _set(league_id, detail="fetching league info")
        info = client.get_league_info(lid)

        if league_info_data:
            _set(league_id, detail="teams + standings")
            fb.store_league_teams(league_cfg, system, league_id, client.get_teams(lid))
            fb.store_standings(league_cfg, system, league_id, client.get_standings(lid))

        for stage, week_index in select_weeks(info, weeks):
            week_path = stage_to_path(stage)
            week_number = week_index + 1
            for data_type in C.WEEKLY_EXPORTS:
                _set(league_id, detail=f"{week_path} week {week_number}: {data_type}")
                payload = client.get_weekly(data_type, lid, stage, week_index)
                try:
                    fb.store_weekly(
                        league_cfg, system, league_id, week_path, week_number,
                        data_type, payload,
                    )
                except StopIteration:
                    # no '...List' key — EA had no data for this week/type
                    continue

        if rosters:
            teams = info.get("teamIdInfoList", [])
            for i, team in enumerate(teams, 1):
                _set(league_id, detail=f"roster {i}/{len(teams)}: {team.get('displayName', team['teamId'])}")
                payload = client.get_team_roster(lid, team["teamId"], team["teamIndex"])
                fb.store_team_roster(league_cfg, system, league_id, str(team["teamId"]), payload)
            _set(league_id, detail="free agents")
            fb.store_free_agents(league_cfg, system, league_id, client.get_free_agents(lid))

        _set(league_id, status="done", detail="complete",
             finished=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    except Exception as e:
        traceback.print_exc()
        _set(league_id, status="error", error=str(e),
             finished=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    finally:
        with _lock:
            _running.discard(league_id)
