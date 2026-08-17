"""Listener route tests: same URL shapes and database paths as the original
Heroku app, with firebase and the token store faked out."""
import json
import importlib

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CFM_DISABLE_SCHEDULER", "1")

    import cfm.tokens
    importlib.reload(cfm.tokens)
    cfm.tokens.store.save({
        "leagues": {
            "111": {
                "leagueId": 111,
                "label": "test",
                "keyFile": "/nonexistent.json",
                "databaseURL": "https://example.firebaseio.com/",
            }
        }
    })

    writes = []
    import cfm.store
    monkeypatch.setattr(cfm.store, "write", lambda league, path, data: writes.append((league["leagueId"], path, data)))

    import app as app_module
    importlib.reload(app_module)
    app_module.token_store = cfm.tokens.store
    app_module.app.config["TESTING"] = True
    test_client = app_module.app.test_client()
    test_client.writes = writes
    return test_client


def _post(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


def test_leagueteams(client):
    res = _post(client, "/ps5/111/leagueteams", {"leagueTeamInfoList": [{"teamId": 1}]})
    assert res.status_code == 200
    assert client.writes == [
        (111, "data/ps5/111/leagueteams", {"leagueTeamInfoList": [{"teamId": 1}]})
    ]


def test_standings(client):
    _post(client, "/xone/111/standings", {"teamStandingInfoList": []})
    assert client.writes[0][1] == "data/xone/111/standings"


def test_team_roster(client):
    _post(client, "/ps5/111/team/55/roster", {"rosterInfoList": []})
    assert client.writes[0][1] == "data/ps5/111/team/55"


def test_freeagents(client):
    _post(client, "/ps5/111/freeagents/roster", {"rosterInfoList": []})
    assert client.writes[0][1] == "data/ps5/111/freeagents"


def test_weekly_stats_extracts_list(client):
    payload = {"playerPassingStatInfoList": [{"statId": 9}], "other": 1}
    _post(client, "/ps5/111/week/reg/5/passing", payload)
    assert client.writes == [
        (111, "data/ps5/111/week/reg/5/passing/playerPassingStatInfoList", [{"statId": 9}])
    ]


def test_unconfigured_league_rejected(client):
    res = _post(client, "/ps5/999/standings", {"teamStandingInfoList": []})
    assert res.status_code == 404
    assert client.writes == []


def test_no_delete_route(client):
    assert client.get("/delete").status_code == 404
