"""Deterministic slot filtering, ranking, and non-clinical explanations."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SlotCandidate:
    slot_id: str
    start_time: datetime
    location_code: str
    modality: str


@dataclass(frozen=True)
class SlotPreferences:
    modality: str
    preferred_location_code: str | None
    preferred_time_of_day: str | None


@dataclass(frozen=True)
class RankedSlot:
    slot_id: str
    start_time: datetime
    score: int
    explanation: str


def rank_slots(candidates: list[SlotCandidate], preferences: SlotPreferences) -> list[RankedSlot]:
    eligible = [item for item in candidates if item.modality == preferences.modality]
    if not eligible:
        return []
    first_date = min(item.start_time.date() for item in eligible)
    results: list[RankedSlot] = []
    for item in eligible:
        days_after_first = (item.start_time.date() - first_date).days
        location_match = item.location_code == preferences.preferred_location_code
        time_match = _time_of_day(item.start_time) == preferences.preferred_time_of_day
        score = 1000 - days_after_first * 100 + int(location_match) * 30 + int(time_match) * 15
        reasons = ["it is within the requested date range"]
        if item.start_time.date() == first_date:
            reasons.insert(0, "it is among the earliest available slots")
        if location_match:
            reasons.append("it matches the preferred location")
        if time_match:
            reasons.append("it matches the preferred time of day")
        explanation = "Recommended because " + ", ".join(reasons) + "."
        results.append(RankedSlot(item.slot_id, item.start_time, score, explanation))
    return sorted(results, key=lambda item: (-item.score, item.start_time, item.slot_id))


def _time_of_day(value: datetime) -> str:
    if value.hour < 12:
        return "morning"
    if value.hour < 17:
        return "afternoon"
    return "evening"
