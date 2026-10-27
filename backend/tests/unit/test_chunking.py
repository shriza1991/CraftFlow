"""Unit tests for deterministic text chunking."""

import pytest
from app.rag.chunking import TextChunk, TextChunker


def test_chunker_empty_input():
    chunker = TextChunker(chunk_size=200, chunk_overlap=20)
    assert chunker.chunk_document("") == []
    assert chunker.chunk_document("   \n\n   ") == []


def test_chunker_short_text():
    chunker = TextChunker(chunk_size=500, chunk_overlap=50)
    text = "The Carrara Monolithic is carved from Italian marble."
    chunks = chunker.chunk_document(text, base_metadata={"title": "Carrara"})

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.chunk_index == 0
    assert chunk.content == text
    assert chunk.character_count == len(text)
    assert chunk.token_count > 0
    assert chunk.metadata["title"] == "Carrara"
    assert chunk.metadata["chunk_index"] == 0


def test_chunker_long_text_and_overlap():
    chunker = TextChunker(chunk_size=150, chunk_overlap=30)
    para1 = "Paragraph 1 describes the luxurious Bianco Carrara quarry in the Apuan Alps of Italy."
    para2 = "Paragraph 2 details the precision CNC carving and artisanal hand-finishing techniques."
    para3 = "Paragraph 3 outlines the structural floor requirements and live-load allowances."
    full_text = f"{para1}\n\n{para2}\n\n{para3}"

    chunks = chunker.chunk_document(full_text)

    assert len(chunks) >= 2
    # Verify sequential indexes
    for i, c in enumerate(chunks):
        assert c.chunk_index == i
        assert len(c.content) > 0
        assert c.token_count > 0
        assert c.character_count == len(c.content)


def test_chunker_deterministic_output():
    chunker1 = TextChunker(chunk_size=200, chunk_overlap=40)
    chunker2 = TextChunker(chunk_size=200, chunk_overlap=40)
    text = (
        "Solid stone bathtubs require careful architectural planning. "
        "The dead load of the stone exceeds 600 kg. "
        "Water adds another 300 kg. "
        "A certified structural engineer must verify the deflection limits."
    )

    chunks1 = chunker1.chunk_document(text)
    chunks2 = chunker2.chunk_document(text)

    assert len(chunks1) == len(chunks2)
    for c1, c2 in zip(chunks1, chunks2, strict=True):
        assert c1.chunk_index == c2.chunk_index
        assert c1.content == c2.content
        assert c1.character_count == c2.character_count
