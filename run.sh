#!/usr/bin/env bash
# =============================================================================
# run.sh — Application startup script
# OT/ICS HMI Web Application — Legacy Build for Moxa UC-8220 / Debian 9
#
# Usage:
#   ./run.sh                    # foreground, logs to stdout
#   ./run.sh --simulated        # start with simulated PLC data (no hardware)
#   ./run.sh --help             # show usage
#
# The script:
#   1. Checks for Python 3 and pip3
#   2. Creates/activates a virtualenv in ./venv using python3 -m venv
#   3. Installs/upgrades pip to a version compatible with Python 3.5
#   4. Installs dependencies from requirements.txt
#   5. Copies .env.example -> .env if no .env exists
#   6. Creates the logs/ directory
#   7. Starts the Flask application
#
# DEBIAN 9 NOTE:
#   python3 -m venv is available on Debian 9 via the python3-venv package.
#   If you see "ensurepip is not available", run:
#     sudo apt-get install python3-venv
#   or use virtualenv directly:
#     sudo apt-get install python3-virtualenv
#     virtualenv -p python3 venv
# =============================================================================

set -euo pipefail

# --- Resolve script directory (works even when called from another path) ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- Colour output helpers ---
RED='\033[0;31m'
GRN='\033[0;32m'
YLW='\033[0;33m'
CYN='\033[0;36m'
NC='\033[0m'  # No Colour

info()  { echo -e "${CYN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GRN}[OK]${NC}    $*"; }
warn()  { echo -e "${YLW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# --- Banner ---
echo ""
echo -e "${CYN}=================================================${NC}"
echo -e "${CYN}  SCADA HMI — OT Security Training Lab${NC}"
echo -e "${CYN}  Legacy Build — Moxa UC-8220 / Debian 9${NC}"
echo -e "${CYN}  DO NOT DEPLOY ON PRODUCTION NETWORKS${NC}"
echo -e "${CYN}=================================================${NC}"
echo ""

# --- Argument parsing ---
SIMULATED=false
for arg in "$@"; do
    case "$arg" in
        --simulated) SIMULATED=true ;;
        --help|-h)
            echo "Usage: $0 [--simulated] [--help]"
            echo ""
            echo "  --simulated   Use simulated PLC data (no physical PLC required)"
            echo "  --help        Show this message"
            exit 0
            ;;
        *)
            warn "Unknown argument: $arg"
            ;;
    esac
done

# --- Check Python 3 ---
if ! command -v python3 &>/dev/null; then
    error "python3 not found."
    error "On Debian 9 run: sudo apt-get install python3 python3-pip python3-venv"
    exit 1
fi
PYTHON_VER=$(python3 --version)
ok "Found $PYTHON_VER"

# --- Check minimum Python version (3.5 required) ---
PYTHON_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
if [ "$PYTHON_MINOR" -lt 5 ]; then
    error "Python 3.5+ is required. Found Python 3.$PYTHON_MINOR."
    exit 1
fi

# --- Patch venv/bin/activate for strict-shell compatibility ---
# Python 3.5 (Debian 9) generates an activate script that references
# $_OLD_VIRTUAL_PATH, $_OLD_VIRTUAL_PYTHONHOME, $_OLD_VIRTUAL_PS1, and $PS1
# without the ${VAR:-} default-value guard.  When this script is sourced
# inside a shell that already has 'set -u' active (nounset), bash treats any
# reference to an unset variable as a fatal error — hence:
#   line 6: _OLD_VIRTUAL_PATH: unbound variable
# The fix: rewrite all bare references in the activate script to the safe
# ${VAR:-} form immediately after venv creation and before sourcing it.
# This function is idempotent — running it on an already-patched script is safe.
patch_activate() {
    local activate_script="$1"
    if [ ! -f "$activate_script" ]; then
        warn "activate script not found at $activate_script — skipping patch."
        return 0
    fi
    # Replace bare $VAR with ${VAR:-} for the four variables that may be unset
    # when the activate script is first sourced:
    #   $_OLD_VIRTUAL_PATH       — not yet set on first activation
    #   $_OLD_VIRTUAL_PYTHONHOME — not yet set on first activation
    #   $_OLD_VIRTUAL_PS1        — not yet set on first activation
    #   $PS1                     — not set in non-interactive shells (e.g. systemd)
    #   $1                       — bare positional inside deactivate() in older templates
    # We use word-boundary anchors to avoid double-patching ${VAR:-} references.
    # NOTE: "$ZSH_VERSION" must be listed explicitly — the Python 3.5 venv activate
    # template emits  PS1="$ZSH_VERSION"  (bare, unquoted-expand form) on line ~20
    # of the generated script.  Under set -u this is fatal when ZSH_VERSION is unset
    # (which it always is in bash).  The ${ZSH_VERSION:-} form expands to an empty
    # string when the variable is unset, which is the correct behaviour.
    sed -i \
        -e 's/"\$_OLD_VIRTUAL_PATH"/"\${_OLD_VIRTUAL_PATH:-}"/g' \
        -e 's/"\$_OLD_VIRTUAL_PYTHONHOME"/"\${_OLD_VIRTUAL_PYTHONHOME:-}"/g' \
        -e 's/"\$_OLD_VIRTUAL_PS1"/"\${_OLD_VIRTUAL_PS1:-}"/g' \
        -e 's/"\$PS1"/"\${PS1:-}"/g' \
        -e 's/\$PS1"/\${PS1:-}"/g' \
        -e 's/" \$1 "/" \${1:-} "/g' \
        -e 's/"\$VIRTUAL_ENV_DISABLE_PROMPT"/"\${VIRTUAL_ENV_DISABLE_PROMPT:-}"/g' \
        -e 's/"\$ZSH_VERSION"/"\${ZSH_VERSION:-}"/g' \
        "$activate_script"
    ok "activate script patched for set -u compatibility."
}

