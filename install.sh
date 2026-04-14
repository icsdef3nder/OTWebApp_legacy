#!/usr/bin/env bash
# =============================================================================
# install.sh — System-level installation script
# OT/ICS HMI Web Application — Legacy Build for Moxa UC-8220 / Debian 9
#
# TARGET OS:  Debian 9 (Stretch), amd64 or x86_64
# TARGET HW:  Moxa UC-8220 industrial computer (Intel Atom E3827, x86_64)
#
# WHAT THIS SCRIPT DOES:
#   1.  Verifies the OS is Debian 9 (warns if not, does not abort)
#   2.  Updates the apt package index
#   3.  Installs system-level dependencies:
#         - python3, python3-pip, python3-venv (or python3-virtualenv fallback)
#         - iputils-ping (for the /diag/ping route)
#         - net-tools (ifconfig, hostname — useful for diagnostics)
#         - git (optional, for pulling updates)
#   4.  Installs the Python virtual environment and Python packages
#       from requirements.txt using pip with Python 3.5-compatible constraints
#   5.  Creates the .env file from .env.example if it does not exist
#   6.  Creates necessary runtime directories (logs/)
#   7.  Installs the systemd unit file for running the app as a service
#   8.  Prints a summary of how to start the service
#
# USAGE:
#   sudo bash install.sh
#   sudo bash install.sh --no-service   # skip systemd setup
#   sudo bash install.sh --simulated    # configure for simulated PLC
#
# NOTES:
#   - Run as root or with sudo.
#   - The app is installed in-place; this script does NOT copy files.
#     Ensure you run it from within the OTWebApp_legacy directory.
#   - The Moxa UC-8220 has an Intel Atom E3827 CPU (x86_64, not ARM).
#     Standard Debian amd64/i386 packages and pip wheels apply.
#   - If behind a corporate proxy, set https_proxy before running:
#       export https_proxy=http://proxy.example.com:3128
# =============================================================================

set -euo pipefail

# --- Colour helpers ---
RED='\033[0;31m'
GRN='\033[0;32m'
YLW='\033[0;33m'
CYN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GRN}[OK]${NC}    $*"; }
warn()  { echo -e "${YLW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()   { error "$*"; exit 1; }

# --- Resolve the directory containing this script ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Parse arguments ---
INSTALL_SERVICE=true
SIMULATED=false

for arg in "$@"; do
    case "$arg" in
        --no-service)  INSTALL_SERVICE=false ;;
        --simulated)   SIMULATED=true ;;
        --help|-h)
            echo "Usage: sudo bash install.sh [--no-service] [--simulated] [--help]"
            echo ""
            echo "  --no-service   Skip systemd service installation"
            echo "  --simulated    Configure .env to use simulated PLC data"
            echo "  --help         Show this message"
            exit 0
            ;;
        *)
            warn "Unknown argument: $arg (ignored)"
            ;;
    esac
done

# --- Banner ---
echo ""
echo -e "${CYN}============================================================${NC}"
echo -e "${CYN}  SCADA HMI — OT Security Training Lab — Install Script${NC}"
echo -e "${CYN}  Legacy Build: Moxa UC-8220 / Debian 9 (Stretch)${NC}"
echo -e "${CYN}  DO NOT DEPLOY ON PRODUCTION NETWORKS${NC}"
echo -e "${CYN}============================================================${NC}"
echo ""

# --- Must be run as root ---
if [ "$(id -u)" -ne 0 ]; then
    die "This script must be run as root: sudo bash install.sh"
fi

# =============================================================================
# Step 1: OS check
# =============================================================================
info "Step 1/8 — Checking OS..."

