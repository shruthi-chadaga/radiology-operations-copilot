from datetime import UTC, datetime

from app.scheduling.slot_ranking import SlotCandidate, SlotPreferences, rank_slots


def test_slot_ranking_is_deterministic_and_explained_without_clinical_claims() -> None:
    slots = [
        SlotCandidate("late-preferred", datetime(2026, 8, 2, 9, tzinfo=UTC), "central", "CT"),
        SlotCandidate("early-other", datetime(2026, 8, 1, 8, tzinfo=UTC), "north", "CT"),
        SlotCandidate("early-preferred", datetime(2026, 8, 1, 14, tzinfo=UTC), "central", "CT"),
    ]

    ranked = rank_slots(
        slots,
        SlotPreferences(
            modality="CT",
            preferred_location_code="central",
            preferred_time_of_day="afternoon",
        ),
    )

    assert [item.slot_id for item in ranked] == ["early-preferred", "early-other", "late-preferred"]
    assert "preferred location" in ranked[0].explanation.lower()
    assert "requested date range" in ranked[0].explanation.lower()
    assert "clinically" not in " ".join(item.explanation.lower() for item in ranked)


def test_slot_ranking_excludes_wrong_modality() -> None:
    ranked = rank_slots(
        [SlotCandidate("mr", datetime(2026, 8, 1, 9, tzinfo=UTC), "central", "MR")],
        SlotPreferences(modality="CT", preferred_location_code=None, preferred_time_of_day=None),
    )

    assert ranked == []
