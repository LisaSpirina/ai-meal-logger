# tests/test_nutrition.py
import pytest
import requests
from unittest.mock import patch, MagicMock
from tools.nutrition import lookup_nutrition


def _mock_get(nutrients: list) -> MagicMock:
    """Helper to build a mock USDA response."""
    mock = MagicMock()
    mock.raise_for_status = lambda: None
    mock.json.return_value = {
        "foods": [{
            "fdcId": 123,
            "description": "Chicken breast",
            "foodNutrients": nutrients
        }]
    }
    return mock


def test_returns_expected_keys():
    nutrients = [
        {"nutrientId": 1008, "value": 165.0},
        {"nutrientId": 1003, "value": 31.0},
        {"nutrientId": 1004, "value": 3.6},
        {"nutrientId": 1005, "value": 0.0},
    ]
    with patch("tools.nutrition.requests.get", return_value=_mock_get(nutrients)):
        result = lookup_nutrition("chicken breast")

    assert result["kcal_per_100g"] == 165.0
    assert result["protein_g"] == 31.0
    assert result["fat_g"] == 3.6
    assert result["carbs_g"] == 0.0
    assert result["fdc_id"] == 123
    assert result["name"] == "Chicken breast"


def test_raises_on_no_match():
    mock = MagicMock()
    mock.raise_for_status = lambda: None
    mock.json.return_value = {"foods": []}
    with patch("tools.nutrition.requests.get", return_value=mock):
        with pytest.raises(ValueError, match="No USDA match"):
            lookup_nutrition("xyznonexistentfood123")


def test_raises_on_network_error():
    with patch("tools.nutrition.requests.get",
               side_effect=requests.ConnectionError("no internet")):
        with pytest.raises(RuntimeError, match="USDA API request failed"):
            lookup_nutrition("chicken")


def test_raises_on_timeout():
    with patch("tools.nutrition.requests.get",
               side_effect=requests.Timeout("timed out")):
        with pytest.raises(RuntimeError, match="USDA API request failed"):
            lookup_nutrition("chicken")


def test_missing_nutrient_defaults_to_zero():
    """If a nutrient is missing from USDA response, should default to 0 not crash."""
    nutrients = [
        {"nutrientId": 1008, "value": 165.0},
        # protein, fat, carbs missing entirely
    ]
    with patch("tools.nutrition.requests.get", return_value=_mock_get(nutrients)):
        result = lookup_nutrition("chicken breast no nutrients test")

    assert result["kcal_per_100g"] == 165.0
    assert result["protein_g"] == 0.0
    assert result["fat_g"] == 0.0
    assert result["carbs_g"] == 0.0


def test_cache_prevents_second_api_call():
    """Same food name should hit cache, not make a second request."""
    nutrients = [{"nutrientId": 1008, "value": 200.0}]
    with patch("tools.nutrition.requests.get", return_value=_mock_get(nutrients)) as mock_get:
        lookup_nutrition("unique_cache_test_food_xyz")
        lookup_nutrition("unique_cache_test_food_xyz")
        assert mock_get.call_count == 1