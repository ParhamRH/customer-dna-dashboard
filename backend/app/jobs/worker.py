"""Background worker process:  python -m app.jobs.worker

Runs ``BDNA_WORKER_CONCURRENCY`` threads that claim jobs from PostgreSQL. Idle threads sleep on
LISTEN bdna_jobs (woken at enqueue commit) with a poll fallback.
"""
from __future__ import annotations

import logging
import os
import signal
import socket
import threading
import time

import psycopg

from app.config import get_settings
from app.jobs.queue import NOTIFY_CHANNEL, claim, requeue_stale, run_job

log = logging.getLogger("bdna.worker")
_stop = threading.Event()


def _listen_dsn() -> str:
    return get_settings().database_system_url.replace("postgresql+psycopg://", "postgresql://")


def _loop(worker_id: str, wake: threading.Event) -> None:
    while not _stop.is_set():
        job = None
        try:
            job = claim(worker_id)
        except Exception:  # noqa: BLE001
            log.exception("claim failed")
            time.sleep(2)
        if job is None:
            wake.wait(get_settings().worker_poll_seconds * 5)
            wake.clear()
            continue
        t0 = time.perf_counter()
        status = run_job(job)
        log.info("%s %s %s in %.1fs", worker_id, job.job_type, status, time.perf_counter() - t0)


def _listener(wake: threading.Event) -> None:
    while not _stop.is_set():
        try:
            with psycopg.connect(_listen_dsn(), autocommit=True) as conn:
                conn.execute(f"LISTEN {NOTIFY_CHANNEL}")
                while not _stop.is_set():
                    for _ in conn.notifies(timeout=get_settings().worker_poll_seconds, stop_after=1):
                        wake.set()
        except Exception:  # noqa: BLE001
            log.exception("listener connection lost; retrying")
            time.sleep(3)


def _janitor() -> None:
    while not _stop.wait(60):
        try:
            n = requeue_stale()
            if n:
                log.warning("requeued %d stale jobs", n)
        except Exception:  # noqa: BLE001
            log.exception("janitor failed")


def main() -> None:
    logging.basicConfig(level=os.environ.get("BDNA_LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    from app.services.bootstrap import ensure_reference_data

    ensure_reference_data()
    s = get_settings()
    base = f"{socket.gethostname()}:{os.getpid()}"
    wake = threading.Event()
    threads = [threading.Thread(target=_listener, args=(wake,), daemon=True), threading.Thread(target=_janitor, daemon=True)]
    threads += [
        threading.Thread(target=_loop, args=(f"{base}:{i}", wake), daemon=True) for i in range(s.worker_concurrency)
    ]
    for t in threads:
        t.start()

    def _shutdown(*_):  # noqa: ANN002
        log.info("shutting down worker")
        _stop.set()
        wake.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    log.info("worker %s started with %d threads", base, s.worker_concurrency)
    while not _stop.is_set():
        time.sleep(0.5)


if __name__ == "__main__":
    main()
