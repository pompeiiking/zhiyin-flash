from fastapi import APIRouter, File, Request, UploadFile
from zhiyin_api.dto.common import ApiResponse
from zhiyin_api.dto.chsi_import import ChsiPdfPreview, ChsiPdfConfirm, ChsiPdfReceipt
from zhiyin_api.facade import get_facade
from zhiyin_kernel.errors import InvalidRequest

router = APIRouter(tags=["chsi"])


@router.post("/app/chsi/pdf/preview", response_model=ApiResponse[ChsiPdfPreview])
async def preview_chsi_pdf(request: Request, file: UploadFile = File(...)):
    facade = get_facade()
    try:
        user_id = await facade.resolve_user_id(request)
        data = await file.read(2_000_001)
        if len(data) > 2_000_000:
            raise InvalidRequest("PDF 超过 2MB，请上传学信网下载的单份原版报告。")
        return ApiResponse(data=await facade.preview_chsi_pdf(user_id, data))
    finally:
        await file.close()


@router.post("/app/chsi/pdf/confirm", response_model=ApiResponse[ChsiPdfReceipt])
async def confirm_chsi_pdf(request: Request, body: ChsiPdfConfirm):
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.confirm_chsi_pdf(user_id, body))
