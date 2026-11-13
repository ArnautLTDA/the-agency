"""Semantic Markdown Chunking along header boundaries (TC-156)."""

import re


def chunk_markdown_by_headers(markdown_text: str, max_chunk_chars: int = 1500) -> list[str]:
    """Splits markdown documents into semantically coherent sections by headers (TC-156)."""
    lines = markdown_text.splitlines()
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_length = 0

    header_pattern = re.compile(r"^(#{1,3})\s+(.+)$")

    for line in lines:
        match = header_pattern.match(line)
        if match and current_chunk:
            chunk_str = "\n".join(current_chunk).strip()
            if chunk_str:
                chunks.append(chunk_str)
            current_chunk = [line]
            current_length = len(line)
        else:
            current_chunk.append(line)
            current_length += len(line) + 1
            if current_length >= max_chunk_chars:
                chunk_str = "\n".join(current_chunk).strip()
                if chunk_str:
                    chunks.append(chunk_str)
                current_chunk = []
                current_length = 0

    if current_chunk:
        chunk_str = "\n".join(current_chunk).strip()
        if chunk_str:
            chunks.append(chunk_str)

    return chunks if chunks else [markdown_text.strip()]
