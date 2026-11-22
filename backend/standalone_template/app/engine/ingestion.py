import csv
import io
import re
import zipfile
import struct
from pathlib import Path, PurePosixPath


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


def extract(path: Path, kind: str):
    from .parse_isolation import parse_document
    return parse_document(path, kind)


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
