"""Tests du générateur de documents."""

from leRH.core.documents.generator import DocumentGenerator, GeneratedCV
from leRH.db.models import User


class TestCertificationFiltering:
    def test_removes_hallucinated_certifications_when_source_has_none(self) -> None:
        generated = [
            "Certification AWS Cloud Practitioner — Amazon Web Services — 2023",
            "Certification Kubernetes Administrator (CKA) — CNCF — 2022",
        ]

        assert DocumentGenerator._filter_certifications(generated, {"profile": {}}) == []

    def test_keeps_certifications_present_in_source(self) -> None:
        cv_analysis = {
            "profile": {
                "certifications": [
                    "Oracle Infrastructure as a Service 2017 Certified Implementation Specialist"
                ]
            }
        }
        generated = [
            "Oracle Infrastructure as a Service — Oracle University — 2017",
            "Certification AWS Cloud Practitioner — Amazon Web Services — 2023",
        ]

        assert DocumentGenerator._filter_certifications(generated, cv_analysis) == [
            "Oracle Infrastructure as a Service — Oracle University — 2017"
        ]

    def test_extracts_certifying_training_from_education_for_legacy_data(self) -> None:
        cv_analysis = {
            "profile": {
                "education": [
                    {
                        "degree": "Formation certifiante",
                        "field": "Oracle Infrastructure as a Service",
                        "institution": "Oracle University",
                        "year": "2017",
                    }
                ]
            }
        }

        assert DocumentGenerator._extract_allowed_certifications(cv_analysis) == [
            "Formation certifiante Oracle Infrastructure as a Service Oracle University 2017"
        ]


class TestGeneratedCVSanitizing:
    def test_removes_unsupported_facts_beyond_certifications(self) -> None:
        user = User(name="BOTOSSI Mawaba")
        cv_analysis = {
            "analysis": "Consultant DevOps Cloud spécialisé en plateformes climatiques.",
            "source_text": (
                "BOTOSSI Mawaba. Cloud Computing AWS Azure Oracle. Kubernetes Docker. "
                "Consultant DevOps Cloud au Ministère de l'Environnement, 2022 - 2023. "
                "Conception de la plateforme climatique du Togo. "
                "Master Professionnel en Droit du Cyberespace africain, "
                "Université Gaston Berger, 2013. Français excellent. Anglais moyen."
            ),
            "profile": {
                "skills": ["Cloud Computing", "AWS", "Azure", "Oracle", "Kubernetes", "Docker"],
                "experiences": [
                    {
                        "company": "Ministère de l'Environnement",
                        "location": "Togo",
                        "title": "Consultant DevOps Cloud",
                        "start_date": "2022",
                        "end_date": "2023",
                        "description": "Conception de la plateforme climatique du Togo.",
                    }
                ],
                "education": [
                    {
                        "degree": "Master Professionnel",
                        "field": "Droit du Cyberespace africain",
                        "institution": "Université Gaston Berger",
                        "year": "2013",
                    }
                ],
                "languages": [
                    {"language": "Français", "level": "Excellent"},
                    {"language": "Anglais", "level": "Moyen"},
                ],
            },
        }
        generated = GeneratedCV(
            summary=(
                "Consultant cloud avec 8 ans d'expérience. "
                "A réduit les coûts de 30% pour 50 000 utilisateurs."
            ),
            core_competencies=[
                "Cloud Computing",
                "Kubernetes",
                "Recrutement (Togo)",
            ],
            experience=[
                {
                    "company": "Ministère de l'Environnement",
                    "location": "Lomé, Togo",
                    "title": "Architecte Logiciel",
                    "start_date": "01/2022",
                    "end_date": "12/2023",
                    "bullets": [
                        "Conçu une plateforme pour 50 000 utilisateurs et réduit les coûts de 30%."
                    ],
                },
                {
                    "company": "DizzitUp SAS",
                    "location": "Lomé, Togo",
                    "title": "Administrateur Système",
                    "start_date": "2022",
                    "end_date": "2023",
                    "bullets": ["Sécurisé 12 entreprises clientes."],
                },
            ],
            education=[
                {
                    "degree": "Master Professionnel en Droit du Cyberespace africain",
                    "institution": "Université Gaston Berger",
                    "year": "2013",
                },
                {
                    "degree": "StartUp Engineering",
                    "institution": "Stanford University",
                    "year": "2014",
                },
            ],
            certifications=[],
            languages=[
                "Français (C2 - Natif)",
                "Anglais (B2 - Courant)",
                "Ewe (C1 - Courant)",
            ],
        )

        generator = DocumentGenerator.__new__(DocumentGenerator)
        sanitized = generator._sanitize_generated_cv(
            generated,
            user,
            cv_analysis,
            DocumentGenerator._source_text_from_analysis(cv_analysis),
        )

        assert sanitized.summary == "Consultant DevOps Cloud spécialisé en plateformes climatiques."
        assert sanitized.core_competencies == ["Cloud Computing", "Kubernetes"]
        assert len(sanitized.experience) == 1
        assert sanitized.experience[0]["company"] == "Ministère de l'Environnement"
        assert sanitized.experience[0]["title"] == "Consultant DevOps Cloud"
        assert sanitized.experience[0]["start_date"] == "2022"
        assert sanitized.experience[0]["end_date"] == "2023"
        assert sanitized.experience[0]["bullets"] == [
            "Conception de la plateforme climatique du Togo."
        ]
        assert sanitized.education == [
            {
                "degree": "Master Professionnel en Droit du Cyberespace africain",
                "institution": "Université Gaston Berger",
                "year": "2013",
            }
        ]
        assert sanitized.languages == ["Français (C2 - Natif)", "Anglais (B2 - Courant)"]
