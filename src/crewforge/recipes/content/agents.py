"""The eight content agents (ported from contentforge).

Each agent keeps contentforge's prompts and ``AgentResult`` shape, but runs on
the crewforge core: :meth:`ContentAgent.execute` raises (naming the agent) on
empty or unparseable output, and the pipeline runs it through ``Crew.step`` so
no failure can be swallowed. :meth:`ContentAgent.run` keeps contentforge's
"never raise, return a failed result" behaviour for library callers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...core.agent import Agent
from ...core.client import LLMClient
from ...core.errors import OutputParseError
from ...core.parsing import parse_json
from ...core.usage import UsageTracker
from .export import export_html, export_json_report, export_markdown
from .settings import ContentSettings
from .text import reading_time, slugify, word_count

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Standardized result from any content agent."""

    agent_name: str
    status: str = "success"  # success | partial | failed
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    tokens_used: int = 0
    latency_ms: float = 0.0
    error: str | None = None
    reasoning: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "success"


class ContentAgent(Agent):
    """Base for content agents: applies per-agent overrides from ``content.agents``."""

    # contentforge's default: writing benefits from more sampling freedom than review.
    temperature = 0.7

    def __init__(
        self,
        client: LLMClient,
        tracker: UsageTracker | None = None,
        *,
        config: ContentSettings | None = None,
    ) -> None:
        self.config = config or ContentSettings()
        override = self.config.get_agent_config(self.name)
        super().__init__(
            client,
            tracker,
            system_prompt=override.system_prompt_override,
            model=override.model_override,
            temperature=override.temperature_override,
            max_tokens=override.max_tokens_override,
        )
        self._agent_config = override
        self._iteration = 0

    async def execute(self, **kwargs: Any) -> AgentResult:  # pragma: no cover - abstract
        raise NotImplementedError

    async def run(self, **kwargs: Any) -> AgentResult:
        """Run with error capture (library API); the pipeline uses ``execute``."""
        self._iteration += 1
        try:
            return await self.execute(**kwargs)
        except Exception as exc:
            logger.error("[%s] failed: %s", self.name, exc)
            return AgentResult(agent_name=self.name, status="failed", error=str(exc))


class ResearchAgent(ContentAgent):
    name = "research"
    description = "Gathers background information, key facts, and expert perspectives"

    system_prompt = """You are the Research Agent in a content creation pipeline.

Your role:
1. Analyze the given topic and identify 5-8 key subtopics
2. Provide factual information, statistics, and expert quotes for each
3. Identify trending angles and unique perspectives
4. Flag any controversial claims that need verification
5. Suggest primary and secondary sources

Output format (JSON):
{
    "topic": "...",
    "key_subtopics": [
        {"title": "...", "key_facts": [...], "statistics": [...], "expert_quotes": [...]}
    ],
    "trending_angles": [...],
    "controversial_claims": [...],
    "suggested_sources": [...],
    "unique_angle": "..."
}

Be thorough but concise.
You have NO web access: work from general knowledge, never invent sources, URLs or
exact statistics, and list anything uncertain under "controversial_claims"."""

    async def execute(self, topic: str = "", **kwargs) -> AgentResult:
        """Research a given topic and return structured findings."""
        prompt = f"""Research the following topic thoroughly:

Topic: {topic}

Provide:
1. 5-8 key subtopics with supporting facts and statistics
2. Expert perspectives and notable quotes
3. Current trends and unique angles
4. Any controversial claims that need fact-checking
5. A suggested unique angle for the article

Return as structured JSON."""

        response = await self.ask(prompt)

        return AgentResult(
            agent_name=self.name,
            content=response.content,
            tokens_used=response.usage.total_tokens,
            latency_ms=response.latency_ms,
            reasoning=response.reasoning or None,
            metadata={
                "topic": topic,
                "has_statistics": "statistics" in response.content.lower(),
                "has_quotes": "quote" in response.content.lower(),
                "output_length": len(response.content),
            },
        )


