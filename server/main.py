# AmberShelf - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""Web interface.

Stage 1 and 2: register disks, mount them, index them, compare them and show
what would happen. Nothing in this file writes to a data disk - the master is
mounted read-only and the slaves are only ever read.
"""
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from engine import apply as apply_engine
from engine import paths
from engine import compare, config, db, fsutil, notify, planner, scanner
from engine.jobs import manager
from platforms import BackendError, backend
from server import i18n

# Bundled into a single executable the templates live somewhere else, so the
# path comes from one place that knows both cases.
BASE_DIR = paths.resource_dir() / "server"

@asynccontextmanager
async def lifespan(_: FastAPI):
    db.initialise()
    refresh_registrations()
    db.log_event("info", "AmberShelf started", None, "app")
    yield


app = FastAPI(title="AmberShelf", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def refresh_registrations() -> None:
    """Pull the host registry into the database. The host stays the authority."""
    try:
        db.sync_disks_from_helper(backend.registrations())
    except BackendError as exc:
        db.log_event("warning", f"host helper unreachable: {exc}", None, "app")


# ---------------------------------------------------------------- plumbing --

def human(value) -> str:
    try:
        return fsutil.human_bytes(float(value or 0))
    except (TypeError, ValueError):
        return "-"


def local_time(value: str | None) -> str:
    if not value:
        return "-"
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return value


# The colour a swatch shows in the settings - the live value lives in CSS.
ACCENT_SWATCHES = {
    "amber": "#e08b12",
    "violet": "#7c5cff",
    "blue": "#3b82f6",
    "emerald": "#10a37f",
    "rose": "#e0457b",
}

templates.env.filters["bytes"] = human
templates.env.filters["dt"] = local_time
templates.env.filters["thousands"] = lambda v: f"{int(v or 0):,}".replace(",", ".")


def context(request: Request, **extra) -> dict:
    language = i18n.pick_language(
        request.cookies.get("lang"),
        request.headers.get("accept-language"),
        config.DEFAULT_LANGUAGE,
    )
    translate = i18n.translator(language)

    def message(entry) -> str:
        """Render a {key, params} pair from the engine in the chosen language."""
        if isinstance(entry, dict) and "key" in entry:
            return translate(entry["key"], **(entry.get("params") or {}))
        return str(entry)

    theme = db.get_setting("theme")
    if theme not in config.THEMES:
        theme = "system"
    accent = db.get_setting("accent")
    if accent not in config.ACCENTS:
        accent = config.ACCENTS[0]

    base = {
        "request": request,
        "t": translate,
        "msg_of": message,
        "theme": theme,
        "accent": accent,
        "accent_swatches": ACCENT_SWATCHES,
        "lang": language,
        "languages": i18n.LANGUAGES,
        "helper_ok": backend.available(),
        "backend_name": backend.name,
        # Drives the warning band: on a desktop system the master is not
        # held read-only by anything, and that has to be said plainly.
        "write_protected": backend.enforces_write_protection,
        "registry_protected": backend.registry_is_protected,
        "is_desktop": paths.desktop_build(),
        "sets": db.all_sets(),
        "open_findings": db.count_open_findings(),
        "active_jobs": [job.as_dict() for job in manager.active()],
        # The job panel is redrawn by script, so it needs its own texts.
        "job_labels": json.dumps({
            **{state: translate(f"job.{state}")
               for state in ("queued", "running", "paused", "done", "failed", "cancelled")},
            **{f"phase.{phase}": translate(f"job.phase.{phase}")
               for phase in ("walk", "hash", "scope", "compare", "apply")},
        }, ensure_ascii=False),
    }
    base.update(extra)
    # Routes hand back short keys for anything they say themselves, so the
    # message ends up in the reader's language rather than the engine's.
    message = base.get("msg")
    if isinstance(message, str) and message in i18n.STRINGS.get(language, {}):
        base["msg"] = translate(message)
    return base


def render(name: str, request: Request, **extra) -> HTMLResponse:
    values = context(request, **extra)
    values.pop("request", None)
    return templates.TemplateResponse(request, name, values)


def back(request: Request, fallback: str = "/") -> RedirectResponse:
    target = request.headers.get("referer") or fallback
    return RedirectResponse(target, status_code=303)


def flash(request: Request, url: str, message: str, level: str = "info") -> RedirectResponse:
    separator = "&" if "?" in url else "?"
    return RedirectResponse(f"{url}{separator}msg={message}&level={level}", status_code=303)


# ---------------------------------------------------------------- overview --

@app.get("/", response_class=HTMLResponse)
def overview(request: Request):
    refresh_registrations()
    sets = []
    for row in db.all_sets():
        sets.append(set_state(row["name"]))
    return render("overview.html", request, sets=sets,
                  msg=request.query_params.get("msg"),
                  level=request.query_params.get("level", "info"))


def set_state(set_name: str) -> dict:
    disks = []
    try:
        status = {entry["fs_uuid"]: entry for entry in backend.status(set_name)}
    except BackendError:
        status = {}

    for disk in db.disks_of_set(set_name):
        entry = dict(disk)
        live = status.get(disk["fs_uuid"], {})
        entry["connected"] = live.get("connected", False)
        entry["mounted"] = live.get("mounted", False)
        entry["read_only"] = live.get("read_only", False)
        entry["mountpoint"] = live.get("mountpoint")
        entry["scan"] = scanner.scan_state(disk["id"])

        # The dirty flag is set for as long as a volume is mounted, so it only
        # means "was not unmounted cleanly" while the disk is sitting idle.
        entry["dirty"] = False
        if (entry["connected"] and not entry["mounted"]
                and (disk["fs_type"] or "").lower() == "exfat"):
            try:
                state = backend.volume_state(disk["fs_uuid"], disk["fs_type"])
                entry["dirty"] = bool(state.get("dirty"))
            except BackendError:
                pass

        if entry["mounted"] and entry["mountpoint"]:
            try:
                entry["free_bytes"] = fsutil.free_bytes(Path(entry["mountpoint"]))
            except OSError:
                entry["free_bytes"] = None
        else:
            entry["free_bytes"] = None
        disks.append(entry)

    plan = compare.latest_plan(set_name)
    return {
        "name": set_name,
        "disks": disks,
        "master": next((d for d in disks if d["role"] == "master"), None),
        "slaves": [d for d in disks if d["role"] == "slave"],
        "any_mounted": any(d["mounted"] for d in disks),
        "connected_count": sum(1 for d in disks if d["connected"]),
        "all_connected": all(d["connected"] for d in disks) and bool(disks),
        "plan": dict(plan) if plan else None,
        "split_enabled": bool(db.scalar(
            "SELECT split_enabled FROM sets WHERE name = ?", (set_name,), 0)),
    }


# ------------------------------------------------------------------- disks --

@app.get("/disks", response_class=HTMLResponse)
def disks_page(request: Request):
    refresh_registrations()
    try:
        connected = [volume.as_dict() for volume in backend.list_volumes()]
        error = None
    except BackendError as exc:
        connected, error = [], str(exc)
    return render("disks.html", request, connected=connected, error=error,
                  registered=db.query("SELECT * FROM disks ORDER BY set_name, role DESC"),
                  msg=request.query_params.get("msg"),
                  level=request.query_params.get("level", "info"))


@app.post("/disks/register")
def register_disk(request: Request, fs_uuid: str = Form(...), role: str = Form(...),
                  set_name: str = Form(...), display_name: str = Form(...)):
    try:
        backend.register(fs_uuid.strip(), role.strip(), set_name.strip(),
                         display_name.strip())
        refresh_registrations()
        db.log_event("info", f"{display_name} registered as {role} of {set_name}",
                     set_name, "disks")
        return flash(request, "/disks", "registered", "ok")
    except BackendError as exc:
        return flash(request, "/disks", str(exc), "error")


# ------------------------------------------------------------------ mounts --

@app.post("/sets/{set_name}/mount")
def mount_set(request: Request, set_name: str):
    try:
        result = backend.attach(set_name)
        missing = ", ".join(entry["display_name"] for entry in result.missing)
        message = f"{len(result.attached)} mounted"
        if missing:
            message += f", not connected: {missing}"
        db.log_event("info", message, set_name, "mount")
        return flash(request, "/", message, "ok")
    except BackendError as exc:
        db.log_event("error", str(exc), set_name, "mount")
        return flash(request, "/", str(exc), "error")


@app.post("/sets/{set_name}/umount")
def umount_set(request: Request, set_name: str):
    if manager.busy_with() is not None:
        return flash(request, "/", "a job is still running", "error")
    try:
        result = backend.detach(set_name)
        if result.failed:
            detail = "; ".join(f"{e['mountpoint']}: {e['error']}" for e in result.failed)
            return flash(request, "/", detail, "error")
        db.log_event("info", f"{len(result.attached)} unmounted", set_name, "mount")
        return flash(request, "/", "unmounted", "ok")
    except BackendError as exc:
        return flash(request, "/", str(exc), "error")


# ------------------------------------------------------------------- scans --

@app.post("/sets/{set_name}/scan/{disk_id}")
def scan_disk(request: Request, set_name: str, disk_id: int):
    disk = db.disk_by_id(disk_id)
    if disk is None:
        return flash(request, "/", "unknown disk", "error")
    if manager.busy_with(disk_id=disk_id) is not None:
        return flash(request, "/", "this disk is already being indexed", "error")

    manager.submit(
        "scan", f"{disk['display_name']}",
        lambda job: scanner.scan_disk(job, disk_id),
        set_name=set_name, disk_id=disk_id,
    )
    return flash(request, "/", "indexing started", "ok")


@app.post("/sets/{set_name}/rehash/{disk_id}")
def rehash_disk(request: Request, set_name: str, disk_id: int):
    if manager.busy_with(disk_id=disk_id) is not None:
        return flash(request, "/", "this disk is busy", "error")
    count = scanner.rehash_disk(disk_id)
    db.log_event("info", f"{count:,} hashes dropped, they are recomputed on the next index run",
                 set_name, "scan")
    return flash(request, "/", f"{count} hashes dropped", "ok")


# ----------------------------------------------------------------- compare --

@app.post("/sets/{set_name}/compare")
def start_compare(request: Request, set_name: str):
    if manager.busy_with() is not None:
        return flash(request, f"/sets/{set_name}/plan", "something else is running", "error")
    state = compare.readiness(set_name)
    if not state["ready"]:
        translate = i18n.translator(i18n.pick_language(
            request.cookies.get("lang"), request.headers.get("accept-language"),
            config.DEFAULT_LANGUAGE))
        return flash(request, f"/sets/{set_name}/plan",
                     "; ".join(translate(p["key"], **p["params"])
                               for p in state["problems"]), "error")

    manager.submit("compare", set_name,
                   lambda job: compare.build_plan(job, set_name), set_name=set_name)
    return flash(request, f"/sets/{set_name}/plan", "comparison started", "ok")


@app.get("/sets/{set_name}/plan", response_class=HTMLResponse)
def plan_page(request: Request, set_name: str):
    plan = compare.latest_plan(set_name)
    detail = compare.plan_summary(plan["id"]) if plan else None
    kind = request.query_params.get("kind")
    slave = request.query_params.get("slave")
    offset = int(request.query_params.get("offset") or 0)

    items = []
    decisions = {}
    pending = 0
    selected = 0
    if plan:
        pending = apply_engine.pending_approvals(plan["id"], set_name)
        selected = sum(len(rows) for by_kind in
                       apply_engine.selected_items(plan["id"], set_name).values()
                       for rows in by_kind.values())
        if kind:
            items = compare.plan_items(plan["id"], kind, int(slave) if slave else None,
                                       offset=offset, limit=200)
            decisions = db.remembered_decisions(set_name)

    slaves = {row["id"]: dict(row) for row in db.slaves_of_set(set_name)}
    return render("plan.html", request, set_name=set_name, plan=detail, items=items,
                  kind=kind, slave=slave, offset=offset, slaves=slaves,
                  decisions=decisions, pending=pending, selected=selected,
                  readiness=compare.readiness(set_name),
                  needs_approval=compare.NEEDS_APPROVAL,
                  kinds=[compare.NEW, compare.CHANGED, compare.RENAMED, compare.DELETED,
                         compare.SLAVE_ONLY, compare.OUT_OF_SCOPE, compare.UNREADABLE],
                  msg=request.query_params.get("msg"),
                  level=request.query_params.get("level", "info"))


@app.post("/sets/{set_name}/plan/{plan_id}/decide")
async def decide(request: Request, set_name: str, plan_id: int):
    """Answer one case, or every case of one kind at once."""
    form = await request.form()
    decision = str(form.get("decision") or "")
    if decision not in ("approve", "skip_once", "skip_forever", "forget"):
        return flash(request, f"/sets/{set_name}/plan", "unknown decision", "error")

    kind = str(form.get("kind") or "")
    slave_id = int(form["slave"]) if form.get("slave") else None
    path = form.get("path")

    if path:
        db.remember_decision(set_name, slave_id, str(path), kind, decision)
        count = 1
    else:
        # Bulk: everything of this kind, for this copy or for all of them.
        where = ["plan_id = ?", "kind = ?"]
        params: list = [plan_id, kind]
        if slave_id:
            where.append("slave_disk_id = ?")
            params.append(slave_id)
        rows = db.query(f"SELECT slave_disk_id, path FROM plan_items "
                        f"WHERE {' AND '.join(where)}", params)
        for row in rows:
            db.remember_decision(set_name, row["slave_disk_id"], row["path"],
                                 kind, decision)
        count = len(rows)

    db.log_event("info", f"{count} × {kind}: {decision}", set_name, "decide")
    target = f"/sets/{set_name}/plan?kind={kind}"
    if slave_id:
        target += f"&slave={slave_id}"
    return flash(request, target, f"{count}", "ok")


@app.post("/sets/{set_name}/plan/{plan_id}/release")
def release_brake(request: Request, set_name: str, plan_id: int,
                  confirm: str = Form("")):
    """Lift the brake - only against the number the user had to read first."""
    detail = compare.plan_summary(plan_id)
    if detail is None or detail["state"] != "blocked":
        return flash(request, f"/sets/{set_name}/plan", "nothing to release", "error")

    expected = str(detail["summary"].get("brake", {}).get("confirm_number", ""))
    if confirm.strip() != expected:
        db.log_event("warning", f"plan {plan_id}: release refused, wrong number",
                     set_name, "brake")
        return flash(request, f"/sets/{set_name}/plan", "brake.wrong_number", "error")

    db.execute("UPDATE plans SET state = 'ready' WHERE id = ?", (plan_id,))
    db.log_event("warning", f"plan {plan_id}: brake released by hand", set_name, "brake")
    return flash(request, f"/sets/{set_name}/plan", "brake.released", "ok")


@app.post("/sets/{set_name}/plan/{plan_id}/apply")
async def apply_plan(request: Request, set_name: str, plan_id: int):
    if manager.busy_with() is not None:
        return flash(request, f"/sets/{set_name}/plan", "something else is running",
                     "error")
    form = await request.form()
    only = form.get("kinds")
    kinds = tuple(str(only).split(",")) if only else None

    try:
        apply_engine.precheck(plan_id, kinds)
    except apply_engine.ApplyRefused as exc:
        return flash(request, f"/sets/{set_name}/plan", str(exc), "error")

    manager.submit("apply", set_name,
                   lambda job: apply_engine.apply_plan(job, plan_id, kinds),
                   set_name=set_name)
    return flash(request, f"/sets/{set_name}/plan", "apply.started", "ok")


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_page(request: Request, run_id: int):
    run = apply_engine.run_summary(run_id)
    if run is None:
        return RedirectResponse("/events", status_code=303)
    state = request.query_params.get("state")
    offset = int(request.query_params.get("offset") or 0)
    slaves = {row["id"]: dict(row) for row in db.query("SELECT * FROM disks")}
    return render("run.html", request, run=run, slaves=slaves, state=state, offset=offset,
                  items=apply_engine.run_items(run_id, state, offset=offset))


# -------------------------------------------------------------- assignment --

@app.get("/sets/{set_name}/assign", response_class=HTMLResponse)
def assign_page(request: Request, set_name: str):
    depth = db.get_int("assignment_depth")
    master = db.master_of_set(set_name)
    has_tree = bool(db.scalar(
        "SELECT COUNT(*) FROM tree_nodes WHERE set_name = ? AND depth = ?",
        (set_name, depth), 0))
    if not has_tree and master and db.scalar(
            "SELECT COUNT(*) FROM files WHERE disk_id = ?", (master["id"],), 0):
        planner.rebuild_tree(set_name, depth)

    state = planner.overview(set_name, depth)
    proposals = []
    if request.query_params.get("suggest"):
        proposals = planner.suggest(set_name, depth)

    return render("assign.html", request, set_name=set_name, state=state,
                  proposals=proposals,
                  slaves={row["id"]: dict(row) for row in db.slaves_of_set(set_name)},
                  msg=request.query_params.get("msg"),
                  level=request.query_params.get("level", "info"))


@app.post("/sets/{set_name}/assign")
async def assign_save(request: Request, set_name: str):
    form = await request.form()
    changed = 0
    for key, value in form.multi_items():
        if not key.startswith("node:"):
            continue
        path = key[5:]
        disk_id = int(value) if value else None
        planner.assign(set_name, path, disk_id)
        changed += 1
    db.log_event("info", f"{changed} assignments updated", set_name, "assign")
    return flash(request, f"/sets/{set_name}/assign", "saved", "ok")


@app.post("/sets/{set_name}/assign/suggest")
def assign_apply_suggestion(request: Request, set_name: str):
    depth = db.get_int("assignment_depth")
    proposals = planner.suggest(set_name, depth)
    for path, disk_id in proposals:
        planner.assign(set_name, path, disk_id)
    db.log_event("info", f"{len(proposals)} folders assigned by proposal", set_name, "assign")
    return flash(request, f"/sets/{set_name}/assign", f"{len(proposals)} assigned", "ok")


@app.post("/sets/{set_name}/assign/split")
def toggle_split(request: Request, set_name: str, enabled: str = Form("0")):
    db.execute("UPDATE sets SET split_enabled = ? WHERE name = ?",
               (1 if enabled == "1" else 0, set_name))
    return flash(request, f"/sets/{set_name}/assign", "saved", "ok")


@app.post("/sets/{set_name}/assign/rebuild")
def rebuild_tree(request: Request, set_name: str):
    depth = db.get_int("assignment_depth")
    count = planner.rebuild_tree(set_name, depth)
    return flash(request, f"/sets/{set_name}/assign", f"{count} folders", "ok")


# -------------------------------------------------------------------- jobs --

@app.get("/api/jobs")
def api_jobs():
    return JSONResponse({
        "active": [job.as_dict() for job in manager.active()],
        "recent": [job.as_dict() for job in manager.recent(8)],
    })


@app.post("/jobs/{job_id}/{action}")
def job_action(request: Request, job_id: int, action: str):
    handlers = {"pause": manager.pause, "resume": manager.resume, "cancel": manager.cancel}
    handler = handlers.get(action)
    if handler is None:
        return flash(request, "/", "unknown action", "error")
    handler(job_id)
    return back(request)


# ------------------------------------------------------------------ events --

@app.get("/findings", response_class=HTMLResponse)
def findings_page(request: Request):
    sets = [row["name"] for row in db.all_sets()]
    chosen = request.query_params.get("set") or (sets[0] if sets else None)
    return render("findings.html", request, sets=sets, chosen=chosen,
                  findings=db.open_findings(chosen) if chosen else [],
                  msg=request.query_params.get("msg"),
                  level=request.query_params.get("level", "info"))


@app.post("/findings/clear")
def clear_findings(request: Request, set_name: str = Form(...), kind: str = Form("")):
    count = db.clear_findings(set_name, kind or None)
    db.log_event("info", f"{count} finding(s) acknowledged", set_name, "integrity")
    return flash(request, f"/findings?set={set_name}", "findings.cleared", "ok")


@app.post("/settings/notify-test")
def notify_test(request: Request):
    url = db.get_setting("notify_url").strip()
    if not url:
        return flash(request, "/settings", "notify.no_url", "error")
    ok, detail = notify.send_test(url, notify.custom_headers())
    db.log_event("info" if ok else "warning",
                 f"test notification: {detail}", None, "notify")
    return flash(request, "/settings", "notify.sent" if ok else f"{detail}",
                 "ok" if ok else "error")


@app.get("/events", response_class=HTMLResponse)
def events_page(request: Request):
    return render("events.html", request,
                  events=db.query("SELECT * FROM events ORDER BY id DESC LIMIT 300"),
                  runs=apply_engine.recent_runs(limit=25),
                  scans=db.query(
                      "SELECT s.*, d.display_name FROM scans s "
                      "JOIN disks d ON d.id = s.disk_id ORDER BY s.id DESC LIMIT 50"))


# ---------------------------------------------------------------- settings --

@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    values = {key: db.get_setting(key) for key in config.DEFAULT_SETTINGS}
    return render("settings.html", request, values=values,
                  msg=request.query_params.get("msg"),
                  level=request.query_params.get("level", "info"))


@app.post("/settings")
async def settings_save(request: Request):
    form = await request.form()
    for key in config.DEFAULT_SETTINGS:
        if key in form:
            db.set_setting(key, str(form[key]).strip())
        elif key in ("detect_renames", "verify_after_copy", "keep_mtime",
                     "integrity_check"):
            db.set_setting(key, "0")      # unchecked boxes are simply absent
    return flash(request, "/settings", "saved", "ok")


@app.post("/theme")
def set_theme(request: Request, theme: str = Form(...)):
    if theme in config.THEMES:
        db.set_setting("theme", theme)
    return back(request)


@app.post("/accent")
def set_accent(request: Request, accent: str = Form(...)):
    if accent in config.ACCENTS:
        db.set_setting("accent", accent)
    return back(request)


@app.post("/language")
def set_language(request: Request, lang: str = Form(...)):
    response = back(request)
    if lang in i18n.LANGUAGES:
        response.set_cookie("lang", lang, max_age=60 * 60 * 24 * 365, samesite="lax")
    return response


@app.get("/healthz")
def healthz():
    return {
        "ok": True,
        "backend": backend.name,
        "backend_available": backend.available(),
        "write_protected": backend.enforces_write_protection,
        "data_dir_present": os.path.isdir(config.DATA_DIR),
    }
