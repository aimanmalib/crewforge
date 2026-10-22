"""Tests for IngestAgent."""

from __future__ import annotations

import pytest

from crewforge.recipes.docs import Document, IngestAgent, TextChunk


class TestIngestAgent:
    """Test the IngestAgent."""

    @pytest.mark.asyncio
    async def test_ingest_markdown(self, config, mock_client, sample_doc_path):
        agent = IngestAgent(config)
        doc = await agent.run(path=sample_doc_path)
        assert isinstance(doc, Document)
        assert doc.filename == "test_document.md"
        assert doc.file_type == "markdown"
        assert len(doc.chunks) > 0

    @pytest.mark.asyncio
    async def test_ingest_plain_text(self, config, mock_client, tmp_path):
        p = tmp_path / "plain.txt"
        p.write_text("Simple text content. " * 50)
        agent = IngestAgent(config)
        doc = await agent.run(path=p)
        assert doc.file_type == "text"
        assert doc.total_words > 0

    @pytest.mark.asyncio
    async def test_ingest_nonexistent_raises(self, config, mock_client):
        agent = IngestAgent(config)
        with pytest.raises(FileNotFoundError):
            await agent.run(path="/nonexistent/file.txt")

    @pytest.mark.asyncio
    async def test_ingest_creates_chunks(self, config, mock_client, sample_doc_path):
        agent = IngestAgent(config)
        doc = await agent.run(path=sample_doc_path)
        for chunk in doc.chunks:
            assert chunk.chunk_id.startswith("doc-")
            assert chunk.document_id == doc.doc_id
            assert len(chunk.text) > 0

    @pytest.mark.asyncio
    async def test_ingest_with_sections(self, config, mock_client, sample_doc_path):
        agent = IngestAgent(config)
        doc = await agent.run(path=sample_doc_path, extract_sections=True)
        sections = {c.section for c in doc.chunks}
        assert len(sections) > 1

    @pytest.mark.asyncio
    async def test_batch_ingest(self, config, mock_client, tmp_path):
        for i in range(3):
            p = tmp_path / f"doc{i}.txt"
            p.write_text(f"Document {i} content. " * 30)
        agent = IngestAgent(config)
        docs = await agent.run_batch([tmp_path / f"doc{i}.txt" for i in range(3)])
        assert len(docs) == 3


class TestTextChunk:
    """Test TextChunk dataclass."""

    def test_word_count_computed(self):
        c = TextChunk(
            chunk_id="c1",
            document_id="d1",
            text="hello world test",
            start_offset=0,
            end_offset=16,
        )
        assert c.word_count == 3

    def test_char_count_computed(self):
        c = TextChunk(chunk_id="c1", document_id="d1", text="hello", start_offset=0, end_offset=5)
        assert c.char_count == 5


class TestDocument:
    """Test Document dataclass."""

    def test_total_words(self):
        chunks = [
            TextChunk("c1", "d1", "hello world", 0, 11),
            TextChunk("c2", "d1", "foo bar baz", 12, 23),
        ]
        doc = Document(
            doc_id="d1",
            filename="test.txt",
            content="...",
            file_type="text",
            chunks=chunks,
        )
        assert doc.total_words == 5


class TestBinaryFormats:
    """Real PDF/DOCX files through the optional ``docs`` extra (skipped without it)."""

    @pytest.mark.asyncio
    async def test_pdf_pages_in_order(self, tmp_path):
        pymupdf = pytest.importorskip("pymupdf")
        path = tmp_path / "two-pages.pdf"
        pdf = pymupdf.open()
        for text in ("Alpha page one.", "Beta page two."):
            pdf.new_page().insert_text((72, 72), text)
        pdf.save(str(path))
        pdf.close()

        doc = await IngestAgent().run(path=path)

        assert doc.file_type == "pdf"
        assert "Alpha page one." in doc.content and "Beta page two." in doc.content
        assert doc.content.index("Alpha") < doc.content.index("Beta")

    @pytest.mark.asyncio
    async def test_docx_paragraphs(self, tmp_path):
        docx = pytest.importorskip("docx")
        path = tmp_path / "note.docx"
        document = docx.Document()
        document.add_paragraph("First paragraph.")
        document.add_paragraph("Second paragraph.")
        document.save(str(path))

        doc = await IngestAgent().run(path=path)

        assert doc.file_type == "docx"
        assert "First paragraph." in doc.content and "Second paragraph." in doc.content
