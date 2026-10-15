"""Dynamic labels in the selected frontend and backend alias rules.
Legacy eight-stop portal copy is retained for registry compatibility; the selected
portal uses trust_blocks. It no longer promises to render the removed canvas.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "redesign-demo/src"


def test_profile_and_badge_copies_are_consumed():
    source = (WEB / "lib/server-copy.ts").read_text(encoding="utf-8")
    assert "profile.field.${key}" in source and "badge.${key}.${part}" in source
    assert "profileLabel(field.key" in (WEB / "views/StudentView.vue").read_text(encoding="utf-8")
    assert "badgeCopy(r.key" in (WEB / "lib/growth-records.ts").read_text(encoding="utf-8")


def test_portal_consumes_published_trust_blocks():
    for name in ["PortalClassicView.vue", "PortalProposalView.vue"]:
        source = (WEB / "views" / name).read_text(encoding="utf-8")
        assert "trust_blocks" in source and "publishedTrust.length" in source


def test_backend_profile_alias_registry_is_preserved():
    source = (
        ROOT / "zhiyin-src/template/zhiyin-business/zhiyin_business/services/dynamic_config.py"
    ).read_text(encoding="utf-8")
    assert "PROFILE_ALIAS_PREFIX" in source
