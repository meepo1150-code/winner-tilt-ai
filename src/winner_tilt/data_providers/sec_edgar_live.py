"""Controlled SEC EDGAR live-ingest infrastructure.

This module provides a small HTTPS transport, fail-closed runtime configuration,
and immutable ingest-only snapshot writing. Repository defaults remain offline;
operators must explicitly enable a run through environment variables.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .base import ProviderResult
from .sec_edgar import SecEdgarCompanyFactsProvider, SecEdgarPilotConfig, SecEdgarPolicyError


class SecEdgarTransportError(RuntimeError):
    """Raised when the bounded HTTPS transport fails closed."""


def _first_nonempty(values: Mapping[str, str], *names: str, default: str = "") -> str:
    """Return the first configured environment value from canonical name or alias."""
    for name in names:
        value = values.get(name, "").strip()
        if value:
            return value
    return default


@dataclass(frozen=True)
class SecEdgarLiveRuntimeConfig:
    enabled: bool
    user_agent: str
    allowed_ciks: tuple[str, ...]
    timeout_seconds: float = 10.0
    max_attempts: int = 3
    backoff_seconds: float = 0.5
    max_requests_per_second: float = 2.0
    max_total_requests: int = 3
    kill_switch: bool = False

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "SecEdgarLiveRuntimeConfig":
        values = os.environ if env is None else env
        enabled = values.get("WINNER_TILT_SEC_EDGAR_LIVE_ENABLED", "false").strip().lower() == "true"
        kill_switch = values.get("WINNER_TILT_SEC_EDGAR_KILL_SWITCH", "false").strip().lower() == "true"

        cik_value = _first_nonempty(
            values,
            "WINNER_TILT_SEC_EDGAR_CIKS",
            "WINNER_TILT_SEC_EDGAR_ALLOWED_CIKS",
        )
        ciks = tuple(item.strip() for item in cik_value.split(",") if item.strip())

        max_total_requests_value = _first_nonempty(
            values,
            "WINNER_TILT_SEC_EDGAR_MAX_TOTAL_REQUESTS",
            "WINNER_TILT_SEC_EDGAR_MAX_REQUESTS",
            default="3",
        )

        config = cls(
            enabled=enabled,
            user_agent=values.get("WINNER_TILT_SEC_EDGAR_USER_AGENT", "").strip(),
            allowed_ciks=ciks,
            timeout_seconds=float(values.get("WINNER_TILT_SEC_EDGAR_TIMEOUT_SECONDS", "10")),
            max_attempts=int(values.get("WINNER_TILT_SEC_EDGAR_MAX_ATTEMPTS", "3")),
            backoff_seconds=float(values.get("WINNER_TILT_SEC_EDGAR_BACKOFF_SECONDS", "0.5")),
            max_requests_per_second=float(values.get("WINNER_TILT_SEC_EDGAR_MAX_RPS", "2")),
            max_total_requests=int(max_total_requests_value),
            kill_switch=kill_switch,
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.kill_switch and self.enabled:
            raise SecEdgarPolicyError("SEC_EDGAR_KILL_SWITCH_ACTIVE")
        if self.enabled and not self.user_agent:
            raise SecEdgarPolicyError("SEC_EDGAR_USER_AGENT_REQUIRED")
        if self.enabled and not self.allowed_ciks:
            raise SecEdgarPolicyError("SEC_EDGAR_ALLOWLIST_REQUIRED")
        if not (0 < self.timeout_seconds <= 30):
            raise SecEdgarPolicyError("SEC_EDGAR_TIMEOUT_OUT_OF_POLICY")
        if not (1 <= self.max_attempts <= 3):
            raise SecEdgarPolicyError("SEC_EDGAR_MAX_ATTEMPTS_OUT_OF_POLICY")
        if not (0 <= self.backoff_seconds <= 5):
            raise SecEdgarPolicyError("SEC_EDGAR_BACKOFF_OUT_OF_POLICY")
        if not (0 < self.max_requests_per_second <= 2):
            raise SecEdgarPolicyError("SEC_EDGAR_RATE_LIMIT_EXCEEDS_PILOT_POLICY")
        if not (1 <= self.max_total_requests <= 3):
            raise SecEdgarPolicyError("SEC_EDGAR_REQUEST_CEILING_EXCEEDED")
        if len(self.allowed_ciks) > self.max_total_requests:
            raise SecEdgarPolicyError("SEC_EDGAR_ALLOWLIST_EXCEEDS_REQUEST_CEILING")


class SecEdgarHttpsTransport:
    """Callable HTTPS transport with bounded retries and rate limiting."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        max_attempts: int = 3,
        backoff_seconds: float = 0.5,
        max_requests_per_second: float = 2.0,
        opener: Callable[..., Any] = urlopen,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self.minimum_interval = 1.0 / max_requests_per_second
        self._opener = opener
        self._sleeper = sleeper
        self._monotonic = monotonic
        self._last_request_at: float | None = None

    def __call__(self, url: str, headers: Mapping[str, str]) -> Mapping[str, Any]:
        user_agent = headers.get("User-Agent", "").strip()
        if not user_agent:
            raise SecEdgarTransportError("SEC_EDGAR_USER_AGENT_REQUIRED")
        if not url.startswith("https://data.sec.gov/"):
            raise SecEdgarTransportError("SEC_EDGAR_UNAPPROVED_HOST")

        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            now = self._monotonic()
            if self._last_request_at is not None:
                delay = self.minimum_interval - (now - self._last_request_at)
                if delay > 0:
                    self._sleeper(delay)
            self._last_request_at = self._monotonic()
            request = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"}, method="GET")
            try:
                with self._opener(request, timeout=self.timeout_seconds) as response:
                    status = getattr(response, "status", 200)
                    if status != 200:
                        raise SecEdgarTransportError(f"SEC_EDGAR_HTTP_STATUS_{status}")
                    payload = json.loads(response.read().decode("utf-8"))
                    if not isinstance(payload, Mapping):
                        raise SecEdgarTransportError("SEC_EDGAR_RESPONSE_NOT_OBJECT")
                    return payload
            except HTTPError as exc:
                last_error = exc
                if exc.code in {403, 429}:
                    raise SecEdgarTransportError(f"SEC_EDGAR_STOP_HTTP_{exc.code}") from exc
                if 400 <= exc.code < 500:
                    raise SecEdgarTransportError(f"SEC_EDGAR_HTTP_{exc.code}") from exc
            except (URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError, SecEdgarTransportError) as exc:
                last_error = exc
            if attempt < self.max_attempts:
                self._sleeper(self.backoff_seconds * (2 ** (attempt - 1)))
        raise SecEdgarTransportError("SEC_EDGAR_TRANSPORT_EXHAUSTED") from last_error


