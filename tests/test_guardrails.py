# tests/test_guardrails.py
import pytest
from unittest.mock import patch, MagicMock
from tools.guardrails import validate_image, get_rejection_message


def _mock_response(json_text: str) -> MagicMock:
    mock = MagicMock()
    mock.text = json_text
    return mock


def _fake_image(tmp_path, name="meal.jpg") -> str:
    """Creates a fake image file for testing."""
    path = tmp_path / name
    path.write_bytes(b"fakejpegdata")
    return str(path)


# tests/test_guardrails.py — update all patch targets

def test_valid_food_image(tmp_path):
    with patch("tools.guardrails.genai.Client") as mock_client_class:
        mock_client_class.return_value.models.generate_content.return_value = _mock_response(
            '{"is_valid": true, "reason": "", "issue": "none"}'
        )
        result = validate_image(_fake_image(tmp_path))
    assert result["is_valid"] is True

def test_rejects_non_food(tmp_path):
    with patch("tools.guardrails.genai.Client") as mock_client_class:
        mock_client_class.return_value.models.generate_content.return_value = _mock_response(
            '{"is_valid": false, "reason": "No food visible", "issue": "not_food"}'
        )
        result = validate_image(_fake_image(tmp_path, "selfie.jpg"))
    assert result["is_valid"] is False
    assert result["issue"] == "not_food"

def test_rejects_blurry(tmp_path):
    with patch("tools.guardrails.genai.Client") as mock_client_class:
        mock_client_class.return_value.models.generate_content.return_value = _mock_response(
            '{"is_valid": false, "reason": "Too blurry", "issue": "too_blurry"}'
        )
        result = validate_image(_fake_image(tmp_path, "blurry.jpg"))
    assert result["is_valid"] is False

def test_rejects_raw_meat(tmp_path):
    with patch("tools.guardrails.genai.Client") as mock_client_class:
        mock_client_class.return_value.models.generate_content.return_value = _mock_response(
            '{"is_valid": false, "reason": "Raw meat", "issue": "raw_food"}'
        )
        result = validate_image(_fake_image(tmp_path, "rawmeat.jpg"))
    assert result["is_valid"] is False

def test_rejects_too_dark(tmp_path):
    with patch("tools.guardrails.genai.Client") as mock_client_class:
        mock_client_class.return_value.models.generate_content.return_value = _mock_response(
            '{"is_valid": false, "reason": "Too dark", "issue": "too_dark"}'
        )
        result = validate_image(_fake_image(tmp_path, "dark.jpg"))
    assert result["is_valid"] is False

def test_raises_on_api_failure(tmp_path):
    with patch("tools.guardrails.genai.Client") as mock_client_class:
        mock_client_class.return_value.models.generate_content.side_effect = Exception("API down")
        with pytest.raises(RuntimeError, match="Validation API call failed"):
            validate_image(_fake_image(tmp_path))

def test_raises_on_invalid_json(tmp_path):
    with patch("tools.guardrails.genai.Client") as mock_client_class:
        mock_client_class.return_value.models.generate_content.return_value = _mock_response(
            "Sure! This looks like a great meal photo."
        )
        with pytest.raises(ValueError, match="Could not parse validation response"):
            validate_image(_fake_image(tmp_path))