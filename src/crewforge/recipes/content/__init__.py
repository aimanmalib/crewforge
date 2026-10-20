"""content recipe: research -> outline -> write -> SEO -> edit <-> quality -> translate -> publish.

Ported from contentforge (github.com/aimanmalib/contentforge).
"""

from .agents import AGENT_REGISTRY, AgentResult, ContentAgent, get_agent
from .pipeline import ContentPipeline, PipelineResult
from .settings import AgentConfig, ContentSettings, PipelineConfig

__all__ = [
    "AGENT_REGISTRY",
    "AgentConfig",
    "AgentResult",
    "ContentAgent",
    "ContentPipeline",
    "ContentSettings",
    "PipelineConfig",
    "PipelineResult",
    "get_agent",
]
