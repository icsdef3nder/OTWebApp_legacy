#!/usr/bin/env python3
# =============================================================================
# plc_reader.py — EtherNet/IP PLC Communication Layer
# OT/ICS HMI Web Application — Legacy Build for Moxa UC-8220 / Debian 9
#
# Author:      [Lab Instructor]
# Date:        2026-04-14
# Description: Handles all communication with the Allen-Bradley Logix PLC
#              using pylogix. Implements a background polling thread that reads
#              configured tags via CIP Read_Tag service over EtherNet/IP.
#
#              Uses a thread-safe cache so the Flask web layer never blocks
#              waiting on PLC I/O. Gracefully handles connection failures with
#              exponential backoff and falls back to last known / default values.
#
# PYTHON 3.5 COMPATIBILITY CHANGES vs. modern version:
#   - No f-strings; use .format() or "%" string formatting throughout.
#   - typing.Dict/Any/Optional are imported from the 'typing' module which
#     exists in Python 3.5; usage is identical.
#   - datetime.utcnow() used instead of datetime.now(timezone.utc) for
#     clarity, though both work in Python 3.5.
#
# Dependencies: pylogix 0.8.13
# Protocol:     EtherNet/IP (explicit messaging, CIP Read_Tag service 0x4C)
# =============================================================================

import os
import threading
import time
import logging
import random
import math
from datetime import datetime
from typing import Dict, Any, Optional

from pylogix import PLC

import config

# Configure module-level logger — output goes to the Flask app logger
logger = logging.getLogger(__name__)


# =============================================================================
# PLCPoller — Background tag polling thread
# =============================================================================

