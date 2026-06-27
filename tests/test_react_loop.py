# tests/test_react_loop.py
import pytest
from unittest.mock import patch, MagicMock
from agent.react_loop import _parse_step, _merge_into_collected


def test_parse_step_valid_json():
    raw = '{"thought": "I should identify food", "action": "identify_food", "action_input": {}}'
    result = _parse_step(raw)
    assert result["action"] == "identify_food"
    assert result["thought"] == "I should identify food"


def test_parse_step_strips_markdown():
    raw = '```json\n{"thought": "test", "action": "finish", "action_input": {"summary": "done"}}\n```'
    result = _parse_step(raw)
    assert result["action"] == "finish"


def test_parse_step_raises_on_invalid_json():
    with pytest.raises(ValueError, match="Agent returned invalid JSON"):
        _parse_step("Sure! I'll help you with that meal.")


def test_merge_into_collected_by_name():
    items = [{"name": "chicken breast"}, {"name": "rice"}]
    data = {"name": "chicken breast", "kcal_per_100g": 165.0, "protein_g": 31.0}
    _merge_into_collected(items, data)
    assert items[0]["kcal_per_100g"] == 165.0
    assert "kcal_per_100g" not in items[1]


def test_merge_into_collected_fallback_to_missing_nutrition():
    """If name doesn't match, merge into first item missing nutrition."""
    items = [{"name": "chicken", "kcal_per_100g": 165.0}, {"name": "rice"}]
    data = {"name": "white rice", "kcal_per_100g": 130.0}
    _merge_into_collected(items, data)
    assert items[1]["kcal_per_100g"] == 130.0


def test_merge_into_collected_last_resort():
    """If all items have nutrition, update the last one."""
    items = [
        {"name": "chicken", "kcal_per_100g": 165.0},
        {"name": "rice", "kcal_per_100g": 130.0}
    ]
    data = {"name": "unknown", "kcal_per_100g": 50.0}
    _merge_into_collected(items, data)
    assert items[-1]["kcal_per_100g"] == 50.0