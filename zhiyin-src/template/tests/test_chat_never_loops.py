"""对话不会"原地打转"、也不会"回到顶部" —— 两条都是 issue 复测里活下来的边界。

- issue #24：`opt--used` 只是**视觉**标记，按钮实际只受 `chatTyping` 控制，
  于是同一个选项能被点第三次、第四次；后端把同一组选项再摆一遍时，
  用户看到的就是"点了还在原地"。
- issue #19：浮层关掉即销毁，`scrollTop` 随节点消失，回来时对话跳回顶部，
  用户只能自己再翻一遍找上次读到哪儿。

两条都读源码钉住：它们的症状只在"后端原地打转"或"关掉再打开"时出现，
普通冒烟测试走不到；而一旦回归，用户只会说"点了没用"。
"""

from __future__ import annotations

from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1]
WEB = TEMPLATE / "zhiyin-web" / "src"
TALK = WEB / "components" / "console" / "TalkOverlay.vue"
SESSION = WEB / "stores" / "session.ts"


def test_answered_option_is_disabled_not_just_styled() -> None:
    """已答的选项必须**真的禁用**，不能只有一个 `--used` 的样式。"""
    source = TALK.read_text(encoding="utf-8")
    assert "isAnswered(opt) || optionsLocked" in source, (
        "快速回答按钮的 disabled 必须同时看「已答」与「连续打转」两件事（issue #24）"
    )
    assert "session.chatRepeats >= 2" in source, "连续两回没推进时应当锁掉整组选项"


def test_repeat_counter_is_reset_when_the_turn_moves_on() -> None:
    """计数器必须回到 0 —— 否则一旦打转过一次，后面的选项会永久锁死。"""
    source = SESSION.read_text(encoding="utf-8")
    assert "chatRepeats = repeated ? this.chatRepeats + 1 : 0" in source
    assert "this.chatRepeats = 0" in source, "不是追问的那一轮也要把计数清掉"


def test_chat_scroll_survives_the_overlay() -> None:
    """滚动位置要存进 store、并在重新打开时还原（有新区则去最新）。"""
    store = SESSION.read_text(encoding="utf-8")
    talk = TALK.read_text(encoding="utf-8")
    assert "rememberChatScroll(" in store, "store 里没有记住滚动位置的动作"
    assert "chatScrollTurns" in store, "缺少「存的时候有几轮」的判据（否则会回到过期的位置）"
    assert "session.rememberChatScroll(el.scrollTop)" in talk, "滚动/关闭时没有存位置"
    assert "onBeforeUnmount" in talk, "浮层销毁前没有把位置存下来"
    assert "session.chatScroll" in talk, "打开时没有还原位置"


def test_jump_buttons_exist_and_respect_reduced_motion() -> None:
    """回到顶部/最新两枚按钮要在，而且关掉动效的人不该被平滑滚动挡着。"""
    talk = TALK.read_text(encoding="utf-8")
    assert "回到顶部" in talk and "回到最新消息" in talk
    assert "prefers-reduced-motion: reduce" in talk