class PLCPoller(object):
    """
    Spawns a daemon thread that continuously reads Logix tags over EtherNet/IP
    using pylogix and caches the results.

    The Flask request handlers read from the cache (self.tag_cache) rather
    than issuing CIP requests directly, ensuring sub-millisecond response
    times on the web layer regardless of PLC round-trip latency.

    CIP Path:    backplane port 1, slot from config.PLC_SLOT
    CIP Service: Read_Tag (0x4C) for each tag in config.TAGS
    """

    def __init__(self):
        # ------------------------------------------------------------------
        # Tag value cache — maps display name -> current float value.
        # Initialised with fallback values so the UI is never blank on startup.
        # ------------------------------------------------------------------
        self.tag_cache = dict(config.FALLBACK_VALUES)  # type: Dict[str, float]

        # ------------------------------------------------------------------
        # Connection state tracking
        # ------------------------------------------------------------------
        self.connected = False                 # type: bool
        self.last_poll_time = None             # type: Optional[datetime]
        self.last_error = None                 # type: Optional[str]
        self.consecutive_failures = 0          # type: int

        # ------------------------------------------------------------------
        # Per-tag error tracking — records last error message per tag name.
        # Displayed on the /diag diagnostics page.
        # ------------------------------------------------------------------
        self.tag_errors = {}                   # type: Dict[str, str]

        # Thread lock — protects all cache reads/writes across threads.
        self._lock = threading.Lock()

        # Background polling thread (daemon=True so it exits with the main process).
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="PLCPoller"
        )
        self._thread.daemon = True  # Python 3.5 compatible daemon assignment

    def start(self):
        """Start the background polling thread."""
        logger.info(
            "Starting PLC poller — target: %s slot %d, interval: %.1fs",
            config.PLC_IP, config.PLC_SLOT, config.POLL_INTERVAL
        )
        self._thread.start()

    # ------------------------------------------------------------------
    # Public read API — called by Flask routes
    # ------------------------------------------------------------------

    def get_tag_values(self):
        # type: () -> Dict[str, Any]
        """
        Return a snapshot of all cached tag values, plus connection metadata.

        Returns:
            dict: {
                "values":     {tag_name: float, ...},
                "connected":  bool,
                "last_poll":  ISO timestamp string or None,
                "last_error": str or None,
                "tag_errors": {tag_name: error_str, ...}
            }
        """
        with self._lock:
            return {
                "values":     dict(self.tag_cache),
                "connected":  self.connected,
                "last_poll":  (
                    self.last_poll_time.isoformat() if self.last_poll_time else None
                ),
                "last_error": self.last_error,
                "tag_errors": dict(self.tag_errors),
            }

    # ------------------------------------------------------------------
    # Internal polling loop — runs in background thread
    # ------------------------------------------------------------------

    def _poll_loop(self):
        """
        Main polling loop. Runs forever in the background daemon thread.

        Implements exponential backoff on connection failure:
          - First failure:              retry in POLL_INTERVAL seconds
          - Each subsequent failure:    double the wait (capped at 30 seconds)

        This prevents flooding the PLC with reconnection attempts when the
        OT network is down or the PLC is in a faulted state.
        """
        backoff = config.POLL_INTERVAL  # Current inter-attempt wait time

        while True:
            try:
                self._poll_once()
                # Successful poll — reset backoff to normal interval
                backoff = config.POLL_INTERVAL
                self.consecutive_failures = 0
                time.sleep(config.POLL_INTERVAL)

            except Exception as exc:
                # Unexpected exception outside normal pylogix error handling
                self.consecutive_failures += 1
                err_msg = "Poller thread exception: {0}".format(exc)
                logger.exception(err_msg)

                with self._lock:
                    self.connected = False
                    self.last_error = err_msg

                # Exponential backoff, capped at 30 seconds
                backoff = min(backoff * 2, 30.0)
                logger.warning(
                    "Retrying PLC connection in %.1f seconds (failure #%d)",
                    backoff, self.consecutive_failures
                )
                time.sleep(backoff)

    def _poll_once(self):
        """
        Perform a single poll cycle: open a pylogix EtherNet/IP session,
        issue CIP Read_Tag requests for all configured tags, update the cache.

        pylogix 0.8.x uses Unconnected explicit messaging for each read batch.
        The CIP path to the PLC is constructed from config.PLC_IP and
        config.PLC_SLOT (e.g., backplane port 1, slot 0 for CompactLogix).

        pylogix 0.8.x Read() batches multiple tags in a single
        CIP Multiple_Service_Packet (service 0x0A) when feasible, reducing
        EtherNet/IP round trips.

        Raises:
            Exception: Propagated to _poll_loop for backoff handling.
        """
        new_values = {}      # type: Dict[str, float]
        new_tag_errors = {}  # type: Dict[str, str]

        # Capture poll timestamp before the network call
        poll_time = datetime.utcnow()

        # Open an EtherNet/IP session to the Logix controller.
        # pylogix manages CIP ForwardOpen / ForwardClose internally.
        with PLC() as comm:
            comm.IPAddress = config.PLC_IP
            comm.ProcessorSlot = config.PLC_SLOT
            comm.SocketTimeout = config.PLC_TIMEOUT

            # Build the list of Logix tag names to read in a single batch.
            # config.TAGS maps display_name -> logix_tag_name.
            tag_names = list(config.TAGS.values())

            logger.debug("Issuing CIP Read_Tag for tags: %s", tag_names)

            # comm.Read() accepts a list and returns a list of Response objects.
            # Each Response has .TagName, .Value, and .Status attributes.
            results = comm.Read(tag_names)

            # pylogix 0.8.x returns a single Response for one tag, list for many.
            # Normalise to a list for consistent iteration.
            if not isinstance(results, list):
                results = [results]

            # Map results back to their display names using parallel index
            display_names = list(config.TAGS.keys())

            for display_name, result in zip(display_names, results):
                if result.Status == "Success":
                    # Cast tag value to float for consistent gauge rendering.
                    # Logix types REAL, DINT, INT, SINT all coerce cleanly.
                    try:
                        new_values[display_name] = float(result.Value)
                        logger.debug(
                            "Tag %s = %s (%s)",
                            display_name,
                            result.Value,
                            type(result.Value).__name__
                        )
                    except (TypeError, ValueError) as conv_err:
                        # CIP returned a value that cannot be cast to float.
                        # Example: STRING tag used by mistake — CIP type 0xD0.
                        err = "Type conversion failed: {0}".format(conv_err)
                        new_tag_errors[display_name] = err
                        logger.warning("Tag %s: %s", display_name, err)
                        # Retain previous cached value rather than showing zero
                        new_values[display_name] = self.tag_cache.get(display_name, 0.0)
                else:
                    # CIP error — e.g., tag not found (0x04), access denied (0x08)
                    err = "CIP error: {0}".format(result.Status)
                    new_tag_errors[display_name] = err
                    logger.warning("Tag %s read failed: %s", display_name, err)
                    # Retain previous cached value rather than displaying zero
                    new_values[display_name] = self.tag_cache.get(display_name, 0.0)

        # Update shared cache atomically under the thread lock
        with self._lock:
            self.tag_cache.update(new_values)
            self.tag_errors = new_tag_errors
            self.connected = True
            self.last_poll_time = poll_time
            self.last_error = None

        logger.debug(
            "Poll cycle complete. %d tags read, %d errors",
            len(new_values), len(new_tag_errors)
        )


