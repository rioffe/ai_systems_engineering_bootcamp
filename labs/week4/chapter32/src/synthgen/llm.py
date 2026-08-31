# pyright: reportMissingImports=false
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .diagnostics import debug_payload
from .errors import ModelError
from .models import GroundTruth, Realization, Scenario


class OllamaRealizer:
    def __init__(self, model: str, host: str = "http://127.0.0.1:11434", timeout: float = 10):
        self.model, self.host, self.timeout = model, host.rstrip("/"), timeout

    def realize(self, scenario: Scenario, truth: GroundTruth, candidate_seed: int) -> Realization:
        prompt = json.dumps({"scenario": scenario.fields, "intent": scenario.category, "instruction": "Return one concise question only."}, sort_keys=True, default=str)
        payload = json.dumps({"model": self.model, "prompt": prompt, "stream": False, "options": {"seed": candidate_seed}}).encode()
        debug_payload("ollama prompt: {}", prompt)
        request = urllib.request.Request(self.host + "/api/generate", payload, {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            text = str(data.get("response", "")).strip()
        except (OSError, urllib.error.URLError, ValueError, KeyError) as exc:
            raise ModelError(f"Ollama request failed: {exc}") from exc
        if not text:
            raise ModelError("Ollama returned an empty response")
        debug_payload("ollama response: {}", text[:4000])
        return Realization(text, "ollama", None, self.model, text[:4000])