class OutlineAgent(ContentAgent):
    name = "outline"
    description = "Creates structured outlines with section hierarchy and word allocation"

    system_prompt = """You are the Outline Agent in a content creation pipeline.

Your role:
1. Take research data and create a well-structured article outline
2. Allocate word count per section proportionally to importance
3. Ensure logical flow: hook → context → body → conclusion
4. Add SEO keyword placement suggestions per section
5. Include transition notes between sections

Output format (JSON):
{
    "title": "...",
    "meta_description": "...",
    "target_word_count": N,
    "sections": [
        {
            "heading": "...",
            "subheadings": [...],
            "word_allocation": N,
            "key_points": [...],
            "seo_keywords": [...],
            "transition_note": "..."
        }
    ],
    "estimated_reading_time": "X min",
    "content_type": "article|guide|listicle|comparison"
}

Aim for 6-10 sections with clear hierarchy."""

    async def execute(
        self, research_data: str = "", target_words: int = 2000, **kwargs
    ) -> AgentResult:
        """Create an outline from research data."""
        prompt = f"""Based on the following research data, create a detailed article outline.

Target word count: {target_words} words

Research Data:
{research_data}

Create a structured outline with:
- Compelling title and meta description
- 6-10 sections with word allocation
- Key points per section
- SEO keyword suggestions
- Logical flow with transitions

Return as structured JSON."""

        response = await self.ask(prompt)

        return AgentResult(
            agent_name=self.name,
            content=response.content,
            tokens_used=response.usage.total_tokens,
            latency_ms=response.latency_ms,
            reasoning=response.reasoning or None,
            metadata={
                "target_words": target_words,
                "output_length": len(response.content),
            },
        )


class WriterAgent(ContentAgent):
    name = "writer"
    description = "Generates full content draft from outline and research"

    system_prompt = """You are the Writer Agent in a content creation pipeline.

Your role:
1. Write engaging, well-researched content following the provided outline
2. Maintain consistent tone and voice throughout
3. Include natural keyword integration (not keyword stuffing)
4. Use varied sentence structures and paragraph lengths
5. Add relevant examples, analogies, and data points
6. Write in a style that's informative yet accessible

Writing guidelines:
- Start with a compelling hook
- Use subheadings (##) for each major section
- Include bullet points and numbered lists for scannability
- Add internal transition sentences between sections
- End with a strong conclusion and call-to-action
- Write in active voice predominantly
- Cite statistics with source context (not raw URLs)

Output: Full article in Markdown format."""

    async def execute(
        self,
        outline: str = "",
        research_data: str = "",
        language: str = "en",
        **kwargs,
    ) -> AgentResult:
        """Generate a full content draft."""
        prompt = f"""Write a complete article based on the following outline and research.

Language: {language}

OUTLINE:
{outline}

RESEARCH DATA:
{research_data}

Write the full article in Markdown. Follow the outline structure precisely.
Each section should meet its word allocation target.
Include natural keyword integration as specified in the outline."""

        response = await self.ask(prompt, max_tokens=8192)

        word_count = len(response.content.split())

        return AgentResult(
            agent_name=self.name,
            content=response.content,
            tokens_used=response.usage.total_tokens,
            latency_ms=response.latency_ms,
            reasoning=response.reasoning or None,
            metadata={
                "word_count": word_count,
                "language": language,
                "output_length": len(response.content),
            },
        )


