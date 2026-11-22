import csv
import io
import re
import zipfile
import struct
from pathlib import Path, PurePosixPath

from docx import Document as DocxDocument
from pypdf import PdfReader


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
        # Bound central-directory allocation before zipfile constructs ZipInfo objects.
        eocd=content.rfind(b"PK\x05\x06",max(0,len(content)-65557))
        if eocd<0 or eocd+22>len(content):raise ExtractionError("The file is not a valid DOCX archive")
        disk,central_disk,disk_entries,entries,central_bytes=struct.unpack_from("<HHHHI",content,eocd+4)
        if disk or central_disk or disk_entries!=entries or entries>2000 or central_bytes>1024*1024:
            raise ExtractionError("DOCX archive directory exceeds the safe limit")
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise ExtractionError("The file is not a DOCX document")
                if sum(x.file_size for x in archive.infolist()) > 50_000_000:
                    raise ExtractionError("DOCX expands beyond the safe extraction limit")
                if len(archive.infolist())>2000 or any(x.file_size>1_000_000 and x.file_size>200*max(x.compress_size,1) for x in archive.infolist()):
                    raise ExtractionError("DOCX compression ratio or entry count exceeds the safe limit")
                if any(PurePosixPath(x.filename.replace('\\','/')).is_absolute() or '..' in PurePosixPath(x.filename.replace('\\','/')).parts or (x.external_attr>>16)&0o170000==0o120000 for x in archive.infolist()):
                    raise ExtractionError("DOCX contains unsafe archive entries")
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


def extract(path: Path, kind: str, max_chars: int = 2_000_000) -> tuple[list[tuple[str, dict]], dict]:
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
            if total > max_chars:
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
    if total > max_chars:
        raise ExtractionError("Extracted content exceeds the configured limit")
    if not any(text.strip() for text, _ in sections):
        raise ExtractionError("No selectable text found. Scanned PDFs require OCR, which is not supported yet.")
    metadata["characters"] = total
    return sections, metadata
