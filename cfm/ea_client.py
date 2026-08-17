"""Client for EA's Madden Companion App API.

Protocol reverse-engineered by the snallabot project (MIT):
https://github.com/snallabot/snallabot-service/blob/main/docs/madden/ea_api.md
"""
import base64
import hashlib
import json
import os
import ssl
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, parse_qs

import httpx

from . import constants as C


class EAError(Exception):
    """Any failure talking to EA."""


class BlazeError(EAError):
    """Blaze returned a structured error (usually an expired session)."""

    def __init__(self, error):
        super().__init__(json.dumps(error))
        self.error = error


def _compact(obj) -> str:
    # match JavaScript's JSON.stringify (no whitespace)
    return json.dumps(obj, separators=(",", ":"))


ACCOUNT_HEADERS = {
    "Accept-Charset": "UTF-8",
    "User-Agent": C.USER_AGENT,
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Accept-Encoding": "gzip",
}


def _blaze_headers(console: str) -> dict:
    return {
        "Accept-Charset": "UTF-8",
        "Accept": "application/json",
        "X-BLAZE-ID": C.BLAZE_SERVICE[console],
        "X-BLAZE-VOID-RESP": "XML",
        "X-Application-Key": "MADDEN-MCA",
        "Content-Type": "application/json",
        "User-Agent": C.USER_AGENT,
    }


# EA's Blaze host negotiates legacy SSL renegotiation and an invalid cert chain.
_legacy_ctx = ssl.create_default_context()
_legacy_ctx.check_hostname = False
_legacy_ctx.verify_mode = ssl.CERT_NONE
_legacy_ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)

_blaze_http = httpx.Client(verify=_legacy_ctx, timeout=60.0)
_account_http = httpx.Client(timeout=30.0, follow_redirects=False)


# ---------------------------------------------------------------------------
# Account auth (steps 1-7 of the flow)
# ---------------------------------------------------------------------------

def parse_login_redirect(pasted: str) -> str:
    """Extract ?code= from the 127.0.0.1/success URL the user pastes."""
    pasted = pasted.strip()
    if "code=" not in pasted:
        raise EAError("That doesn't look like the redirect URL — it should contain 'code='")
    qs = parse_qs(urlparse(pasted).query)
    code = qs.get("code", [None])[0]
    if not code:
        raise EAError("Could not find a code= parameter in that URL")
    return code


def exchange_code(code: str) -> dict:
    res = _account_http.post(
        "https://accounts.ea.com/connect/token",
        headers=ACCOUNT_HEADERS,
        content=(
            f"authentication_source={C.AUTH_SOURCE}&client_secret={C.CLIENT_SECRET}"
            f"&grant_type=authorization_code&code={code}&redirect_uri={C.REDIRECT_URL}"
            f"&release_type=prod&client_id={C.CLIENT_ID}"
        ),
    )
    data = res.json()
    if res.status_code != 200 or "access_token" not in data:
        raise EAError(f"EA rejected the login code: {data}")
    return data


def get_pid(access_token: str) -> str:
    res = _account_http.get(
        f"https://accounts.ea.com/connect/tokeninfo?access_token={access_token}",
        headers={
            "Accept-Charset": "UTF-8",
            "X-Include-Deviceid": "true",
            "User-Agent": C.USER_AGENT,
            "Accept-Encoding": "gzip",
        },
    )
    data = res.json()
    if "pid_id" not in data:
        raise EAError(f"Could not retrieve EA account id: {data}")
    return data["pid_id"]


def get_madden_entitlements(access_token: str, pid: str) -> list:
    res = _account_http.get(
        f"https://gateway.ea.com/proxy/identity/pids/{pid}/entitlements/?status=ACTIVE",
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": C.USER_AGENT,
            "Accept-Charset": "UTF-8",
            "X-Expand-Results": "true",
            "Accept-Encoding": "gzip",
        },
    )
    if res.status_code != 200:
        raise EAError(f"Could not retrieve entitlements: {res.text}")
    entitlements = res.json().get("entitlements", {}).get("entitlement", [])
    valid = [
        e for e in entitlements
        if e.get("entitlementTag") == "ONLINE_ACCESS"
        and e.get("groupName") in C.ENTITLEMENT_TO_SYSTEM
    ]
    if not valid:
        raise EAError(
            "No Madden entitlements on this EA account. Make sure you logged in "
            "with the account that owns Madden (check linked accounts at "
            "https://myaccount.ea.com/cp-ui/connectaccounts/index)."
        )
    return valid