class SEOAgent(ContentAgent):
    name = "seo"
    description = "Analyzes and optimizes content for search engine visibility"

    system_prompt = """You are the SEO Agent in a content creation pipeline.

Your role:
1. Analyze content for SEO effectiveness
2. Suggest keyword density improvements
3. Optimize title and meta description for CTR
4. Check heading hierarchy (H1 → H2 → H3)
5. Recommend internal/external linking opportunities
6. Identify featured snippet opportunities
7. Suggest image alt-text recommendations

Output format (JSON):
{
    "seo_score": 0-100,
    "keyword_analysis": {
        "primary_keyword": "...",
        "secondary_keywords": [...],
        "keyword_density": "...%",
        "recommendations": [...]
    },
    "title_optimization": {
        "current": "...",
        "suggested": "...",
        "reason": "..."
    },
    "meta_description": {
        "current": "...",
        "optimized": "...",
        "char_count": N
    },
    "heading_structure": {
        "issues": [...],
        "suggestions": [...]
    },
    "featured_snippet_candidates": [...],
    "internal_link_suggestions": [...],
    "image_alt_suggestions": [...],
    "overall_recommendations": [...]
}"""

    async def execute(
        self, content: str = "", target_keywords: list[str] | None = None, **kwargs
    ) -> AgentResult:
        """Analyze content for SEO and provide optimization recommendations."""
        keywords_str = ", ".join(target_keywords) if target_keywords else "auto-detect"

        prompt = f"""Analyze the following content for SEO effectiveness.

Target Keywords: {keywords_str}

CONTENT:
{content}

Provide:
1. SEO score (0-100)
2. Keyword density analysis
3. Title and meta description optimization
4. Heading structure review
5. Featured snippet opportunities
6. Internal linking suggestions
7. Image alt-text recommendations

Return as structured JSON."""

        response = await self.ask(prompt)

        return AgentResult(
            agent_name=self.name,
            content=response.content,
            tokens_used=response.usage.total_tokens,
            latency_ms=response.latency_ms,
            reasoning=response.reasoning or None,
            metadata={
                "target_keywords": target_keywords or [],
                "content_length": len(content),
            },
        )


class EditorAgent(ContentAgent):
    name = "editor"
    description = "Refines content for clarity, grammar, tone, and readability"

    system_prompt = """You are the Editor Agent in a content creation pipeline.

Your role:
1. Fix grammar, spelling, and punctuation errors
2. Improve sentence clarity and readability
3. Ensure consistent tone and voice
4. Remove redundancy and filler words
5. Strengthen weak transitions
6. Verify factual claims have proper attribution
7. Improve paragraph flow and pacing
8. Ensure the content matches the target reading level

Editing principles:
- Preserve the author's voice while improving clarity
- Short sentences for impact, longer for explanation
- Every paragraph must earn its place
- Active voice over passive
- Specific over vague
- Show, don't tell

Output: Return the FULL edited article in Markdown, plus a change summary."""

    async def execute(
        self,
        content: str = "",
        seo_recommendations: str = "",
        target_reading_level: str = "general",
        **kwargs,
    ) -> AgentResult:
        """Edit and refine the content draft."""
        seo_block = ""
        if seo_recommendations:
            seo_block = f"SEO RECOMMENDATIONS TO INCORPORATE:\n{seo_recommendations}\n"

        prompt = f"""Edit the following article for maximum quality.

Target reading level: {target_reading_level}

{seo_block}
CONTENT:
{content}

Return:
1. The FULL edited article in Markdown (not a diff)
2. A brief change summary at the end (as a comment block)"""

        response = await self.ask(prompt, max_tokens=8192)

        return AgentResult(
            agent_name=self.name,
            content=response.content,
            tokens_used=response.usage.total_tokens,
            latency_ms=response.latency_ms,
            reasoning=response.reasoning or None,
            metadata={
                "input_length": len(content),
                "output_length": len(response.content),
                "reading_level": target_reading_level,
            },
        )


