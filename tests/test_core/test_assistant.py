"""Tests de l'Assistant IA avec mock OpenAI."""

from unittest.mock import MagicMock, patch

import pytest

from leRH.core.assistants.manager import DEFAULT_INSTRUCTIONS, Assistant


@pytest.fixture
def mock_openai():
    with patch("leRH.core.assistants.manager.OpenAI") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


def test_assistant_init(mock_openai) -> None:
    a = Assistant(name="Test", country="Togo", activity="Dev")
    assert a.name == "Test"
    assert a.country == "Togo"
    assert a.activity == "Dev"


def test_assistant_default_instructions(mock_openai) -> None:
    a = Assistant()
    assert len(a.instructions) == len(DEFAULT_INSTRUCTIONS)


def test_interact_returns_text(mock_openai) -> None:
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Hello!"
    mock_openai.chat.completions.create.return_value = mock_response

    a = Assistant()
    result = a.interact("Hi")
    assert result == "Hello!"


def test_interact_with_history(mock_openai) -> None:
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Reply"
    mock_openai.chat.completions.create.return_value = mock_response

    a = Assistant()
    history = [{"role": "assistant", "content": "Previous response"}]
    result = a.interact_with_history("New message", history)
    assert result == "Reply"


def test_interact_returns_empty_on_api_error(mock_openai) -> None:
    from openai import APIError

    error = APIError("Test error", request=MagicMock(), body=None)
    error.status_code = 500
    mock_openai.chat.completions.create.side_effect = error

    a = Assistant()
    result = a.interact("Hi")
    assert "indisponible" in result


def test_interact_returns_error_on_exception(mock_openai) -> None:
    mock_openai.chat.completions.create.side_effect = Exception("Unexpected")

    a = Assistant()
    result = a.interact("Hi")
    assert "erreur" in result


def test_system_message_contains_info(mock_openai) -> None:
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "OK"
    mock_openai.chat.completions.create.return_value = mock_response

    a = Assistant(name="Koffi", country="Togo", activity="developer")
    a.interact("test")

    call_args = mock_openai.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    system_msg = messages[0]["content"]
    assert "Koffi" in system_msg
    assert "Togo" in system_msg
    assert "developer" in system_msg
