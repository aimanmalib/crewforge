"""`crewforge ingest | ask | summarize` (ported from documind tests/test_cli.py).

The end-to-end tests run the real client through the fake endpoint fixture.
"""

from __future__ import annotations

import json

import httpx
from click.testing import CliRunner

from crewforge.cli import main


class TestCLI:
    def test_main_runs(self):
        result = CliRunner().invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "ask" in result.output and "summarize" in result.output

    def test_ingest_help(self):
        assert CliRunner().invoke(main, ["ingest", "--help"]).exit_code == 0

    def test_ask_help(self):
        result = CliRunner().invoke(main, ["ask", "--help"])
        assert result.exit_code == 0
        assert "question" in result.output.lower()

    def test_version(self):
        result = CliRunner().invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "crewforge" in result.output

    def test_ask_requires_question(self, sample_doc_path):
        result = CliRunner().invoke(main, ["ask", str(sample_doc_path)])
        assert result.exit_code == 2
        assert "-q" in result.output

    def test_ingest_runs_without_llm(self, sample_doc_path):
        # No API key in the environment at all: ingest never needs one.
        result = CliRunner().invoke(main, ["ingest", str(sample_doc_path)])
        assert result.exit_code == 0, result.output
        assert "test_document.md" in result.output

    def test_summarize_help(self):
        assert CliRunner().invoke(main, ["summarize", "--help"]).exit_code == 0


class TestCLIEndToEnd:
    def test_ask_answers_and_exports(self, fake_llm, sample_doc_path, tmp_path):
        fake_llm.replies = ["The pipeline uses agents [Source 1]."]
        out = tmp_path / "session.md"
        result = CliRunner().invoke(
            main,
            [
                "ask",
                str(sample_doc_path),
                "-q",
                "What does the pipeline use?",
                "--export",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "The pipeline uses agents" in result.output
        assert "Token usage" in result.output
        assert len(fake_llm.calls) == 1
        assert fake_llm.calls[0]["model"] == "gpt-4o-mini"
        assert "What does the pipeline use?" in fake_llm.calls[0]["messages"][-1]["content"]
        assert "The pipeline uses agents" in out.read_text()

    def test_ask_with_verify(self, fake_llm, sample_doc_path):
        fake_llm.replies = ["Agents [Source 1].", "Claim 1: VERIFIED\nOVERALL: verified"]
        result = CliRunner().invoke(
            main, ["ask", str(sample_doc_path), "-q", "What does the pipeline use?", "--verify"]
        )
        assert result.exit_code == 0, result.output
        assert "Verification: verified" in result.output
        assert len(fake_llm.calls) == 2

    def test_summarize(self, fake_llm, sample_doc_path):
        fake_llm.replies = ["A short summary."]
        result = CliRunner().invoke(main, ["summarize", str(sample_doc_path)])
        assert result.exit_code == 0, result.output
        assert "A short summary." in result.output


class TestHonestFailure:
    def test_empty_answer_fails_naming_answerer(self, fake_llm, sample_doc_path):
        fake_llm.replies = [""]
        result = CliRunner().invoke(
            main, ["ask", str(sample_doc_path), "-q", "What does the pipeline use?"]
        )
        assert result.exit_code == 1
        assert "agent 'answerer'" in result.output

    def test_prose_fact_check_fails_naming_fact_checker(self, fake_llm, sample_doc_path):
        fake_llm.replies = ["Agents [Source 1].", "Looks right to me."]
        result = CliRunner().invoke(
            main, ["ask", str(sample_doc_path), "-q", "What does the pipeline use?", "--verify"]
        )
        assert result.exit_code == 1
        assert "agent 'fact_checker'" in result.output and "(parse)" in result.output

    def test_unmatched_question_fails_without_calling_the_llm(self, fake_llm, sample_doc_path):
        result = CliRunner().invoke(
            main, ["ask", str(sample_doc_path), "-q", "zebra xylophone quokka"]
        )
        assert result.exit_code == 1
        assert "agent 'retriever'" in result.output
        assert fake_llm.calls == []

    def test_empty_summary_fails_naming_summarizer(self, fake_llm, sample_doc_path):
        fake_llm.replies = ["  "]
        result = CliRunner().invoke(main, ["summarize", str(sample_doc_path)])
        assert result.exit_code == 1
        assert "agent 'summarizer'" in result.output

    def test_rerank_garbage_fails_naming_reranker(self, fake_llm, sample_doc_path):
        fake_llm.replies = ["the second one is best"]
        result = CliRunner().invoke(
            main, ["ask", str(sample_doc_path), "-q", "What does the pipeline use?", "--rerank"]
        )
        assert result.exit_code == 1
        assert "agent 'reranker'" in result.output

    def test_ask_without_key_is_config_error(self, sample_doc_path):
        result = CliRunner().invoke(main, ["ask", str(sample_doc_path), "-q", "pipeline?"])
        assert result.exit_code == 2
        assert "OPENAI_API_KEY" in result.output

    def test_pdf_without_extra_names_the_extra(self, fake_llm, tmp_path, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def no_fitz(name, *args, **kwargs):
            if name in ("fitz", "pymupdf"):
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_fitz)
        pdf = tmp_path / "a.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        result = CliRunner().invoke(main, ["ingest", str(pdf)])
        assert result.exit_code == 2
        assert "crewforge[docs]" in result.output

    def test_json_export_carries_verification(self, fake_llm, sample_doc_path, tmp_path):
        fake_llm.replies = [
            "Agents [Source 1].",
            json.dumps({"claims": [{"claim": "agents", "verdict": "verified"}]}),
        ]
        out = tmp_path / "s.json"
        result = CliRunner().invoke(
            main,
            [
                "ask",
                str(sample_doc_path),
                "-q",
                "What does the pipeline use?",
                "--verify",
                "--export",
                str(out),
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(out.read_text())
        assert data["answers"][0]["verification"]["verdict"] == "verified"

    def test_http_error_is_reported(self, fake_llm, sample_doc_path):
        fake_llm.replies = [httpx.Response(403, json={"error": {"message": "forbidden"}})]
        result = CliRunner().invoke(main, ["ask", str(sample_doc_path), "-q", "pipeline?"])
        assert result.exit_code == 1
        assert "forbidden" in result.output and len(fake_llm.calls) == 1


def test_bullet_glyphs_render_as_a_markdown_list():
    from crewforge.recipes.docs.cli import as_markdown

    assert as_markdown("Summary.\n• One\n  • Two") == "Summary.\n- One\n- Two"
