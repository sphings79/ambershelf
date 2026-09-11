# AmberSync - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""Web interface.

Stage 1 and 2: register disks, mount them, index them, compare them and show
what would happen. Nothing in this file writes to a data disk - the master is
mounted read-only and the slaves are only ever read.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import compare, config, db, fsutil, helper, i18n, planner, scanner
from .jobs import manager

BASE_DIR = Path(__file__).resolve().parent

@asynccontextmanager
async def lifespan(_: FastAPI):
    db.initialise()
    refresh_registrations()
    db.log_event("info", "AmberSync started", None, "app")
    yield


app = FastAPI(title="AmberSync", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def refresh_registrations() -> None:
    """Pull the host registry into the database. The host stays the authority."""
    try:
        db.sync_disks_from_helper(helper.list_registrations())
    except helper.HelperError as exc:
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

    base = {
        "request": request,
        "t": translate,
        "msg_of": message,
        "lang": language,
        "languages": i18n.LANGUAGES,
        "helper_ok": helper.available(),
        "sets": db.all_sets(),
        "active_jobs": [job.as_dict() for job in manager.active()],
    }
    base.update(extra)
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
        status = {entry["fs_uuid"]: entry for entry in helper.mount_status(set_name)["disks"]}
    except helper.HelperError:
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
                state = helper.volume_state(disk["fs_uuid"], disk["fs_type"])
                entry["dirty"] = bool(state.get("dirty"))
            except helper.HelperError:
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
        connected = helper.list_disks()
        error = None
    except helper.HelperError as exc:
        connected, error = [], str(exc)
    return render("disks.html", request, connected=connected, error=error,
                  registered=db.query("SELECT * FROM disks ORDER BY set_name, role DESC"),
                  msg=request.query_params.get("msg"),
                  level=request.query_params.get("level", "info"))


@app.post("/disks/register")
def register_disk(request: Request, fs_uuid: str = Form(...), role: str = Form(...),
                  set_name: str = Form(...), display_name: str = Form(...)):
    try:
        helper.register(fs_uuid.strip(), role.strip(), set_name.strip(), display_name.strip())
        refresh_registrations()
        db.log_event("info", f"{display_name} registered as {role} of {set_name}",
                     set_name, "disks")
        return flash(request, "/disks", "registered", "ok")
    except helper.HelperError as exc:
        return flash(request, "/disks", str(exc), "error")


# ------------------------------------------------------------------ mounts --

@app.post("/sets/{set_name}/mount")
def mount_set(request: Request, set_name: str):
    try:
        result = helper.mount_set(set_name)
        missing = ", ".join(entry["display_name"] for entry in result["missing"])
        message = f"{len(result['mounted'])} mounted"
        if missing:
            message += f", not connected: {missing}"
        db.log_event("info", message, set_name, "mount")
        return flash(request, "/", message, "ok")
    except helper.HelperError as exc:
        db.log_event("error", str(exc), set_name, "mount")
        return flash(request, "/", str(exc), "error")


@app.post("/sets/{set_name}/umount")
def umount_set(request: Request, set_name: str):
    if manager.busy_with() is not None:
        return flash(request, "/", "a job is still running", "error")
    try:
        result = helper.umount_set(set_name)
        if result["failed"]:
            detail = "; ".join(f"{e['mountpoint']}: {e['error']}" for e in result["failed"])
            return flash(request, "/", detail, "error")
        db.log_event("info", f"{len(result['released'])} unmounted", set_name, "mount")
        return flash(request, "/", "unmounted", "ok")
    except helper.HelperError as exc:
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
    if plan and kind:
        items = compare.plan_items(plan["id"], kind, int(slave) if slave else None,
                                   offset=offset, limit=200)

    slaves = {row["id"]: dict(row) for row in db.slaves_of_set(set_name)}
    return render("plan.html", request, set_name=set_name, plan=detail, items=items,
                  kind=kind, slave=slave, offset=offset, slaves=slaves,
                  readiness=compare.readiness(set_name),
                  kinds=[compare.NEW, compare.CHANGED, compare.RENAMED,
                         compare.SLAVE_ONLY, compare.OUT_OF_SCOPE, compare.UNREADABLE],
                  msg=request.query_params.get("msg"),
                  level=request.query_params.get("level", "info"))


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

@app.get("/events", response_class=HTMLResponse)
def events_page(request: Request):
    return render("events.html", request,
                  events=db.query("SELECT * FROM events ORDER BY id DESC LIMIT 300"),
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
        elif key in ("detect_renames", "verify_after_copy"):
            db.set_setting(key, "0")      # unchecked boxes are simply absent
    return flash(request, "/settings", "saved", "ok")


@app.post("/language")
def set_language(request: Request, lang: str = Form(...)):
    response = back(request)
    if lang in i18n.LANGUAGES:
        response.set_cookie("lang", lang, max_age=60 * 60 * 24 * 365, samesite="lax")
    return response


@app.get("/healthz")
def healthz():
    return {"ok": True, "helper": helper.available(),
            "mount_root": str(config.MOUNT_ROOT),
            "mount_root_present": os.path.isdir(config.MOUNT_ROOT)}
