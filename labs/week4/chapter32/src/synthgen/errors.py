# pyright: reportMissingImports=false
from __future__ import annotations


class SynthgenError(Exception):
    """Base class for user-facing structured failures."""

    code = "SYNTHGEN_ERROR"
    exit_code = 2

    def __init__(self, message: str, *, details: dict[str, object] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class SpecificationError(SynthgenError):
    code = "SPECIFICATION_ERROR"


class ConstraintError(SynthgenError):
    code = "CONSTRAINT_ERROR"


class CalculatorError(SynthgenError):
    code = "CALCULATOR_ERROR"
    exit_code = 1


class ModelError(SynthgenError):
    code = "MODEL_ERROR"
    exit_code = 5


class ExhaustedError(SynthgenError):
    code = "GENERATION_EXHAUSTED"
    exit_code = 1


class ArtifactError(SynthgenError):
    code = "ARTIFACT_ERROR"
    exit_code = 5
