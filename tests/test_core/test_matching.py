"""Tests du module de matching."""

from leRH.core.matching.engine import Criterion, Matcher, MatchResult, _extract_words


class TestExtractWords:
    def test_from_list(self) -> None:
        words = _extract_words(["python", "javascript", "teamwork"])
        assert "python" in words
        assert "javascript" in words
        assert "teamwork" in words

    def test_from_dict(self) -> None:
        words = _extract_words({"skills": ["python"], "level": "senior"})
        assert "python" in words
        assert "senior" in words

    def test_from_string(self) -> None:
        words = _extract_words("5 years python experience")
        assert "python" in words
        assert "years" in words
        assert "experience" in words

    def test_removes_stopwords(self) -> None:
        words = _extract_words("the and of in to for")
        assert words == set()

    def test_none_input(self) -> None:
        assert _extract_words(None) == set()

    def test_empty_input(self) -> None:
        assert _extract_words("") == set()


class TestKeywordOverlap:
    def test_high_overlap(self) -> None:
        matcher = Matcher()
        score = matcher._keyword_overlap(
            ["python", "fastapi", "sql"],
            {"skills": ["python", "fastapi", "sql", "docker"]},
        )
        assert score >= 50

    def test_no_overlap(self) -> None:
        matcher = Matcher()
        score = matcher._keyword_overlap(
            ["cooking", "driving"],
            {"skills": ["python", "sql"]},
        )
        assert score < 50

    def test_both_empty(self) -> None:
        matcher = Matcher()
        score = matcher._keyword_overlap(None, None)
        assert score == 50.0

    def test_one_empty(self) -> None:
        matcher = Matcher()
        score = matcher._keyword_overlap(["python"], None)
        assert score == 50.0


class TestExtractJson:
    def test_valid_json(self) -> None:
        data = '{"criteria": [], "summary": "ok"}'
        result = Matcher._extract_json(data)
        assert result == {"criteria": [], "summary": "ok"}

    def test_json_in_text(self) -> None:
        data = 'Here is the result:\n{"summary": "test"}\nEnd'
        result = Matcher._extract_json(data)
        assert result == {"summary": "test"}

    def test_invalid_text(self) -> None:
        result = Matcher._extract_json("no json here")
        assert result is None


class TestRecommendation:
    def test_strong_match(self) -> None:
        assert Matcher._recommendation(85) == "strong_match"
        assert Matcher._recommendation(70) == "strong_match"

    def test_possible_match(self) -> None:
        assert Matcher._recommendation(55) == "possible_match"
        assert Matcher._recommendation(40) == "possible_match"

    def test_weak_match(self) -> None:
        assert Matcher._recommendation(35) == "weak_match"
        assert Matcher._recommendation(0) == "weak_match"


class TestBuildResult:
    def test_valid_data(self) -> None:
        data = {
            "criteria": [
                {"name": "skills", "score": 80, "weight": 0.30, "details": "Good match"},
                {"name": "experience", "score": 70, "weight": 0.30, "details": "Relevant"},
            ],
            "summary": "Good fit overall",
            "recommendation": "strong_match",
        }
        result = Matcher._build_result("c1", "j1", data)
        assert result.candidate_id == "c1"
        assert result.job_id == "j1"
        assert result.overall_score == 45.0
        assert result.summary == "Good fit overall"
        assert result.recommendation == "strong_match"
        assert len(result.criteria) == 2

    def test_empty_criteria(self) -> None:
        data = {"criteria": [], "summary": "", "recommendation": "weak_match"}
        result = Matcher._build_result("c1", "j1", data)
        assert result.overall_score == 0

    def test_missing_fields(self) -> None:
        result = Matcher._build_result("c1", "j1", {})
        assert result.overall_score == 0
        assert result.criteria == []


class TestCriterion:
    def test_creation(self) -> None:
        c = Criterion(name="skills", score=85.0, weight=0.30, details="Good")
        assert c.name == "skills"
        assert c.score == 85.0
        assert c.weight == 0.30


class TestMatchResult:
    def test_defaults(self) -> None:
        r = MatchResult(candidate_id="c1", job_id="j1", overall_score=75.0)
        assert r.criteria == []
        assert r.summary == ""
        assert r.recommendation == "possible_match"
        assert r.llm_enhanced is False
