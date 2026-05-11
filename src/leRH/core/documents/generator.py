from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from fpdf import FPDF
from openai import OpenAI

from leRH.config import settings
from leRH.db.models import Job, User

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "data"
GENERATED_DIR = DATA_DIR / "generated"

_FONT_PATHS = [
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
]
_BOLD_FONT_PATHS = [
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
]

FONT_PATH = next((p for p in _FONT_PATHS if Path(p).exists()), None)
BOLD_FONT_PATH = next((p for p in _BOLD_FONT_PATHS if Path(p).exists()), None)
PDF_FONT = "DejaVu" if FONT_PATH and BOLD_FONT_PATH else "Helvetica"

CV_GENERATION_PROMPT = """You are an expert resume writer specializing in ATS (Applicant Tracking System) optimization. Generate a tailored, ATS-friendly CV in French for the candidate based on their profile and the target job.

ATS RULES — STRICTLY FOLLOW:
- Use standard section headers: "Résumé Professionnel", "Compétences Clés", "Expérience Professionnelle", "Formation"
- No graphics, images, tables, columns, headers/footers
- Simple bullet points (standard dash -)
- Include keywords from the job description naturally throughout
- Use both abbreviations and full terms (e.g., "SEO (Search Engine Optimization)")
- Quantify achievements with numbers where possible
- Reverse chronological order for experience (max 10-15 years)

CANDIDATE PROFILE:
{profile}

TARGET JOB:
{job}

Respond with ONLY a valid JSON object (no other text):
{{
  "summary": "Professional summary in French, 3-5 sentences, integrating key requirements from the job.",
  "core_competencies": ["skill1", "skill2", ...],
  "experience": [
    {{
      "company": "Company name",
      "location": "City",
      "title": "Job title",
      "start_date": "MM/YYYY",
      "end_date": "MM/YYYY or 'Présent'",
      "bullets": ["Achievement with keyword integration", ...]
    }}
  ],
  "education": [
    {{
      "degree": "Degree name",
      "institution": "Institution name",
      "year": "Year or 'En cours'"
    }}
  ],
  "certifications": ["cert1", ...],
  "languages": ["Langue (Niveau)", ...]
}}

If experience is empty, use [] for the array. If education is empty, use []. Ensure all text is in French."""

COVER_LETTER_PROMPT = """You are an expert in writing professional cover letters in French. Write a tailored cover letter for the candidate based on their profile and the target job.

CANDIDATE PROFILE:
{profile}

TARGET JOB:
{job}

MATCH ANALYSIS (optional):
{match_analysis}

Rules:
- Professional and warm tone in French
- Opening paragraph: express interest in the specific role and company
- Body paragraph 1: connect candidate's key skills to job requirements
- Body paragraph 2: additional relevant experience or motivation
- Closing paragraph: call to action, availability for interview, thank you
- Include the job title and company name naturally
- Max 4 paragraphs, concise

Respond with ONLY a valid JSON object (no other text):
{{
  "recipient": "À l'attention du recruteur" or specific if known,
  "subject": "Candidature au poste de [Job Title]",
  "body_paragraphs": ["Paragraph 1", "Paragraph 2", "Paragraph 3", "Paragraph 4"],
  "closing": "Sincères salutations" or similar
}}

Ensure all text is in French."""


@dataclass
class GeneratedCV:
    summary: str
    core_competencies: list[str]
    experience: list[dict]
    education: list[dict]
    certifications: list[str]
    languages: list[str]


@dataclass
class GeneratedCoverLetter:
    recipient: str
    subject: str
    body_paragraphs: list[str]
    closing: str


class DocumentGenerationError(Exception):
    pass


