from firmware import simulator


class PostResponse:
    status_code = 201

    def __init__(self, reading_id):
        self.reading_id = reading_id

    def json(self):
        return {"success": True, "device_reading_id": self.reading_id}


class PollResponse:
    status_code = 200

    def __init__(self, status):
        self.status = status

    def json(self):
        return {
            "success": True,
            "data": {
                "freshness": {"status": self.status, "reason": "test warning"},
                "gas_anomaly_active": 1,
            },
        }


def install_auto_test_backend(monkeypatch, poll_responses):
    posted = []
    food_ids = []

    def fake_send_reading(payload):
        posted.append(payload.copy())
        return PostResponse(payload["device_reading_id"])

    def fake_create_food(food_id):
        food_ids.append(food_id)
        return True

    monkeypatch.setattr(simulator, "send_reading", fake_send_reading)
    monkeypatch.setattr(simulator, "_create_auto_test_food", fake_create_food)
    monkeypatch.setattr(
        simulator.requests,
        "get",
        lambda *_args, **_kwargs: poll_responses.pop(0),
    )
    return posted, food_ids


def test_auto_test_runs_fresh_use_soon_check_food_in_order(monkeypatch, capsys):
    posted, food_ids = install_auto_test_backend(
        monkeypatch,
        [
            PollResponse("Fresh / Normal"),
            PollResponse("Use Soon"),
            PollResponse("Check Food"),
        ],
    )

    assert simulator.run_auto_test() is True

    assert len(posted) == 3
    assert len({reading["device_reading_id"] for reading in posted}) == 3
    assert len({reading["device_id"] for reading in posted}) == 1
    assert all(reading["gas_raw"] == 300 for reading in posted)
    assert [reading["open_duration_seconds"] for reading in posted] == [0, 0, 30]
    assert "food_id" not in posted[0]
    assert posted[1]["food_id"] == food_ids[0]
    assert "freshness" not in posted[0]
    output = capsys.readouterr().out
    assert "BACKEND STATUS: Fresh / Normal" in output
    assert "BACKEND STATUS: Use Soon" in output
    assert "BACKEND STATUS: Check Food" in output
    assert "AUTO TEST RESULT: 3/3 PASS" in output


def test_auto_test_reports_poll_failure_without_faking_expected_status(
    monkeypatch, capsys
):
    posted, _food_ids = install_auto_test_backend(
        monkeypatch,
        [
            PollResponse("Fresh / Normal"),
            http_500_response(),
            PollResponse("Check Food"),
        ],
    )

    assert simulator.run_auto_test() is False
    assert len(posted) == 3
    output = capsys.readouterr().out
    assert "HTTP 500" in output
    assert "EXPECTED STATUS: Use Soon" in output
    assert "ACTUAL LED: GREEN" in output
    assert "AUTO TEST RESULT: FAIL (2/3 PASS)" in output


def http_500_response():
    class ErrorResponse:
        status_code = 500

        def json(self):
            raise AssertionError("HTTP error response should not be parsed")

    return ErrorResponse()
