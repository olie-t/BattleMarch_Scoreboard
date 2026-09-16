from app.display import format_faction


def test_format_faction_removes_hyphens_and_title_cases() -> None:
    assert format_faction("orc-and-goblin-tribes") == "Orc And Goblin Tribes"


def test_format_faction_handles_missing_values() -> None:
    assert format_faction(None) is None
    assert format_faction("   ") is None