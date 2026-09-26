import pytest
import requests

from firmware import simulator


class FakeResponse:
    def __init__(self, status_code=200, body=None, json_error=None):
        self.status_code = status_code
        self.body = body
        self.json_error = json_error

    def json(self):
        if self.json_error is not None:
            raise self.json_error
        return self.body


@pytest.mark.parametrize(
    ("status", "expected_led"),
    [
        ("Fresh / Normal", simulator.LED_GREEN),
        ("Use Soon", simulator.LED_YELLOW),
        ("Check Food", simulator.LED_RED),
    ],
)
def test_status_maps_to_led_from_business_status_only(
    status, expected_led, monkeypatch
):
    captured = {}

    def fake_get(url, *, timeout):
        captured.update(url=url, timeout=timeout)
        return FakeResponse(
            body={
                "success": True,
                "data": {
                    "freshness": {"status": status, "reason": "High humidity warning"},
                    "gas_anomaly_active": 1 if status == "Fresh / Normal" else 0,
                },
            }
        )

    monkeypatch.setattr(simulator.requests, "get", fake_get)
    state = simulator.LedStateMachine()

    result = simulator.poll_latest_freshness(state)

    assert result == expected_led
    assert state.last_led_state == expected_led
    assert captured == {
        "url": simulator.LATEST_READING_URL,
        "timeout": simulator.FRESHNESS_POLL_TIMEOUT,
    }
    assert simulator.FRESHNESS_POLL_INTERVAL == 5


def test_initial_led_state_is_unknown_not_red():
    assert simulator.LedStateMachine().last_led_state == simulator.LED_UNKNOWN


def test_unknown_status_does_not_change_last_led(monkeypatch, capsys):
    state = simulator.LedStateMachine()
    state.last_led_state = simulator.LED_YELLOW
    monkeypatch.setattr(
        simulator.requests,
        "get",
        lambda *_args, **_kwargs: FakeResponse(
            body={"success": True, "data": {"freshness": {"status": "Unknown"}}}
        ),
    )

    assert simulator.poll_latest_freshness(state) == simulator.LED_YELLOW
    assert "keep LED=YELLOW" in capsys.readouterr().out
    assert simulator.status_to_led("Freshly normal") is None


@pytest.mark.parametrize("error", [requests.Timeout("late"), requests.ConnectionError("offline")])
def test_poll_request_errors_keep_last_led(error, monkeypatch, capsys):
    state = simulator.LedStateMachine()
    state.last_led_state = simulator.LED_GREEN

    def fail_get(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(simulator.requests, "get", fail_get)

    assert simulator.poll_latest_freshness(state) == simulator.LED_GREEN
    assert "keep LED=GREEN" in capsys.readouterr().out


@pytest.mark.parametrize("status_code", [404, 500])
def test_http_failure_keeps_last_led(status_code, monkeypatch, capsys):
    state = simulator.LedStateMachine()
    state.last_led_state = simulator.LED_RED
    monkeypatch.setattr(
        simulator.requests,
        "get",
        lambda *_args, **_kwargs: FakeResponse(status_code=status_code),
    )

    assert simulator.poll_latest_freshness(state) == simulator.LED_RED
    assert f"HTTP {status_code}" in capsys.readouterr().out
    assert state.last_led_state == simulator.LED_RED


@pytest.mark.parametrize(
    "body",
    [
        None,
        {"success": True},
        {"success": True, "data": {}},
        {"success": True, "data": {"freshness": {}}},
        {"success": False, "data": {"freshness": {"status": "Check Food"}}},
    ],
)
def test_missing_or_invalid_response_fields_keep_last_led(body, monkeypatch):
    state = simulator.LedStateMachine()
    state.last_led_state = simulator.LED_YELLOW
    monkeypatch.setattr(
        simulator.requests,
        "get",
        lambda *_args, **_kwargs: FakeResponse(body=body),
    )

    assert simulator.poll_latest_freshness(state) == simulator.LED_YELLOW
    assert state.last_led_state == simulator.LED_YELLOW


def test_malformed_json_keeps_last_led(monkeypatch, capsys):
    state = simulator.LedStateMachine()
    state.last_led_state = simulator.LED_GREEN
    monkeypatch.setattr(
        simulator.requests,
        "get",
        lambda *_args, **_kwargs: FakeResponse(
            json_error=requests.exceptions.JSONDecodeError("bad json", "{", 0)
        ),
    )

    assert simulator.poll_latest_freshness(state) == simulator.LED_GREEN
    assert "malformed JSON" in capsys.readouterr().out
