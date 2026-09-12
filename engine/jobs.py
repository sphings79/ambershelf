# AmberShelf - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""One background worker, one job at a time.

USB disks share the bus, so running two scans in parallel would be slower
than running them one after the other. The queue is deliberately serial.

Every job can be paused and resumed. Progress is written to the database
after each file, so a container restart costs at most the file that was in
flight.
"""
from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from queue import Empty, Queue
from typing import Callable


@dataclass
class Job:
    id: int
    kind: str
    label: str
    set_name: str | None = None
    disk_id: int | None = None
    scan_id: int | None = None
    state: str = "queued"          # queued running paused done failed cancelled
    phase: str = ""
    message: str = ""
    error: str = ""
    files_total: int = 0
    bytes_total: int = 0
    files_done: int = 0
    bytes_done: int = 0
    current_path: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    _pause: threading.Event = field(default_factory=threading.Event, repr=False)
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    def should_continue(self) -> bool:
        """Called from inside the work. Blocks while paused."""
        while self._pause.is_set() and not self._cancel.is_set():
            self.state = "paused"
            self._pause.wait(0.25)
        if self._cancel.is_set():
            return False
        if self.state == "paused":
            self.state = "running"
        return True

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def as_dict(self) -> dict:
        percent = 0.0
        if self.bytes_total:
            percent = min(100.0, self.bytes_done * 100.0 / self.bytes_total)
        elif self.files_total:
            percent = min(100.0, self.files_done * 100.0 / self.files_total)
        return {
            "id": self.id, "kind": self.kind, "label": self.label,
            "set_name": self.set_name, "disk_id": self.disk_id, "scan_id": self.scan_id,
            "state": self.state, "phase": self.phase, "message": self.message,
            "error": self.error, "files_total": self.files_total,
            "bytes_total": self.bytes_total, "files_done": self.files_done,
            "bytes_done": self.bytes_done, "current_path": self.current_path,
            "percent": round(percent, 1),
            "started_at": self.started_at, "finished_at": self.finished_at,
        }


class JobManager:
    def __init__(self) -> None:
        self._queue: "Queue[tuple[Job, Callable[[Job], None]]]" = Queue()
        self._lock = threading.Lock()
        self._jobs: dict[int, Job] = {}
        self._order: list[int] = []
        self._next_id = 1
        self._current: Job | None = None
        self._thread = threading.Thread(target=self._run, name="ambershelf-worker", daemon=True)
        self._thread.start()

    # ------------------------------------------------------------ queueing --

    def submit(self, kind: str, label: str, work: Callable[[Job], None],
               set_name: str | None = None, disk_id: int | None = None) -> Job:
        with self._lock:
            job = Job(id=self._next_id, kind=kind, label=label,
                      set_name=set_name, disk_id=disk_id)
            self._jobs[job.id] = job
            self._order.append(job.id)
            self._next_id += 1
            # Keep the last 50 finished jobs, drop older ones.
            finished = [i for i in self._order
                        if self._jobs[i].state in ("done", "failed", "cancelled")]
            for old in finished[:-50]:
                self._jobs.pop(old, None)
                self._order.remove(old)
        self._queue.put((job, work))
        return job

    def busy_with(self, kind: str | None = None, disk_id: int | None = None) -> Job | None:
        """Is there a queued or running job matching this?"""
        with self._lock:
            for job_id in self._order:
                job = self._jobs[job_id]
                if job.state not in ("queued", "running", "paused"):
                    continue
                if kind is not None and job.kind != kind:
                    continue
                if disk_id is not None and job.disk_id != disk_id:
                    continue
                return job
        return None

    # ------------------------------------------------------------ querying --

    def get(self, job_id: int) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def current(self) -> Job | None:
        return self._current

    def active(self) -> list[Job]:
        with self._lock:
            return [self._jobs[i] for i in self._order
                    if self._jobs[i].state in ("queued", "running", "paused")]

    def recent(self, limit: int = 10) -> list[Job]:
        with self._lock:
            return [self._jobs[i] for i in reversed(self._order)][:limit]

    # ------------------------------------------------------------- control --

    def pause(self, job_id: int) -> bool:
        job = self.get(job_id)
        if job is None or job.state not in ("running", "queued"):
            return False
        job._pause.set()
        return True

    def resume(self, job_id: int) -> bool:
        job = self.get(job_id)
        if job is None:
            return False
        job._pause.clear()
        if job.state == "paused":
            job.state = "running"
        return True

    def cancel(self, job_id: int) -> bool:
        job = self.get(job_id)
        if job is None or job.state in ("done", "failed", "cancelled"):
            return False
        job._cancel.set()
        job._pause.clear()
        if job.state == "queued":
            job.state = "cancelled"
            job.finished_at = _now()
        return True

    # -------------------------------------------------------------- worker --

    def _run(self) -> None:
        while True:
            try:
                job, work = self._queue.get(timeout=1)
            except Empty:
                continue

            if job.cancelled:
                job.state = "cancelled"
                job.finished_at = _now()
                continue

            self._current = job
            job.state = "running"
            job.started_at = _now()
            try:
                work(job)
                if job.cancelled:
                    job.state = "cancelled"
                elif job.state != "failed":
                    job.state = "done"
            except Exception as exc:  # noqa: BLE001 - a failed job must not kill the worker
                job.state = "failed"
                job.error = f"{type(exc).__name__}: {exc}"
                traceback.print_exc()
            finally:
                job.finished_at = _now()
                job.current_path = ""
                self._current = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


manager = JobManager()
