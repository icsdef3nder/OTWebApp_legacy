# SCADA HMI — OT Security Training Lab
## Legacy Build for Moxa UC-8220 / Debian 9 (Stretch)

```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
WARNING: THIS APPLICATION CONTAINS INTENTIONAL SECURITY VULNERABILITIES
FOR CTF / PENETRATION TESTING TRAINING PURPOSES ONLY.

DO NOT DEPLOY ON PRODUCTION NETWORKS OR EXPOSE TO UNTRUSTED USERS.
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
```

---

## Overview

This is the **legacy-compatible port** of the SCADA HMI OT Security Training Lab,
adapted to run on a **Moxa UC-8220** industrial computer running **Debian 9 (Stretch)**
with Python 3.5.

The application simulates a water-treatment process HMI dashboard that reads live
tag values from a Rockwell Allen-Bradley Logix PLC over EtherNet/IP (CIP protocol).
It contains intentional security vulnerabilities for CTF and penetration testing
training exercises.

### What is different from the modern version?

| Feature | Modern version | This legacy version |
|---|---|---|
| Python requirement | Python 3.8+ | Python 3.5+ |
| Flask | 3.0.3 | 1.1.4 |
| pylogix | 1.1.5 | 0.8.13 |
| python-dotenv | 1.0.1 | 0.15.0 |
| Jinja2 | 3.x | 2.11.3 |
| Werkzeug | 3.x | 1.0.1 |
| subprocess API | capture_output=True (Py 3.7+) | Popen + communicate() |
| String formatting | f-strings (Py 3.6+) | .format() / % formatting |
| JS fetch() | Yes | XMLHttpRequest (wider compat) |
| JS var/let/const | let/const | var (Firefox ESR 52 compat) |
| Target OS | Debian 11/12 | Debian 9 (Stretch) |
| Target hardware | General x86_64 | Moxa UC-8220 (Intel Atom x86_64) |

The **functional behaviour is identical**: same routes, same intentional
vulnerabilities, same dashboard, same tag simulation.

---

## Hardware Notes: Moxa UC-8220

- **CPU**: Intel Atom E3827 dual-core, 1.75 GHz (x86_64 architecture)
- **RAM**: 2 GB DDR3L
- **Storage**: 8 GB on-board flash + mSATA slot
- **OS pre-loaded**: Debian 9 (Stretch) — Linux kernel 4.14 LTS
- **Architecture**: x86_64 — standard Debian amd64 packages and pip binary wheels apply
- **Note**: The UC-8220 is NOT ARM. Do not use armhf/arm64 package repositories.
- **Interfaces**: 2x GbE (eth0 IT-side, eth1 OT-side), 4x COM, 4x USB

---

## Prerequisites

### Hardware / Network
- Moxa UC-8220 (or any x86_64 machine running Debian 9)
- Network access to the internet during installation (or pre-downloaded packages)
- For real PLC connectivity: eth1 reachable to an Allen-Bradley Logix PLC
- For training without hardware: set `USE_SIMULATED_PLC=true` in `.env`

### Software
- Debian 9 (Stretch) — kernel 4.x
- Python 3.5.3 (ships with Debian 9 — no manual install needed)
- pip 9.x (ships with Debian 9 via `python3-pip`)
- python3-venv (needs `apt-get install python3-venv`)
- Internet access for pip (or a local PyPI mirror)

---

## Quick Start

### 1. Copy files to the UC-8220

```bash
# Option A: SCP from a workstation
scp -r /path/to/OTWebApp_legacy root@<UC8220_IP>:/opt/OTWebApp_legacy

# Option B: USB stick
cp -r /media/usb/OTWebApp_legacy /opt/OTWebApp_legacy
```

### 2. Run the installer

```bash
cd /opt/OTWebApp_legacy
sudo bash install.sh
```

This installs system packages, creates the Python virtualenv, installs pip
dependencies, creates the `.env` file, and sets up the systemd service.

For simulated PLC mode (no physical hardware):

```bash
sudo bash install.sh --simulated
```

### 3. Configure the application

Edit `/opt/OTWebApp_legacy/.env`:

```bash
nano /opt/OTWebApp_legacy/.env
```

Key settings:

```
PLC_IP=192.168.0.10          # IP address of your Allen-Bradley Logix PLC
PLC_SLOT=0                   # Chassis slot of the Logix processor (0 for CompactLogix)
USE_SIMULATED_PLC=false      # Set true if no physical PLC available
WEB_PORT=5000                # Port the web UI listens on
```

### 4. Start the application

```bash
# Manual foreground start (useful for testing):
cd /opt/OTWebApp_legacy
./run.sh

# With simulated PLC data:
./run.sh --simulated

# As a background systemd service:
sudo systemctl start ot-hmi
sudo systemctl enable ot-hmi   # auto-start on boot
```

