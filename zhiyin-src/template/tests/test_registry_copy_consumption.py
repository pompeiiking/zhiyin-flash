"""Dynamic field labels and the user-selected classic portal entry."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "zhiyin-src/template/zhiyin-web/src"


def test_profile_and_badge_copies_are_consumed():
    source = (WEB / "lib/server-copy.ts").read_text(encoding="utf-8")
    assert "profile.field.${key}" in source and "badge.${key}.${part}" in source
    assert "profileLabel(field.key" in (WEB / "views/StudentView.vue").read_text(encoding="utf-8")
    assert "badgeCopy(record.key" in (WEB / "lib/growth-records.ts").read_text(encoding="utf-8")


def test_portal_keeps_the_selected_classic_intro():
    entry = (WEB / "views/PortalView.vue").read_text(encoding="utf-8")
    source = (WEB / "views/PortalClassicView.vue").read_text(encoding="utf-8")
    assert "<PortalClassic />" in entry
    assert not (WEB / "views/PortalProposalView.vue").exists()
    assert 'v-for="w in what"' in source
    assert "publishedTrust" not in source


def test_backend_profile_alias_registry_is_preserved():
    source = (
        ROOT / "zhiyin-src/template/zhiyin-business/zhiyin_business/services/dynamic_config.py"
    ).read_text(encoding="utf-8")
    assert "PROFILE_ALIAS_PREFIX" in source