class QualityAgent(ContentAgent):
    name = "quality"
    description = "Fact-checks content, scores quality, and flags issues"

    system_prompt = """You are the Quality Agent in a content creation pipeline.

Your role:
1. Score overall content quality (0-100)
2. Check factual accuracy of claims and statistics
3. Verify logical consistency throughout the piece
4. Detect potential plagiarism patterns
5. Check for bias or unbalanced perspectives
6. Verify all statistics have proper context
7. Ensure the content delivers on the title's promise
8. Check readability metrics

Quality dimensions (score each 0-100):
- Accuracy: Factual correctness
- Completeness: Covers the topic thoroughly
- Clarity: Easy to understand
- Engagement: Keeps reader interest
- Originality: Unique perspective
- Structure: Logical organization
- SEO: Search optimization
- Readability: Appropriate reading level

Output format (JSON):
{
    "overall_score": N,
    "pass_threshold": true|false,
    "dimensions": {
        "accuracy": {"score": N, "notes": "..."},
        "completeness": {"score": N, "notes": "..."},
        "clarity": {"score": N, "notes": "..."},
        "engagement": {"score": N, "notes": "..."},
        "originality": {"score": N, "notes": "..."},
        "structure": {"score": N, "notes": "..."},
        "seo": {"score": N, "notes": "..."},
        "readability": {"score": N, "notes": "..."}
    },
    "factual_issues": [...],
    "logical_inconsistencies": [...],
    "bias_flags": [...],
    "improvement_suggestions": [...],
    "strengths": [...]
}"""

    async def execute(
        self,
        content: str = "",
        threshold: float = 0.8,
        title: str = "",
        **kwargs,
    ) -> AgentResult:
        """Score content quality and flag issues."""
        prompt = f"""Evaluate the quality of the following article.

Title: {title}
Quality threshold: {threshold * 100}%

CONTENT:
{content}

Score each dimension (0-100) and provide:
1. Overall quality score
2. Per-dimension scores with notes
3. Factual issues found
4. Logical inconsistencies
5. Bias flags
6. Improvement suggestions
7. Key strengths

Return as structured JSON."""

        response = await self.ask(prompt)

        # Fences and surrounding prose are tolerated; a reply without a numeric
        # overall_score is a failure of this agent (contentforge silently used 0,
        # which made the editor loop burn every iteration).
        parsed = parse_json(response.content, agent=self.name)
        raw_score = parsed.get("overall_score")
        if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float, str)):
            raise OutputParseError(self.name, "JSON has no numeric overall_score")
        try:
            overall_score = float(raw_score)
        except ValueError as exc:
            raise OutputParseError(
                self.name, f"overall_score is not a number: {raw_score!r}"
            ) from exc
        if not 0 <= overall_score <= 100:
            raise OutputParseError(self.name, f"overall_score {overall_score} is outside 0-100")

        return AgentResult(
            agent_name=self.name,
            content=response.content,
            tokens_used=response.usage.total_tokens,
            latency_ms=response.latency_ms,
            reasoning=response.reasoning or None,
            metadata={
                "overall_score": overall_score,
                "threshold": threshold,
                "passes_threshold": overall_score >= threshold * 100,
                "content_length": len(content),
            },
        )


class TranslatorAgent(ContentAgent):
    name = "translator"
    description = "Adapts content to target languages while preserving tone and SEO"

    system_prompt = """You are the Translator Agent in a content creation pipeline.

Your role:
1. Translate content to the target language accurately
2. Adapt cultural references and idioms for the target audience
3. Preserve SEO keywords (transliterate or localize as appropriate)
4. Maintain heading structure and Markdown formatting
5. Keep proper nouns and brand names unchanged unless localized versions exist
6. Adapt statistics and date formats for the target locale
7. Preserve the original tone and voice

Supported languages:
- zh (Chinese Simplified) — 优先使用简体中文
- ms (Malay) — Gunakan bahasa Melayu standard
- ja (Japanese) — 日本語で自然な表現を使用
- ko (Korean) — 한국어로 자연스러운 표현 사용
- id (Indonesian) — Gunakan bahasa Indonesia baku
- th (Thai) — ใช้ภาษาไทยที่เป็นธรรมชาติ
- vi (Vietnamese) — Sử dụng tiếng Việt tự nhiên
- ar (Arabic) — استخدم اللغة العربية الفصحى

Output: Full translated article in Markdown, same structure as original."""

    async def execute(
        self,
        content: str = "",
        target_language: str = "zh",
        source_language: str = "en",
        preserve_keywords: list[str] | None = None,
        **kwargs,
    ) -> AgentResult:
        """Translate content to target language."""
        keywords_note = ""
        if preserve_keywords:
            keywords_note = (
                f"\nPreserve these keywords in original form: {', '.join(preserve_keywords)}"
            )

        prompt = f"""Translate the following article from {source_language} to {target_language}.

Rules:
- Maintain Markdown formatting exactly
- Adapt cultural references naturally
- Keep brand names and proper nouns unchanged{keywords_note}

ARTICLE:
{content}

Return the full translated article in Markdown."""

        response = await self.ask(prompt, max_tokens=8192)

        return AgentResult(
            agent_name=self.name,
            content=response.content,
            tokens_used=response.usage.total_tokens,
            latency_ms=response.latency_ms,
            metadata={
                "source_language": source_language,
                "target_language": target_language,
                "input_length": len(content),
                "output_length": len(response.content),
            },
        )


