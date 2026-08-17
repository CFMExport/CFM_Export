"""Admin UI: connect an EA account, map leagues to Firebase projects, export.

Reachable on the LAN only (nothing here is exposed unless you forward the
port). Set ADMIN_PASSWORD to additionally require HTTP basic auth.
"""
import glob
import os

from urllib.parse import quote_plus

from flask import Blueprint, request, redirect, render_template_string, Response

from . import constants as C
from . import ea_client as ea
from . import exporter
from . import store as fb
from .tokens import store as token_store

admin = Blueprint("admin", __name__)

CONFIG_DIR = os.environ.get("CONFIG_DIR", "/config")


def back(message: str | None = None, error: str | None = None):
    if error:
        return redirect(f"/admin/?error={quote_plus(error)}")
    if message:
        return redirect(f"/admin/?message={quote_plus(message)}")
    return redirect("/admin/")


@admin.before_request
def _basic_auth():
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        return None
    auth = request.authorization
    if auth and auth.password == password:
        return None
    return Response(
        "Authentication required", 401,
        {"WWW-Authenticate": 'Basic realm="cfm-exporter admin"'},
    )


PAGE = """<!doctype html>
<title>CFM Exporter</title>
<style>
 body { font-family: system-ui, sans-serif; max-width: 60rem; margin: 2rem auto; padding: 0 1rem; }
 h1 { font-size: 1.4rem; } h2 { font-size: 1.1rem; margin-top: 2rem; }
 table { border-collapse: collapse; width: 100%; }
 td, th { border: 1px solid #ccc; padding: .4rem .6rem; text-align: left; font-size: .9rem; }
 form.inline { display: inline; }
 input[type=text], input[type=url], select { width: 100%; box-sizing: border-box; }
 .error { color: #b00020; white-space: pre-wrap; }
 .ok { color: #1b5e20; }
 .muted { color: #666; font-size: .85rem; }
 button { cursor: pointer; }
</style>
<h1>Madden CFM Exporter</h1>
{% if error %}<p class="error">{{ error }}</p>{% endif %}
{% if message %}<p class="ok">{{ message }}</p>{% endif %}
{{ body }}
"""


def page(body, error=None, message=None):
    from markupsafe import Markup
    return render_template_string(
        PAGE, body=Markup(body), error=error, message=message
    )


def _key_files():
    return sorted(glob.glob(os.path.join(CONFIG_DIR, "*.json")))


def _state():
    return token_store.load() or {}


@admin.route("/")
def home():
    return page(_home_body(), error=request.args.get("error"),
                message=request.args.get("message"))


def _home_body():
    state = _state()
    connected = "token" in state
    leagues = state.get("leagues", {})
    html = ["<h2>EA account</h2>"]
    if connected:
        html.append(
            f"<p class='ok'>Connected (console: {state['token']['console']})</p>"
            "<form class='inline' method='post' action='/admin/ea/disconnect'>"
            "<button>Disconnect EA account</button></form>"
        )
    else:
        html.append(f"""
        <p>Not connected. To connect:</p>
        <ol>
          <li><a href="{C.EA_LOGIN_URL}" target="_blank">Open the EA login page</a>
              and sign in with the EA account that owns Madden.</li>
          <li>You will land on a broken page at <code>127.0.0.1/success</code> —
              that is expected. Copy the <b>full URL</b> from the address bar.</li>
          <li>Paste it here:</li>
        </ol>
        <form method="post" action="/admin/ea/code">
          <input type="text" name="redirect_url" placeholder="http://127.0.0.1/success?code=...">
          <button>Continue</button>
        </form>""")

    html.append("<h2>Leagues</h2>")
    if leagues:
        html.append("<table><tr><th>Label</th><th>League ID</th><th>Database</th>"
                    "<th>Export</th><th>Status</th><th></th></tr>")
        for lid, lg in leagues.items():
            job = exporter.job_status(lid) or {}
            status = job.get("status", "-")
            if status == "running":
                status = f"running: {job.get('detail', '')}"
            elif status == "error":
                status = f"error: {job.get('error', '')[:200]}"
            elif status == "done":
                status = f"done at {job.get('finished', '')}"
            html.append(f"""<tr>
              <td>{lg.get('label', '')}</td>
              <td>{lid}</td>
              <td class="muted">{lg['databaseURL']}</td>
              <td>
                <form class="inline" method="post" action="/admin/league/{lid}/export">
                  <select name="weeks">
                    <option value="current">Current week</option>
                    <option value="all">All weeks</option>
                  </select>
                  <label><input type="checkbox" name="rosters"> rosters</label>
                  <button>Export</button>
                </form>
              </td>
              <td>{status}</td>
              <td><form class="inline" method="post" action="/admin/league/{lid}/delete"
                    onsubmit="return confirm('Remove league {lid}? (Firebase data is untouched)')">
                  <button>Remove</button></form></td>
            </tr>""")
        html.append("</table>")
    else:
        html.append("<p class='muted'>No leagues configured yet.</p>")

    if connected:
        key_options = "".join(
            f"<option value='{f}'>{os.path.basename(f)}</option>" for f in _key_files()
        )
        if not key_options:
            html.append(f"<p class='error'>No .json key files found in {CONFIG_DIR}. "
                        "Drop each league's Firebase service-account key there first.</p>")
        try:
            client = ea.EAClient(token_store)
            league_options = "".join(
                f"<option value='{lg['leagueId']}'>{lg.get('leagueName', lg['leagueId'])}"
                f" ({lg['leagueId']})</option>"
                for lg in client.get_leagues()
            )
        except Exception as e:
            league_options = ""
            html.append(f"<p class='error'>Could not list EA leagues: {e}</p>")
        html.append(f"""
        <h3>Add a league</h3>
        <form method="post" action="/admin/league/add">
          <table>
            <tr><th>EA league</th><td>
              <select name="leagueId">{league_options}</select>
              <span class="muted">Pulled live from your EA account</span></td></tr>
            <tr><th>Label</th><td><input type="text" name="label" placeholder="my league"></td></tr>
            <tr><th>Firebase key file</th><td><select name="keyFile">{key_options}</select></td></tr>
            <tr><th>Database URL</th><td><input type="url" name="databaseURL"
                 placeholder="https://myproject-default-rtdb.firebaseio.com/"></td></tr>
          </table>
          <button>Add league</button>
        </form>""")

    html.append(
        "<h2>Companion App push (fallback)</h2>"
        "<p class='muted'>The Madden Companion App can still push to this server: "
        "use <code>http://&lt;this-host&gt;:5000</code> as the export URL. "
        "Only configured league IDs are accepted.</p>"
    )
    return "\n".join(html)


