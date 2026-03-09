from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from app.config import settings


class LLMService:
    """LLM adapter for requirement extraction.

    Uses OpenAI when USE_LOCAL_AI is False.
    Local AI branch is intentionally scaffolded for production airgapped setup.
    """

    def __init__(self) -> None:
        self.use_local_ai = settings.USE_LOCAL_AI

    def extract_job_requirements(
        self,
        job_text: str,
        role_title: str | None = None,
        location: str | None = None,
    ) -> dict[str, Any]:
        if self.use_local_ai:
            raise NotImplementedError("Local AI path is not wired yet. Set USE_LOCAL_AI=false for OpenAI.")

        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is missing. Set it in .env.")

        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        prompt = self._build_prompt(job_text=job_text, role_title=role_title, location=location)

        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You extract structured hiring requirements from a job description. "
                        "Return strict JSON only with the exact schema requested. "
                        "Do not invent requirements not evidenced by the input text."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )

        content = response.choices[0].message.content or "{}"
        return self._parse_json(content)

    def _build_prompt(self, job_text: str, role_title: str | None, location: str | None) -> str:
        return (
            "Extract job requirements into this JSON schema:\n"
            "{\n"
            "  \"role_title\": string|null,\n"
            "  \"seniority\": string|null,\n"
            "  \"must_have_skills\": [{\"skill\": string, \"min_years\": number|null, \"weight\": number}],\n"
            "  \"nice_to_have_skills\": [{\"skill\": string, \"min_years\": number|null, \"weight\": number}],\n"
            "  \"domain_keywords\": [string],\n"
            "  \"education\": {\"min_level\": string|null, \"preferred_majors\": [string], \"min_gpa\": number|null},\n"
            "  \"experience\": {\"min_years_total\": number|null, \"min_years_relevant\": number|null, \"required_titles\": [string]},\n"
            "  \"work_constraints\": {\"location\": string|null, \"onsite_policy\": string|null, \"language\": string|null, \"authorization\": string|null},\n"
            "  \"scoring_preferences\": {\"weight_skills\": number, \"weight_title_fit\": number, \"weight_domain\": number, \"weight_scores\": number, \"weight_education\": number},\n"
            "  \"exclusions\": object,\n"
            "  \"confidence\": number,\n"
            "  \"missing_fields\": [string]\n"
            "}\n\n"
            f"Input role_title_hint: {role_title}\n"
            f"Input location_hint: {location}\n"
            "Job description text:\n"
            f"{job_text}\n\n"
            "Rules:\n"
            "- Use only evidence from text or provided hints.\n"
            "- Keep confidence between 0 and 1.\n"
            "- missing_fields should include unresolved critical fields among: must_have_skills, experience.min_years_relevant, work_constraints.location, education.min_level.\n"
            "- If uncertain, leave fields null/empty and add the corresponding missing_fields entry."
        )

    def _parse_json(self, raw: str) -> dict[str, Any]:
        cleaned = raw.strip()
        cleaned = re.sub(r"^```json\s*", "", cleaned)
        cleaned = re.sub(r"```$", "", cleaned)
        return json.loads(cleaned)
