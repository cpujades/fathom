from pydantic import BaseModel, HttpUrl


class SummarizeRequest(BaseModel):
    url: HttpUrl


class SummarizeResponse(BaseModel):
    summary_id: str
    markdown: str
    pdf_url: str
