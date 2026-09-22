import { onBeforeUnmount, onMounted } from 'vue'

// Esc 的归属权。
//
// 一个页面上可能同时开着好几层（覆盖层 → 抽屉 → 浮窗）。如果每层各自监听 document，
// 按一次 Esc 会全部关掉 —— 用户丢掉的东西比他打算关的多。
// 所以这里维护一个栈：只有最后打开的那一层处理 Esc；关掉它之后，下一层才接回来。
type Handler = () => void

const stack: Handler[] = []
let listening = false

function onKeydown(e: KeyboardEvent) {
  if (e.key !== 'Escape' || !stack.length) return
  e.preventDefault()
  stack[stack.length - 1]()
}

export function useEscLayer(handler: Handler) {
  onMounted(() => {
    add(handler)
  })

  onBeforeUnmount(() => {
    remove(handler)
  })
}

function add(handler: Handler) {
  if (!listening) {
    document.addEventListener('keydown', onKeydown)
    listening = true
  }
  stack.push(handler)
}

function remove(handler: Handler) {
  const at = stack.indexOf(handler)
  if (at >= 0) stack.splice(at, 1)
  if (!stack.length && listening) {
    document.removeEventListener('keydown', onKeydown)
    listening = false
  }
}

/**
 * 给"组件一直挂着、但层是开开关关"的情况用（例如抽屉：组件随页面挂载，
 * 里面的面板才是 v-if）。这类层必须在真正打开的那一刻才占住 Esc，
 * 否则它会在页面加载时就抢先注册，把 Esc 从后来打开的层手里夺走。
 */
export function useEscLayerManual(handler: Handler) {
  let active = false
  const entry: Handler = () => handler()

  onBeforeUnmount(() => {
    if (active) remove(entry)
    active = false
  })

  return {
    activate() {
      if (active) return
      active = true
      add(entry)
    },
    deactivate() {
      if (!active) return
      active = false
      remove(entry)
    },
  }
}