def _result_payload(result: ProviderResult) -> dict[str, Any]:
    value = asdict(result)
    value["rows"] = list(result.rows)
    value["pilot_tag"] = "ingest_only_no_downstream_consumption"
    return value


def write_immutable_snapshot(result: ProviderResult, destination: str | Path) -> Path:
    """Write one immutable canonical JSON snapshot and refuse overwrite."""
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise SecEdgarPolicyError("SEC_EDGAR_SNAPSHOT_ALREADY_EXISTS")
    encoded = json.dumps(_result_payload(result), sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    path.write_text(encoded, encoding="utf-8")
    return path


def run_authorized_pilot(
    runtime: SecEdgarLiveRuntimeConfig,
    *,
    snapshot_dir: str | Path,
    transport: Callable[[str, Mapping[str, str]], Mapping[str, Any]] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> tuple[Path, ...]:
    """Execute the bounded ingest-only run for the configured CIK allowlist."""
    runtime.validate()
    if not runtime.enabled:
        raise SecEdgarPolicyError("SEC_EDGAR_LIVE_MODE_DISABLED")
    if runtime.kill_switch:
        raise SecEdgarPolicyError("SEC_EDGAR_KILL_SWITCH_ACTIVE")

    https_transport = transport or SecEdgarHttpsTransport(
        timeout_seconds=runtime.timeout_seconds,
        max_attempts=runtime.max_attempts,
        backoff_seconds=runtime.backoff_seconds,
        max_requests_per_second=runtime.max_requests_per_second,
    )
    provider = SecEdgarCompanyFactsProvider(
        SecEdgarPilotConfig(
            allowed_ciks=runtime.allowed_ciks,
            user_agent=runtime.user_agent,
            live_enabled=True,
            max_requests_per_second=runtime.max_requests_per_second,
            retain_raw_payload=False,
        ),
        transport=https_transport,
        clock=clock,
    )

    run_id = (clock or (lambda: datetime.now(timezone.utc)))().astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outputs: list[Path] = []
    for cik in runtime.allowed_ciks:
        result = provider.fetch(cik=cik)
        validation = provider.validate(result)
        if getattr(validation, "valid", True) is False:
            raise SecEdgarPolicyError("SEC_EDGAR_VALIDATION_FAILED")
        normalized_cik = str(cik).zfill(10)
        outputs.append(write_immutable_snapshot(result, Path(snapshot_dir) / run_id / f"CIK{normalized_cik}.json"))
    return tuple(outputs)