def get_personas(access_token: str, entitlement: dict) -> list:
    pid_uri = entitlement["pidUri"]
    namespace = C.ENTITLEMENT_TO_NAMESPACE[entitlement["groupName"]]
    res = _account_http.get(
        f"https://gateway.ea.com/proxy/identity{pid_uri}/personas"
        f"?status=ACTIVE&access_token={access_token}",
        headers={
            "Accept-Charset": "UTF-8",
            "X-Expand-Results": "true",
            "User-Agent": C.USER_AGENT,
            "Accept-Encoding": "gzip",
        },
    )
    if res.status_code != 200:
        raise EAError(f"Could not retrieve personas: {res.text}")
    personas = res.json().get("personas", {}).get("persona", [])
    return [
        {
            "personaId": p["personaId"],
            "displayName": p.get("displayPersona") or p.get("displayName") or p.get("name"),
            "namespaceName": p["namespaceName"],
            "console": C.ENTITLEMENT_TO_SYSTEM[entitlement["groupName"]],
            "namespaceDisplay": C.NAMESPACE_DISPLAY.get(p["namespaceName"], p["namespaceName"]),
        }
        for p in personas
        if p.get("namespaceName") == namespace
    ]


def get_persona_token(access_token: str, persona_id, namespace: str) -> dict:
    """Step 6: exchange the chosen persona for the long-lived token pair."""
    res = _account_http.get(
        f"{C.EA_LOGIN_URL}&access_token={access_token}"
        f"&persona_id={persona_id}&persona_namespace={namespace}",
        headers={"User-Agent": C.USER_AGENT},
    )
    location = res.headers.get("location")
    if not location or "code=" not in location:
        raise EAError(f"EA did not return a persona code (status {res.status_code})")
    ea_code = parse_qs(urlparse(location).query)["code"][0]
    res = _account_http.post(
        "https://accounts.ea.com/connect/token",
        headers=ACCOUNT_HEADERS,
        content=(
            f"authentication_source={C.AUTH_SOURCE}&code={ea_code}"
            f"&grant_type=authorization_code&token_format=JWS&release_type=prod"
            f"&client_secret={C.CLIENT_SECRET}&redirect_uri={C.REDIRECT_URL}"
            f"&client_id={C.CLIENT_ID}"
        ),
    )
    data = res.json()
    if res.status_code != 200 or "access_token" not in data:
        raise EAError(f"Persona token exchange failed: {data}")
    return data


def token_record(token_response: dict, console: str) -> dict:
    """Normalize an EA token response into what we persist."""
    expiry = datetime.now(timezone.utc) + timedelta(seconds=token_response["expires_in"])
    return {
        "accessToken": token_response["access_token"],
        "refreshToken": token_response["refresh_token"],
        "expiry": expiry.isoformat(),
        "console": console,
    }


def refresh_token_if_needed(token: dict) -> dict:
    if datetime.now(timezone.utc) < datetime.fromisoformat(token["expiry"]):
        return token
    res = _account_http.post(
        "https://accounts.ea.com/connect/token",
        headers=ACCOUNT_HEADERS,
        content=(
            f"grant_type=refresh_token&client_id={C.CLIENT_ID}"
            f"&client_secret={C.CLIENT_SECRET}&release_type=prod"
            f"&refresh_token={token['refreshToken']}"
            f"&authentication_source={C.AUTH_SOURCE}&token_format=JWS"
        ),
    )
    data = res.json()
    if res.status_code != 200 or "access_token" not in data:
        raise EAError(
            f"Token refresh failed ({data}). Reconnect your EA account from the admin page."
        )
    return {**token_record(data, token["console"])}


# ---------------------------------------------------------------------------
# Blaze (steps 8-10)
# ---------------------------------------------------------------------------

def blaze_login(token: dict) -> dict:
    res = _blaze_http.post(
        f"{C.BLAZE_HOST}/wal/authentication/login",
        headers=_blaze_headers(token["console"]),
        content=_compact({
            "accessToken": token["accessToken"],
            "productName": C.BLAZE_PRODUCT_NAME[token["console"]],
        }),
    )
    try:
        info = res.json()["userLoginInfo"]
    except Exception:
        raise EAError(f"Blaze login failed: {res.text[:500]}")
    return {
        "blazeId": info["personaDetails"]["personaId"],
        "sessionKey": info["sessionKey"],
        "requestId": 1,
    }


def message_auth(blaze_id: int, request_id: int, rand4: bytes | None = None) -> dict:
    """Per-request signed auth blob. Port of snallabot's calculateMessageAuthData."""
    rand4 = rand4 if rand4 is not None else os.urandom(4)
    request_data = _compact({
        "staticData": "05e6a7ead5584ab4",
        "requestId": request_id,
        "blazeId": blaze_id,
    }).encode("utf-8")
    static_bytes = bytes.fromhex("634203362017bf72f70ba900c0aa4e6b")
    xor_hash = hashlib.md5(rand4 + static_bytes).digest()
    scrambled = bytes(b ^ xor_hash[i % 16] for i, b in enumerate(request_data))
    auth_data_bytes = rand4 + scrambled
    static_auth_code = bytes.fromhex("3a53413521464c3b6531326530705b70203a2900")
    return {
        "authData": base64.b64encode(auth_data_bytes).decode(),
        "authCode": base64.b64encode(
            hashlib.md5(static_auth_code + auth_data_bytes).digest()
        ).decode(),
        "authType": 17039361,
    }


