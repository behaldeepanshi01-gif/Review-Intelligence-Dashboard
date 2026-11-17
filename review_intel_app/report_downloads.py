"""Ephemeral, single-use report delivery; never register reports as public media."""
import secrets
import re
import threading
import time
from urllib.parse import parse_qs

from starlette.responses import HTMLResponse, Response
from starlette.routing import Route
import manager_identity as identity

TTL_SECONDS = 120
MAX_REPORT_BYTES = 2_000_000
_lock = threading.RLock()
_reports = {}
_attempts = []
HEADERS = {
    "Cache-Control": "no-store, private, max-age=0",
    "Pragma": "no-cache",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; form-action 'self'; frame-ancestors 'none'",
}


def _prune():
    now = time.time()
    for token, row in list(_reports.items()):
        if now >= row["expires"] or not identity.permits(
                row["grant"], row["dataset"], row["locations"]):
            del _reports[token]


def revoke(grant):
    """Invalidate every outstanding link from this dashboard login."""
    if not grant:
        return
    with _lock:
        for token, row in list(_reports.items()):
            if row["grant"] == grant:
                del _reports[token]


def issue(grant, dataset, locations, text, *, acknowledged,
          filename="manager_action_report.txt", media_type="text/plain",
          revoke_existing=True):
    if not acknowledged or not identity.permits(grant, dataset, locations):
        raise PermissionError("Report access or privacy acknowledgment required.")
    if media_type not in {"text/plain", "text/csv", "application/json", "text/html"}:
        raise ValueError("Unsupported export format.")
    # Filenames are display metadata, never authorization or a filesystem path.
    filename = re.sub(r"[^A-Za-z0-9._-]", "_", filename)[:150].strip(".")
    if not filename:
        filename = "export"
    content = text.encode("utf-8") if isinstance(text, str) else bytes(text)
    if len(content) > MAX_REPORT_BYTES:
        raise ValueError("Report is too large. Select fewer restaurants.")
    with _lock:
        _prune()
        if revoke_existing:
            revoke(grant)
        if len(_reports) >= 100:
            raise ValueError("Report service is busy. Try again in two minutes.")
        token = secrets.token_urlsafe(32)
        _reports[token] = {
            "grant": dict(grant), "dataset": dataset, "locations": tuple(locations),
            "content": content, "expires": min(time.time() + TTL_SECONDS, grant["expires"]),
            "filename": filename, "media_type": media_type,
        }
        return token


def retrieve(token, username, password, *, with_metadata=False):
    # Bound password hashing work globally, not only per guessable username/link.
    with _lock:
        _prune()
        now = time.time()
        _attempts[:] = [t for t in _attempts if t > now - 60]
        if len(_attempts) >= 10:
            return None
        row = _reports.get(token)
        if row is None:
            return None
        _attempts.append(now)
    fresh = identity.authenticate(username, password)
    with _lock:
        # Logout, expiry, and grant edits may have happened during authentication.
        _prune()
        if _reports.get(token) is not row or not fresh:
            return None
        if fresh["username"] != row["grant"]["username"]:
            return None
        if not identity.permits(fresh, row["dataset"], row["locations"]):
            return None
        del _reports[token]
        return row if with_metadata else row["content"]


def unavailable():
    return HTMLResponse(
        "<h1>Report unavailable</h1><p>The link expired, was used, was locked, or access "
        "could not be verified. Return to the dashboard and prepare a new link.</p>",
        status_code=403, headers=HEADERS)


async def download(request):
    token = request.path_params["token"]
    with _lock:
        _prune()
        if token not in _reports:
            return unavailable()
    if request.method == "GET":
        return HTMLResponse(
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Confirm secure export download</title>'
            '<h1>Confirm secure export download</h1>'
            '<p>Enter the same manager account that prepared this export. '
            'This single-use link expires after two minutes. Locking the dashboard '
            'invalidates it. Files already downloaded cannot be recalled.</p>'
            '<form method="post"><label>Manager ID <input name="username" '
            'autocomplete="username" required maxlength="200"></label><br>'
            '<label>Password <input name="password" type="password" '
            'autocomplete="current-password" required maxlength="1000"></label><br>'
            '<button type="submit">Download file</button></form>'
            '</html>', headers=HEADERS)
    # No ambient credential/cookie authentication: every POST requires credentials.
    # Still reject cross-site forms so credentials cannot be submitted by other sites.
    if request.headers.get("sec-fetch-site") == "cross-site":
        return unavailable()
    if request.headers.get("content-type", "").split(";")[0] != "application/x-www-form-urlencoded":
        return unavailable()
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 8192:
            return unavailable()
    try:
        values = parse_qs(body.decode("utf-8"), max_num_fields=2)
        username = values.get("username", [""])[0]
        password = values.get("password", [""])[0]
    except (ValueError, UnicodeError):
        return unavailable()
    # scrypt should not block Streamlit's event loop.
    from starlette.concurrency import run_in_threadpool
    delivery = await run_in_threadpool(retrieve, token, username, password, with_metadata=True)
    if delivery is None:
        return unavailable()
    return Response(delivery["content"], media_type=delivery["media_type"], headers={
        **HEADERS, "Content-Disposition": f'attachment; filename="{delivery["filename"]}"'})


routes = [Route("/dashboard/report-download/{token}", download, methods=["GET", "POST"])]
