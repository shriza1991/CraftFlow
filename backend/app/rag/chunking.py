"""Deterministic text chunking preserving paragraph boundaries and origin metadata."""

import re
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings

settings = get_settings()


@dataclass
class TextChunk:
    """Represents a chunk of text extracted from a knowledge document."""

    chunk_index: int
    content: str
    character_count: int
    token_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


class TextChunker:
    """Splits knowledge document text into bounded, overlapping chunks."""

    def __init__(
        self,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ):
        self.chunk_size = chunk_size or settings.RAG_CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.RAG_CHUNK_OVERLAP
        if self.chunk_overlap >= self.chunk_size:
            self.chunk_overlap = max(0, self.chunk_size // 4)

    @staticmethod
    def estimate_token_count(text: str) -> int:
        """Rough token count estimation (~4 characters per token in English)."""
        return max(1, len(text) // 4)

    def chunk_document(
        self,
        content: str,
        base_metadata: dict[str, Any] | None = None,
    ) -> list[TextChunk]:
        """Split text into chunks, prioritizing paragraph and sentence breaks."""
        raw_text = content.strip()
        if not raw_text:
            return []

        # If text is smaller than chunk size, return single chunk
        if len(raw_text) <= self.chunk_size:
            meta = dict(base_metadata or {})
            meta["chunk_index"] = 0
            return [
                TextChunk(
                    chunk_index=0,
                    content=raw_text,
                    character_count=len(raw_text),
                    token_count=self.estimate_token_count(raw_text),
                    metadata=meta,
                )
            ]

        # Break text into atomic units (paragraphs, then sentences if necessary)
        paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
        units: list[str] = []
        for p in paragraphs:
            if len(p) <= self.chunk_size:
                units.append(p)
            else:
                # Break large paragraphs into sentences
                sentences = re.split(r"(?<=[.!?])\s+", p)
                for s in sentences:
                    s_clean = s.strip()
                    if s_clean:
                        units.append(s_clean)

        chunks: list[TextChunk] = []
        current_chunk_parts: list[str] = []
        current_length = 0
        chunk_idx = 0

        for unit in units:
            unit_len = len(unit)
            # If adding unit exceeds chunk_size and we already have content:
            if current_length + unit_len + 1 > self.chunk_size and current_chunk_parts:
                chunk_text = "\n\n".join(current_chunk_parts).strip()
                meta = dict(base_metadata or {})
                meta["chunk_index"] = chunk_idx
                chunks.append(
                    TextChunk(
                        chunk_index=chunk_idx,
                        content=chunk_text,
                        character_count=len(chunk_text),
                        token_count=self.estimate_token_count(chunk_text),
                        metadata=meta,
                    )
                )
                chunk_idx += 1

                # Carry over overlap from the end of current_chunk_parts
                overlap_parts: list[str] = []
                overlap_len = 0
                for part in reversed(current_chunk_parts):
                    if overlap_len + len(part) <= self.chunk_overlap:
                        overlap_parts.insert(0, part)
                        overlap_len += len(part)
                    else:
                        break

                current_chunk_parts = overlap_parts
                current_length = overlap_len

            current_chunk_parts.append(unit)
            current_length += unit_len + 1

        # Final trailing chunk
        if current_chunk_parts:
            chunk_text = "\n\n".join(current_chunk_parts).strip()
            if chunk_text:
                meta = dict(base_metadata or {})
                meta["chunk_index"] = chunk_idx
                chunks.append(
                    TextChunk(
                        chunk_index=chunk_idx,
                        content=chunk_text,
                        character_count=len(chunk_text),
                        token_count=self.estimate_token_count(chunk_text),
                        metadata=meta,
                    )
                )

        return chunks
