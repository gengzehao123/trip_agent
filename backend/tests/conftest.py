import pytest

from app.models.schemas import Attraction, DayPlan, Location, Meal, TripPlan


@pytest.fixture
def trip_plan() -> TripPlan:
    return TripPlan(
        city="北京",
        start_date="2026-09-01",
        end_date="2026-09-01",
        days=[
            DayPlan(
                date="2026-09-01",
                day_index=0,
                description="第一天",
                transportation="公共交通",
                accommodation="经济型酒店",
                attractions=[
                    Attraction(
                        name="故宫",
                        address="北京市东城区",
                        location=Location(longitude=116.397, latitude=39.916),
                        visit_duration=180,
                        description="历史文化景点",
                    )
                ],
                meals=[
                    Meal(type="breakfast", name="早餐"),
                    Meal(type="lunch", name="午餐"),
                    Meal(type="dinner", name="晚餐"),
                ],
            )
        ],
        weather_info=[],
        overall_suggestions="提前预约",
    )