### 5. Access the application

Open a browser and navigate to:

```
http://<UC8220_IP>:5000/        Dashboard
http://<UC8220_IP>:5000/diag    Diagnostics (contains the vulnerable ping tool)
http://<UC8220_IP>:5000/api/tags   JSON tag data
http://<UC8220_IP>:5000/api/config JSON config dump
```

---

## Detailed Installation Steps (Manual / Step by Step)

This section walks through each installation step manually, useful if
`install.sh` fails or if you need to understand what each step does.

### Step 1: Update apt and install Python 3

Debian 9 ships Python 3.5.3. No additional Python version is needed.

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv iputils-ping net-tools
```

If `python3-venv` installs but `python3 -m venv` still fails with
"ensurepip is not available", install the virtualenv package instead:

```bash
sudo apt-get install -y python3-virtualenv
```

### Step 2: Create a Python virtual environment

```bash
cd /opt/OTWebApp_legacy

# Method A (preferred):
python3 -m venv venv

# Method B (fallback if python3-venv is missing):
virtualenv -p python3 venv

# Activate it:
source venv/bin/activate
```

You should now see `(venv)` in your shell prompt.

### Step 3: Upgrade pip within the virtualenv

Debian 9's system pip is version 9.x. Upgrading to pip 18/19 within the
virtualenv improves package resolution. **Do not upgrade pip system-wide.**

**IMPORTANT**: pip 20.0 and newer dropped Python 3.5 support. Cap the upgrade:

```bash
pip install "pip>=9.0,<=19.3.1"
```

### Step 4: Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs the pinned versions from `requirements.txt`:

```
Flask==1.1.4
Werkzeug==1.0.1
Jinja2==2.11.3
itsdangerous==1.1.0
click==7.1.2
MarkupSafe==1.1.1
pylogix==0.8.13
python-dotenv==0.15.0
```

If pip cannot find a specific version, check that your pip version is
between 9.x and 19.3.1. Older pip may not resolve dependency versions
correctly; newer pip (20+) does not support Python 3.5.

### Step 5: Configure the environment

```bash
cp .env.example .env
nano .env   # edit PLC_IP and other settings
```

### Step 6: Create logs directory

```bash
mkdir -p /opt/OTWebApp_legacy/logs
```

### Step 7: Test the application manually

```bash
source venv/bin/activate
python3 app.py
```

You should see:

```
[INFO] Starting PLC poller...
[INFO] Starting Flask application on 0.0.0.0:5000 (debug=True)
 * Running on http://0.0.0.0:5000/
```

### Step 8: Install systemd service (optional)

```bash
# Edit the unit file to update paths if needed:
nano systemd/ot-hmi.service

# Install and enable:
sudo cp systemd/ot-hmi.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ot-hmi
sudo systemctl start ot-hmi

# Check it is running:
sudo systemctl status ot-hmi
sudo journalctl -u ot-hmi -f
```

---

## PLC Connection / Tag Addressing

The application uses **pylogix 0.8.13** to communicate with Allen-Bradley
Logix PLCs over EtherNet/IP (explicit messaging, CIP Read_Tag service 0x4C).

### Supported PLC families
- ControlLogix (1756-Lxx) — any firmware 16+
- CompactLogix (1769-Lxx) — any firmware 16+
- GuardLogix (1756-LSxx)
- Micro800 series (limited support in pylogix 0.8.x)

### Tag addressing

| Tag type | Example | Notes |
|---|---|---|
| Controller-scoped | `Tank_Level` | Top-level tag in the controller scope |
| Program-scoped | `Program:MainProgram.Tank_Level` | Prefix with `Program:ProgramName.` |
| Array element | `My_Array[0]` | Zero-indexed |
| UDT member | `MyUDT.Field1` | Dot-separated path |

Tag names are configured in `.env`:

```
TAG_TANK_LEVEL=Tank_Level
TAG_PUMP_SPEED=Pump_Speed
TAG_PRESSURE=Pressure
TAG_TEMPERATURE=Temperature
TAG_FLOW_RATE=Flow_Rate
TAG_MOTOR_RPM=Motor_RPM
```

### CIP data type notes

pylogix 0.8.x automatically detects the CIP data type for each tag by
issuing a Get_Instance_Attribute_List request before reading. Supported
types include: BOOL, SINT, INT, DINT, LINT, REAL, LREAL, DWORD, STRING.

All tag values returned by the app are cast to `float` for gauge rendering.
If a tag is of type STRING or a UDT, the read will fail with a type
conversion error visible on the `/diag` page.

---

## Air-Gapped / Offline Deployment

If the UC-8220 does not have internet access:

### Python packages (offline)

On a connected machine with Python 3.5 installed:

```bash
pip download -r requirements.txt -d ./pip_packages/ \
    --platform linux_x86_64 --python-version 35 \
    --only-binary=:none:
