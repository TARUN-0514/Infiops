"""Turn uploaded files into text sections, locally. Each section keeps its page, slide or
sheet so answers can cite where a passage came from."""

import csv
import io
import re
from dataclasses import dataclass
from pathlib import PurePath

TEXT_TYPES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "text/vtt",
    "application/x-subrip",
    "application/json",
}
PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
IMAGES = {"image/png", "image/jpeg", "image/webp"}
SUPPORTED = TEXT_TYPES | {PDF, DOCX, XLSX, PPTX} | IMAGES

EXTENSIONS = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".vtt": "text/vtt",
    ".srt": "application/x-subrip",
    ".json": "application/json",
    ".pdf": PDF,
    ".docx": DOCX,
    ".xlsx": XLSX,
    ".pptx": PPTX,
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class ParseError(ValueError):
    pass


@dataclass
class Section:
    text: str
    page: int | None = None
    label: str | None = None


def detect_type(filename: str, data: bytes, declared: str | None) -> str:
    """Trust the file's bytes over the browser's claim."""
    if data.startswith(b"%PDF"):
        return PDF
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    ext = PurePath(filename.lower()).suffix
    guessed = EXTENSIONS.get(ext)
    if data.startswith(b"PK\x03\x04"):
        if guessed in (DOCX, XLSX, PPTX):
            return guessed
        raise ParseError("This archive isn't a Word, Excel or PowerPoint file.")
    if guessed in TEXT_TYPES:
        try:
            data[:4096].decode("utf-8")
        except UnicodeDecodeError:
            raise ParseError("This text file isn't UTF-8.") from None
        return guessed
    raise ParseError(
        "Unsupported file. Use PDF, DOCX, XLSX, PPTX, PNG, JPG, WEBP, TXT, MD, CSV, VTT or SRT."
    )


def _clean(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _pdf(data: bytes) -> list[Section]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ParseError("This PDF is password protected.")
        return [
            Section(_clean(p.extract_text() or ""), page=i + 1) for i, p in enumerate(reader.pages)
        ]
    except PdfReadError as exc:
        raise ParseError(f"Couldn't read this PDF ({exc}).") from None


def _docx(data: bytes) -> list[Section]:
    import docx

    d = docx.Document(io.BytesIO(data))
    parts = [p.text for p in d.paragraphs if p.text.strip()]
    for table in d.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    return [Section(_clean("\n".join(parts)))]


def _xlsx(data: bytes) -> list[Section]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out = []
    for i, ws in enumerate(wb.worksheets):
        rows = []
        for row in ws.iter_rows(values_only=True):
            cells = ["" if v is None else str(v) for v in row]
            if any(c.strip() for c in cells):
                rows.append(" | ".join(cells).rstrip(" |"))
            if len(rows) >= 5000:
                break
        out.append(Section(_clean("\n".join(rows)), page=i + 1, label=ws.title[:120]))
    wb.close()
    return out


def _pptx(data: bytes) -> list[Section]:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    out = []
    for i, slide in enumerate(prs.slides):
        parts = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip():
                parts.append(shape.text_frame.text)
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                parts.append(f"Notes: {notes}")
        out.append(Section(_clean("\n".join(parts)), page=i + 1, label=f"Slide {i + 1}"))
    return out


_TIMESTAMP = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?[.,]\d{1,3} --> .*$|^\d+$|^WEBVTT.*$")


def _text(data: bytes, mime: str) -> list[Section]:
    text = data.decode("utf-8", "replace")
    if mime in ("text/vtt", "application/x-subrip"):
        text = "\n".join(
            line for line in text.splitlines() if line.strip() and not _TIMESTAMP.match(line)
        )
    elif mime == "text/csv":
        rows = list(csv.reader(io.StringIO(text)))
        text = "\n".join(" | ".join(r) for r in rows[:20000])
    return [Section(_clean(text))]


def parse(data: bytes, mime: str) -> list[Section]:
    """Text sections for every type except images (those need the vision model)."""
    if mime == PDF:
        sections = _pdf(data)
    elif mime == DOCX:
        sections = _docx(data)
    elif mime == XLSX:
        sections = _xlsx(data)
    elif mime == PPTX:
        sections = _pptx(data)
    elif mime in TEXT_TYPES:
        sections = _text(data, mime)
    else:
        raise ParseError("Unsupported file type.")
    return [s for s in sections if s.text]


def chunk(sections: list[Section], size: int = 1200, overlap: int = 150) -> list[Section]:
    """Split sections into overlapping chunks on paragraph or sentence boundaries."""
    out: list[Section] = []
    for sec in sections:
        text = sec.text
        start = 0
        while start < len(text):
            end = min(len(text), start + size)
            if end < len(text):
                window = text[start:end]
                cut = max(window.rfind("\n\n"), window.rfind(". "), window.rfind("\n"))
                if cut > size // 2:
                    end = start + cut + 1
            piece = text[start:end].strip()
            if piece:
                out.append(Section(piece, sec.page, sec.label))
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
    return out