# --- Create virtualenv if not present ---
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    info "Creating Python virtual environment in ./venv ..."
    # Prefer python3 -m venv (requires python3-venv package on Debian 9)
    if python3 -m venv "$SCRIPT_DIR/venv" 2>/dev/null; then
        ok "Virtualenv created with python3 -m venv."
    else
        warn "python3 -m venv failed. Trying virtualenv fallback..."
        if command -v virtualenv &>/dev/null; then
            virtualenv -p python3 "$SCRIPT_DIR/venv"
            ok "Virtualenv created with virtualenv."
        else
            error "Neither python3-venv nor virtualenv is available."
            error "Install with: sudo apt-get install python3-venv"
            exit 1
        fi
    fi
else
    info "Using existing virtualenv at ./venv"
fi

# Patch the activate script regardless of whether the venv was just created or
# already existed — the Moxa device may have an existing venv with the old
# unguarded script, and patching an already-correct script is harmless.
patch_activate "$SCRIPT_DIR/venv/bin/activate"

# --- Activate virtualenv ---
# shellcheck disable=SC1091
source "$SCRIPT_DIR/venv/bin/activate"
ok "Virtualenv activated."

# --- Upgrade pip to a version that can handle pinned requirements ---
# pip 9.x (Debian 9 default) works but upgrading to pip 18.x or 19.x
# improves dependency resolution. We cap at 19.3.1 which is the last
# version with Python 3.5 support (pip 20+ requires Python 3.6+).
info "Upgrading pip (capping at 19.3.1 for Python 3.5 compatibility)..."
pip install --quiet "pip>=9.0,<=19.3.1" || warn "pip upgrade failed — continuing with existing pip."

# --- Install dependencies ---
info "Installing dependencies from requirements.txt ..."
# Use --no-build-isolation for older pip versions that may not support it
pip install --quiet -r "$SCRIPT_DIR/requirements.txt"
ok "Dependencies installed."

# --- Create .env from example if missing ---
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    warn ".env not found — copying from .env.example"
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    warn "Review and edit .env before use (especially PLC_IP)"
else
    info "Using existing .env configuration."
fi

# --- Create logs directory ---
mkdir -p "$SCRIPT_DIR/logs"
ok "Log directory ready at ./logs/"

# --- Print configuration summary ---
echo ""
echo -e "${CYN}--- Configuration ---${NC}"
# Source .env manually just for display (dotenv will load it inside Flask too)
set -a
# shellcheck disable=SC1091
source "$SCRIPT_DIR/.env" 2>/dev/null || true
set +a

# --- Override USE_SIMULATED_PLC if --simulated flag passed ---
# Must happen AFTER sourcing .env, otherwise source overwrites the export
if [ "$SIMULATED" = true ]; then
    export USE_SIMULATED_PLC=true
    warn "Simulated PLC mode enabled — no physical PLC required."
fi
echo -e "  PLC IP:    ${PLC_IP:-192.168.0.10}"
echo -e "  Web Host:  ${WEB_HOST:-0.0.0.0}"
echo -e "  Web Port:  ${WEB_PORT:-5000}"
echo -e "  Simulated: ${USE_SIMULATED_PLC:-false}"
echo -e "  Debug:     ${DEBUG:-true}"
echo ""
echo -e "${CYN}--- Access URLs ---${NC}"
echo -e "  Dashboard:   http://$(hostname -I | awk '{print $1}'):${WEB_PORT:-5000}/"
echo -e "  Diagnostics: http://$(hostname -I | awk '{print $1}'):${WEB_PORT:-5000}/diag"
echo -e "  Tag API:     http://$(hostname -I | awk '{print $1}'):${WEB_PORT:-5000}/api/tags"
echo ""

# --- Start Flask application ---
info "Starting Flask application (Python 3.5 legacy build)..."
exec python3 "$SCRIPT_DIR/app.py"