```

Copy the `pip_packages/` directory to the UC-8220, then:

```bash
pip install --no-index --find-links=./pip_packages/ -r requirements.txt
```

### Chart.js (offline)

The dashboard loads Chart.js from a CDN (`cdn.jsdelivr.net`). This requires
internet access on the **browser** (not the UC-8220 server).

For air-gapped environments:

1. Download Chart.js from the CDN on a connected machine:
   ```
   https://cdn.jsdelivr.net/npm/chart.js@4.4.2/dist/chart.umd.min.js
   ```

2. Place it in `static/js/chart.umd.min.js` on the UC-8220.

3. In `templates/index.html`, change the `<script src=...>` line from:
   ```html
   <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.2/dist/chart.umd.min.js"></script>
   ```
   to:
   ```html
   <script src="/static/js/chart.umd.min.js"></script>
   ```

---

## Environment Variables Reference

All settings can be configured in the `.env` file or as shell environment
variables. Environment variables take precedence over the `.env` file.

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `ot-lab-insecure-key-change-me` | Flask session key |
| `DEBUG` | `true` | Enable Werkzeug debug mode (also enables debug console) |
| `WEB_HOST` | `0.0.0.0` | IP address to bind the web server to |
| `WEB_PORT` | `5000` | TCP port for the web server |
| `PLC_IP` | `192.168.0.10` | EtherNet/IP address of the Logix PLC |
| `PLC_SLOT` | `0` | Processor slot in the chassis (0 = CompactLogix) |
| `PLC_TIMEOUT` | `3.0` | Socket timeout in seconds for CIP sessions |
| `POLL_INTERVAL` | `2.0` | Seconds between tag read cycles (minimum 0.1) |
| `USE_SIMULATED_PLC` | `false` | Set `true` for demo without physical PLC |
| `TAG_TANK_LEVEL` | `Tank_Level` | Logix tag name for tank level |
| `TAG_PUMP_SPEED` | `Pump_Speed` | Logix tag name for pump speed |
| `TAG_PRESSURE` | `Pressure` | Logix tag name for pressure |
| `TAG_TEMPERATURE` | `Temperature` | Logix tag name for temperature |
| `TAG_FLOW_RATE` | `Flow_Rate` | Logix tag name for flow rate |
| `TAG_MOTOR_RPM` | `Motor_RPM` | Logix tag name for motor RPM |

---

## Application Routes

| Route | Method | Description |
|---|---|---|
| `/` | GET | Main process dashboard with live gauges |
| `/api/tags` | GET | JSON: current tag values + connection state |
| `/api/config` | GET | JSON: config dump (intentional info disclosure) |
| `/diag` | GET | Internal diagnostics page (hidden from nav) |
| `/diag/ping` | POST | Server-side ping (command injection vulnerability) |

---

## Intentional Vulnerabilities (Training Lab)

This application contains the following deliberate vulnerabilities:

1. **Command injection** — `POST /diag/ping` passes unsanitized form input
   directly to `/bin/sh` via `subprocess.Popen(shell=True)`. Any shell
   metacharacter can be injected. Example: `192.168.0.1; id`.

2. **Information disclosure** — `GET /api/config` returns the PLC IP address,
   slot, tag names, and poll interval without authentication.

3. **No authentication** — All routes are accessible without login.

4. **Werkzeug debugger** — With `DEBUG=true`, Flask shows an interactive Python
   debugger on unhandled exceptions. The PIN can be bypassed (a known CTF challenge).

5. **Hidden diagnostics page** — `/diag` is not linked from the dashboard but
   is discoverable via directory brute-force.

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'flask'"
The virtualenv is not activated. Run:
```bash
source /opt/OTWebApp_legacy/venv/bin/activate
python3 app.py
```
Or use the run.sh script which activates the venv automatically.

### "SyntaxError: invalid syntax" on startup
You are running the wrong version of Python. This app requires Python 3.5+.
Check with `python3 --version`. If you see Python 2.x, ensure you installed
`python3` from apt and are calling `python3`, not `python`.

### "Could not find a version that satisfies the requirement Flask==1.1.4"
Your pip version may be too old (pip 9.x sometimes has resolution issues).
Upgrade pip first:
```bash
pip install "pip>=18.0,<=19.3.1"
pip install -r requirements.txt
```

### "ensurepip is not available" when creating virtualenv
Install `python3-venv` from apt:
```bash
sudo apt-get install python3-venv
```
Or use `virtualenv` as a fallback:
```bash
sudo apt-get install python3-virtualenv
virtualenv -p python3 venv
```

### PLC connection errors in the dashboard
- Check `PLC_IP` in `.env` is correct and reachable from eth1.
- Verify the Logix processor slot (`PLC_SLOT=0` for CompactLogix, may differ for ControlLogix).
- Check the Logix processor is in Run or Remote Run mode.
- CIP error `0x04` usually means the tag name does not exist in the controller.
- CIP error `0x08` means the service is not supported (wrong PLC model or old firmware).
- Use `ping <PLC_IP>` from the UC-8220 to verify basic network connectivity.
- For classroom use without a physical PLC, set `USE_SIMULATED_PLC=true`.

### "Address already in use" on port 5000
Another process is using port 5000. Either stop it or change `WEB_PORT` in `.env`.
Find the process: `sudo ss -tlnp | grep 5000` (or `sudo netstat -tlnp | grep 5000`).

### Chart.js gauges do not appear (blank circles)
The browser cannot reach the Chart.js CDN (`cdn.jsdelivr.net`). Either:
- Ensure the browser machine has internet access (the UC-8220 server does not need it).
- Or follow the offline Chart.js instructions in the "Air-Gapped Deployment" section.

### systemd service fails to start
Check the journal for the error:
```bash
sudo journalctl -u ot-hmi -n 50 --no-pager
```
Common causes: wrong `WorkingDirectory` or `ExecStart` path in the unit file,
missing `.env` file, Python virtualenv not created.

---

## Architecture

```
Browser (operator workstation)
    |
    | HTTP (port 5000)
    |
