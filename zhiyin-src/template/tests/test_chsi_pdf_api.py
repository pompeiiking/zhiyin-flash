from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx

from zhiyin_api.app import create_app
from zhiyin_api.facade import configure_facade
from zhiyin_api.facade.application import DefaultApplicationFacade
from zhiyin_business.contracts.chsi_import import ChsiPdfPreview
from zhiyin_kernel.errors import AccessDenied


class Facade:
    def __init__(self):
        self.preview_chsi_pdf = AsyncMock(return_value=ChsiPdfPreview(
            preview_id='preview', expires_at=datetime.now(timezone.utc).isoformat(),
            fields=[], can_import=False))
        self.confirm_chsi_pdf = AsyncMock()

    async def resolve_user_id(self, request):
        if request.headers.get('Authorization') != 'Bearer test-only':
            raise AccessDenied('请登录。')
        return 'alice'


async def test_authenticated_upload_limits_and_confirm_rejects_client_values():
    facade = Facade()
    configure_facade(facade)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url='http://test') as client:
        response = await client.post('/api/v1/app/chsi/pdf/preview', files={'file': ('r.pdf', b'%PDF-')})
        assert response.status_code == 401 and not facade.preview_chsi_pdf.called
        headers = {'Authorization': 'Bearer test-only'}
        response = await client.post('/api/v1/app/chsi/pdf/preview', headers=headers,
                                     files={'file': ('r.pdf', b'x' * 2_000_001)})
        assert response.status_code == 422 and not facade.preview_chsi_pdf.called
        response = await client.post('/api/v1/app/chsi/pdf/preview', headers=headers,
                                     files={'file': ('r.pdf', b'%PDF-')})
        assert response.status_code == 200 and response.json()['data']['preview_id'] == 'preview'
        assert facade.preview_chsi_pdf.call_args.args == ('alice', b'%PDF-')
        response = await client.post('/api/v1/app/chsi/pdf/confirm', headers=headers,
            json={'preview_id': 'preview', 'selected_keys': ['major'], 'value': 'forged'})
        assert response.status_code == 422 and not facade.confirm_chsi_pdf.called


async def test_application_facade_delegates_to_import_service():
    service = AsyncMock()
    facade = DefaultApplicationFacade(identity=None, registry=None, orchestrator=None, workspace=None,
        assets=None, function=None, ai_tasks=None, chsi_imports=service)
    await facade.preview_chsi_pdf('alice', b'pdf')
    service.preview.assert_awaited_once_with('alice', b'pdf')
    await facade.confirm_chsi_pdf('alice', 'request')
    service.confirm.assert_awaited_once_with('alice', 'request')
