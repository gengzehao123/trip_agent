import asyncio

from app.models.schemas import TripRequest
from app.services.conversation_service import ConversationService
from app.services.task_manager import TripTaskManager


class PlannerStub:
    def __init__(self, plan, error=None):
        self.plan = plan
        self.error = error
        self.revision_args = None

    async def plan_trip(self, request, on_progress=None):
        if self.error:
            raise self.error
        return self.plan

    async def revise_trip(
        self, current_plan, instruction, history, preferences, on_progress=None
    ):
        self.revision_args = (current_plan, instruction, history, preferences)
        if self.error:
            raise self.error
        return self.plan


def test_plan_success_updates_conversation(trip_plan):
    conversations = ConversationService()
    conversations.create("s1")
    manager = TripTaskManager(conversations=conversations)
    task = manager.create(session_id="s1")
    request = TripRequest(
        city="北京",
        start_date="2026-09-01",
        end_date="2026-09-01",
        travel_days=1,
        transportation="公共交通",
        accommodation="经济型酒店",
        preferences=["历史文化"],
    )

    asyncio.run(manager.run(task.task_id, request, PlannerStub(trip_plan)))

    context = conversations.get("s1")
    assert context.current_trip_plan == trip_plan
    assert context.messages[-1].role == "assistant"
    assert manager.get(task.task_id).status == "completed"


def test_revision_failure_keeps_previous_plan(trip_plan):
    conversations = ConversationService()
    conversations.create("s1")
    conversations.set_current_plan("s1", trip_plan)
    conversations.add_message("s1", "user", "修改第一天")
    manager = TripTaskManager(conversations=conversations)
    task = manager.create(session_id="s1")
    assert conversations.start_revision("s1", task.task_id) is True

    asyncio.run(
        manager.run_revision(
            task.task_id,
            "修改第一天",
            PlannerStub(trip_plan, error=RuntimeError("LLM failed")),
        )
    )

    assert conversations.get("s1").current_trip_plan == trip_plan
    assert manager.get(task.task_id).status == "failed"
    assert conversations.start_revision("s1", "next-task") is True


def test_revision_context_is_a_defensive_snapshot(trip_plan):
    conversations = ConversationService()
    conversations.create("s1")
    conversations.set_current_plan("s1", trip_plan)
    conversations.add_message("s1", "user", "保留故宫，增加颐和园")
    conversations.merge_preferences("s1", ["历史文化"])

    snapshot = conversations.get_revision_context("s1")

    assert snapshot is not None
    current_plan, messages, preferences = snapshot
    current_plan.days.clear()
    messages.clear()
    preferences.append("美食")

    context = conversations.get("s1")
    assert context.current_trip_plan == trip_plan
    assert [message.content for message in context.messages] == [
        "保留故宫，增加颐和园"
    ]
    assert context.user_preferences == ["历史文化"]


def test_revision_passes_current_context_and_replaces_plan(trip_plan):
    revised_plan = trip_plan.model_copy(deep=True)
    revised_plan.overall_suggestions = ["已根据上下文调整"]
    conversations = ConversationService()
    conversations.create("s1")
    conversations.set_current_plan("s1", trip_plan)
    conversations.add_message("s1", "user", "保留故宫，增加颐和园")
    conversations.merge_preferences("s1", ["历史文化"])
    manager = TripTaskManager(conversations=conversations)
    task = manager.create(session_id="s1")
    assert conversations.start_revision("s1", task.task_id) is True
    planner = PlannerStub(revised_plan)

    asyncio.run(manager.run_revision(task.task_id, "调整第一天", planner))

    current_plan, instruction, history, preferences = planner.revision_args
    assert current_plan == trip_plan
    assert instruction == "调整第一天"
    assert [message.content for message in history] == [
        "保留故宫，增加颐和园"
    ]
    assert preferences == ["历史文化"]
    assert conversations.get("s1").current_trip_plan == revised_plan
    assert conversations.get("s1").messages[-1].content == "已更新旅行计划"
    assert manager.get(task.task_id).status == "completed"
