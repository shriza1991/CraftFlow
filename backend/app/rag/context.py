"""RAG context builder formatting retrieved knowledge snippets with source attribution."""

from typing import Any

from app.rag.base import RetrievalChunk


class ContextBuilder:
    """Formats retrieved knowledge chunks into grounded context blocks for prompts."""

    @staticmethod
    def build_context(chunks: list[RetrievalChunk]) -> str:
        """Format retrieved chunks into a clearly demarcated data block."""
        if not chunks:
            return ""

        context_blocks = []
        for i, chunk in enumerate(chunks, 1):
            title = chunk.title or "Untitled Document"
            doc_id = chunk.document_id
            chunk_idx = chunk.chunk_index if chunk.chunk_index is not None else 0
            score = chunk.score

            header = f"[Source {i}: {title} | DocID: {doc_id} | Chunk {chunk_idx} | Relevance: {score:.2f}]"
            context_blocks.append(f"{header}\n{chunk.content.strip()}")

        return "\n\n".join(context_blocks)

    @staticmethod
    def extract_sources(chunks: list[RetrievalChunk]) -> list[dict[str, Any]]:
        """Extract structured source citation metadata from retrieved chunks."""
        sources = []
        seen = set()
        for chunk in chunks:
            key = (chunk.document_id, chunk.chunk_index)
            if key not in seen:
                seen.add(key)
                sources.append(
                    {
                        "document_id": chunk.document_id,
                        "chunk_id": chunk.id,
                        "title": chunk.title,
                        "score": chunk.score,
                        "source_id": chunk.source_id,
                        "chunk_index": chunk.chunk_index,
                    }
                )
        return sources
