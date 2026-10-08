"""用户手动更正画像字段的守卫（issue #26 第三条）。

现象（用户原话）
----------------
"仅告知系统为计算机大类专业，系统就直接默认认定为计算机科学与技术专业；
后续用户想要更正专业信息，无法完成修改。"

前半句是采集口径（提示词里已写明：说的是大类就存大类，见 `data/registry/prompts.json`）；
后半句是这里守的东西：**画像上必须有一条用户自己发起的写路径**。

这里钉住四件事，每一件都对应一种"看起来改好了、其实没有"的失败：

1. 改完值、来源与中文名一起对 —— 来源要是 `user_edit`（他自己写的），
   姓名 / 院系这类学信网字段不能被"不在采集动线里"挡在门外；
2. 改完的那一条**不再是缺口** —— 否则界面还挂着「没定」，他刚写完就看到自相矛盾；
3. 空值、超长、没登记过的键都要**如实拒**（1001 / 422），而不是悄悄写进去；
4. 接口回的是服务端存下来的那一条，字段形状与工作台面板一致。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zhiyin_api.app import API_PREFIX, create_app
from zhiyin_boot import Settings, build_container, wire_application
from zhiyin_business.services.profile import MAX_FIELD_VALUE_CHARS
from zhiyin_kernel.blackboard import ProfileGap
from zhiyin_kernel.enums import ProfileSource
from zhiyin_kernel.errors import InvalidRequest

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _settings() -> Settings:
    return Settings(
        # 本项目不提供 mock 产出：没有真模型就没有智能体引擎。
        # 构造真网关不发请求，测试里给一个占位密钥即可。
        use_remote_llm=True,
        llm_api_key="sk-test",
        llm_base_url="https://api.deepseek.com",
        llm_model="deepseek-flash",
        env="test",
        local_data_dir=str(DATA_DIR),
        local_registry_dir=str(DATA_DIR / "registry"),
        local_knowledge_dir=str(DATA_DIR / "knowledge"),
        local_object_dir=str(DATA_DIR / "objects"),
    )


@pytest.fixture
def client() -> TestClient:
    """走 lifespan 的整装应用：动态配置（采集规则 / 字段词表）真的装进来。"""
    app = wire_application(build_container(_settings()))
    with TestClient(app) as test_client:
        yield test_client


async def _profile_service():
    """直接驱动业务服务的那条装配（同一个 container，同一份动态配置）。"""
    from zhiyin_business.services.dynamic_config import load_snapshot

    container = build_container(_settings())
    wire_application(container)
    await load_snapshot(container.registry_service)
    return container.profile_service


async def test_correction_writes_the_value_with_the_user_as_source() -> None:
    """更正之后：值是他写的那句，来源是"本人填写"，中文名与缺口收尾一起对。"""
    profiles = await _profile_service()
    # 先造一份"系统记错了"的画像：学信网来源、一个具体专业名，并且挂在缺口里
    await profiles.update_field(
        "u-correct",
        "major",
        "计算机科学与技术",
        confidence=1.0,
        source=ProfileSource.RECORD.value,
        label="专业",
    )
    await profiles.replace_gaps(
        "u-correct",
        [ProfileGap(key="major", reason="还缺专业", suggested_next_action="去核验学籍")],
    )

    saved = await profiles.correct_field("u-correct", "major", "计算机大类")

    assert saved.value == "计算机大类"
    assert saved.source is ProfileSource.USER_EDIT
    # 中文名不能丢：upsert 是整行替换，不带上界面就只剩一个英文键
    assert saved.label == "专业"
    # 改完就不再是缺口（否则界面继续显示「没定」）
    assert [gap.key for gap in await profiles.get_gaps("u-correct")] == []
    # 旧证据撑的是旧值，不继承
    assert saved.evidence == []
    # 把握度给满：这条不是推出来的
    assert saved.confidence == 1.0


async def test_correction_accepts_fields_outside_the_collection_plan() -> None:
    """姓名 / 院系这类字段也能改。

    它们不在采集动线里（学信网核验一次就带回来，没有"去哪儿取"这一步），
    但确实是画像里的一格 —— 只按采集规则表放行的话，用户看着自己写错的院系
    却改不动，那正是这个 issue 的另一半。
    """
    profiles = await _profile_service()
    saved = await profiles.correct_field("u-dept", "department", "计算机学院")
    assert saved.value == "计算机学院"
    assert saved.source is ProfileSource.USER_EDIT


async def test_correction_rejects_empty_too_long_and_unregistered() -> None:
    """三类不合格的值都要在**业务层**被拒（不是接口层各自判一遍）。"""
    profiles = await _profile_service()

    with pytest.raises(InvalidRequest):
        await profiles.correct_field("u-bad", "major", "   ")
    with pytest.raises(InvalidRequest):
        await profiles.correct_field("u-bad", "major", "专" * (MAX_FIELD_VALUE_CHARS + 1))
    with pytest.raises(InvalidRequest):
        await profiles.correct_field("u-bad", "not_a_registered_field", "随便")

    # 三条都拒了，画像里一条都不该留下（宁可没有，也不要半份对不上的记录）
    assert await profiles.get_fields("u-bad") == []


def test_endpoint_degrades_when_the_facade_is_missing() -> None:
    """裸 app（未装配门面）按 1007 降级，而不是 500 —— 与其它接口同一条口径。"""
    with TestClient(create_app()) as bare:
        response = bare.post(
            f"{API_PREFIX}/app/profile/fields/major", json={"value": "计算机大类"}
        )
    assert response.status_code == 503
    assert response.json()["code"] == 1007


def test_endpoint_corrects_a_field_over_http(client: TestClient) -> None:
    """完整链路：默认登录态 → 写库 → 回包是存下来的那一条，工作台读到的也是它。"""
    response = client.post(
        f"{API_PREFIX}/app/profile/fields/major", json={"value": "计算机大类"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["key"] == "major"
    assert data["value"] == "计算机大类"
    assert data["source"] == "user_edit"
    assert data["label"] == "专业"

    workspace = client.get(f"{API_PREFIX}/app/workspace").json()
    fields = {item["key"]: item for item in workspace["data"]["profile_panel"]["fields"]}
    assert fields["major"]["value"] == "计算机大类"
    assert fields["major"]["source"] == "user_edit"


def test_endpoint_rejects_an_empty_value_with_a_usable_message(client: TestClient) -> None:
    """空值：422 + 1001 + 一句能照着改的中文话（不是 Pydantic 的英文报错）。"""
    response = client.post(f"{API_PREFIX}/app/profile/fields/major", json={"value": "  "})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == 1001
    assert "专业" in body["message"]
    assert "空" in body["message"]


def test_endpoint_rejects_an_unregistered_key(client: TestClient) -> None:
    """没登记过的键：422 + 1001，且**不**在画像里留下这一格。"""
    response = client.post(
        f"{API_PREFIX}/app/profile/fields/ghost_field", json={"value": "随便"}
    )
    assert response.status_code == 422
    assert response.json()["code"] == 1001

    workspace = client.get(f"{API_PREFIX}/app/workspace").json()
    keys = {item["key"] for item in workspace["data"]["profile_panel"]["fields"]}
    assert "ghost_field" not in keys