[eth0 - IT network]
    |
Moxa UC-8220  ─────── app.py (Flask 1.1.4, Python 3.5)
    |                     |
    |                 plc_reader.py (PLCPoller thread)
    |                     |
[eth1 - OT network]       | EtherNet/IP (TCP port 44818)
    |                     | CIP Read_Tag service (0x4C)
    |                     |
Allen-Bradley Logix PLC (192.168.0.10)
```

- The Flask app runs as a single process with threading enabled.
- `PLCPoller` runs in a background daemon thread, polling the PLC every
  `POLL_INTERVAL` seconds using pylogix's batched CIP Read_Tag.
- Flask routes read from the in-memory cache (protected by `threading.Lock`)
  rather than issuing CIP requests directly on each HTTP request.
- The dashboard page polls `/api/tags` via XMLHttpRequest every 2 seconds.

---

## Known Differences and Limitations vs. Modern Version

1. **Flask 1.x vs 3.x**: Flask 1.1.4 uses the Werkzeug 1.x WSGI server. It is
   single-process but multi-threaded (`threaded=True`). Performance is adequate
   for training lab use (1-10 concurrent connections).

2. **pylogix 0.8.x vs 1.x**: The 0.8.x API is functionally the same for
   Read_Tag operations. The main differences are internal to pylogix (minor
   bug fixes, Micro800 improvements in 0.9+). For ControlLogix and CompactLogix
   with standard tags, 0.8.13 is fully functional.

3. **Error messages**: pylogix 0.8.x `result.Status` strings may differ
   slightly from 1.x (e.g., "Success" vs "Success" — typically the same).

4. **`datetime.utcnow()` vs `datetime.now(timezone.utc)`**: The server time
   displayed on `/diag` uses `datetime.utcnow()`. This is equivalent in
   practice but `utcnow()` is deprecated in Python 3.12+ (not relevant here).

5. **No gunicorn support**: gunicorn 22.x requires Python 3.7+. For production-
   grade deployment on Debian 9, use `waitress` (Python 3.5 compatible):
   ```bash
   pip install "waitress==1.4.4"
   waitress-serve --host=0.0.0.0 --port=5000 app:app
   ```

---

## File Structure

```
OTWebApp_legacy/
├── README_LEGACY.md          This file
├── app.py                    Flask application (Python 3.5 compatible)
├── plc_reader.py             EtherNet/IP PLC polling thread (pylogix 0.8.x)
├── config.py                 Configuration loader
├── requirements.txt          Pinned Python 3.5-compatible dependencies
├── run.sh                    Quick-start script (creates venv, installs deps)
├── install.sh                Full Debian 9 system installation script
├── .env.example              Environment variable template
├── .env                      Active configuration (create from .env.example)
├── logs/
│   └── app.log               Application log file
├── templates/
│   ├── base.html             Common HTML shell (nav, footer, clock)
│   ├── index.html            Dashboard with Chart.js gauges
│   ├── diag.html             Diagnostics page (contains vulnerable ping form)
│   ├── 404.html              Not found error page
│   └── 500.html              Internal server error page
├── static/
│   └── css/
│       └── style.css         Industrial dark theme stylesheet
└── systemd/
    └── ot-hmi.service        systemd unit file for Debian 9
```

---

## License

[Lab Instructor — placeholder]

## Author

[Lab Instructor — placeholder]
