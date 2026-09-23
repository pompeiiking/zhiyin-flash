"""对话里交材料：文件真的传上来，正文**不进对话流**。

为什么值得单独守
----------------
此前"交一份材料"是前端把文件读成一大段文本，当成一条消息发出去。
代价有两笔，用户都看得见：

1. 对话框当场铺开几百行原文 —— 他要读的是主理的回话，不是自己刚交上去的东西；
2. 那段文本同时落进逐轮原文（`biz_conversation_turn`），于是"会话历史"点进去
   又是一整篇简历。

现在分成两件事，本文件把这条分工钉住：

   · **正文**只进这一轮的模型输入（`prompt_vars.user_input`）；
   · **落库与显示**的只有用户说的那一句（"简历在这，你看看"）。

顺带守住三件容易退化的：读不了的文件要给可执行的下一步、别人的材料 id 取不到、
上传回执里不许夹带正文。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from zhiyin_api.app import create_app
from zhiyin_api.dto.conversation import MessageRequest
from zhiyin_boot import Settings, build_container, wire_application
from zhiyin_boot.container import Container
from zhiyin_business.policies import (
    DisclosureHandoffPolicy,
    KeywordIntentPolicy,
    RegistryLeadPolicy,
    RuleStagePolicy,
)
from zhiyin_business.ports.orchestrator import TurnRequest
from zhiyin_business.services import DefaultOrchestrator
from zhiyin_business.services.memory import DefaultConversationMemoryService
from zhiyin_data_sdk.gateways.documents import DocumentReadError
from zhiyin_infrastructure.local.object_store import LocalFileStore
from zhiyin_infrastructure.local.repository import InMemoryConversationMemoryRepository
from zhiyin_infrastructure.textfile import LocalTextExtractor
from zhiyin_kernel.errors import InvalidRequest
from zhiyin_orchestration import AgentEngine, AgentRequest, AgentResult

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
USER_ID = "u-material"

RESUME = "我的简历\n技能：Python、数据分析\n项目：校园二手平台"


# ------------------------------------------------------------------ 抽取本身


def test_text_extraction_reads_common_encodings() -> None:
    """GBK 与带 BOM 的 UTF-8 都要读得对 —— 教务/办公软件导出的正是这两种。"""
    extractor = LocalTextExtractor()
    assert extractor.extract_text(RESUME.encode("gbk"), filename="简历.txt") == RESUME
    assert (
        extractor.extract_text(b"\xef\xbb\xbf" + RESUME.encode("utf-8"), filename="简历.txt")
        == RESUME
    )


def test_binary_documents_are_refused_with_the_next_step() -> None:
    """Excel / PDF 不是"读不出来"，是**本地读不了**：要说清换成什么再传。"""
    extractor = LocalTextExtractor()
    with pytest.raises(DocumentReadError) as excinfo:
        extractor.extract_text(b"PK\x03\x04\x14\x00", filename="简历.xlsx")
    assert "另存为 CSV" in str(excinfo.value)


def test_empty_document_is_not_reported_as_success() -> None:
    """空文件必须抛错：返回空串会被上游当成"读到了，只是没有内容"。"""
    extractor = LocalTextExtractor()
    with pytest.raises(DocumentReadError):
        extractor.extract_text(b"   ", filename="简历.txt")


# ------------------------------------------------------------------ 服务侧


def _memory_service(tmp_path: Path, *, with_documents: bool = True):
    return DefaultConversationMemoryService(
        InMemoryConversationMemoryRepository(),
        None,
        LocalTextExtractor() if with_documents else None,
        LocalFileStore(str(tmp_path)) if with_documents else None,
    )


@pytest.mark.asyncio
async def test_a_material_round_trips_and_stays_scoped_to_its_owner(tmp_path: Path) -> None:
    service = _memory_service(tmp_path)
    material = await service.put_material(USER_ID, name="简历.txt", data=RESUME.encode("gbk"))

    assert material.name == "简历.txt"
    assert material.chars == len(RESUME)
    body = await service.material_body(USER_ID, material.material_id)
    assert body.name == "简历.txt"
    assert body.text == RESUME

    # 别人的 id 取不到自己的材料：对象键里带 user_id，越权就是"找不到"
    with pytest.raises(LookupError):
        await service.material_body("u-other", material.material_id)


@pytest.mark.asyncio
async def test_unreadable_material_becomes_a_user_fixable_error(tmp_path: Path) -> None:
    """传 Excel → InvalidRequest（422 + 原话），不是 500。"""
    service = _memory_service(tmp_path)
    with pytest.raises(InvalidRequest) as excinfo:
        await service.put_material(USER_ID, name="简历.xlsx", data=b"PK\x03\x04")
    assert "另存为 CSV" in str(excinfo.value)


@pytest.mark.asyncio
async def test_unwired_material_upload_says_so(tmp_path: Path) -> None:
    """没装配就明确报错 —— 假装收下了等于"用户交了一份材料，模型什么都没看到"。"""
    service = _memory_service(tmp_path, with_documents=False)
    with pytest.raises(RuntimeError):
        await service.put_material(USER_ID, name="简历.txt", data=RESUME.encode())


# ------------------------------------------------------------------ 编排：正文只进模型输入


@pytest.fixture
def container(tmp_path: Path) -> Container:
    return build_container(
        Settings(
            use_remote_llm=True,
            llm_api_key="sk-test",
            llm_base_url="https://api.deepseek.com",
            llm_model="deepseek-flash",
            env="test",
            local_data_dir=str(DATA_DIR),
            local_registry_dir=str(DATA_DIR / "registry"),
            local_knowledge_dir=str(DATA_DIR / "knowledge"),
            local_object_dir=str(tmp_path / "objects"),
        )
    )


class _RecordingEngine(AgentEngine):
    """引擎桩：只记下这一轮下发的提示词变量，不调模型。"""

    def __init__(self) -> None:
        self.requests: list[AgentRequest] = []

    async def invoke(self, request: AgentRequest) -> AgentResult:
        self.requests.append(request)
        return AgentResult(
            agent_id=request.agent_id,
            structured={},
            raw_text="收到，我先看一遍这份材料。",
            valid=True,
        )


def _orchestrator(container: Container, engine: AgentEngine) -> DefaultOrchestrator:
    return DefaultOrchestrator(
        profiles=container.profile_service,
        behaviors=container.behavior_service,
        memories=container.memory_service,
        assets=container.asset_service,
        intent_policy=KeywordIntentPolicy(container.registry_service),
        stage_policy=RuleStagePolicy(container.registry_service),
        lead_policy=RegistryLeadPolicy(container.registry_service),
        handoff_policy=DisclosureHandoffPolicy(),
        agent_engine=engine,
        sessions=container.sessions,
        registry=container.registry_service,
        event_bus=container.event_bus_primitive,
    )


async def test_material_text_reaches_the_model_but_not_the_conversation(
    container: Container,
) -> None:
    """一份材料交上去：模型看得到正文，对话流里只有那一句话。"""
    engine = _RecordingEngine()
    task_id = "t-material"
    await _orchestrator(container, engine).handle_message(
        TurnRequest(
            user_id=USER_ID,
            task_id=task_id,
            message="简历在这，你看看",
            attachment_name="简历.txt",
            attachment_text=RESUME,
        )
    )

    # 1. 正文进模型输入（不然用户白交一份）
    user_input = engine.requests[0].prompt_vars["user_input"]
    assert RESUME in user_input
    assert "简历在这，你看看" in user_input
    assert "简历.txt" in user_input, "要交代这段正文是哪份材料，否则模型不知道在看什么"

    # 2. 落库的只有那一句话（会话历史点进去不该又是一整篇简历）
    turns = await container.memory_service.list_turns(USER_ID, task_id)
    mine = [turn for turn in turns if turn.role == "user"]
    assert mine and mine[0].text == "简历在这，你看看"
    assert RESUME not in mine[0].text


# ------------------------------------------------------------------ 接口侧


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(
        use_remote_llm=True,
        llm_api_key="sk-test",
        llm_base_url="https://api.deepseek.com",
        llm_model="deepseek-flash",
        env="test",
        local_data_dir=str(DATA_DIR),
        local_registry_dir=str(DATA_DIR / "registry"),
        local_knowledge_dir=str(DATA_DIR / "knowledge"),
        local_object_dir=str(tmp_path / "objects"),
    )
    with TestClient(wire_application(build_container(settings))) as test_client:
        yield test_client


def test_upload_endpoint_returns_what_it_is_not_the_text(client: TestClient) -> None:
    """回执里有"它是什么"（名字 / 大小 / 字数），**没有正文**。"""
    response = client.post(
        "/api/v1/app/conversation/material",
        files={"file": ("简历.txt", RESUME.encode("gbk"), "text/plain")},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "简历.txt"
    assert data["chars"] == len(RESUME)
    assert data["material_id"].startswith("mat_")
    assert "text" not in data
    assert RESUME not in response.text, "正文不许出现在回执里 —— 前端就是照着回执渲染的"


def test_upload_endpoint_refuses_an_excel_with_a_next_step(client: TestClient) -> None:
    response = client.post(
        "/api/v1/app/conversation/material",
        files={"file": ("简历.xlsx", b"PK\x03\x04\x14\x00", "application/vnd.ms-excel")},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == 1001
    assert "另存为 CSV" in body["message"]


def test_message_accepts_material_ids_instead_of_the_text() -> None:
    """一轮消息带的是材料 **id**，不是正文 —— 契约上就不给"把正文发上来"留位置。"""
    body = MessageRequest(task_id="t1", message="简历在这，你看看", material_ids=["mat_x"])
    assert body.material_ids == ["mat_x"]


def test_app_serves_the_material_route() -> None:
    """路由真的挂着（前端对齐守卫之外的这一条：路径存在性）。"""
    paths: dict[str, Any] = create_app().openapi()["paths"]
    assert "/api/v1/app/conversation/material" in paths
