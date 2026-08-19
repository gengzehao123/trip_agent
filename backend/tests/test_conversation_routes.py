from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import conversation
from app.services.conversation_service import ConversationService
from app.services.task_manager import TripTaskManager


def make_client(monkeypatch):
    conversations = ConversationService()
    tasks = TripTaskManager(conversations=conversations)
    monkeypatch.setattr(conversation, "conversation_service", conversations)
    monkeypatch.setattr(conversation, "task_manager", tasks)
    monkeypatch.setattr(conversation, "get_trip_planner_agent", lambda: object())
    app = FastAPI()
    app.include_router(conversation.router, prefix="/api")
    return TestClient(app), conversations


def test_unknown_conversation_returns_404(monkeypatch):
    client, _ = make_client(monkeypatch)

    assert client.get("/api/conversations/missing").status_code == 404


def test_revision_validates_plan_message_and_conflict(monkeypatch, trip_plan):
    client, conversations = make_client(monkeypatch)
    conversations.create("s1")

    assert client.post(
        "/api/conversations/s1/messages", json={"content": "修改"}
    ).status_code == 409

    conversations.set_current_plan("s1", trip_plan)
    assert client.post(
        "/api/conversations/s1/messages", json={"content": "   "}
    ).status_code == 422

    def discard_task(coroutine):
        coroutine.close()

    monkeypatch.setattr(conversation.asyncio, "create_task", discard_task)
    first = client.post(
        "/api/conversations/s1/messages", json={"content": "修改第一天"}
    )
    second = client.post(
        "/api/conversations/s1/messages", json={"content": "修改第二天"}
    )

    assert first.status_code == 200
    assert first.json()["session_id"] == "s1"
    assert second.status_code == 409
