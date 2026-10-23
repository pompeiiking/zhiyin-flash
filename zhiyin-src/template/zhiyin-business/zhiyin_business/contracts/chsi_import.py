from pydantic import BaseModel, ConfigDict, Field


class PdfFieldPreview(BaseModel):
    key: str
    label: str
    value: object
    current_value: object = None
    selectable: bool
    selected: bool = False
    reason: str = ""


class ChsiPdfPreview(BaseModel):
    preview_id: str
    expires_at: str
    report_date: str = ""
    valid_until: str = ""
    fields: list[PdfFieldPreview]
    warnings: list[str] = Field(default_factory=list)
    can_import: bool
    requires_ownership_confirmation: bool = False


class ChsiPdfConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_id: str = Field(min_length=1, max_length=80)
    selected_keys: list[str] = Field(max_length=20)
    ownership_confirmed: bool = False


class ChsiPdfReceipt(BaseModel):
    import_id: str
    imported_at: str
    imported: list[str]
    retained: list[str]
    skipped: list[str]
    message: str = "报告材料已导入，待在线核验。"
