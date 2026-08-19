import asyncio

import pytest

from app.agents.trip_planner_agent import LangGraphTripPlanner
from app.models.schemas import ConversationMessage, TripRequest


def test_revision_prompt_contains_all_context(trip_plan):
    planner = object.__new__(LangGraphTripPlanner)

    prompt = planner._build_revision_prompt(
        trip_plan,
        "把第一天改成亲子景点",
        [ConversationMessage(role="user", content="不要安排太早")],
        ["亲子", "美食"],
    )

    assert '"city": "北京"' in prompt
    assert "不要安排太早" in prompt
    assert "亲子" in prompt and "美食" in prompt
    assert "把第一天改成亲子景点" in prompt
    assert "返回完整" in prompt


def test_normalize_plan_data_unwraps_trip_plan(trip_plan):
    planner = object.__new__(LangGraphTripPlanner)

    normalized = planner._normalize_plan_data({"trip_plan": trip_plan.model_dump()})

    assert normalized["city"] == "北京"
    assert "trip_plan" not in normalized


def test_normalize_plan_data_unwraps_basic_info(trip_plan):
    planner = object.__new__(LangGraphTripPlanner)

    normalized = planner._normalize_plan_data({"basic_info": trip_plan.model_dump()})

    assert normalized["city"] == "北京"
    assert "basic_info" not in normalized


def test_normalize_loose_trip_plan_shape_for_model_output(trip_plan):
    planner = object.__new__(LangGraphTripPlanner)
    request = TripRequest(
        city="苏州",
        start_date="2026-08-20",
        end_date="2026-08-21",
        travel_days=2,
        transportation="公共交通",
        accommodation="经济型酒店",
    )
    raw = {
        "city": "苏州",
        "start_date": "2026-08-20",
        "end_date": "2026-08-21",
        "days": [
            {
                "date": "2026-08-20",
                "attractions": trip_plan.days[0].model_dump()["attractions"],
                "meals": {"午餐": "苏州面馆"},
            },
            {
                "date": "2026-08-21",
                "attractions": trip_plan.days[0].model_dump()["attractions"],
                "meals": {"晚餐": "本帮菜"},
            },
        ],
        "weather_info": {"summary": "夏季炎热，注意防晒"},
        "overall_suggestions": ["提前预约", "准备防晒用品"],
        "budget": "人均约1000元",
    }

    normalized = planner._normalize_plan_data(raw, request)
    plan = planner._validate_trip_plan(normalized, request)

    assert [day.day_index for day in plan.days] == [0, 1]
    assert plan.days[0].transportation == "公共交通"
    assert {meal.type for meal in plan.days[0].meals} >= {
        "breakfast",
        "lunch",
        "dinner",
    }
    assert len(plan.weather_info) == 2
    assert "提前预约" in plan.overall_suggestions
    assert plan.budget is not None


def test_revise_trip_propagates_generation_failure(monkeypatch, trip_plan):
    planner = object.__new__(LangGraphTripPlanner)

    async def fail(*args, **kwargs):
        raise ValueError("invalid revision")

    monkeypatch.setattr(planner, "_generate_revision", fail)

    with pytest.raises(ValueError, match="invalid revision"):
        asyncio.run(planner.revise_trip(trip_plan, "修改", [], []))
