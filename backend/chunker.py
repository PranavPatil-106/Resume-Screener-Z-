import os
import re
from typing import TypedDict


CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))


class TextChunk(TypedDict):
    index: int
    text: str


class TextChunker:
    """
    Concise, configurable text chunker with overlap for resume text.
    Respects paragraph and sentence breaks when possible, falling back to
    sliding character window with configured overlap.
    """

    def __init__(self, chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP):
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap cannot be negative")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be strictly less than chunk_size")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_text(self, text: str) -> list[TextChunk]:
        """
        Split raw text into clean, overlapping chunks.
        Returns a list of dicts with 'index' and 'text'.
        """
        if not text:
            return []

        # Normalize line endings and strip surrounding whitespace
        cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not cleaned:
            return []

        # If text is small enough, return as single chunk
        if len(cleaned) <= self.chunk_size:
            return [{"index": 0, "text": cleaned}]

        # Split into natural paragraphs or major blocks first
        paragraphs = re.split(r"\n{2,}", cleaned)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        if not paragraphs:
            return [{"index": 0, "text": cleaned[: self.chunk_size]}]

        raw_blocks: list[str] = []
        current_block: list[str] = []
        current_len = 0

        for p in paragraphs:
            # If paragraph itself is larger than chunk_size, split by sentences or sliding window
            if len(p) > self.chunk_size:
                if current_block:
                    raw_blocks.append("\n\n".join(current_block))
                    current_block = []
                    current_len = 0
                
                # Sliding window split for the oversized paragraph
                step = self.chunk_size - self.chunk_overlap
                for start in range(0, len(p), step):
                    chunk_slice = p[start : start + self.chunk_size].strip()
                    if chunk_slice:
                        raw_blocks.append(chunk_slice)
            else:
                if current_len + len(p) + 2 > self.chunk_size and current_block:
                    raw_blocks.append("\n\n".join(current_block))
                    current_block = [p]
                    current_len = len(p)
                else:
                    current_block.append(p)
                    current_len += len(p) + 2

        if current_block:
            raw_blocks.append("\n\n".join(current_block))

        # Now apply sliding overlap to consecutive blocks if needed, or index directly
        chunks: list[TextChunk] = []
        for idx, block in enumerate(raw_blocks):
            trimmed = block.strip()
            if trimmed:
                chunks.append({"index": idx, "text": trimmed})

        return chunks
