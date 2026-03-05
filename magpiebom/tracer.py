"""Structured JSONL tracing for MagpieBOM pipeline runs."""

import json
import os
import re
import sys
from datetime import datetime, timezone


class Tracer:
    """Writes structured JSONL trace files for pipeline debugging.

    Each event is one JSON line with a ``ts`` (ISO 8601 UTC) and ``type`` field.
    High-level steps and errors are also echoed to stderr so the user sees
    progress.  Detail events only appear on stderr when *verbose* is True.
    """

    _MAX_BODY = 2048

    def __init__(
        self,
        part_number: str,
        trace_dir: str = "traces",
        verbose: bool = False,
    ) -> None:
        self._verbose = verbose

        # Sanitize part number for use in filename
        safe_pn = re.sub(r"[^A-Za-z0-9_-]", "_", part_number)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self._filename = f"{safe_pn}-{ts}.jsonl"

        os.makedirs(trace_dir, exist_ok=True)
        self._path = os.path.join(trace_dir, self._filename)
        self._file = open(self._path, "a", encoding="utf-8")  # noqa: SIM115

    # -- properties ----------------------------------------------------------

    @property
    def trace_path(self) -> str:
        """Full path to the JSONL trace file."""
        return self._path

    @property
    def filename(self) -> str:
        """Basename of the trace file."""
        return self._filename

    # -- event methods -------------------------------------------------------

    def step(self, message: str) -> None:
        """High-level pipeline step.  Always writes JSONL + stderr."""
        self._write({"type": "step", "message": message})
        self._stderr(message)

    def detail(self, message: str, **data) -> None:
        """Detail event.  JSONL always; stderr only when verbose."""
        self._write({"type": "detail", "message": message, **data})
        if self._verbose:
            self._stderr(message)

    def http(
        self,
        url: str,
        method: str,
        status: int,
        headers: dict,
        body: str | None,
        duration_ms: float,
        **extra,
    ) -> None:
        """HTTP request/response event.  JSONL only.  Body truncated at 2048 chars."""
        truncated = body[:self._MAX_BODY] if body is not None else None
        self._write({
            "type": "http",
            "url": url,
            "method": method,
            "status": status,
            "headers": headers,
            "body": truncated,
            "duration_ms": duration_ms,
            **extra,
        })

    def llm(
        self,
        purpose: str,
        prompt: str,
        response: str,
        tokens: dict,
        duration_ms: float,
    ) -> None:
        """LLM call event.  JSONL only."""
        self._write({
            "type": "llm",
            "purpose": purpose,
            "prompt": prompt,
            "response": response,
            "tokens": tokens,
            "duration_ms": duration_ms,
        })

    def image(
        self,
        url: str,
        path: str,
        width: int,
        height: int,
        size_bytes: int,
        format: str,
    ) -> None:
        """Image metadata event.  JSONL only."""
        self._write({
            "type": "image",
            "url": url,
            "path": path,
            "width": width,
            "height": height,
            "size_bytes": size_bytes,
            "format": format,
        })

    def error(self, message: str, exception: BaseException | None = None, **data) -> None:
        """Error event.  Always writes JSONL + stderr (prefixed with ``ERROR: ``)."""
        event: dict = {"type": "error", "message": message, **data}
        if exception is not None:
            event["exception"] = f"{type(exception).__name__}: {exception}"
        self._write(event)
        self._stderr(f"ERROR: {message}")

    def result(self, data: dict) -> None:
        """Final result event.  JSONL only."""
        self._write({"type": "result", "data": data})

    # -- lifecycle -----------------------------------------------------------

    def close(self) -> None:
        """Flush and close the trace file."""
        if not self._file.closed:
            self._file.flush()
            self._file.close()

    def __enter__(self) -> "Tracer":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # -- internals -----------------------------------------------------------

    def _write(self, event: dict) -> None:
        event["ts"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        self._file.write(json.dumps(event, default=str) + "\n")
        self._file.flush()

    @staticmethod
    def _stderr(msg: str) -> None:
        print(f"  {msg}", file=sys.stderr)
