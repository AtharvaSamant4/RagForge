"""Deterministic compiler: only versioned trusted files plus validated JSON/source bytes."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

from .config import settings

VERSION="1.2.0"
TEMPLATE=Path(__file__).resolve().parents[1]/"standalone_template"


class ExportError(ValueError):
    pass


def canonical(path):
    return path.read_bytes().removeprefix(b"\xef\xbb\xbf").replace(b"\r\n",b"\n")


def template_files():
    entries={}
    for path in sorted(TEMPLATE.rglob("*")):
        if path.is_symlink():raise ExportError("Symlinks are not allowed in trusted templates")
        if path.is_dir() or "__pycache__" in path.parts:continue
        name=path.relative_to(TEMPLATE).as_posix()
        allowed=name in {"Dockerfile","compose.yaml","requirements.lock.txt","README.md",".env.example",".gitignore",".dockerignore","data/knowledge/.keep"} or (path.suffix==".py" and name.startswith(("app/","scripts/","tests/"))) or name=="scripts/example.mjs"
        if not allowed:raise ExportError("File is outside the approved template catalog")
        if path.suffix in (".pyc",".log") or name in (".env",".standalone-key"):
            raise ExportError("Unexpected file in trusted template")
        entries[name]=canonical(path)
    return entries


def template_digest(entries=None):
    entries=entries if entries is not None else template_files()
    return hashlib.sha256(b"".join(name.encode()+b"\0"+hashlib.sha256(data).digest() for name,data in sorted(entries.items()))).hexdigest()


def safe_source(storage_name,expected_size,expected_sha):
    if not re.fullmatch(r"[a-f0-9]{32}\.(pdf|docx|txt|md|csv)",storage_name):
        raise ExportError("Unsafe source storage name")
    path=settings().storage_dir/storage_name
    before=path.lstat()
    if not stat.S_ISREG(before.st_mode) or getattr(before,"st_file_attributes",0)&0x400:
        raise ExportError("Source must be a regular file, without symlinks or reparse points")
    if before.st_size!=expected_size or expected_size>settings().max_upload_mb*1024**2:
        raise ExportError("Source size changed or exceeds its limit")
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_BINARY",0))
    with os.fdopen(fd,"rb") as source:
        opened=os.fstat(source.fileno())
        if (opened.st_dev,opened.st_ino)!=(before.st_dev,before.st_ino):
            raise ExportError("Source changed during export")
        data=source.read(expected_size+1)
    if len(data)!=expected_size or hashlib.sha256(data).hexdigest()!=expected_sha:
        raise ExportError("Source checksum changed; retry after repairing the document")
    return data


def scan(name,data,secrets=()):
    path=PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or any(ord(c)<32 for c in name):
        raise ExportError("Unsafe archive entry")
    if name in (".env",".standalone-key") or name.endswith((".pem",".key")):
        raise ExportError("Credential files cannot be exported")
    if any(secret and len(secret)>=12 and secret.encode() in data for secret in secrets):
        raise ExportError("A server credential was detected in the package; remove it before exporting")
    if not name.startswith("data/knowledge/") and re.search(rb"(?:sk-(?:proj-)?[A-Za-z0-9_-]{24,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)",data):
        raise ExportError("Potential credential in generated configuration/template")


def compile_archive(target:Path,manifest:dict,sources:list[dict],pilot_evidence=None):
    entries=template_files()
    if manifest.get("generator_version")!=VERSION or manifest.get("template_sha256")!=template_digest(entries):
        raise ExportError("Trusted template version changed after enqueue; create a new export")
    if sum(s["size_bytes"] for s in sources)>settings().export_max_source_mb*1024**2:
        raise ExportError("Selected sources exceed the export limit")
    entries["config/manifest.json"]=(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+"\n").encode()
    if pilot_evidence is not None:
        entries['config/pilot-evidence.json']=(json.dumps(pilot_evidence,sort_keys=True,indent=2)+'\n').encode()
    credentials=[settings().openai_api_key]
    def write(archive,name,data):
        scan(name,data,credentials)
        info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
        info.create_system=3
        info.external_attr=0o100644<<16
        info.compress_type=zipfile.ZIP_DEFLATED
        archive.writestr(info,data,compresslevel=6)
        if archive.fp.tell()>settings().export_max_archive_mb*1024**2:
            raise ExportError("Generated archive exceeds the configured size limit")
    with zipfile.ZipFile(target,"w") as archive:
        for name,data in sorted(entries.items()):write(archive,name,data)
        for source in sources:
            data=safe_source(source["storage_name"],source["size_bytes"],source["sha256"])
            write(archive,source["path"],data)
    if target.stat().st_size>settings().export_max_archive_mb*1024**2:
        raise ExportError("Generated archive exceeds the configured size limit")
    return {"size_bytes":target.stat().st_size,"sha256":hashlib.sha256(target.read_bytes()).hexdigest()}
