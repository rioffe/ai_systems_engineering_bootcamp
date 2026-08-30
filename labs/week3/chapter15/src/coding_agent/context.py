# R-03 / R-10 / K-05 / K-09 / I-005 / I-007: deterministic context engineering.
#
# `context.py` is IN the I-009 LLM/network-free core list (stdlib only). It
# composes `C_t` for each iteration from three selected slices -- the task, a
# working set of file contents, and recent feedback (verifier output, I-007) --
# NEVER the whole repository (I-005). Composition is a pure function of the
# accumulated state, so identical runs yield byte-identical contexts (I-002).
#
# The budget is measured in CHARACTERS (K-09, consistent with the K-07 surrogate;
# units never mix chars and tokens), default 8000. When |C_t| > BUDGET:
#   * compaction on (default): R-10/K-05 compaction fires -- salient state is
#     preserved (task always; latest open-edit content per file; the most recent
#     verdict/feedback), redundant history is discarded -- instead of overflow.
#   * compaction off (--no-compact): BudgetOverflow is raised, which the loop
#     maps to STALLED:BUDGET (E-13).
#
# Compaction is STATE management, not just trimming: it mutates the manager's
# state (old feedback dropped, oversized file contents truncated with a marker),
# deterministically.

from __future__ import annotations

from dataclasses import dataclass

# K-09: the pinned compaction budget, measured in characters.
DEFAULT_BUDGET = 8000
# R-10: how many of the most recent feedback entries survive compaction (the
# latest verdict plus one context entry).
_KEEP_FEEDBACK = 2
# R-10: stage-2 cap on a file's content once compaction has already trimmed
# feedback and the context is still over budget.
_FILE_CONTENT_CAP = 200


# E-13: a --no-compact context overflow. The loop maps this to STALLED:BUDGET.
class BudgetOverflow(Exception):
    name = "BUDGET_OVERFLOW"


# The composed context for one iteration: the deterministic C_t text plus the
# K-05/K-09 bookkeeping the loop records (budget, post-compaction size).
@dataclass(frozen=True)
class Context:
    text: str
    chars: int
    compacted: bool
    budget: int


# Composes C_t per iteration (R-03) and owns the K-05/K-09 budget + R-10
# compaction. Selection is explicit: only what the loop adds via add_file /
# add_feedback ever reaches the policy (I-005).
class ContextManager:
    def __init__(self, *, budget: int = DEFAULT_BUDGET, compact: bool = True) -> None:
        if budget <= 0:
            raise ValueError(f"budget must be a positive char count, got {budget}")
        self.budget = budget
        self.compact = compact
        self._files: dict[str, str] = {}  # working set: path -> latest content
        self._feedback: list[str] = []  # recent feedback, oldest first

    def add_file(self, path: str, content: str) -> None:
        # Select a file into the working set. A re-add of the same path is an
        # "open edit": the latest version wins (R-10 salient state).
        self._files[path] = content

    def add_feedback(self, text: str) -> None:
        # I-007: verifier output / tool feedback becomes a reasoning signal in the
        # next iteration's C_t.
        self._feedback.append(text)

    def manifest(self) -> list[str]:
        # The file manifest (R-10 salient state): the selected working set.
        return list(self._files)

    def _raw(self, task, iteration: int) -> str:
        # The deterministic composition: fixed section order, insertion-ordered
        # files, oldest-first feedback.
        parts = [f"=== ITERATION {iteration} ===", "=== TASK ===", task.prompt]
        if task.acceptance_test:
            parts.append(f"acceptance: {task.acceptance_test}")
        parts.append("")
        parts.append("=== WORKING SET ===")
        for path, content in self._files.items():
            parts.append(f"--- {path} ---")
            parts.append(content)
        if self._feedback:
            parts.append("")
            parts.append("=== FEEDBACK ===")
            parts.extend(self._feedback)
        return "\n".join(parts)

    def _compact(self, task, iteration: int) -> str:
        # R-10: preserve salient state, discard redundant history.
        #  stage 1 -- keep only the most recent feedback entries (the latest
        #             verdict/feedback is the salient signal);
        #  stage 2 -- if still over budget, cap each file's content (the path
        #             + manifest are preserved, bodies truncated with a marker).
        self._feedback = self._feedback[-_KEEP_FEEDBACK:]
        text = self._raw(task, iteration)
        if len(text) > self.budget:
            capped: dict[str, str] = {}
            for path, content in self._files.items():
                if len(content) > _FILE_CONTENT_CAP:
                    capped[path] = (
                        content[:_FILE_CONTENT_CAP] + f"... [truncated, {len(content)} chars total]"
                    )
                else:
                    capped[path] = content
            self._files = capped
            text = self._raw(task, iteration)
        return text

    def compose(self, task, iteration: int) -> Context:
        # R-03 composition with the K-05/K-09 budget check. Units are chars.
        raw = self._raw(task, iteration)
        if len(raw) <= self.budget:
            return Context(raw, len(raw), False, self.budget)
        if not self.compact:
            raise BudgetOverflow(
                f"C_t is {len(raw)} chars > budget {self.budget} with compaction off (E-13)"
            )
        # K-05: compaction fires rather than overflowing; the post-compaction
        # size is what the loop records in the trajectory.
        text = self._compact(task, iteration)
        return Context(text, len(text), True, self.budget)


__all__ = [
    "DEFAULT_BUDGET",
    "BudgetOverflow",
    "Context",
    "ContextManager",
]
