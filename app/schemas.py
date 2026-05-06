from datetime import datetime

from pydantic import BaseModel, Field


class KeywordCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    enabled: bool = True


class KeywordBulkCreate(BaseModel):
    text: str | None = Field(default=None, max_length=5000)
    names: list[str] = Field(default_factory=list)
    enabled: bool = True


class KeywordUpdate(BaseModel):
    enabled: bool


class KeywordOut(BaseModel):
    id: int
    name: str
    enabled: bool
    created_at: datetime


class KeywordBulkOut(BaseModel):
    created: list[KeywordOut]
    existing: list[str] = Field(default_factory=list)
    invalid: list[str] = Field(default_factory=list)


class RunRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=100)


class SourcePaper(BaseModel):
    title: str
    url: str | None = None
    authors: list[str] = Field(default_factory=list)


class SourceNews(BaseModel):
    title: str
    url: str | None = None


class Sources(BaseModel):
    arxiv: list[SourcePaper] = Field(default_factory=list)
    huggingface_papers: list[SourcePaper] = Field(default_factory=list)
    huggingface_models: list[SourcePaper] = Field(default_factory=list)
    geeknews: list[SourceNews] = Field(default_factory=list)
    aitimes: list[SourceNews] = Field(default_factory=list)


class AnalysisOut(BaseModel):
    id: int
    keyword: str
    result: str
    run_type: str
    sources: Sources | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime


class AnalysisPage(BaseModel):
    items: list[AnalysisOut]
    total: int
    has_more: bool
    next_before_id: int | None = None
