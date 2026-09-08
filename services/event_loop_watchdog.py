from __future__ import annotations

import asyncio
import os
import threading
import time

from services.runtime_configuration import env_int
from utils.log import logger


WATCHDOG_INTERVAL_SECONDS = 5
WATCHDOG_STALL_SECONDS = 60


class EventLoopWatchdog:
    def __init__(self) -> None:
        self._last_heartbeat = time.monotonic()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    async def heartbeat(self) -> None:
        interval = env_int(
            "CHATGPT2API_EVENT_LOOP_WATCHDOG_INTERVAL_SECONDS",
            WATCHDOG_INTERVAL_SECONDS,
            minimum=1,
            maximum=30,
        )
        while not self._stop_event.is_set():
            self._last_heartbeat = time.monotonic()
            await asyncio.sleep(interval)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._last_heartbeat = time.monotonic()
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._monitor,
            daemon=True,
            name="event-loop-watchdog",
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=1)
        self._thread = None

    def _monitor(self) -> None:
        stall_seconds = env_int(
            "CHATGPT2API_EVENT_LOOP_WATCHDOG_STALL_SECONDS",
            WATCHDOG_STALL_SECONDS,
            minimum=30,
            maximum=600,
        )
        check_interval = min(5.0, max(1.0, stall_seconds / 4))
        while not self._stop_event.wait(check_interval):
            stalled_for = time.monotonic() - self._last_heartbeat
            if stalled_for < stall_seconds:
                continue
            logger.error({
                "event": "event_loop_watchdog_stalled",
                "stalled_for_seconds": round(stalled_for, 1),
                "exit_code": 70,
            })
            os._exit(70)


event_loop_watchdog = EventLoopWatchdog()
