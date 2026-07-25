"""Deterministic offline provider for tests and reproducible demonstrations."""

import re

from app.ai.schemas import ExtractedField, ReferralExtraction


class MockAIProvider:
    model_name = "mock-v1"
    prompt_version = "referral-extraction-v1"

    def extract_referral(self, text: str) -> ReferralExtraction:
        normalized = " ".join(text.split())
        lower = normalized.lower()
        modality = self._first_explicit(normalized, ("CT", "MR", "MRI", "CR", "US", "NM"))
        if modality == "MRI":
            modality = "MR"
        region = self._first_explicit(
            lower, ("abdomen_pelvis", "abdomen", "pelvis", "chest", "head", "knee", "spine")
        )
        if region == "abdomen_pelvis":
            region = "abdomen/pelvis"
        exam = " ".join(part for part in (modality, region) if part) or None
        priority = self._first_explicit(lower, ("routine", "urgent"))
        auth = "approved" if re.search(r"authorization\s+(?:is\s+)?approved", lower) else None
        sedation = "required" if re.search(r"sedation\s+(?:is\s+)?required", lower) else None
        contrast = self._first_explicit(lower, ("with contrast", "without contrast"))
        location = self._location(normalized)

        missing = [
            name
            for name, value in (
                ("requested_exam", exam),
                ("modality", modality),
                ("authorization_status", auth),
            )
            if value is None
        ]
        return ReferralExtraction(
            requested_exam=self._field(exam, normalized),
            modality=self._field(modality, normalized),
            body_region=self._field(region, normalized),
            laterality=self._field(None, normalized),
            explicit_priority=self._field(priority, normalized),
            preferred_location=self._field(location, normalized),
            contrast_indicator=self._field(contrast, normalized),
            sedation_indicator=self._field(sedation, normalized),
            authorization_status=self._field(auth, normalized),
            missing_or_ambiguous_fields=missing,
            requires_human_review=bool(missing or sedation),
            review_reasons=(["Required administrative information is absent"] if missing else [])
            + (["Sedation-marked cases require human review"] if sedation else []),
            model_name=self.model_name,
            prompt_version=self.prompt_version,
        )

    @staticmethod
    def _first_explicit(text: str, values: tuple[str, ...]) -> str | None:
        for value in values:
            pattern = re.escape(value).replace("_", r"[/\s]+")
            if re.search(rf"\b{pattern}\b", text, re.IGNORECASE):
                return value
        return None

    @staticmethod
    def _location(text: str) -> str | None:
        match = re.search(r"\bat\s+([A-Z][A-Za-z -]{2,40}?)(?:\.|,|$)", text)
        return match.group(1).strip() if match else None

    @staticmethod
    def _field(value: str | None, source: str) -> ExtractedField[str]:
        if value is None:
            return ExtractedField(value=None, confidence=1.0, source_excerpt=None)
        match = re.search(re.escape(value), source, re.IGNORECASE)
        excerpt = match.group(0) if match else value
        return ExtractedField(value=value, confidence=0.99, source_excerpt=excerpt)
