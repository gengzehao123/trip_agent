from app.services.conversation_service import ConversationService


def test_create_reuses_session_and_stores_context(trip_plan):
    service = ConversationService(max_messages=3)

    assert service.create("s1").session_id == service.create("s1").session_id
    service.merge_preferences("s1", ["美食", "历史文化", "美食", " "])
    assert service.set_current_plan("s1", trip_plan) is True

    context = service.get("s1")
    assert context.user_preferences == ["美食", "历史文化"]
    assert context.current_trip_plan == trip_plan


def test_messages_trim_oldest_and_return_defensive_copy():
    service = ConversationService(max_messages=3)
    service.create("s1")

    for index in range(5):
        service.add_message("s1", "user", f"message-{index}")

    context = service.get("s1")
    assert [item.content for item in context.messages] == [
        "message-2",
        "message-3",
        "message-4",
    ]
    context.messages.clear()
    assert len(service.get("s1").messages) == 3


def test_unknown_session_is_not_created_by_write(trip_plan):
    service = ConversationService()

    assert service.get("missing") is None
    assert service.set_current_plan("missing", trip_plan) is False
