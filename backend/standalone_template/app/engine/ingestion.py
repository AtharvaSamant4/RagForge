import csv
import io
import re
import zipfile
from pathlib import Path

from docx import Document as DocxDocument
from pypdf import PdfReader

from .config import settings

SUPPORTED = {".pdf", ".docx", ".txt", ".md", ".csv"}


class ExtractionError(ValueError):
    pass


def validate_file(name: str, content: bytes) -> tuple[str, str]:
    # Display names are never used as filesystem paths.
    safe = name.replace("\\", "/").split("/")[-1]
    safe = re.sub(r"[\x00-\x1f\x7f]", "", safe)[:255]
    kind = Path(safe).suffix.lower()
    if kind not in SUPPORTED:
        raise ExtractionError("Supported files: PDF, DOCX, TXT, Markdown and textual CSV")
    if not content:
        raise ExtractionError("The file is empty")
    if kind == ".pdf" and not content.startswith(b"%PDF-"):
        raise ExtractionError("The file does not have a valid PDF signature")
    if kind == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise ExtractionError("The file is not a DOCX document")
                if sum(x.file_size for x in archive.infolist()) > 50_000_000:
                    raise ExtractionError("DOCX expands beyond the safe extraction limit")
                if any(x.flag_bits & 1 for x in archive.infolist()):
                    raise ExtractionError("Encrypted DOCX files are not supported")
        except zipfile.BadZipFile:
            raise ExtractionError("The file is not a valid DOCX archive") from None
    if kind in {".txt", ".md", ".csv"}:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ExtractionError("Text files must use UTF-8 encoding") from None
        if "\x00" in text:
            raise ExtractionError("Binary content is not supported")
    return safe, kind.lstrip(".")


def extract(path: Path, kind: str) -> tuple[list[tuple[str, dict]], dict]:
    sections = []
    if kind == "pdf":
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ExtractionError("Encrypted PDFs are not supported")
        if len(reader.pages) > 500:
            raise ExtractionError("PDF exceeds the 500-page limit")
        total = 0
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            total += len(text)
            if total > settings().max_extracted_chars:
                raise ExtractionError("Extracted content exceeds the configured limit")
            sections.append((text, {"page": i + 1}))
        metadata = {"pages": len(reader.pages), "parser": "pypdf"}
    elif kind == "docx":
        # Recheck archive expansion in worker as a defense in depth.
        validate_file("source.docx", path.read_bytes())
        doc = DocxDocument(path)
        for i, paragraph in enumerate(doc.paragraphs):
            if paragraph.text.strip():
                sections.append((paragraph.text, {"paragraph": i + 1}))
        for t, table in enumerate(doc.tables):
            for r, row in enumerate(table.rows):
                sections.append((" | ".join(cell.text for cell in row.cells), {"table": t + 1, "row": r + 1}))
        metadata = {"parser": "python-docx", "paragraphs": len(doc.paragraphs)}
    elif kind == "csv":
        reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig")))
        if not reader.fieldnames or len(reader.fieldnames) > 100:
            raise ExtractionError("CSV needs a header and at most 100 columns")
        numeric, textual = 0, 0
        for i, row in enumerate(reader):
            if i >= 20_000:
                raise ExtractionError("CSV exceeds the 20,000-row limit")
            for value in row.values():
                if not isinstance(value, str) or not value.strip():
                    continue
                try:
                    float(value.replace(",", ""))
                    numeric += 1
                except ValueError:
                    textual += 1
            sections.append(("; ".join(f"{k}: {v}" for k, v in row.items() if k and isinstance(v, str) and v.strip()), {"row": i + 2}))
        if numeric > textual:
            raise ExtractionError("This CSV is mainly numeric. RAG supports textual/FAQ CSV, not analytical calculations.")
        metadata = {"parser": "csv", "columns": reader.fieldnames, "limitation": "Text retrieval only; no aggregation or analytical queries"}
    else:
        text = path.read_text(encoding="utf-8-sig")
        sections = [(text, {"section": "document"})]
        metadata = {"parser": "utf8"}
    total = sum(len(text) for text, _ in sections)
    if total > settings().max_extracted_chars:
        raise ExtractionError("Extracted content exceeds the configured limit")
    if not any(text.strip() for text, _ in sections):
        raise ExtractionError("No selectable text found. Scanned PDFs require OCR, which is not supported yet.")
    metadata["characters"] = total
    return sections, metadata


def chunk_sections(sections: list[tuple[str, dict]], size: int, overlap: int, count_tokens=None, max_tokens: int = 256) -> list[tuple[str, dict]]:
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("Invalid chunk boundaries")
    result = []
    for text, location in sections:
        words = list(re.finditer(r"\S+", text))
        start = 0
        while start < len(words):
            end = min(start + size, len(words))
            if count_tokens:
                low, high = start + 1, end
                while low <= high:
                    middle = (low + high) // 2
                    if count_tokens(text[words[start].start():words[middle-1].end()]) <= max_tokens:
                        low = middle + 1
                    else:
                        high = middle - 1
                end = max(start + 1, high)
                if count_tokens(text[words[start].start():words[end-1].end()]) > max_tokens:
                    raise ExtractionError("A single token sequence exceeds the embedding budget. Split the source into shorter words or identifiers.")
            left, right = words[start].start(), words[end - 1].end()
            result.append((text[left:right], {**location, "char_start": left, "char_end": right, **({"tokens": count_tokens(text[left:right])} if count_tokens else {})}))
            if end == len(words):
                break
            start = max(start + 1, end - min(overlap, max(0, (end - start)//3))) if count_tokens else end - overlap
    if len(result) > 10_000:
        raise ExtractionError("Document exceeds the 10,000-chunk limit")
    return result