class DocumentGenerator:
    def __init__(self) -> None:
        self._client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.openai_timeout,
        )
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    def _build_profile_text(self, user: User) -> str:
        parts = [f"Nom: {user.name}"]
        if user.activity:
            parts.append(f"Titre actuel: {user.activity}")
        if user.city:
            parts.append(f"Localisation: {user.city}")
        if user.country:
            parts.append(f"Pays: {user.country}")
        if user.diploma:
            parts.append(f"Diplôme: {user.diploma}")
        if user.experience:
            parts.append(f"Expérience: {user.experience}")
        if user.skills:
            skills = user.skills
            if isinstance(skills, list):
                parts.append(f"Compétences: {', '.join(skills)}")
            elif isinstance(skills, dict):
                parts.append(f"Compétences: {json.dumps(skills, ensure_ascii=False)}")
        if user.languages:
            langs = user.languages
            if isinstance(langs, list):
                lang_strs = []
                for lang in langs:
                    if isinstance(lang, dict):
                        lang_strs.append(f"{lang.get('language', '')} ({lang.get('level', '')})")
                    else:
                        lang_strs.append(str(lang))
                parts.append(f"Langues: {', '.join(lang_strs)}")
        if user.phone:
            parts.append(f"Téléphone: {user.phone}")
        return "\n".join(parts)

    def _build_job_text(self, job: Job) -> str:
        parts = [
            f"Titre du poste: {job.title}",
            f"Description: {job.description}",
        ]
        if job.company:
            parts.append(f"Entreprise: {job.company}")
        if job.city:
            parts.append(f"Ville: {job.city}")
        if job.salary_min or job.salary_max:
            parts.append(f"Salaire: {job.salary_min or ''} - {job.salary_max or ''}")
        if job.requirements:
            reqs = job.requirements
            if isinstance(reqs, dict):
                parts.append(f"Prérequis: {json.dumps(reqs, ensure_ascii=False)}")
            else:
                parts.append(f"Prérequis: {reqs}")
        return "\n".join(parts)

    def _call_llm(self, prompt: str, system_prompt: str, max_tokens: int = 2048) -> str:
        try:
            response = self._client.chat.completions.create(
                model=settings.llm_model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
        except Exception:
            logger.exception("LLM call failed during document generation")
            raise DocumentGenerationError(
                "Le service IA est temporairement indisponible."
            ) from None

    def _parse_json(self, content: str) -> dict | None:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None

    def generate_cv_content(self, user: User, job: Job) -> GeneratedCV:
        profile_text = self._build_profile_text(user)
        job_text = self._build_job_text(job)
        prompt = CV_GENERATION_PROMPT.format(profile=profile_text, job=job_text)

        content = self._call_llm(
            prompt,
            "You generate ATS-optimized CVs in French. Return ONLY valid JSON.",
        )
        data = self._parse_json(content)
        if not data:
            raise DocumentGenerationError("Impossible de générer le contenu du CV.")

        return GeneratedCV(
            summary=data.get("summary", ""),
            core_competencies=data.get("core_competencies", []),
            experience=data.get("experience", []),
            education=data.get("education", []),
            certifications=data.get("certifications", []),
            languages=data.get("languages", []),
        )

    def generate_cover_letter_content(
        self, user: User, job: Job, match_analysis: str | None = None
    ) -> GeneratedCoverLetter:
        profile_text = self._build_profile_text(user)
        job_text = self._build_job_text(job)
        prompt = COVER_LETTER_PROMPT.format(
            profile=profile_text,
            job=job_text,
            match_analysis=match_analysis or "Non disponible",
        )

        content = self._call_llm(
            prompt,
            "You write professional cover letters in French. Return ONLY valid JSON.",
        )
        data = self._parse_json(content)
        if not data:
            raise DocumentGenerationError("Impossible de générer la lettre de motivation.")

        return GeneratedCoverLetter(
            recipient=data.get("recipient", "À l'attention du recruteur"),
            subject=data.get("subject", ""),
            body_paragraphs=data.get("body_paragraphs", []),
            closing=data.get("closing", "Sincères salutations"),
        )

    def _set_cell_font(self, cell, name: str = "Calibri", size: int = 11, bold: bool = False):
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.font.name = name
                run.font.size = Pt(size)
                run.font.bold = bold

    def build_cv_docx(self, cv: GeneratedCV, user: User, job: Job) -> BytesIO:
        doc = Document()

        style = doc.styles["Normal"]
        style.font.name = "Calibri"
        style.font.size = Pt(11)
        style.paragraph_format.space_after = Pt(4)
        style.paragraph_format.space_before = Pt(0)

        for section in doc.sections:
            section.top_margin = Inches(0.7)
            section.bottom_margin = Inches(0.7)
            section.left_margin = Inches(0.8)
            section.right_margin = Inches(0.8)

        name_para = doc.add_paragraph()
        name_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        name_run = name_para.add_run(user.name)
        name_run.font.name = "Calibri"
        name_run.font.size = Pt(20)
        name_run.bold = True
        name_run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x1A)

        contact_parts = []
        if user.phone:
            contact_parts.append(user.phone)
        if user.city:
            contact_parts.append(user.city)
        contact_parts.append("Email: disponible sur demande")
        contact_para = doc.add_paragraph()
        contact_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        contact_run = contact_para.add_run(" | ".join(contact_parts))
        contact_run.font.name = "Calibri"
        contact_run.font.size = Pt(10)
        contact_run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

        self._add_section_heading(doc, "Résumé Professionnel")
        summary_para = doc.add_paragraph()
        summary_run = summary_para.add_run(cv.summary)
        summary_run.font.name = "Calibri"
        summary_run.font.size = Pt(11)

        if cv.core_competencies:
            self._add_section_heading(doc, "Compétences Clés")
            comps = ", ".join(cv.core_competencies)
            comp_para = doc.add_paragraph()
            comp_run = comp_para.add_run(comps)
            comp_run.font.name = "Calibri"
            comp_run.font.size = Pt(11)

        if cv.experience:
            self._add_section_heading(doc, "Expérience Professionnelle")
            for exp in cv.experience:
                company = exp.get("company", "")
                location = exp.get("location", "")
                title = exp.get("title", "")
                start = exp.get("start_date", "")
                end = exp.get("end_date", "")

                header_para = doc.add_paragraph()
                company_run = header_para.add_run(f"{company}")
                company_run.font.name = "Calibri"
                company_run.font.size = Pt(12)
                company_run.bold = True
                if location:
                    loc_run = header_para.add_run(f"  |  {location}")
                    loc_run.font.name = "Calibri"
                    loc_run.font.size = Pt(11)
                    loc_run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

                title_para = doc.add_paragraph()
                title_run = title_para.add_run(f"{title}")
                title_run.font.name = "Calibri"
                title_run.font.size = Pt(11)
                title_run.italic = True
                if start or end:
                    date_run = title_para.add_run(f"  |  {start} - {end}")
                    date_run.font.name = "Calibri"
                    date_run.font.size = Pt(10)
                    date_run.font.color.rgb = RGBColor(0x77, 0x77, 0x77)

                for bullet in exp.get("bullets", []):
                    bp = doc.add_paragraph(bullet, style="List Bullet")
                    for run in bp.runs:
                        run.font.name = "Calibri"
                        run.font.size = Pt(11)

        if cv.education:
            self._add_section_heading(doc, "Formation")
            for edu in cv.education:
                degree = edu.get("degree", "")
                institution = edu.get("institution", "")
                year = edu.get("year", "")

                edu_para = doc.add_paragraph()
                deg_run = edu_para.add_run(f"{degree}")
                deg_run.font.name = "Calibri"
                deg_run.font.size = Pt(11)
                deg_run.bold = True
                if institution:
                    inst_run = edu_para.add_run(f"  —  {institution}")
                    inst_run.font.name = "Calibri"
                    inst_run.font.size = Pt(11)
                if year and year.lower() not in ("", "en cours"):
                    year_run = edu_para.add_run(f"  ({year})")
                    year_run.font.name = "Calibri"
                    year_run.font.size = Pt(10)
                    year_run.font.color.rgb = RGBColor(0x77, 0x77, 0x77)

        certs_and_langs = []
        if cv.certifications:
            certs_and_langs.extend(cv.certifications)
        if cv.languages:
            certs_and_langs.extend(cv.languages)

        if certs_and_langs:
            self._add_section_heading(doc, "Langues & Certifications")
            for item in certs_and_langs:
                item_para = doc.add_paragraph(item, style="List Bullet")
                for run in item_para.runs:
                    run.font.name = "Calibri"
                    run.font.size = Pt(11)

        buf = BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf

    def build_cover_letter_docx(
        self, letter: GeneratedCoverLetter, user: User, job: Job
    ) -> BytesIO:
        doc = Document()

        style = doc.styles["Normal"]
        style.font.name = "Calibri"
        style.font.size = Pt(11)
        style.paragraph_format.space_after = Pt(6)
        style.paragraph_format.line_spacing = 1.15

        for section in doc.sections:
            section.top_margin = Inches(1.0)
            section.bottom_margin = Inches(1.0)
            section.left_margin = Inches(1.0)
            section.right_margin = Inches(1.0)

        today = datetime.now().strftime("%d %B %Y")
        date_para = doc.add_paragraph(today)
        date_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        for run in date_para.runs:
            run.font.name = "Calibri"
            run.font.size = Pt(11)

        doc.add_paragraph()

        subject_para = doc.add_paragraph()
        subj_run = subject_para.add_run(letter.subject)
        subj_run.font.name = "Calibri"
        subj_run.font.size = Pt(12)
        subj_run.bold = True

        doc.add_paragraph()

        body = letter.body_paragraphs or []
        for para_text in body:
            para = doc.add_paragraph(para_text)
            para.paragraph_format.first_line_indent = Inches(0.3)
            for run in para.runs:
                run.font.name = "Calibri"
                run.font.size = Pt(11)

        doc.add_paragraph()

        closing_para = doc.add_paragraph(letter.closing)
        for run in closing_para.runs:
            run.font.name = "Calibri"
            run.font.size = Pt(11)

        doc.add_paragraph()
        name_para = doc.add_paragraph(user.name)
        for run in name_para.runs:
            run.font.name = "Calibri"
            run.font.size = Pt(11)
            run.bold = True

        if user.phone:
            phone_para = doc.add_paragraph(user.phone)
            for run in phone_para.runs:
                run.font.name = "Calibri"
                run.font.size = Pt(10)
                run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

        buf = BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf

    def _add_section_heading(self, doc: Document, text: str) -> None:
        para = doc.add_paragraph()
        run = para.add_run(text)
        run.font.name = "Calibri"
        run.font.size = Pt(13)
        run.bold = True
        run.font.color.rgb = RGBColor(0x1A, 0x56, 0x8E)
        fmt = para.paragraph_format
        fmt.space_before = Pt(10)
        fmt.space_after = Pt(4)

        ppr = para._p.get_or_add_pPr()
        pbdr = ppr.makeelement(qn("w:pBdr"), {})
        bottom = pbdr.makeelement(
            qn("w:bottom"),
            {
                qn("w:val"): "single",
                qn("w:sz"): "6",
                qn("w:space"): "1",
                qn("w:color"): "1A568E",
            },
        )
        pbdr.append(bottom)
        ppr.append(pbdr)

    def build_cv_pdf(self, cv: GeneratedCV, user: User, job: Job) -> BytesIO:
        pdf = FPDF()
        pdf.add_page()

        margin = 20
        pdf.set_margins(margin, margin, margin)
        pdf.set_auto_page_break(auto=True, margin=20)

        if FONT_PATH and BOLD_FONT_PATH:
            pdf.add_font("DejaVu", "", FONT_PATH, uni=True)
            pdf.add_font("DejaVu", "B", BOLD_FONT_PATH, uni=True)
        else:
            logger.warning("DejaVu fonts not found, using built-in Helvetica")

        pdf.set_font(PDF_FONT, "B", 18)
        pdf.cell(0, 10, user.name, new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(2)

        contact_parts = []
        if user.phone:
            contact_parts.append(user.phone)
        if user.city:
            contact_parts.append(user.city)
        contact_parts.append("Email: disponible sur demande")

        pdf.set_font(PDF_FONT, "", 9)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 6, " | ".join(contact_parts), new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(4)

        self._pdf_section(pdf, "Résumé Professionnel")
        pdf.set_font(PDF_FONT, "", 10)
        pdf.multi_cell(0, 5.5, cv.summary)
        pdf.ln(2)

        if cv.core_competencies:
            self._pdf_section(pdf, "Compétences Clés")
            pdf.set_font(PDF_FONT, "", 10)
            comps = ", ".join(cv.core_competencies)
            pdf.multi_cell(0, 5.5, comps)
            pdf.ln(2)

        if cv.experience:
            self._pdf_section(pdf, "Expérience Professionnelle")
            for exp in cv.experience:
                company = exp.get("company", "")
                location = exp.get("location", "")
                title = exp.get("title", "")
                start = exp.get("start_date", "")
                end = exp.get("end_date", "")

                pdf.set_font(PDF_FONT, "B", 11)
                line = company
                if location:
                    line += f"  |  {location}"
                pdf.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")

                pdf.set_font(PDF_FONT, "I", 10)
                line2 = title
                if start or end:
                    line2 += f"  —  {start} - {end}"
                pdf.cell(0, 5.5, line2, new_x="LMARGIN", new_y="NEXT")
                pdf.ln(1)

                pdf.set_font(PDF_FONT, "", 10)
                for bullet in exp.get("bullets", []):
                    pdf.cell(5)
                    pdf.multi_cell(0, 5, f"- {bullet}")
                pdf.ln(2)

        if cv.education:
            self._pdf_section(pdf, "Formation")
            for edu in cv.education:
                degree = edu.get("degree", "")
                institution = edu.get("institution", "")
                year = edu.get("year", "")

                pdf.set_font(PDF_FONT, "B", 10)
                line = degree
                if institution:
                    line += f"  —  {institution}"
                pdf.cell(0, 5.5, line, new_x="LMARGIN", new_y="NEXT")

                if year and year.lower() not in ("", "en cours"):
                    pdf.set_font(PDF_FONT, "", 9)
                    pdf.set_text_color(100, 100, 100)
                    pdf.cell(0, 5, f"({year})", new_x="LMARGIN", new_y="NEXT")
                    pdf.set_text_color(0, 0, 0)
                pdf.ln(1)

        certs_and_langs = []
        if cv.certifications:
            certs_and_langs.extend(cv.certifications)
        if cv.languages:
            certs_and_langs.extend(cv.languages)

        if certs_and_langs:
            self._pdf_section(pdf, "Langues & Certifications")
            pdf.set_font(PDF_FONT, "", 10)
            for item in certs_and_langs:
                pdf.cell(5)
                pdf.multi_cell(0, 5.5, f"- {item}")
            pdf.ln(2)

        buf = BytesIO()
        pdf.output(buf)
        buf.seek(0)
        return buf

    def build_cover_letter_pdf(self, letter: GeneratedCoverLetter, user: User, job: Job) -> BytesIO:
        pdf = FPDF()
        pdf.add_page()

        margin = 25
        pdf.set_margins(margin, margin, margin)
        pdf.set_auto_page_break(auto=True, margin=20)

        if FONT_PATH and BOLD_FONT_PATH:
            pdf.add_font("DejaVu", "", FONT_PATH, uni=True)
            pdf.add_font("DejaVu", "B", BOLD_FONT_PATH, uni=True)

        today = datetime.now().strftime("%d %B %Y")
        pdf.set_font(PDF_FONT, "", 10)
        pdf.cell(0, 6, today, new_x="LMARGIN", new_y="NEXT", align="R")
        pdf.ln(8)

        pdf.set_font(PDF_FONT, "B", 12)
        pdf.multi_cell(0, 6, letter.subject)
        pdf.ln(6)

        pdf.set_font(PDF_FONT, "", 11)
        for para_text in letter.body_paragraphs:
            pdf.multi_cell(0, 6, para_text)
            pdf.ln(3)

        pdf.ln(4)
        pdf.set_font(PDF_FONT, "", 11)
        pdf.multi_cell(0, 6, letter.closing)
        pdf.ln(8)

        pdf.set_font(PDF_FONT, "B", 11)
        pdf.cell(0, 6, user.name, new_x="LMARGIN", new_y="NEXT")
        if user.phone:
            pdf.set_font(PDF_FONT, "", 9)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(0, 5, user.phone, new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)

        buf = BytesIO()
        pdf.output(buf)
        buf.seek(0)
        return buf

    def _pdf_section(self, pdf: FPDF, title: str) -> None:
        pdf.set_font(PDF_FONT, "B", 12)
        pdf.set_text_color(26, 86, 142)
        pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(26, 86, 142)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(3)
        pdf.set_text_color(0, 0, 0)

    def generate_cv(self, user: User, job: Job, fmt: str = "docx") -> tuple[BytesIO, str]:
        logger.info(
            f"Génération du CV pour {user.name} (user_id={user.id}) - Poste: {job.title} (job_id={job.id})"
        )
        cv = self.generate_cv_content(user, job)
        filename = f"CV_{user.name.replace(' ', '_')}_{job.title.replace(' ', '_')}".replace(
            "/", "_"
        )[:80]

        if fmt == "pdf":
            buf = self.build_cv_pdf(cv, user, job)
            return buf, f"{filename}.pdf"

        buf = self.build_cv_docx(cv, user, job)
        return buf, f"{filename}.docx"

    def generate_cover_letter(
        self, user: User, job: Job, fmt: str = "docx", match_analysis: str | None = None
    ) -> tuple[BytesIO, str]:
        logger.info(
            f"Génération de la lettre de motivation pour {user.name} (user_id={user.id}) - Poste: {job.title} (job_id={job.id})"
        )
        letter = self.generate_cover_letter_content(user, job, match_analysis)
        filename = f"Lettre_Motivation_{user.name.replace(' ', '_')}_{job.title.replace(' ', '_')}".replace(
            "/", "_"
        )[:80]

        if fmt == "pdf":
            buf = self.build_cover_letter_pdf(letter, user, job)
            return buf, f"{filename}.pdf"

        buf = self.build_cover_letter_docx(letter, user, job)
        return buf, f"{filename}.docx"
