from fastapi.testclient import TestClient

from ..app.api.main import app
from ..app.api.routes import map as map_routes
from ..app.api.routes import trip as trip_routes
from ..app.models.schemas import Location, RouteInfo, TripPlan


client = TestClient(app)


class FakeMapService:
    def __init__(self, route_result=None):
        self.route_result = route_result

    def search_poi(self, *_args):
        return []

    def get_weather(self, *_args):
        return []

    def plan_route(self, **_kwargs):
        return self.route_result


def test_root_and_health():
    assert client.get("/").status_code == 200
    assert client.get("/health").json()["status"] == "healthy"


def test_map_poi_and_weather_return_success(monkeypatch):
    monkeypatch.setattr(map_routes, "get_amap_service", lambda: FakeMapService())

    poi_response = client.get("/api/map/poi", params={"keywords": "故宫", "city": "北京"})
    weather_response = client.get("/api/map/weather", params={"city": "北京"})

    assert poi_response.status_code == 200
    assert poi_response.json() == {"success": True, "message": "POI搜索成功", "data": []}
    assert weather_response.status_code == 200
    assert weather_response.json() == {"success": True, "message": "天气查询成功", "data": []}


def test_map_route_returns_route_info(monkeypatch):
    route = RouteInfo(
        distance=1200,
        duration=900,
        route_type="walking",
        description="沿道路步行",
    ).model_dump()
    monkeypatch.setattr(map_routes, "get_amap_service", lambda: FakeMapService(route))

    response = client.post("/api/map/route", json={
        "origin_address": "起点",
        "destination_address": "终点",
    })

    assert response.status_code == 200
    assert response.json()["data"] == route


def test_map_route_returns_502_when_service_fails(monkeypatch):
    monkeypatch.setattr(map_routes, "get_amap_service", lambda: FakeMapService({}))

    response = client.post("/api/map/route", json={
        "origin_address": "起点",
        "destination_address": "终点",
    })

    assert response.status_code == 502
    assert response.json()["detail"] == "高德地图路线服务暂时不可用"


def test_trip_plan_rejects_invalid_request():
    response = client.post("/api/trip/plan", json={"city": "北京"})
    assert response.status_code == 422


def test_trip_plan_returns_structured_response(monkeypatch):
    plan = TripPlan(
        city="北京",
        start_date="2026-08-18",
        end_date="2026-08-18",
        days=[],
        weather_info=[],
        overall_suggestions="建议提前预约",
    )

    class FakeAgent:
        def plan_trip(self, _request):
            return plan

    monkeypatch.setattr(trip_routes, "get_trip_planner_agent", lambda: FakeAgent())
    response = client.post("/api/trip/plan", json={
        "city": "北京",
        "start_date": "2026-08-18",
        "end_date": "2026-08-18",
        "travel_days": 1,
        "transportation": "公共交通",
        "accommodation": "经济型酒店",
        "preferences": [],
        "free_text_input": "",
    })

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["city"] == "北京"
