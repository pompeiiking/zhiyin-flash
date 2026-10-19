"""Dynamic field labels and the user-selected classic portal entry."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "zhiyin-src/template/zhiyin-web/src"
_FRONTEND_SUFFIXES = {".vue", ".ts"}


def _frontend_consumes(pattern: str) -> bool:
    """在前端源码树里找一处调用点。

    不钉具体文件：2026-10-19 把 `StudentView.vue` 拆成 composables 后，
    `profileLabel(field.key` 随渲染逻辑搬进了 `lib/use-profile-fields.ts`。
    这条守卫要守的是"页面确实在用注册表里的文案"，而不是"哪一行在哪个文件"。
    """
    return any(
        pattern in path.read_text(encoding="utf-8")
        for path in sorted(WEB.rglob("*"))
        if path.suffix in _FRONTEND_SUFFIXES and path.is_file()
    )


def test_profile_and_badge_copies_are_consumed():
    source = (WEB / "lib/server-copy.ts").read_text(encoding="utf-8")
    assert "profile.field.${key}" in source and "badge.${key}.${part}" in source
    assert _frontend_consumes("profileLabel(field.key")
    assert _frontend_consumes("badgeCopy(record.key")


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
