#!/usr/bin/env python3
# =============================================================================
# test_plc_connection.py — PLC connectivity verification script
# OT/ICS HMI Web Application (CTF/Pentest Training Lab)
# Legacy Build — Moxa UC-8220 / Debian 9 (Stretch) / Python 3.5
#
# Author:      [Lab Instructor]
# Date:        2026-04-14
# Description: Standalone test script to verify pylogix can connect to the
#              configured Logix PLC and read all configured tags.
#              Run this before starting the web app to confirm the OT network
#              path and tag names are correct.
#
#              PYTHON 3.5 COMPATIBILITY:
#                - No f-strings (f-strings require Python 3.6+).
#                  All string formatting uses str.format() or the % operator.
#                - pylogix 0.8.13 is used (0.9.x+ requires Python 3.6+).
#
# Dependencies: pylogix==0.8.13 (from requirements.txt)
#
# Usage:
#   cd /home/rocky/Documents/OTWebApp_legacy
#   source venv/bin/activate
#   python3 tests/test_plc_connection.py
# =============================================================================

import sys
import os
import time

# Allow imports from the parent directory (config.py, plc_reader.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

# Colour codes for terminal output
RED   = "\033[0;31m"
GRN   = "\033[0;32m"
YLW   = "\033[0;33m"
CYN   = "\033[0;36m"
NC    = "\033[0m"

# String-format wrappers for coloured terminal output.
# f-strings are Python 3.6+; use str.format() for Python 3.5 compatibility.
def ok(msg):   print("{0}[PASS]{1} {2}".format(GRN, NC, msg))
def fail(msg): print("{0}[FAIL]{1} {2}".format(RED, NC, msg))
def info(msg): print("{0}[INFO]{1} {2}".format(CYN, NC, msg))
def warn(msg): print("{0}[WARN]{1} {2}".format(YLW, NC, msg))


def test_plc_connection():
    """
    Attempt to open an EtherNet/IP session to the configured PLC and
    read all configured tags using pylogix.

    Tests:
      1. Import pylogix successfully
      2. Open connection to PLC_IP:44818 (EtherNet/IP default port)
      3. Read each tag in config.TAGS
      4. Verify CIP status == "Success" for each tag
      5. Verify values can be cast to float
    """
    print("")
    print("=" * 58)
    print("  OT HMI — PLC Connection Test")
    print("  Target: {0}  Slot: {1}".format(config.PLC_IP, config.PLC_SLOT))
    print("=" * 58)
    print("")

    # --- Test 1: Import pylogix ---
    info("Checking pylogix import...")
    try:
        from pylogix import PLC
        ok("pylogix imported successfully.")
    except ImportError as e:
        fail("Could not import pylogix: {0}".format(e))
        fail("Install with: pip3 install pylogix==0.8.13")
        sys.exit(1)

    # --- Test 2: Open EtherNet/IP session ---
    info("Opening EtherNet/IP session to {0} (slot {1})...".format(
        config.PLC_IP, config.PLC_SLOT))
    session_ok = False

    try:
        with PLC() as comm:
            comm.IPAddress      = config.PLC_IP
            comm.ProcessorSlot  = config.PLC_SLOT
            comm.SocketTimeout  = config.PLC_TIMEOUT  # pylogix >= 0.7.x renamed Timeout -> SocketTimeout

            # --- Test 3 & 4: Read each configured tag ---
            print("")
            info("Reading configured tags:")
            tag_names    = list(config.TAGS.values())
            display_names = list(config.TAGS.keys())

            # Issue batch CIP Read_Tag request
            t0      = time.time()
            results = comm.Read(tag_names)
            elapsed = time.time() - t0

            if not isinstance(results, list):
                results = [results]

            all_pass = True
            for display, result in zip(display_names, results):
                if result.Status == "Success":
                    # --- Test 5: Type cast ---
                    try:
                        fval = float(result.Value)
                        # Format: left-pad display name to 20 chars, right-align
                        # value to 12 chars with 2 decimal places.
                        # str.format() supports the same alignment/precision specs
                        # as f-strings — {0:<width><type>} syntax is identical.
                        ok("  {0:<20s} = {1:>12.2f}  (CIP type: {2})".format(
                            display, fval, type(result.Value).__name__))
                    except (TypeError, ValueError) as conv_err:
                        # repr() replaces the f-string !r conversion flag,
                        # which is not available via str.format() in Python 3.5.
                        warn("  {0:<20s} = {1}  (cast failed: {2})".format(
                            display, repr(result.Value), conv_err))
                        all_pass = False
                else:
                    fail("  {0:<20s}: CIP error -- {1}".format(display, result.Status))
                    all_pass = False

            print("")
            # elapsed * 1000 converts seconds to milliseconds.
            # The :.1f format spec works identically inside str.format().
            info("Batch read round-trip: {0:.1f} ms".format(elapsed * 1000))

            session_ok = True

    except Exception as exc:
        fail("Connection failed: {0}".format(exc))
        warn("Possible causes:")
        warn("  - PLC is powered off or unreachable (check eth1 routing)")
        warn("  - Firewall blocking TCP/44818 (EtherNet/IP)")
        warn("  - Wrong PLC_IP or PLC_SLOT in .env")
        warn("  - PLC firmware does not support pylogix (use v16+ Logix5000)")
        print("")
        sys.exit(1)

    # --- Summary ---
    print("")
    if session_ok and all_pass:
        ok("All tests passed. The web application should connect successfully.")
    elif session_ok:
        warn("Connection succeeded but some tags had errors.")
        warn("Check tag names in .env match the controller program exactly.")
    else:
        fail("Tests failed.")
        sys.exit(1)

    print("")


if __name__ == "__main__":
    test_plc_connection()
