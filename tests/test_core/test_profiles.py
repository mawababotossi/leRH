"""Tests du ProfileExtractor."""

from leRH.core.profiles.extractor import ProfileExtractor
from leRH.db.models import User


class TestParseJson:
    def test_valid_json(self) -> None:
        data = '{"skills": ["python"], "diploma": "Master"}'
        result = ProfileExtractor._parse_json(data)
        assert result == {"skills": ["python"], "diploma": "Master"}

    def test_json_in_text(self) -> None:
        data = 'Here is:\n{"skills": ["python"]}\nDone.'
        result = ProfileExtractor._parse_json(data)
        assert result == {"skills": ["python"]}

    def test_invalid(self) -> None:
        assert ProfileExtractor._parse_json("nope") is None


class TestEnrichUser:
    def test_enriches_all_fields(self) -> None:
        user = User(name="Test")
        data = {
            "skills": ["python", "sql"],
            "diploma": "Master",
            "experience": "5 years dev",
            "languages": [{"language": "French", "level": "native"}],
        }
        result = ProfileExtractor.enrich_user(user, data)
        assert result.skills == ["python", "sql"]
        assert result.diploma == "Master"
        assert result.experience == "5 years dev"
        assert result.languages == [{"language": "French", "level": "native"}]

    def test_skips_none_fields(self) -> None:
        user = User(name="Test", skills=["existing"])
        data = {"skills": None, "diploma": "Bachelor"}
        result = ProfileExtractor.enrich_user(user, data)
        assert result.skills == ["existing"]
        assert result.diploma == "Bachelor"

    def test_empty_data(self) -> None:
        user = User(name="Test", skills=["keep"])
        result = ProfileExtractor.enrich_user(user, {})
        assert result.skills == ["keep"]
