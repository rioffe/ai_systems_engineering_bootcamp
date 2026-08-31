# pyright: reportMissingImports=false
from __future__ import annotations

import re
from difflib import SequenceMatcher

from .models import DuplicateDecision
from .validators import normalize_question


class Deduplicator:
    def __init__(self, near: bool = True, threshold: float = 0.92):
        self.near, self.threshold, self._seen = near, threshold, {}

    def check(self, question: str, record_id: str) -> DuplicateDecision:
        key = normalize_question(question)
        if key in self._seen:
            return DuplicateDecision(True, "exact", key, self._seen[key])
        if self.near:
            for prior_key, prior_id in self._seen.items():
                if SequenceMatcher(None, key, prior_key).ratio() >= self.threshold:
                    return DuplicateDecision(True, "near", key, prior_id)
        self._seen[key] = record_id
        return DuplicateDecision(False, "none", key)