class PublisherAgent(ContentAgent):
    name = "publisher"
    description = "Formats content for target platforms and exports files"

    system_prompt = """You are the Publisher Agent in a content creation pipeline.

Your role:
1. Format content for the target platform(s)
2. Generate platform-specific metadata
3. Create social media snippets for distribution
4. Generate email newsletter version
5. Create plain-text fallback version
6. Add proper front matter (YAML/TOML as needed)

Platform formats:
- markdown: Clean Markdown with YAML front matter
- html: Semantic HTML5 with proper meta tags
- wordpress: WordPress-compatible with shortcodes
- medium: Medium-optimized (clean, no front matter)
- newsletter: Email-friendly HTML with inline styles
- social: Social media snippets (Twitter, LinkedIn, Facebook)

Output format (JSON):
{
    "formats": {
        "markdown": "...",
        "html_snippet": "...",
        "social_twitter": "...",
        "social_linkedin": "...",
        "newsletter_subject": "...",
        "newsletter_preview": "..."
    },
    "metadata": {
        "title": "...",
        "description": "...",
        "tags": [...],
        "category": "...",
        "reading_time": "...",
        "word_count": N
    }
}"""

    async def execute(
        self,
        content: str = "",
        title: str = "",
        publish_targets: list[str] | None = None,
        output_dir: str = "./output",
        **kwargs,
    ) -> AgentResult:
        """Format and export content for target platforms."""
        targets = publish_targets or ["markdown"]
        targets_str = ", ".join(targets)

        prompt = f"""Format the following article for these platforms: {targets_str}

Title: {title}

CONTENT:
{content}

Generate:
1. Platform-specific formatted versions
2. Social media snippets (Twitter: 280 chars, LinkedIn: professional tone)
3. Email newsletter subject line and preview text
4. Complete metadata (tags, category, reading time, word count)

Return as structured JSON."""

        response = await self.ask(prompt)
        formats = parse_json(response.content, agent=self.name)

        meta = formats.get("metadata") if isinstance(formats.get("metadata"), dict) else {}
        metadata = {
            "title": title,
            "description": str(meta.get("description", "")),
            "tags": meta.get("tags", []),
            "language": kwargs.get("language", "en"),
            "word_count": word_count(content),
            "reading_time": reading_time(content),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        output_path = Path(output_dir)
        stem = slugify(title)[:60] or "article"
        files: list[str] = []
        for target in targets:
            if target == "markdown":
                files.append(str(export_markdown(content, metadata, output_path / f"{stem}.md")))
            elif target == "html":
                files.append(str(export_html(content, metadata, output_path / f"{stem}.html")))
            elif target == "json":
                record = {"metadata": metadata, "content": content}
                files.append(str(export_json_report(record, output_path / f"{stem}.json")))
            else:
                raise ValueError(f"unknown publish target {target!r}")
        # Social snippets, newsletter lines and metadata exactly as the model returned them.
        files.append(str(export_json_report(formats, output_path / f"{stem}.publisher.json")))

        return AgentResult(
            agent_name=self.name,
            content=response.content,
            tokens_used=response.usage.total_tokens,
            latency_ms=response.latency_ms,
            metadata={
                "publish_targets": targets,
                "output_files": files,
                "content_length": len(content),
            },
        )


AGENT_REGISTRY: dict[str, type[ContentAgent]] = {
    "research": ResearchAgent,
    "outline": OutlineAgent,
    "writer": WriterAgent,
    "seo": SEOAgent,
    "editor": EditorAgent,
    "translator": TranslatorAgent,
    "quality": QualityAgent,
    "publisher": PublisherAgent,
}


def get_agent(name: str, **kwargs: Any) -> ContentAgent:
    cls = AGENT_REGISTRY.get(name)
    if not cls:
        raise ValueError(f"Unknown agent: {name}. Available: {list(AGENT_REGISTRY)}")
    return cls(**kwargs)
