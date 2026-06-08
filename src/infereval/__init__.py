"""infereval: inferentialist evaluation of LLMs.

Derive implication frames from an LLM's endorsement verdicts and measure
model–analyst agreement on analyst-labeled inference benchmarks (coverage,
Cohen's kappa, Fleiss' kappa). The agreement is evidence bearing on an
inferential-mastery attribution — not a measurement of mastery itself
(see Remark 8 of Allen, 2026).
"""

__version__ = "0.15.0"

from .frame import DerivedFrame
from .types import Bearer, Implication, Verdict

__all__ = [
    "__version__",
    "Bearer",
    "DerivedFrame",
    "Implication",
    "Verdict",
]
