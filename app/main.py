"""
SwiftDeploy API Service
-----------------------
Runs in stable or canary mode via MODE env var.
Canary mode:
  - adds X-Mode: canary header to every response
  - activates the POST /chaos endpoint

Endpoints:
  GET  /        -> welcome message with mode, version, timestamp
  GET  /healthz -> liveness check with uptime in seconds
  POST /chaos   -> chaos simulation (canary only)
"""

import os
import time
import random
import threading

from flask import Flask, request, jsonify
from flask import make_response as flask_make_response

app = Flask(__name__)

# Read once at startup — MODE changes require a container restart (by design)
MODE        = os.environ.get("MODE", "stable")
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")
APP_PORT    = int(os.environ.get("APP_PORT", 3000))
START_TIME  = time.time()

# ── Chaos state: protected by a lock for thread safety ──
_chaos_lock  = threading.Lock()
_chaos_state = {"mode": None, "param": None}


def _get_chaos():
    with _chaos_lock:
        return _chaos_state["mode"], _chaos_state["param"]


def _set_chaos(mode, param):
    with _chaos_lock:
        _chaos_state["mode"]  = mode
        _chaos_state["param"] = param


def _build_response(body, status=200):
    """Build a JSON response, injecting X-Mode header in canary mode."""
    resp = flask_make_response(jsonify(body), status)
    if MODE == "canary":
        resp.headers["X-Mode"] = "canary"
    return resp


# ── Before-request: apply chaos on all routes except /healthz and /chaos ──
@app.before_request
def apply_chaos_middleware():
    if request.path in ("/healthz", "/chaos"):
        return  # chaos-exempt routes

    chaos_mode, param = _get_chaos()

    if chaos_mode == "slow":
        time.sleep(param)

    elif chaos_mode == "error":
        if random.random() < param:
            return _build_response(
                {"error": "chaos-injected error", "mode": "error", "rate": param},
                status=500
            )


# ── Routes ──

@app.route("/")
def index():
    return _build_response({
        "message":   f"SwiftDeploy API is running in {MODE} mode",
        "mode":      MODE,
        "version":   APP_VERSION,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })


@app.route("/healthz")
def healthz():
    return _build_response({
        "status": "ok",
        "mode":   MODE,
        "uptime": round(time.time() - START_TIME, 2),
    })


@app.route("/chaos", methods=["POST"])
def chaos():
    if MODE != "canary":
        return _build_response(
            {"error": "chaos endpoint only active in canary mode"},
            status=403
        )

    body       = request.get_json(silent=True) or {}
    chaos_mode = body.get("mode")

    if chaos_mode == "recover":
        _set_chaos(None, None)
        return _build_response({"status": "chaos cleared"})

    elif chaos_mode == "slow":
        duration = int(body.get("duration", 2))
        _set_chaos("slow", duration)
        return _build_response({
            "status":   "chaos active",
            "mode":     "slow",
            "duration": duration,
        })

    elif chaos_mode == "error":
        rate = float(body.get("rate", 0.5))
        _set_chaos("error", rate)
        return _build_response({
            "status": "chaos active",
            "mode":   "error",
            "rate":   rate,
        })

    else:
        return _build_response(
            {"error": "invalid chaos mode", "valid": ["slow", "error", "recover"]},
            status=400
        )


if __name__ == "__main__":
    # Dev only — production uses gunicorn (see Dockerfile CMD)
    app.run(host="0.0.0.0", port=APP_PORT, debug=False)