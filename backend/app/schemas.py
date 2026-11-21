from typing import Literal
from urllib.parse import urlparse
import ipaddress
import re

from pydantic import BaseModel, Field, field_validator, model_validator


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=200)

    @field_validator("email")
    @classmethod
    def email_valid(cls, value):
        value = value.strip().lower()
        if "@" not in value or "." not in value.split("@")[-1] or any(x.isspace() for x in value):
            raise ValueError("Enter a valid email address")
        return value


class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)

    @field_validator("name")
    @classmethod
    def name_valid(cls, value):
        if not value.strip():
            raise ValueError("A project name is required")
        return value.strip()


class PipelineInput(BaseModel):
    strategy: Literal["vector", "keyword", "hybrid"] = "hybrid"
    chunk_size: int = Field(default=180, ge=60, le=1000)
    overlap: int = Field(default=30, ge=0, le=200)
    top_k: int = Field(default=5, ge=1, le=15)
    min_score: float = Field(default=0.12, ge=0.05, le=0.9)
    semantic_min_score: float = Field(default=0.32, ge=0.15, le=0.9)
    auto: bool = True

    @model_validator(mode="after")
    def check_overlap(self):
        if self.overlap >= self.chunk_size:
            raise ValueError("Overlap must be smaller than chunk size")
        return self


class QueryInput(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    conversation_id: str | None = None

    @field_validator("question")
    @classmethod
    def nonempty(cls, value):
        if len(value.strip()) < 2:
            raise ValueError("Enter a question")
        return value.strip()


class KeyInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[Literal["query", "read", "documents"]] = Field(default_factory=lambda: ["query", "read"], min_length=1)


class WidgetInput(BaseModel):
    enabled: bool = False
    title: str = Field(default="Knowledge assistant", min_length=1, max_length=80)
    welcome: str = Field(default="Ask a question about our documentation.", max_length=300)
    color: str = Field(default="#14b8a6", pattern=r"^#[0-9a-fA-F]{6}$")
    theme: Literal["dark", "light"] = "dark"
    allowed_origins: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("allowed_origins")
    @classmethod
    def valid_origins(cls, values):
        result = []
        for value in values:
            p = urlparse(value)
            if p.scheme not in ("https", "http") or not p.netloc or p.username or p.password or p.path not in ("", "/") or p.query or p.fragment:
                raise ValueError("Use explicit http(s) origins without paths or wildcards")
            try:
                host = p.hostname or ""
                port = p.port
                if ":" in host:
                    host = "[" + str(ipaddress.IPv6Address(host)) + "]"
                else:
                    host = host.encode("idna").decode("ascii").lower()
                    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host):
                        raise ValueError("Invalid hostname")
            except (ValueError, UnicodeError):
                raise ValueError("Use a valid hostname or IP address and optional port") from None
            result.append(f"{p.scheme}://{host}" + (f":{port}" if port is not None else ""))
        return result

    @model_validator(mode="after")
    def publication(self):
        if self.enabled and not self.allowed_origins:
            raise ValueError("At least one embedding origin is required for publication")
        return self


class CaseInput(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    relevant_document_ids: list[str] = Field(default_factory=list, max_length=20)
    expected_answer: str = Field(default="", max_length=3000)
    expect_refusal: bool = False
    verified: bool = True


class RunInput(BaseModel):
    include_unverified: bool = False
