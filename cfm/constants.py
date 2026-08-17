"""EA / Madden Companion App constants.

These values are extracted from the Madden Companion App (credit: snallabot,
https://github.com/snallabot/snallabot-service, MIT). EA rotates some of them
each Madden year. If exports stop working after a new Madden releases, copy the
new values from snallabot's src/dashboard/ea_constants.ts into the environment
(see .env.example) — no code change needed.

Current defaults are for Madden 27 (snallabot as of 2026-08-15). For a league
still on Madden 26, set EA_BLAZE_YEAR=2026 and EA_COMPONENT_NAME=careermode.
"""
import os

CLIENT_ID = os.environ.get("EA_CLIENT_ID", "MCA_26_COMP_APP")
CLIENT_SECRET = os.environ.get(
    "EA_CLIENT_SECRET",
    "teJpJ9cSXFqZAuKNW8IuHpy8D4dwWPoVrPoek38iCnrGbrUSfjqnHMBAv8iCVjeSm_20250910175618",
)
AUTH_SOURCE = os.environ.get("EA_AUTH_SOURCE", "317239")
MACHINE_KEY = os.environ.get("EA_MACHINE_KEY", "444d362e8e067fe2")
REDIRECT_URL = "http://127.0.0.1/success"

# Entitlement names have kept the "26" suffix into Madden 27.
ENTITLEMENT_YEAR = os.environ.get("EA_ENTITLEMENT_YEAR", "26")
# Blaze service names track the season year (Madden 27 -> 2027).
BLAZE_YEAR = os.environ.get("EA_BLAZE_YEAR", "2027")
# "careermode" through Madden 26, "franchisemode" from Madden 27 on.
COMPONENT_NAME = os.environ.get("EA_COMPONENT_NAME", "franchisemode")

USER_AGENT = "Dalvik/2.1.0 (Linux; U; Android 13; sdk_gphone_x86_64 Build/TE1A.220922.031)"

EA_LOGIN_URL = (
    "https://accounts.ea.com/connect/auth?hide_create=true&release_type=prod"
    f"&response_type=code&redirect_uri={REDIRECT_URL}&client_id={CLIENT_ID}"
    f"&machineProfileKey={MACHINE_KEY}&authentication_source={AUTH_SOURCE}"
)

BLAZE_HOST = "https://wal2.tools.gos.bio-iad.ea.com"

# console key -> entitlement group name
VALID_ENTITLEMENTS = {
    "xone": f"MADDEN_{ENTITLEMENT_YEAR}XONE",
    "ps4": f"MADDEN_{ENTITLEMENT_YEAR}PS4",
    "pc": f"MADDEN_{ENTITLEMENT_YEAR}PC",
    "ps5": f"MADDEN_{ENTITLEMENT_YEAR}PS5",
    "xbsx": f"MADDEN_{ENTITLEMENT_YEAR}XBSX",
    "stadia": f"MADDEN_{ENTITLEMENT_YEAR}SDA",
}
ENTITLEMENT_TO_SYSTEM = {v: k for k, v in VALID_ENTITLEMENTS.items()}
ENTITLEMENT_TO_NAMESPACE = {
    f"MADDEN_{ENTITLEMENT_YEAR}XONE": "xbox",
    f"MADDEN_{ENTITLEMENT_YEAR}PS4": "ps3",
    f"MADDEN_{ENTITLEMENT_YEAR}PC": "cem_ea_id",
    f"MADDEN_{ENTITLEMENT_YEAR}PS5": "ps3",
    f"MADDEN_{ENTITLEMENT_YEAR}XBSX": "xbox",
    f"MADDEN_{ENTITLEMENT_YEAR}SDA": "stadia",
}
NAMESPACE_DISPLAY = {
    "xbox": "XBOX",
    "ps3": "PSN",
    "cem_ea_id": "EA Account",
    "stadia": "Stadia",
}

BLAZE_SERVICE = {c: f"madden-{BLAZE_YEAR}-{c}" for c in VALID_ENTITLEMENTS}
BLAZE_PRODUCT_NAME = {c: f"madden-{BLAZE_YEAR}-{c}-mca" for c in VALID_ENTITLEMENTS}

# Blaze export endpoint names
EXPORT_TEAMS = "CareerMode_GetLeagueTeamsExport"
EXPORT_STANDINGS = "CareerMode_GetStandingsExport"
EXPORT_TEAM_ROSTER = "CareerMode_GetTeamRostersExport"
WEEKLY_EXPORTS = {
    # dataType used in the companion-app URL/db path -> Blaze endpoint
    "schedules": "CareerMode_GetWeeklySchedulesExport",
    "teamstats": "CareerMode_GetWeeklyTeamStatsExport",
    "passing": "CareerMode_GetWeeklyPassingStatsExport",
    "rushing": "CareerMode_GetWeeklyRushingStatsExport",
    "receiving": "CareerMode_GetWeeklyReceivingStatsExport",
    "defense": "CareerMode_GetWeeklyDefensiveStatsExport",
    "kicking": "CareerMode_GetWeeklyKickingStatsExport",
    "punting": "CareerMode_GetWeeklyPuntingStatsExport",
}

STAGE_PRESEASON = 0
STAGE_SEASON = 1
