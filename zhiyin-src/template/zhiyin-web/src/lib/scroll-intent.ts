/** Adapted from open-claude-ui scroll pinning. See public/licenses/open-claude-ui.txt. */
export function createScrollIntent() {
  let pinned = true
  let releasedAt = -Infinity
  return {
    get pinned() { return pinned },
    release(now: number) { pinned = false; releasedAt = now },
    update(distance: number, now: number) {
      if (now - releasedAt >= 150) pinned = distance <= 40
      return pinned
    },
    pin() { pinned = true; releasedAt = -Infinity },
  }
}

export function isComposingKey(event: { isComposing?: boolean; keyCode?: number }) {
  return !!event.isComposing || event.keyCode === 229
}