def blaze_rpc(token: dict, session: dict, command_name: str, command_id: int, payload: dict):
    body = {
        "apiVersion": 2,
        "clientDevice": 3,
        "requestInfo": _compact({
            "commandName": command_name,
            "componentId": 2060,
            "commandId": command_id,
            "componentName": C.COMPONENT_NAME,
            "messageAuthData": message_auth(session["blazeId"], session["requestId"]),
            "messageExpirationTime": int(time.time()),
            "deviceId": C.MACHINE_KEY,
            "ipAddress": "127.0.0.1",
            "requestPayload": _compact(payload),
        }),
    }
    res = _blaze_http.post(
        f"{C.BLAZE_HOST}/wal/mca/Process/{session['sessionKey']}",
        headers=_blaze_headers(token["console"]),
        content=_compact(body),
    )
    try:
        data = res.json()
    except Exception:
        raise EAError(f"Blaze RPC {command_name} failed: {res.text[:500]}")
    if isinstance(data, dict) and data.get("error"):
        raise BlazeError(data)
    return data


_CONTROL_CHARS = {c: None for c in list(range(0x00, 0x20)) + list(range(0x7F, 0xA0))}


def get_export(token: dict, session: dict, export_type: str, body: dict,
               retries: int = 5, base_delay: float = 1.0):
    for attempt in range(retries):
        res = _blaze_http.post(
            f"{C.BLAZE_HOST}/wal/mca/{export_type}/{session['sessionKey']}",
            headers=_blaze_headers(token["console"]),
            content=_compact(body),
        )
        try:
            data = json.loads(res.text.translate(_CONTROL_CHARS))
        except Exception as e:
            raise EAError(f"Could not parse export {export_type}: {e}: {res.text[:300]}")
        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            if data["error"].get("errorname") == "ERR_TIMEOUT" and attempt < retries - 1:
                time.sleep(base_delay * 2 ** attempt)
                continue
            raise BlazeError(data)
        return data
    raise EAError(f"Export {export_type} timed out after {retries} attempts")


# ---------------------------------------------------------------------------
# High-level client
# ---------------------------------------------------------------------------

class EAClient:
    """Refreshes tokens / Blaze sessions transparently; persists via the store."""

    def __init__(self, token_store):
        self.store = token_store
        state = token_store.load()
        if not state or "token" not in state:
            raise EAError("EA account not connected yet — connect it from the admin page.")
        self.token = state["token"]
        self.session = state.get("session")

    def _persist(self):
        state = self.store.load() or {}
        state["token"] = self.token
        state["session"] = self.session
        self.store.save(state)

    def _ensure_session(self):
        self.token = refresh_token_if_needed(self.token)
        if not self.session:
            self.session = blaze_login(self.token)
        self._persist()

    def _rpc(self, command_name, command_id, payload):
        self._ensure_session()
        try:
            return blaze_rpc(self.token, self.session, command_name, command_id, payload)
        except BlazeError:
            self.session = blaze_login(self.token)
            self._persist()
            return blaze_rpc(self.token, self.session, command_name, command_id, payload)

    def _export(self, export_type, body):
        self._ensure_session()
        try:
            return get_export(self.token, self.session, export_type, body)
        except BlazeError:
            self.session = blaze_login(self.token)
            self._persist()
            return get_export(self.token, self.session, export_type, body)

    @property
    def console(self) -> str:
        return self.token["console"]

    def get_leagues(self) -> list:
        res = self._rpc("Mobile_GetMyLeagues", 801, {})
        return res["responseInfo"]["value"]["leagues"]

    def get_league_info(self, league_id: int) -> dict:
        res = self._rpc("Mobile_Career_GetLeagueHub", 811, {"leagueId": league_id})
        return res["responseInfo"]["value"]

    def get_teams(self, league_id: int) -> dict:
        return self._export(C.EXPORT_TEAMS, {"leagueId": league_id})

    def get_standings(self, league_id: int) -> dict:
        return self._export(C.EXPORT_STANDINGS, {"leagueId": league_id})

    def get_weekly(self, data_type: str, league_id: int, stage: int, week_index: int) -> dict:
        return self._export(
            C.WEEKLY_EXPORTS[data_type],
            {"leagueId": league_id, "stageIndex": stage, "weekIndex": week_index},
        )

    def get_team_roster(self, league_id: int, team_id: int, team_index: int) -> dict:
        return self._export(C.EXPORT_TEAM_ROSTER, {
            "leagueId": league_id, "listIndex": team_index,
            "returnFreeAgents": False, "teamId": team_id,
        })

    def get_free_agents(self, league_id: int) -> dict:
        return self._export(C.EXPORT_TEAM_ROSTER, {
            "leagueId": league_id, "listIndex": -1,
            "returnFreeAgents": True, "teamId": 0,
        })
