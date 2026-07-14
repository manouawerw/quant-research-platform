"""Evidence collection and validation for the Quant Research Platform."""

from .evidence_builder import build_evidence_package
from .research_report import generate_evidence_grounded_report

__all__ = [
    "build_evidence_package",
    "generate_evidence_grounded_report",
]
