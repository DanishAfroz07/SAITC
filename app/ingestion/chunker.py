"""Splits document text into chunks, section by section. Tables (detected
as runs of pipe-delimited lines) are always kept whole in their own chunk,
never split row by row or merged with prose - so the model always sees a
table row's columns together, e.g. "SAR 100,000 | Board approval".
"""
import re
from dataclasses import dataclass

from app.models import Chunk, DocumentMetadata

_HEADING_RE = re.compile(r"^(?:\d+(?:\.\d+)*\.?\s+\S.*|##\s+\S.*|Q:\s+\S.*)$")
_TABLE_ROW_RE = re.compile(r".+\|.+")


@dataclass
class _Section:
    heading: str
    lines: list[str]


class SectionChunker:
    """Chunks one document's text, section by section."""

    def __init__(self, max_chars: int) -> None:
        self._max_chars = max_chars

    def chunk(self, text: str, metadata: DocumentMetadata) -> list[Chunk]:
        chunks: list[Chunk] = []
        index = 0
        for section in self._split_sections(text):
            for piece_text, is_table in self._split_section_body(section.lines):
                if not piece_text.strip():
                    continue
                chunks.append(
                    Chunk(
                        chunk_id=f"{metadata.document_id}::{index}",
                        document_id=metadata.document_id,
                        section=section.heading,
                        text=piece_text.strip(),
                        is_table=is_table,
                        metadata=metadata,
                    )
                )
                index += 1
        return chunks

    def _split_sections(self, text: str) -> list[_Section]:
        sections: list[_Section] = []
        current = _Section(heading="Document header", lines=[])
        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            if _HEADING_RE.match(line.strip()):
                if current.lines:
                    sections.append(current)
                current = _Section(heading=line.strip(), lines=[])
            else:
                current.lines.append(line)
        if current.lines:
            sections.append(current)
        return sections

    def _split_section_body(self, lines: list[str]) -> list[tuple[str, bool]]:
        """Groups table rows separately from prose. A blank line inside a
        table run is dropped, not treated as a break - PDF extraction can
        insert one between a table's header and body rows as an artefact."""
        pieces: list[tuple[str, bool]] = []
        prose_buffer: list[str] = []
        table_buffer: list[str] = []

        def flush_prose() -> None:
            if prose_buffer:
                pieces.extend(self._split_prose("\n".join(prose_buffer)))
                prose_buffer.clear()

        def flush_table() -> None:
            if table_buffer:
                pieces.append(("\n".join(table_buffer), True))
                table_buffer.clear()

        for line in lines:
            stripped = line.strip()
            if _TABLE_ROW_RE.match(stripped):
                flush_prose()
                table_buffer.append(line)
            elif not stripped:
                if not table_buffer:
                    prose_buffer.append(line)
                # else: blank line inside a table run - dropped, see above.
            else:
                flush_table()
                prose_buffer.append(line)
        flush_table()
        flush_prose()
        return pieces

    def _split_prose(self, text: str) -> list[tuple[str, bool]]:
        """Splits prose on paragraph (blank-line) boundaries, packing
        paragraphs into chunks up to max_chars rather than cutting mid-idea."""
        paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
        if not paragraphs:
            return []

        pieces: list[tuple[str, bool]] = []
        buffer = ""
        for paragraph in paragraphs:
            candidate = f"{buffer}\n\n{paragraph}" if buffer else paragraph
            if len(candidate) > self._max_chars and buffer:
                pieces.append((buffer, False))
                buffer = paragraph
            else:
                buffer = candidate
        if buffer:
            pieces.append((buffer, False))
        return pieces
