"""Ollama daemon health + model selection for the desktop (Qt-free).

Single home for the unification-plan Bridge 1 wiring: startup
health-checks, best-model selection, and one-click daemon launch all
funnel through here so tabs and workers share one loopback-only
code path with :mod:`mimir.llama_intent`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from typing import Any, Optional

from mimir.llama_intent import (
    DEFAULT_LLAMA_MODEL,
    DEFAULT_LOCAL_ENDPOINT,
    get_available_local_models,
    is_ollama_available,
    select_best_local_model,
)

__all__ = [
    "OLLAMA_DOWNLOAD_URL",
    "best_model_for",
    "ensure_ollama_daemon",
    "ollama_endpoint",
    "probe_ollama",
]

#: Where to send users whose machine has no Ollama daemon.
OLLAMA_DOWNLOAD_URL = "https://ollama.com/download"


def ollama_endpoint(prefs: Any = None) -> str:
    """Effective Ollama base URL (prefs override or loopback default)."""
    if prefs is not None:
        override = (getattr(prefs, "model_endpoint", "") or "").strip()
        if override:
            return override.rstrip("/")
    return DEFAULT_LOCAL_ENDPOINT


def probe_ollama(endpoint: str = DEFAULT_LOCAL_ENDPOINT,
                 timeout_s: float = 1.0) -> dict[str, Any]:
    """Snapshot the local Ollama daemon (never raises).

    Returns ``{"available", "models", "selected", "endpoint", "error"}``.
    ``selected`` is the model the desktop would use (preferred when no
    daemon answers, so callers always have a concrete name).
    """
    endpoint = (endpoint or DEFAULT_LOCAL_ENDPOINT).rstrip("/")
    try:
        available = is_ollama_available(endpoint, timeout_s=timeout_s)
    except Exception as exc:
        return {"available": False, "models": [], "selected": DEFAULT_LLAMA_MODEL,
                "endpoint": endpoint, "error": str(exc)}
    models: list[str] = []
    selected = DEFAULT_LLAMA_MODEL
    if available:
        try:
            models = get_available_local_models(endpoint, timeout_s=timeout_s)
        except Exception:
            models = []
        try:
            selected = select_best_local_model(endpoint, DEFAULT_LLAMA_MODEL)
        except Exception:
            selected = models[0] if models else DEFAULT_LLAMA_MODEL
    return {"available": available, "models": models, "selected": selected,
            "endpoint": endpoint, "error": ""}


def best_model_for(prefs: Any = None,
                   endpoint: str = DEFAULT_LOCAL_ENDPOINT) -> str:
    """Model the desktop should use (explicit pref wins, else best local)."""
    if prefs is not None:
        explicit = (getattr(prefs, "model_name", "") or "").strip()
        if explicit:
            return explicit
    try:
        return select_best_local_model(endpoint, DEFAULT_LLAMA_MODEL)
    except Exception:
        return DEFAULT_LLAMA_MODEL


def ensure_ollama_daemon(endpoint: str = DEFAULT_LOCAL_ENDPOINT,
                         timeout_s: float = 10.0) -> tuple[bool, str]:
    """Make sure an Ollama daemon answers (ok, message).

    Fast path: returns immediately when the daemon already responds.
    Otherwise tries to launch ``ollama serve`` detached (no console
    window) and polls until it answers or the timeout expires. When no
    ``ollama`` binary exists, the message points at the download page.
    Never raises.
    """
    endpoint = (endpoint or DEFAULT_LOCAL_ENDPOINT).rstrip("/")
    try:
        if is_ollama_available(endpoint, timeout_s=1.0):
            return (True, f"Ollama is already running at {endpoint}.")
    except Exception:
        pass
    binary = shutil.which("ollama")
    if not binary:
        return (False,
                "Ollama is not installed — download it from "
                f"{OLLAMA_DOWNLOAD_URL}, then press Retry.")
    try:
        kwargs: dict[str, Any] = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        }
        if os.name == "nt":
            kwargs["creationflags"] = (
                getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            )
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen([binary, "serve"], **kwargs)  # noqa: S603
    except Exception as exc:
        return (False, f"Could not launch Ollama: {exc}")
    deadline = time.monotonic() + max(1.0, timeout_s)
    while time.monotonic() < deadline:
        try:
            if is_ollama_available(endpoint, timeout_s=0.5):
                return (True,
                        f"Ollama daemon started at {endpoint}.")
        except Exception:
            pass
        if proc.poll() is not None:
            return (False,
                    "Ollama exited during startup — run 'ollama serve' "
                    "in a terminal to see why.")
        time.sleep(0.4)
    return (False, "Ollama is still starting — press Retry in a moment.")


def _cli(argv: Optional[list[str]] = None) -> int:  # pragma: no cover
    args = list(sys.argv[1:] if argv is None else argv)
    endpoint = args[0] if args else DEFAULT_LOCAL_ENDPOINT
    report = probe_ollama(endpoint)
    if report["available"]:
        print(f"ollama live at {endpoint}: {report['selected']} "
              f"({len(report['models'])} model(s))")
        return 0
    print(f"ollama down at {endpoint}. {report['error']}")
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli())
