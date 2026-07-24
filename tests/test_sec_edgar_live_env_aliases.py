from winner_tilt.data_providers.sec_edgar_live import SecEdgarLiveRuntimeConfig


def _base_env() -> dict[str, str]:
    return {
        "WINNER_TILT_SEC_EDGAR_LIVE_ENABLED": "true",
        "WINNER_TILT_SEC_EDGAR_USER_AGENT": "WinnerTiltAI/1.0 test@example.com",
        "WINNER_TILT_SEC_EDGAR_KILL_SWITCH": "false",
    }


def test_runtime_accepts_workflow_allowlist_and_request_limit_aliases() -> None:
    env = {
        **_base_env(),
        "WINNER_TILT_SEC_EDGAR_ALLOWED_CIKS": "0000320193",
        "WINNER_TILT_SEC_EDGAR_MAX_REQUESTS": "1",
    }

    runtime = SecEdgarLiveRuntimeConfig.from_env(env)

    assert runtime.allowed_ciks == ("0000320193",)
    assert runtime.max_total_requests == 1


def test_canonical_names_take_precedence_over_aliases() -> None:
    env = {
        **_base_env(),
        "WINNER_TILT_SEC_EDGAR_CIKS": "0000789019",
        "WINNER_TILT_SEC_EDGAR_ALLOWED_CIKS": "0000320193",
        "WINNER_TILT_SEC_EDGAR_MAX_TOTAL_REQUESTS": "2",
        "WINNER_TILT_SEC_EDGAR_MAX_REQUESTS": "1",
    }

    runtime = SecEdgarLiveRuntimeConfig.from_env(env)

    assert runtime.allowed_ciks == ("0000789019",)
    assert runtime.max_total_requests == 2
