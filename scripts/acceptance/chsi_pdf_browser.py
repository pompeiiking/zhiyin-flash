"""Loopback-only disposable PDF import acceptance API. No production credentials/data.

Run from the repository root with project dependencies installed. The browser harness
mounts the production AcademicVerification component and uses real PDF extraction,
production controllers and import services; only identity/workspace composition is
minimal and explicitly test-only. Synthetic PDFs do not replace official sample QA.
"""
from pathlib import Path
import io
import sys

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / 'zhiyin-src/template'
for package in ('zhiyin-kernel','zhiyin-api','zhiyin-business','zhiyin-data-sdk','zhiyin-infrastructure','zhiyin-orchestration'):
    sys.path.insert(0, str(TEMPLATE / package))

from fastapi.responses import Response
from zhiyin_api.app import create_app
from zhiyin_api.facade import configure_facade
from zhiyin_api.dto.workspace import WorkspacePageView, ProfilePanelView, ProfileFieldView
from zhiyin_business.services.chsi_import import ChsiPdfImportService
from zhiyin_business.services.profile import DefaultProfileService
from zhiyin_infrastructure.chsi.pdf import ChsiPdfReader
from zhiyin_infrastructure.local.chsi_imports import InMemoryChsiImportRepository
from zhiyin_infrastructure.local.repository import InMemoryProfileRepository, LocalJsonRegistryRepository
from zhiyin_kernel.errors import AccessDenied


class Events:
    async def publish(self, event): pass


repo = InMemoryProfileRepository()
profiles = DefaultProfileService(repo, Events())
imports = ChsiPdfImportService(profiles, InMemoryChsiImportRepository(repo), ChsiPdfReader(),
    LocalJsonRegistryRepository(str(TEMPLATE / 'data/registry')))


class AcceptanceFacade:
    async def resolve_user_id(self, request):
        token = request.headers.get('Authorization', '').removeprefix('Bearer ')
        if not token.startswith('acceptance-'):
            raise AccessDenied('隔离验收需要测试身份。')
        return token

    async def preview_chsi_pdf(self, user_id, data):
        return await imports.preview(user_id, data)

    async def confirm_chsi_pdf(self, user_id, body):
        return await imports.confirm(user_id, body)

    async def get_workspace(self, user_id):
        fields = await repo.list_fields(user_id)
        return WorkspacePageView(profile_panel=ProfilePanelView(fields=[ProfileFieldView(
            key=f.key, label=f.label, value=f.value, confidence=f.confidence, source=f.source,
            evidence=f.evidence, verification=f.verification, origin_ref=f.origin_ref, updated_at=f.updated_at)
            for f in fields]))


configure_facade(AcceptanceFacade())
app = create_app()


@app.get('/__acceptance/report.pdf')
async def synthetic_report():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    buffer = io.BytesIO()
    doc = canvas.Canvas(buffer)
    doc.setFont('STSong-Light', 12)
    for index, line in enumerate(['教育部学籍在线验证报告','姓名：验收测试人','学校名称：测试大学',
        '专业名称：计算机科学与技术','学号：20240001','入学日期：2024-09-01','有效期至：2099-12-31']):
        doc.drawString(40, 800-index*25, line)
    doc.save()
    return Response(buffer.getvalue(), media_type='application/pdf')


if __name__ == '__main__':
    import uvicorn
    harness = TEMPLATE / 'zhiyin-web/_chsi_pdf_acceptance.html'
    if harness.exists():
        raise SystemExit('临时验收 HTML 已存在，请先确认并移除后重试。')
    harness.write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>学籍导入隔离验收</title>
<body><h1>学籍导入隔离验收</h1><p>合成报告 · 本机临时数据</p><div id="app"></div>
<script type="module">
import {createApp,h} from 'vue';
import Component from '/src/components/AcademicVerification.vue';
import Sheet from '/src/components/InfoSheet.vue';
import '/src/styles/tokens.css';import '/src/styles/base.css';
import '/src/styles/workspace.css';import '/src/styles/touch.css';
localStorage.setItem('zhiyin_token','acceptance-'+(new URLSearchParams(location.search).get('user')||'desktop'));
createApp({render:()=>h(Sheet,{open:true,shape:'panel',title:'学籍核验与报告导入'},()=>h(Component))}).mount('#app');
</script></body></html>''', encoding='utf-8')
    try:
        uvicorn.run(app, host='127.0.0.1', port=8813, access_log=False)
    finally:
        harness.unlink(missing_ok=True)
