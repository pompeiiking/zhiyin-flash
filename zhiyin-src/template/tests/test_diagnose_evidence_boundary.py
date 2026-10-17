import pytest
from pydantic import ValidationError

from zhiyin_business.contracts.diagnose import DiagnoseOutput


def payload():
    return {
        "verdict": {"title": "先核对材料", "summary": "现有信息只能确认课程项目名称。"},
        "swot": {"strength": [], "weakness": [], "opportunity": [], "risk": []},
        "dimensions": [{
            "group": "SELF-PORTRAIT", "group_method": "已提供材料逐项核对",
            "items": [{"index": 1, "name": "项目经历", "tag": "待验证", "conclusion": "先查看项目内容", "evidence": "目前只提供了项目名称"}],
        }],
        "gaps": [],
    }


def test_unknown_evidence_can_remain_pending():
    assert DiagnoseOutput.model_validate(payload()).dimensions[0].items[0].tag == "待验证"


@pytest.mark.parametrize("location", ["dimension", "swot", "gap"])
def test_missing_evidence_cannot_be_relabelled_as_a_deficit(location):
    body = payload()
    if location == "dimension":
        body["dimensions"][0]["items"][0].update(tag="短板", evidence="未看到公开作品")
    elif location == "swot":
        body["swot"]["weakness"] = ["未提供导师评价，因此协作能力不足"]
    else:
        body["gaps"] = [{"gap_id": "g1", "requirement": "作品要求", "current_state": "未提供作品集", "suggestion": "先查看材料"}]
    with pytest.raises(ValidationError):
        DiagnoseOutput.model_validate(body)
