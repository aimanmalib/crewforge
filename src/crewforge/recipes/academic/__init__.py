"""``academic`` recipe: an honest academic writing assistant.

It helps a student or researcher plan and improve their OWN work: parse a
brief into a plan, comment on a draft, format references the user supplies,
and write an AI-use disclosure from a record of what the tool actually did.
It does not write assignments, does not invent references, and has no
"humanise" or detector-evasion feature (see docs/porting.md).
"""

from .agents import (
    ArgumentAgent,
    BriefAgent,
    CitationReviewAgent,
    ClarityAgent,
    FormatterAgent,
    PlannerAgent,
    StructureAgent,
)
from .citations import SourceCheck, analyse_draft, check_formatted, check_source, identifiers
from .disclosure import build_statement, make_record, read_records
from .pipeline import AcademicCrew, CiteResult, FeedbackResult, PlanResult, allocate_words
from .settings import AcademicSettings

__all__ = [
    "AcademicCrew",
    "AcademicSettings",
    "ArgumentAgent",
    "BriefAgent",
    "CitationReviewAgent",
    "CiteResult",
    "ClarityAgent",
    "FeedbackResult",
    "FormatterAgent",
    "PlanResult",
    "PlannerAgent",
    "SourceCheck",
    "StructureAgent",
    "allocate_words",
    "analyse_draft",
    "build_statement",
    "check_formatted",
    "check_source",
    "identifiers",
    "make_record",
    "read_records",
]
