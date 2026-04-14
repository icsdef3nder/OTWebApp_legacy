# =============================================================================
# config.py — Application Configuration
# OT/ICS HMI Web Application — Legacy Build for Moxa UC-8220 / Debian 9
#
# Author:      [Lab Instructor]
# Date:        2026-04-14
# Description: Central configuration for Flask app, PLC connection parameters,
#              and tag definitions. Override values via environment variables
#              or a .env file in the project root.
#
#              PYTHON 3.5 COMPATIBLE — no f-strings, no walrus operator,
#              no Python 3.6+ library features.
#
# TRAINING LAB — DO NOT DEPLOY ON PRODUCTION NETWORKS
# =============================================================================

import os

# python-dotenv 0.15.0 API is identical to 1.x for basic load_dotenv() usage.
from dotenv import load_dotenv

# Load .env file if present in the project directory (overrides defaults below)
load_dotenv()

# -----------------------------------------------------------------------------
# Flask / Web Server Configuration
# -----------------------------------------------------------------------------

# Secret key for Flask session signing — insecure default for the training lab
SECRET_KEY = os.getenv("SECRET_KEY", "ot-lab-insecure-key-change-me")

# Network interface binding
# IT-side interface (eth0) — serves the web UI to the training/attacker network
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "5000"))

# Debug mode — left enabled intentionally for verbose Werkzeug error output
DEBUG = os.getenv("DEBUG", "true").lower() in ("true", "1", "yes")

# -----------------------------------------------------------------------------
# PLC / EtherNet/IP Configuration
# -----------------------------------------------------------------------------

# IP address of the Allen-Bradley Logix PLC on the OT-side network (eth1)
# Default assumes a CompactLogix or ControlLogix at 192.168.0.10
PLC_IP = os.getenv("PLC_IP", "192.168.0.10")

# Slot number of the Logix processor in the chassis (0 for CompactLogix)
PLC_SLOT = int(os.getenv("PLC_SLOT", "0"))

# Tag poll interval in seconds — how often the backend reads tags from the PLC.
# Do not set below 0.1 (100 ms) to respect PLC scan cycle constraints.
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "2.0"))

# Connection timeout in seconds for pylogix EtherNet/IP sessions
PLC_TIMEOUT = float(os.getenv("PLC_TIMEOUT", "3.0"))

# -----------------------------------------------------------------------------
# Tag Definitions
# Tags are read from the Logix controller using the CIP Read_Tag service.
# Format: { "display_name": "LogixTagName" }
# Use fully qualified names for program-scoped tags:
#   "Program:MainProgram.TagName"
# Controller-scoped tags use the bare name: "Tank_Level"
# -----------------------------------------------------------------------------

TAGS = {
    "Tank_Level":   os.getenv("TAG_TANK_LEVEL",   "Tank_Level"),
    "Pump_Speed":   os.getenv("TAG_PUMP_SPEED",   "Pump_Speed"),
    "Pressure":     os.getenv("TAG_PRESSURE",     "Pressure"),
    "Temperature":  os.getenv("TAG_TEMPERATURE",  "Temperature"),
    "Flow_Rate":    os.getenv("TAG_FLOW_RATE",     "Flow_Rate"),
    "Motor_RPM":    os.getenv("TAG_MOTOR_RPM",     "Motor_RPM"),
}

# Gauge display ranges for each tag [min, max, unit]
# Used by the frontend to scale gauge visuals correctly
TAG_RANGES = {
    "Tank_Level":  {"min": 0,    "max": 100,  "unit": "%",    "warn": 80,  "crit": 95},
    "Pump_Speed":  {"min": 0,    "max": 3600, "unit": "RPM",  "warn": 3000,"crit": 3400},
    "Pressure":    {"min": 0,    "max": 200,  "unit": "PSI",  "warn": 150, "crit": 175},
    "Temperature": {"min": -10,  "max": 150,  "unit": "°C",   "warn": 110, "crit": 130},
    "Flow_Rate":   {"min": 0,    "max": 500,  "unit": "GPM",  "warn": 400, "crit": 470},
    "Motor_RPM":   {"min": 0,    "max": 1800, "unit": "RPM",  "warn": 1600,"crit": 1750},
}

# -----------------------------------------------------------------------------
# Simulated / Fallback Values
# Used when the PLC is unreachable — provides a realistic-looking idle state
# rather than a blank dashboard. Values cycle slightly to appear "live".
# -----------------------------------------------------------------------------

FALLBACK_VALUES = {
    "Tank_Level":   42.7,
    "Pump_Speed":   1450.0,
    "Pressure":     87.3,
    "Temperature":  73.6,
    "Flow_Rate":    215.4,
    "Motor_RPM":    890.0,
}