# =============================================================================
# SimulatedPLCPoller — drop-in replacement when no physical PLC is available
# =============================================================================

class SimulatedPLCPoller(object):
    """
    Drop-in replacement for PLCPoller that generates realistic-looking
    simulated tag values without requiring a physical PLC connection.

    Activated automatically when USE_SIMULATED_PLC=true in the environment,
    or can be explicitly instantiated in tests.

    Values oscillate sinusoidally with small random noise to appear live
    on the dashboard gauges — each tag has a unique phase and period.
    """

    def __init__(self):
        self.tag_cache = dict(config.FALLBACK_VALUES)  # type: Dict[str, float]
        self.connected = True              # Simulated poller is always "connected"
        self.last_poll_time = None         # type: Optional[datetime]
        self.last_error = None             # type: Optional[str]
        self.tag_errors = {}               # type: Dict[str, str]
        self.consecutive_failures = 0      # type: int
        self._lock = threading.Lock()
        self._t0 = time.time()             # Phase reference for oscillation

        self._thread = threading.Thread(
            target=self._sim_loop,
            name="SimulatedPLCPoller"
        )
        self._thread.daemon = True         # Python 3.5 compatible daemon flag

    def start(self):
        """Start the simulation loop thread."""
        logger.info("Starting SIMULATED PLC poller (no physical PLC required)")
        self._thread.start()

    def get_tag_values(self):
        # type: () -> Dict[str, Any]
        """Return cached simulated tag values and connection metadata."""
        with self._lock:
            return {
                "values":     dict(self.tag_cache),
                "connected":  self.connected,
                "last_poll":  (
                    self.last_poll_time.isoformat() if self.last_poll_time else None
                ),
                "last_error": self.last_error,
                "tag_errors": dict(self.tag_errors),
            }

    def _sim_loop(self):
        """
        Generate sinusoidal + noise tag values at POLL_INTERVAL rate.

        Each tag has a unique oscillation period (seconds) and amplitude
        so they do not move in lockstep (which would look artificial).
        """
        # Simulation parameters per tag: centre value, amplitude, period (seconds)
        sim_params = {
            "Tank_Level":  {"center": 42.7,  "amp": 8.0,   "period": 45},
            "Pump_Speed":  {"center": 1450,  "amp": 120,   "period": 30},
            "Pressure":    {"center": 87.3,  "amp": 12.0,  "period": 20},
            "Temperature": {"center": 73.6,  "amp": 5.0,   "period": 60},
            "Flow_Rate":   {"center": 215.4, "amp": 30.0,  "period": 25},
            "Motor_RPM":   {"center": 890.0, "amp": 50.0,  "period": 35},
        }

        # Unique phase offset per tag to desynchronise their waveforms
        phase_offsets = {k: i * 1.1 for i, k in enumerate(sim_params)}

        while True:
            t = time.time() - self._t0
            new_values = {}

            for tag, params in sim_params.items():
                period = params["period"]
                osc = math.sin((2 * math.pi * t / period) + phase_offsets[tag])
                noise = random.uniform(-0.5, 0.5) * params["amp"] * 0.1
                raw = params["center"] + osc * params["amp"] * 0.5 + noise

                # Clamp to valid display range
                tag_range = config.TAG_RANGES.get(tag, {"min": 0, "max": 100})
                clamped = max(tag_range["min"], min(tag_range["max"], raw))
                new_values[tag] = round(clamped, 1)

            with self._lock:
                self.tag_cache.update(new_values)
                self.last_poll_time = datetime.utcnow()

            time.sleep(config.POLL_INTERVAL)


# =============================================================================
# Factory function — returns the appropriate poller based on configuration
# =============================================================================

def create_poller():
    """
    Instantiate, configure, and start either a PLCPoller or SimulatedPLCPoller
    based on the USE_SIMULATED_PLC environment variable.

    Returns:
        PLCPoller or SimulatedPLCPoller: configured and already started
    """
    use_sim = os.getenv("USE_SIMULATED_PLC", "false").lower() in ("true", "1", "yes")

    if use_sim:
        logger.info("USE_SIMULATED_PLC=true — using simulated data source")
        poller = SimulatedPLCPoller()
    else:
        logger.info(
            "USE_SIMULATED_PLC=false — connecting to physical PLC at %s",
            config.PLC_IP
        )
        poller = PLCPoller()

    poller.start()
    return poller