if [ -f /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    if [ "${ID:-}" = "debian" ] && [ "${VERSION_ID:-}" = "9" ]; then
        ok "Detected Debian 9 (Stretch) — fully supported."
    else
        warn "This system is: ${PRETTY_NAME:-unknown}"
        warn "This script is designed for Debian 9 (Stretch)."
        warn "Continuing anyway — package names may differ on other distributions."
    fi
else
    warn "/etc/os-release not found — cannot verify OS. Proceeding."
fi

# =============================================================================
# Step 2: Update apt package index
# =============================================================================
info "Step 2/8 — Updating apt package index..."
apt-get update -qq
ok "apt index updated."

# =============================================================================
# Step 3: Install system packages
# =============================================================================
info "Step 3/8 — Installing system packages..."

# Core Python packages for Debian 9
#   python3        — Python 3.5.3 on Debian 9 Stretch
#   python3-pip    — pip package manager (pip 9.x on Debian 9)
#   python3-venv   — venv module for creating virtual environments
#                    (separate package on Debian 9; not bundled with python3)
PACKAGES="python3 python3-pip python3-venv iputils-ping net-tools"

apt-get install -y --no-install-recommends $PACKAGES

# Verify python3-venv installed correctly; fall back to python3-virtualenv
if ! python3 -m venv --help &>/dev/null; then
    warn "python3-venv may not be working. Trying python3-virtualenv fallback..."
    apt-get install -y --no-install-recommends python3-virtualenv
    ok "python3-virtualenv installed as fallback."
fi

ok "System packages installed: $PACKAGES"

# =============================================================================
# Step 4: Create Python virtualenv
# =============================================================================
info "Step 4/8 — Creating Python virtual environment..."

VENV_DIR="$SCRIPT_DIR/venv"

if [ -d "$VENV_DIR" ]; then
    warn "Virtual environment already exists at $VENV_DIR — skipping creation."
else
    if python3 -m venv "$VENV_DIR"; then
        ok "Virtualenv created at $VENV_DIR"
    else
        warn "python3 -m venv failed — falling back to virtualenv..."
        if command -v virtualenv &>/dev/null; then
            virtualenv -p python3 "$VENV_DIR"
            ok "Virtualenv created with virtualenv at $VENV_DIR"
        else
            die "Cannot create virtual environment. Install python3-venv or python3-virtualenv."
        fi
    fi
fi

# --- Patch venv/bin/activate for strict-shell compatibility ---
# Python 3.5 (Debian 9) generates an activate script that references
# $_OLD_VIRTUAL_PATH, $_OLD_VIRTUAL_PYTHONHOME, $_OLD_VIRTUAL_PS1, and $PS1
# without the ${VAR:-} default-value guard.  When this script is sourced
# inside a shell that already has 'set -u' active (nounset), bash treats any
# reference to an unset variable as a fatal error — hence:
#   line 6: _OLD_VIRTUAL_PATH: unbound variable
# The fix: rewrite all bare references to the safe ${VAR:-} form before
# sourcing the activate script. This is idempotent — running it on an
# already-patched (or modern) script is safe because sed simply finds
# nothing to replace.
patch_activate() {
    local activate_script="$1"
    if [ ! -f "$activate_script" ]; then
        warn "activate script not found at $activate_script — skipping patch."
        return 0
    fi
    # Replace bare $VAR with ${VAR:-} for variables that may be unset when
    # the activate script is first sourced in a non-interactive / strict shell:
    #   $_OLD_VIRTUAL_PATH       — not yet set on first activation
    #   $_OLD_VIRTUAL_PYTHONHOME — not yet set on first activation
    #   $_OLD_VIRTUAL_PS1        — not yet set on first activation
    #   $PS1                     — not set in non-interactive shells (systemd, etc.)
    #   $1                       — bare positional inside deactivate() in older templates
    # Word-boundary anchors prevent double-patching ${VAR:-} that is already correct.
    sed -i \
        -e 's/"\$_OLD_VIRTUAL_PATH"/"\${_OLD_VIRTUAL_PATH:-}"/g' \
        -e 's/"\$_OLD_VIRTUAL_PYTHONHOME"/"\${_OLD_VIRTUAL_PYTHONHOME:-}"/g' \
        -e 's/"\$_OLD_VIRTUAL_PS1"/"\${_OLD_VIRTUAL_PS1:-}"/g' \
        -e 's/"\$PS1"/"\${PS1:-}"/g' \
        -e 's/\$PS1"/\${PS1:-}"/g' \
        -e 's/" \$1 "/" \${1:-} "/g' \
        -e 's/"\$VIRTUAL_ENV_DISABLE_PROMPT"/"\${VIRTUAL_ENV_DISABLE_PROMPT:-}"/g' \
        "$activate_script"
    ok "activate script patched for set -u compatibility."
}

# Apply the patch regardless of whether the venv was just created or already
# existed — an existing venv on the Moxa device may still have the old script.
patch_activate "$VENV_DIR/bin/activate"

# Activate the virtualenv for the remaining steps
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"
ok "Virtualenv activated."

# =============================================================================
# Step 5: Upgrade pip and install Python dependencies
# =============================================================================
info "Step 5/8 — Installing Python dependencies..."

# Upgrade pip within the virtualenv.
# pip 9.x (Debian 9 default) has trouble with some wheel formats.
# We upgrade to pip 19.3.1 which is the last pip release with Python 3.5 support.
# pip 20.0+ dropped Python 3.5 support.
"$VENV_DIR/bin/pip" install --quiet "pip>=9.0,<=19.3.1" \
    || warn "pip upgrade failed — proceeding with existing pip version."

# Install application dependencies pinned to Python 3.5 compatible versions
"$VENV_DIR/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"
ok "Python dependencies installed."

# Verify key packages installed correctly
"$VENV_DIR/bin/python3" -c "import flask; print('  Flask:', flask.__version__)"
"$VENV_DIR/bin/python3" -c "import pylogix; print('  pylogix: installed')"
"$VENV_DIR/bin/python3" -c "import dotenv; print('  python-dotenv: installed')"

# =============================================================================
# Step 6: Create .env configuration file
# =============================================================================
info "Step 6/8 — Setting up configuration..."

ENV_FILE="$SCRIPT_DIR/.env"
ENV_EXAMPLE="$SCRIPT_DIR/.env.example"

if [ ! -f "$ENV_FILE" ]; then
    if [ -f "$ENV_EXAMPLE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        ok "Created $ENV_FILE from .env.example"
    else
        warn ".env.example not found — creating minimal .env"
        cat > "$ENV_FILE" <<'ENVEOF'
SECRET_KEY=change-me-in-production
DEBUG=true
WEB_HOST=0.0.0.0
WEB_PORT=5000
PLC_IP=192.168.0.10
PLC_SLOT=0
PLC_TIMEOUT=3.0
POLL_INTERVAL=2.0
USE_SIMULATED_PLC=false
ENVEOF
        ok "Created minimal $ENV_FILE"
    fi
else
    info "Using existing $ENV_FILE"
fi

# If --simulated flag was passed, set USE_SIMULATED_PLC=true in .env
if [ "$SIMULATED" = true ]; then
    # Use sed to replace or append USE_SIMULATED_PLC
    if grep -q "^USE_SIMULATED_PLC=" "$ENV_FILE"; then
        sed -i 's/^USE_SIMULATED_PLC=.*/USE_SIMULATED_PLC=true/' "$ENV_FILE"
    else
        echo "USE_SIMULATED_PLC=true" >> "$ENV_FILE"
    fi
    ok "USE_SIMULATED_PLC=true set in $ENV_FILE"
fi

# =============================================================================
# Step 7: Create runtime directories
# =============================================================================
info "Step 7/8 — Creating runtime directories..."

mkdir -p "$SCRIPT_DIR/logs"
ok "Log directory: $SCRIPT_DIR/logs"

# =============================================================================
# Step 8: Install systemd service (optional)
# =============================================================================
if [ "$INSTALL_SERVICE" = true ]; then
    info "Step 8/8 — Installing systemd service..."

    SERVICE_SRC="$SCRIPT_DIR/systemd/ot-hmi.service"
    SERVICE_DST="/etc/systemd/system/ot-hmi.service"

    if [ ! -f "$SERVICE_SRC" ]; then
        warn "systemd/ot-hmi.service not found — generating it now..."
        mkdir -p "$SCRIPT_DIR/systemd"

        # Determine the user who owns the script dir (not root)
        # Fall back to creating the service running as root if no non-root owner found
        SERVICE_USER=$(stat -c '%U' "$SCRIPT_DIR" 2>/dev/null || echo "root")
        if [ "$SERVICE_USER" = "root" ]; then
            SERVICE_USER="root"
            warn "Service will run as root. Consider creating a dedicated user."
        fi

        cat > "$SERVICE_SRC" <<SVCEOF
[Unit]
Description=SCADA HMI OT Security Training Lab (Legacy / Debian 9)
After=network.target
Wants=network.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${SCRIPT_DIR}
ExecStart=${VENV_DIR}/bin/python3 ${SCRIPT_DIR}/app.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=ot-hmi-legacy
EnvironmentFile=${SCRIPT_DIR}/.env

[Install]
WantedBy=multi-user.target
SVCEOF
        ok "Generated $SERVICE_SRC"
    fi

    # Copy unit file to systemd directory
    cp "$SERVICE_SRC" "$SERVICE_DST"
    systemctl daemon-reload
    ok "Systemd service installed: $SERVICE_DST"
    ok "Enable on boot:  sudo systemctl enable ot-hmi"
    ok "Start now:       sudo systemctl start ot-hmi"
    ok "Check status:    sudo systemctl status ot-hmi"
    ok "View logs:       sudo journalctl -u ot-hmi -f"
else
    info "Step 8/8 — Skipping systemd service (--no-service)."
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
echo -e "${GRN}============================================================${NC}"
echo -e "${GRN}  Installation complete!${NC}"
echo -e "${GRN}============================================================${NC}"
echo ""
echo -e "  App directory:  ${SCRIPT_DIR}"
echo -e "  Python venv:    ${VENV_DIR}"
echo -e "  Config file:    ${ENV_FILE}"
echo -e "  Log directory:  ${SCRIPT_DIR}/logs"
echo ""
echo -e "${CYN}--- To start the application ---${NC}"
echo -e "  Foreground:    cd ${SCRIPT_DIR} && ./run.sh"
echo -e "  Simulated PLC: cd ${SCRIPT_DIR} && ./run.sh --simulated"
if [ "$INSTALL_SERVICE" = true ]; then
echo -e "  As a service:  sudo systemctl start ot-hmi"
fi
echo ""
echo -e "${YLW}  IMPORTANT: Edit ${ENV_FILE} to set PLC_IP before starting.${NC}"
echo ""
