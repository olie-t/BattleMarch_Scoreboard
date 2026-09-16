from typing import Any

from app.display import format_faction
from app.models import ArmyList


SECTION_LABELS = {
    "characters": "Characters",
    "core": "Core",
    "special": "Special",
    "rare": "Rare",
    "mercenaries": "Mercenaries",
    "allies": "Allies",
}

OPTIONAL_SECTIONS = {"special", "rare", "mercenaries", "allies"}


def display_name(value: Any) -> str:
    if isinstance(value, dict):
        name = value.get("name_en") or value.get("name") or value.get("id")
        return str(name) if name else "Unnamed choice"
    return str(value)


def is_chosen(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("active") is True:
        return True
    selected = value.get("selected")
    if isinstance(selected, list) and selected:
        return True
    return False


def chosen_names(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    names = []
    for value in values:
        if not isinstance(value, dict):
            continue

        selected = value.get("selected")
        if isinstance(selected, list) and selected:
            names.extend(display_name(choice) for choice in selected)

        nested_options = value.get("options")
        if isinstance(nested_options, list):
            selected_nested = [display_name(option) for option in nested_options if is_chosen(option)]
            if selected_nested:
                names.append(f"{display_name(value)}: {', '.join(selected_nested)}")
                continue

        if is_chosen(value):
            names.append(display_name(value))

    return names


def choice_cost(choice: dict[str, Any], model_count: int) -> int:
    points = choice.get("points")
    if not isinstance(points, int):
        return 0
    if choice.get("perModel") is True:
        return points * model_count
    return points


def chosen_costs(values: Any, model_count: int) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []

    costs = []
    for value in values:
        if not isinstance(value, dict):
            continue

        selected = value.get("selected")
        if isinstance(selected, list) and selected:
            for selected_choice in selected:
                if isinstance(selected_choice, dict):
                    costs.append(
                        {
                            "name": display_name(selected_choice),
                            "points": selected_choice.get("points", 0),
                            "per_model": selected_choice.get("perModel") is True,
                            "total": choice_cost(selected_choice, model_count),
                        }
                    )

        nested_options = value.get("options")
        if isinstance(nested_options, list):
            selected_nested = [option for option in nested_options if is_chosen(option)]
            if selected_nested:
                for option in selected_nested:
                    costs.append(
                        {
                            "name": f"{display_name(value)}: {display_name(option)}",
                            "points": option.get("points", 0),
                            "per_model": option.get("perModel") is True,
                            "total": choice_cost(option, model_count),
                        }
                    )
                continue

        if is_chosen(value):
            costs.append(
                {
                    "name": display_name(value),
                    "points": value.get("points", 0),
                    "per_model": value.get("perModel") is True,
                    "total": choice_cost(value, model_count),
                }
            )
    return costs


def selected_costs(unit: dict[str, Any], model_count: int) -> list[dict[str, Any]]:
    costs = []
    for label, key in (
        ("Command", "command"),
        ("Equipment", "equipment"),
        ("Armour", "armor"),
        ("Armour", "armour"),
        ("Mounts", "mounts"),
        ("Options", "options"),
        ("Items", "items"),
    ):
        for cost in chosen_costs(unit.get(key), model_count):
            if cost["total"]:
                costs.append({"category": label, **cost})
    return costs


def special_rules(unit: dict[str, Any]) -> list[str]:
    rules = unit.get("specialRules")
    if isinstance(rules, dict):
        rule_text = rules.get("name_en") or rules.get("name")
        if isinstance(rule_text, str) and rule_text.strip():
            return [rule.strip() for rule in rule_text.split(",") if rule.strip()]
    if isinstance(rules, str) and rules.strip():
        return [rule.strip() for rule in rules.split(",") if rule.strip()]
    return []


def render_unit(unit: dict[str, Any]) -> dict[str, Any]:
    model_count = unit.get("strength") if isinstance(unit.get("strength"), int) else 1
    points = unit.get("points") if isinstance(unit.get("points"), int) else 0
    base_total = points * model_count
    upgrade_costs = selected_costs(unit, model_count)
    return {
        "name": display_name(unit),
        "strength": unit.get("strength"),
        "points": unit.get("points"),
        "base_total": base_total,
        "upgrade_costs": upgrade_costs,
        "total_cost": base_total + sum(cost["total"] for cost in upgrade_costs),
        "command": chosen_names(unit.get("command")),
        "equipment": chosen_names(unit.get("equipment")),
        "armour": chosen_names(unit.get("armor")) or chosen_names(unit.get("armour")),
        "mounts": chosen_names(unit.get("mounts")),
        "options": chosen_names(unit.get("options")),
        "items": chosen_names(unit.get("items")),
        "special_rules": special_rules(unit),
    }


def render_army_list(army_list: ArmyList) -> dict[str, Any]:
    sections = []
    for section_key, section_label in SECTION_LABELS.items():
        units = army_list.data.get(section_key, [])
        if section_key in OPTIONAL_SECTIONS and not units:
            continue
        sections.append(
            {
                "label": section_label,
                "units": [render_unit(unit) for unit in units if isinstance(unit, dict)],
            }
        )

    return {
        "army_list": army_list,
        "faction_display": format_faction(army_list.faction),
        "sections": sections,
    }