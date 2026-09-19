"""Daily file logging for docToCloud.

Every run records its download/upload activity in
``docToCloud/logs/YYYY-MM-DD.log`` — one file per calendar day.  The file is
selected when each record is emitted, so a long-running process rolls over
automatically at midnight without restarting.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import TextIO

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_LOG_DIR = PROJECT_DIR / "logs"


class DailyFileHandler(logging.Handler):
    """Write records to ``<log_dir>/YYYY-MM-DD.log``, one file per day."""

    def __init__(
        self,
        log_dir: str | Path = DEFAULT_LOG_DIR,
        encoding: str = "utf-8",
    ) -> None:
        super().__init__()
        self.log_dir = Path(log_dir)
        self.encoding = encoding
        self._current_day: str | None = None
        self._stream: TextIO | None = None

    def _stream_for_today(self) -> TextIO:
        today = date.today().isoformat()
        if self._stream is None or self._current_day != today:
            if self._stream is not None:
                self._stream.close()
            self.log_dir.mkdir(parents=True, exist_ok=True)
            self._stream = open(
                self.log_dir / f"{today}.log", "a", encoding=self.encoding
            )
            self._current_day = today
        return self._stream

    def emit(self, record: logging.LogRecord) -> None:
        try:
            stream = self._stream_for_today()
            stream.write(self.format(record) + "\n")
            stream.flush()
        except Exception:  # noqa: BLE001
            self.handleError(record)

    def close(self) -> None:
        try:
            if self._stream is not None:
                self._stream.close()
                self._stream = None
        finally:
            super().close()


def configure_logging(log_dir: str | Path = DEFAULT_LOG_DIR) -> None:
    """Log to stderr and to the daily file under ``log_dir``.

    Idempotent: repeated calls do not stack duplicate handlers.
    """
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    has_console = any(
        isinstance(h, logging.StreamHandler)
        and not isinstance(h, DailyFileHandler)
        for h in root.handlers
    )
    if not has_console:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root.addHandler(console)

    if not any(isinstance(h, DailyFileHandler) for h in root.handlers):
        file_handler = DailyFileHandler(log_dir)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
