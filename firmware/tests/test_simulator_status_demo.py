from firmware import simulator


class FakeResponse:
    status_code = 201


def test_status_demo_uses_backend_status_transitions(monkeypatch):
    sent = []
    statuses = iter(("Fresh / Normal", "Use Soon", "Check Food"))

    monkeypatch.setattr(simulator, "_create_status_demo_food", lambda food_id: True)
    monkeypatch.setattr(simulator, "send_reading", lambda reading: sent.append(reading) or FakeResponse())
    monkeypatch.setattr(simulator.time, "sleep", lambda seconds: None)

    def poll(state_machine):
        status = next(statuses)
        state_machine.last_poll_status = status
        state_machine.update_from_status(status)
        return state_machine.last_led_state

    monkeypatch.setattr(simulator, "poll_latest_freshness", poll)

    assert simulator.run_status_demo() is True
    assert len(sent) == 3
    assert sent[0]["door_open"] is False
    assert sent[1]["food_id"].startswith("FG-STATUS-DEMO-FOOD-")
    assert sent[2]["door_open"] is True
    assert sent[2]["open_duration_seconds"] == simulator.DOOR_TIMEOUT_SECONDS
