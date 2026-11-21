"""Cancellable Python worker process for local information-set search."""

import atexit
import itertools
import json
import os
from pathlib import Path
import queue
import secrets
import subprocess
import sys
import threading
import weakref


_ROOT = Path(__file__).resolve().parent
_REQUEST_IDS = itertools.count(1)
_ACTIVE_TASKS = weakref.WeakSet()
_CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
WORKER_FLAG = "--ai-worker"


def _request(observation, *, iterations=700, time_limit_ms=650, seed=None):
    return {
        "version": 1, "id": next(_REQUEST_IDS), "observation": observation,
        "iterations": iterations, "time_limit_ms": time_limit_ms,
        "seed": secrets.randbits(64) if seed is None else seed,
    }


def _execute(request, cancelled=None, started=None):
    if cancelled is not None and cancelled.is_set():
        raise RuntimeError("Search cancelled")
    if getattr(sys, "frozen", False):
        command = [sys.executable, WORKER_FLAG]
    else:
        command = [sys.executable, "-X", "utf8", "-m", "ai_worker"]
    process = subprocess.Popen(
        command, cwd=_ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="strict", creationflags=_CREATION_FLAGS,
    )
    if started is not None:
        started(process)
    try:
        # One process per decision makes cancellation independent of later games.
        output, errors = process.communicate(json.dumps(request, ensure_ascii=False) + "\n", timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise RuntimeError("The Python AI did not respond within 15 seconds") from None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    if cancelled is not None and cancelled.is_set():
        raise RuntimeError("Search cancelled")
    if process.returncode:
        raise RuntimeError(f"Python AI exited with code {process.returncode}: {errors.strip()}")
    try:
        lines = output.splitlines()
        if len(lines) != 1:
            raise ValueError("Expected exactly one response")
        result = json.loads(lines[0])
        if result.get("version") != 1 or result.get("id") != request["id"]:
            raise ValueError("Mismatched response version or request ID")
        if "error" in result:
            raise RuntimeError(result["error"])
        if "action" not in result:
            raise ValueError("Missing action")
    except (ValueError, AttributeError) as exc:
        raise RuntimeError(f"Invalid Python AI response: {exc}") from exc
    return result


def search(observation, *, iterations=700, time_limit_ms=650, seed=None):
    """Blocking entry point for command-line tools and scripted tests."""
    return _execute(_request(observation, iterations=iterations,
                             time_limit_ms=time_limit_ms, seed=seed))


class SearchTask:
    """A cancellable daemon worker. It never invokes tkinter or reads Game."""

    def __init__(self, observation, *, iterations=700, time_limit_ms=650, seed=None):
        # Freeze the wire value before the thread starts.
        view = json.loads(json.dumps(observation))
        self._request = _request(view, iterations=iterations, time_limit_ms=time_limit_ms, seed=seed)
        self._cancelled = threading.Event()
        self._lock = threading.Lock()
        self._process = None
        self._result = queue.Queue(maxsize=1)
        _ACTIVE_TASKS.add(self)
        threading.Thread(target=self._run, name="bombcat-ai", daemon=True).start()

    def _started(self, process):
        with self._lock:
            self._process = process
            if self._cancelled.is_set() and process.poll() is None:
                process.terminate()

    def _run(self):
        try:
            result = _execute(self._request, self._cancelled, self._started)
            self._result.put((True, result, None))
        except Exception as exc:
            self._result.put((True, None, exc))
        finally:
            with self._lock:
                self._process = None

    def poll(self):
        try:
            return self._result.get_nowait()
        except queue.Empty:
            return False, None, None

    def cancel(self):
        self._cancelled.set()
        with self._lock:
            process = self._process
            if process is not None and process.poll() is None:
                try:
                    process.terminate()
                except OSError:
                    pass


@atexit.register
def _cancel_remaining_tasks():
    for task in list(_ACTIVE_TASKS):
        task.cancel()
