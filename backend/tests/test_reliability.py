import time

from ..app.services.retry import run_with_retry
from ..app.agents.trip_planner_agent import MultiAgentTripPlanner
from ..app.models.schemas import TripRequest


def test_run_with_retry_succeeds_on_third_attempt(monkeypatch):
    attempts = 0
    sleeps = []

    def operation():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError("temporary failure")
        return "ok"

    monkeypatch.setattr("app.services.retry.sleep", sleeps.append)

    assert run_with_retry(operation, operation_name="test") == "ok"
    assert attempts == 3
    assert sleeps == [1, 2]


def test_run_with_retry_raises_after_max_attempts(monkeypatch):
    attempts = 0

    def operation():
        nonlocal attempts
        attempts += 1
        raise ValueError("permanent failure")

    monkeypatch.setattr("app.services.retry.sleep", lambda _seconds: None)

    try:
        run_with_retry(operation, operation_name="test")
    except ValueError as exc:
        assert str(exc) == "permanent failure"
    else:
        raise AssertionError("expected ValueError")

    assert attempts == 3


def test_run_with_retry_applies_timeout(monkeypatch):
    monkeypatch.setattr("app.services.retry.sleep", lambda _seconds: None)

    def operation():
        time.sleep(0.1)

    try:
        run_with_retry(operation, operation_name="test", timeout_seconds=0.01)
    except TimeoutError as exc:
        assert "超时" in str(exc)
    else:
        raise AssertionError("expected TimeoutError")


def test_trip_plan_validation_rejects_wrong_day_count():
    request = TripRequest(
        city="北京",
        start_date="2026-08-18",
        end_date="2026-08-19",
        travel_days=2,
        transportation="公共交通",
        accommodation="经济型酒店",
    )

    try:
        MultiAgentTripPlanner._validate_trip_plan({
            "city": "北京",
            "start_date": "2026-08-18",
            "end_date": "2026-08-19",
            "days": [],
            "weather_info": [],
            "overall_suggestions": "建议",
        }, request)
    except ValueError as exc:
        assert "行程天数" in str(exc)
    else:
        raise AssertionError("expected day count validation error")