# ---------------------------------------------------------------------------
# EA connection flow
# ---------------------------------------------------------------------------

@admin.route("/ea/code", methods=["POST"])
def ea_code():
    try:
        code = ea.parse_login_redirect(request.form.get("redirect_url", ""))
        token = ea.exchange_code(code)
        access_token = token["access_token"]
        pid = ea.get_pid(access_token)
        personas = []
        for ent in ea.get_madden_entitlements(access_token, pid):
            personas.extend(ea.get_personas(access_token, ent))
        if not personas:
            raise ea.EAError("No Madden personas found on this account")
    except ea.EAError as e:
        return page("", error=str(e))
    rows = "".join(
        f"""<tr><td><input type="radio" name="persona" required
              value="{p['personaId']}|{p['namespaceName']}|{p['console']}"></td>
            <td>{p['displayName']}</td><td>{p['namespaceDisplay']}</td>
            <td>{p['console']}</td></tr>"""
        for p in personas
    )
    return page(f"""
      <h2>Select your console persona</h2>
      <form method="post" action="/admin/ea/persona">
        <input type="hidden" name="access_token" value="{access_token}">
        <table><tr><th></th><th>Name</th><th>Network</th><th>Console</th></tr>{rows}</table>
        <button>Connect</button>
      </form>""")


@admin.route("/ea/persona", methods=["POST"])
def ea_persona():
    try:
        persona_id, namespace, console = request.form["persona"].split("|")
        token_response = ea.get_persona_token(
            request.form["access_token"], persona_id, namespace
        )
        token = ea.token_record(token_response, console)
        session = ea.blaze_login(token)
        token_store.update(token=token, session=session)
    except ea.EAError as e:
        return page("", error=str(e))
    return back(message="EA account connected")


@admin.route("/ea/disconnect", methods=["POST"])
def ea_disconnect():
    state = _state()
    state.pop("token", None)
    state.pop("session", None)
    token_store.save(state)
    return back(message="EA account disconnected")


# ---------------------------------------------------------------------------
# League management + exports
# ---------------------------------------------------------------------------

@admin.route("/league/add", methods=["POST"])
def league_add():
    league_id = request.form["leagueId"].strip()
    cfg = {
        "leagueId": int(league_id),
        "label": request.form.get("label", "").strip() or league_id,
        "keyFile": request.form["keyFile"],
        "databaseURL": request.form["databaseURL"].strip(),
    }
    if not cfg["databaseURL"].startswith("https://"):
        return back(error="Database URL must start with https://")
    try:
        fb.check_connection(cfg)
    except Exception as e:
        fb.drop_app(league_id)
        return back(error=f"Firebase connection failed: {e}")
    state = _state()
    state.setdefault("leagues", {})[league_id] = cfg
    token_store.save(state)
    return back(message=f"League {league_id} added")


@admin.route("/league/<league_id>/delete", methods=["POST"])
def league_delete(league_id):
    state = _state()
    state.get("leagues", {}).pop(league_id, None)
    token_store.save(state)
    fb.drop_app(league_id)
    return back(message=f"League {league_id} removed")


@admin.route("/league/<league_id>/export", methods=["POST"])
def league_export(league_id):
    league = _state().get("leagues", {}).get(league_id)
    if not league:
        return back(error=f"League {league_id} not configured")
    started = exporter.run_export(
        league,
        weeks=request.form.get("weeks", "current"),
        rosters=bool(request.form.get("rosters")),
    )
    msg = "Export started" if started else "An export is already running for this league"
    return back(message=f"{msg}")
