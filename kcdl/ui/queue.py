"""Cola de descargas: lanza hasta N trabajos a la vez en hilos y lleva sus
eventos al hilo de la interfaz mediante señales de Qt."""

from __future__ import annotations

import dataclasses
import threading

from PySide6.QtCore import QObject, Signal, Slot

from ..config import Settings
from ..jobs import Job, Runner
from ..tools import ToolManager


class QueueController(QObject):
    job_added = Signal(int)
    job_changed = Signal(int)
    job_removed = Signal(int)
    log = Signal(str)
    activity = Signal(bool)          # True mientras haya algo descargando

    _event = Signal(int, str, object)    # desde los hilos de trabajo
    _finished = Signal(int)

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.jobs: list[Job] = []
        self._runners: dict[int, Runner] = {}
        self._running_queue = False
        self._event.connect(self._on_event)
        self._finished.connect(self._on_finished)

    # ── consulta
    def get(self, job_id: int) -> Job | None:
        return next((j for j in self.jobs if j.id == job_id), None)

    def active_count(self) -> int:
        return len(self._runners)

    def is_busy(self) -> bool:
        return bool(self._runners)

    def counts(self) -> dict:
        c = {"queued": 0, "running": 0, "done": 0, "error": 0, "cancelled": 0}
        for j in self.jobs:
            c[j.status] = c.get(j.status, 0) + 1
        return c

    # ── edición
    def add(self, job: Job, start: bool = False) -> None:
        self.jobs.append(job)
        self.job_added.emit(job.id)
        if start:
            self.start()

    def remove(self, job_id: int) -> None:
        if job_id in self._runners:
            self.cancel(job_id)
            return
        job = self.get(job_id)
        if job:
            self.jobs.remove(job)
            self.job_removed.emit(job_id)

    def clear_finished(self) -> None:
        for j in [j for j in self.jobs if j.status in ("done", "cancelled")]:
            self.remove(j.id)

    def retry(self, job_id: int) -> None:
        job = self.get(job_id)
        if job and job.status in ("error", "cancelled", "done"):
            job.reset()
            self.job_changed.emit(job_id)
            self.start()

    # ── ejecución
    def start(self) -> None:
        self._running_queue = True
        self._schedule()

    def cancel(self, job_id: int) -> None:
        r = self._runners.get(job_id)
        if r:
            r.cancel()
        else:
            job = self.get(job_id)
            if job and job.status == "queued":
                job.status = "cancelled"
                self.job_changed.emit(job_id)

    def cancel_all(self) -> None:
        self._running_queue = False
        for j in self.jobs:
            if j.status == "queued":
                j.status = "cancelled"
                self.job_changed.emit(j.id)
        for r in list(self._runners.values()):
            r.cancel()

    def _schedule(self) -> None:
        if not self._running_queue:
            return
        limit = max(1, self.settings.concurrent)
        for job in self.jobs:
            if len(self._runners) >= limit:
                break
            if job.status == "queued" and job.id not in self._runners:
                self._launch(job)
        if not self._runners:
            self._running_queue = False
        self.activity.emit(bool(self._runners))

    def _launch(self, job: Job) -> None:
        # Cada trabajo usa una copia de los ajustes: cambiarlos a mitad no le afecta.
        snap = dataclasses.replace(self.settings, tool_paths=dict(self.settings.tool_paths))
        tm = ToolManager(snap.tool_paths)
        jid = job.id
        runner = Runner(job, snap, tm, lambda kind, data: self._event.emit(jid, kind, data))
        self._runners[jid] = runner
        self.log.emit(f"▶ {job.url}")

        def work():
            try:
                runner.run()
            finally:
                self._finished.emit(jid)

        threading.Thread(target=work, name=f"job-{jid}", daemon=True).start()

    @Slot(int, str, object)
    def _on_event(self, job_id: int, kind: str, data: object) -> None:
        if kind == "log":
            self.log.emit(str(data))
        else:
            self.job_changed.emit(job_id)

    @Slot(int)
    def _on_finished(self, job_id: int) -> None:
        self._runners.pop(job_id, None)
        job = self.get(job_id)
        if job:
            self.job_changed.emit(job_id)
            tag = {"done": "✓", "error": "✗", "cancelled": "■"}.get(job.status, "·")
            msg = f"{tag} {job.title or job.url}"
            if job.status == "error" and job.error:
                msg += f" — {job.error}"
            self.log.emit(msg)
        self._schedule()
