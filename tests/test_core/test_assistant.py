"""Tests de l'Assistant IA avec mock OpenAI."""

import json
from unittest.mock import MagicMock, patch

import pytest

import leRH.core.assistants.manager as assistant_manager
from leRH.core.assistants.manager import DEFAULT_INSTRUCTIONS, Assistant
from leRH.db.models import Job


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


def test_whatsapp_safe_format_keeps_native_formatting(mock_openai) -> None:
    text = (
        "### Détails\n"
        "*Chef Pâtissier*\n"
        "Compétences en **sécurité** et _réseau_.\n"
        "Lien : [postuler](https://example.com/offre)\n"
        "`Réf: abc123`"
    )

    assert Assistant._whatsapp_safe_format(text) == (
        "Détails\n"
        "*Chef Pâtissier*\n"
        "Compétences en *sécurité* et _réseau_.\n"
        "Lien : https://example.com/offre\n"
        "Réf: abc123"
    )


def test_whatsapp_safe_format_removes_unbalanced_markers(mock_openai) -> None:
    text = "*réseaux (LAN/WAN), **sécurité, et **administration système*"

    assert Assistant._whatsapp_safe_format(text) == (
        "réseaux (LAN/WAN), sécurité, et administration système"
    )


def _text_response(content: str):
    mock_response = MagicMock()
    mock_response.choices[0].message.content = content
    mock_response.choices[0].message.tool_calls = None
    mock_response.choices[0].finish_reason = "stop"
    return mock_response


@pytest.mark.asyncio
async def test_interact_returns_text(mock_openai) -> None:
    mock_response = _text_response("Hello!")
    mock_openai.chat.completions.create.return_value = mock_response

    a = Assistant()
    result = await a.interact("Hi")
    assert result == "Hello!"


@pytest.mark.asyncio
async def test_interact_strips_markdown_for_whatsapp(mock_openai) -> None:
    mock_response = _text_response("*Bonjour* [lien](https://example.com)")
    mock_openai.chat.completions.create.return_value = mock_response

    a = Assistant(platform="whatsapp")
    result = await a.interact("Hi")
    assert result == "*Bonjour* https://example.com"


@pytest.mark.asyncio
async def test_interact_with_history(mock_openai) -> None:
    mock_response = _text_response("Reply")
    mock_openai.chat.completions.create.return_value = mock_response

    a = Assistant()
    history = [{"role": "assistant", "content": "Previous response"}]
    result = await a.interact_with_history("New message", history)
    assert result == "Reply"


@pytest.mark.asyncio
async def test_interact_returns_empty_on_api_error(mock_openai) -> None:
    from openai import APIError

    error = APIError("Test error", request=MagicMock(), body=None)
    error.status_code = 500
    mock_openai.chat.completions.create.side_effect = error

    a = Assistant()
    result = await a.interact("Hi")
    assert "indisponible" in result


@pytest.mark.asyncio
async def test_interact_handles_api_connection_error_without_status_code(mock_openai) -> None:
    from openai import APIConnectionError

    error = APIConnectionError(request=MagicMock())
    mock_openai.chat.completions.create.side_effect = error

    a = Assistant()
    result = await a.interact("Hi")
    assert "indisponible" in result


@pytest.mark.asyncio
async def test_interact_returns_error_on_exception(mock_openai) -> None:
    mock_openai.chat.completions.create.side_effect = Exception("Unexpected")

    a = Assistant()
    result = await a.interact("Hi")
    assert "erreur" in result


@pytest.mark.asyncio
async def test_system_message_contains_info(mock_openai) -> None:
    mock_response = _text_response("OK")
    mock_openai.chat.completions.create.return_value = mock_response

    a = Assistant(name="Koffi", country="Togo", activity="developer")
    await a.interact("test")

    call_args = mock_openai.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    system_msg = messages[0]["content"]
    assert "Koffi" in system_msg
    assert "Togo" in system_msg
    assert "developer" in system_msg


class _ToolCall:
    def __init__(self, name: str, arguments: dict) -> None:
        self.function = MagicMock()
        self.function.name = name
        self.function.arguments = json.dumps(arguments)


@pytest.mark.asyncio
async def test_search_local_jobs_returns_source_url_and_details(mock_openai) -> None:
    job = Job(
        id="jet123",
        title="Chef Pâtissier - Lomé",
        company="JET CAFÉ",
        city="Lomé",
        description="Missions : préparer des desserts et gérer la pâtisserie.",
        source_url="https://www.emploi.tg/offre-emploi-togo/chef-patissier-lome-376171",
        source_name="Emploi.tg",
        status="active",
        requirements={
            "Type de contrat": "CDI - CDD",
            "Salaire proposé": "< 150 000 FCFA",
            "skills": ["Pâtisserie", "Hygiène alimentaire"],
        },
    )
    assistant = Assistant(local_jobs=[job])

    raw = await assistant._handle_tool_call(
        _ToolCall("search_local_jobs", {"keywords": "cuisinier pâtissier"})
    )

    data = json.loads(raw)
    assert data[0]["id"] == "jet123"
    assert data[0]["source_url"] == job.source_url
    assert data[0]["contract_type"] == "CDI - CDD"
    assert data[0]["salary"] == "< 150 000 FCFA"


def test_search_local_jobs_randomizes_equal_score_before_limit(mock_openai, monkeypatch) -> None:
    jobs = [
        Job(
            id=f"job{i}",
            title="Développeur Python",
            description="Poste Python backend.",
            status="active",
        )
        for i in range(6)
    ]
    assistant = Assistant(local_jobs=jobs)

    def reverse_matches(matches):
        matches.reverse()

    monkeypatch.setattr(assistant_manager.random, "shuffle", reverse_matches)

    results = assistant._search_local_jobs("python", max_results=3)

    assert [job.id for job in results] == ["job5", "job4", "job3"]


@pytest.mark.asyncio
async def test_get_job_details_returns_full_offer_link(mock_openai) -> None:
    job = Job(
        id="jet123",
        title="Chef Pâtissier - Lomé",
        company="JET CAFÉ",
        city="Lomé",
        description="Description complète de l'annonce avec missions et profil recherché.",
        source_url="https://www.emploi.tg/offre-emploi-togo/chef-patissier-lome-376171",
        source_name="Emploi.tg",
        status="active",
        requirements={"Nombre de poste(s)": "1"},
    )
    assistant = Assistant(local_jobs=[job])

    raw = await assistant._handle_tool_call(_ToolCall("get_job_details", {"job_id": "jet123"}))

    data = json.loads(raw)
    assert data["title"] == "Chef Pâtissier - Lomé"
    assert data["company"] == "JET CAFÉ"
    assert data["source_url"] == job.source_url
    assert data["requirements"] == {"Nombre de poste(s)": "1"}


@pytest.mark.asyncio
async def test_document_for_other_person_requires_target_profile(mock_openai) -> None:
    job = Job(
        id="jet123",
        title="Chef Pâtissier - Lomé",
        company="JET CAFÉ",
        city="Lomé",
        description="Offre pâtisserie.",
        status="active",
    )
    assistant = Assistant(
        name="BOTOSSI Mawaba",
        activity="Architecte IT",
        local_jobs=[job],
        user_id="user123",
        credits=10,
    )

    raw = await assistant._handle_document_tool(
        "generate_cover_letter",
        {
            "job_id": "jet123",
            "confirmed": True,
            "beneficiary_type": "other",
            "target_profile": {"activity": "Cuisinier"},
        },
    )

    data = json.loads(raw)
    assert data["needs_target_profile"] is True
    assert "nom/prénom" in data["error"]
    assert "compétences" in data["error"]
