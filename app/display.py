from typing import Optional


def format_faction(faction: Optional[str]) -> Optional[str]:
    if faction is None:
        return None
    cleaned = " ".join(faction.replace("-", " ").split())
    if not cleaned:
        return None
    return cleaned.title()