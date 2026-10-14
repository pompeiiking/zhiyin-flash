import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import './styles/tokens.css'
import './styles/base.css'
import './styles/workspace.css'
import './styles/experience.css'
import './styles/journey.css'
import './styles/dialogue.css'
import './styles/redesign.css'
import './styles/c2-fidelity.css'
import './styles/refinement.css'

const app = createApp(App)

/**
 * 白屏不许静默发生。
 *
 * 这个工程是"边改边给评审看"的：dev server 正在被写文件时，浏览器可能拉到一个
 * 暂时读不出来的模块（Vite 日志里的 EBUSY / ENOENT / Pre-transform error）。
 * 结果是 Vue 挂不上、或懒加载的路由组件拿不到 —— 页面闪一下正常界面然后变白，
 * 而白屏不报错也不提示，看起来就是"坏了"。
 *
 * 所以兜住两层：Vue 渲染期异常，以及全局未捕获异常 / 未处理的 Promise。
 * 一律画成一块看得见的说明，而不是留一个白页。
 *
 * 这里的颜色是**故意写死的字面量**：这块提示必须在样式表本身没加载成功时也能看见，
 * 所以不能依赖 tokens.css。它是全工程唯一允许出现颜色字面量的地方（#96000e 是河大红）。
 */
const FALLBACK_ID = 'boot-error'

function showFatal(reason: unknown): void {
  if (document.getElementById(FALLBACK_ID)) return
  const box = document.createElement('div')
  box.id = FALLBACK_ID
  box.setAttribute('role', 'alert')
  box.style.cssText = [
    'position:fixed',
    'left:0',
    'right:0',
    'bottom:0',
    'z-index:9999',
    'padding:14px 20px',
    'background:#96000e',
    'color:#ffffff',
    'font:13px/1.6 system-ui,-apple-system,sans-serif',
  ].join(';')
  console.error('[page]', reason)
  box.textContent = '页面暂时无法显示。请重新加载后继续。'
  const retry = document.createElement('button')
  retry.textContent = '重新加载'
  retry.style.cssText = 'margin-left:16px;padding:8px 12px;background:white;color:#96000e;border-radius:6px'
  retry.onclick = () => window.location.reload()
  box.appendChild(retry)
  document.body.appendChild(box)
}

app.config.errorHandler = (err) => {
  console.error('[vue]', err)
  showFatal(err)
}
window.addEventListener('error', (e) => showFatal(e.error ?? e.message))
window.addEventListener('unhandledrejection', (e) => showFatal(e.reason))

app.use(router).mount('#app')
