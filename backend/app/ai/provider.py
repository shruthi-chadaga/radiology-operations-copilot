"""Provider interface. Model output is data and has no action execution capability."""

from typing import Protocol

from app.ai.schemas import ReferralExtraction


class AIProvider(Protocol):
    def extract_referral(self, text: str) -> ReferralExtraction: ...
