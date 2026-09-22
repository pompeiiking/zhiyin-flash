import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
/*
 * 中文字体自托管（npm 分片包，按 unicode-range 按需下载，整包不会进首屏）：
 *   · ZCOOL KuaiLe（站酷快乐体）：全站主打字 —— 笔画歪歪扭扭的马克笔手绘字，
 *     "激进草稿风"的字面担当。规整的楷体/黑体都试过，用户判的是"太规整、不搭"；
 *   · MiSans VF：兜底正文字。快乐体没有的字形（生僻字/部分符号）落到它，
 *     密集小字数据仍可读。
 */
import '@fontsource/zcool-kuaile'
import 'misans/lib/Normal/MiSansVF.min.css'
import './styles/base.css'

/*
 * 磨砂玻璃的开关：分两次探。
 *
 * 第一次在挂载前（测环境本身），第二次在挂载之后 —— 因为真正贵的是应用装上以后
 * 那几块大面积 backdrop-filter。只测第一次的话，快的机器照样会在装完之后掉帧，
 * 而开关已经定完了。第二次掉帧就补挂 no-glass。
 */
function probeFps(windowMs: number) {
  return new Promise<number>((r) => {
    let n = 0
    const t0 = performance.now()
    const loop = () => {
      if (performance.now() - t0 < windowMs) {
        n++
        requestAnimationFrame(loop)
      } else {
        r((n * 1000) / (performance.now() - t0))
      }
    }
    requestAnimationFrame(loop)
  })
}

;(async () => {
  if ((await probeFps(350)) < 45) document.documentElement.classList.add('no-glass')
})()

createApp(App).use(createPinia()).use(router).mount('#app')

/* 挂载之后再量一次：这时玻璃块已经在画面上了，掉帧就补挂 no-glass */
window.setTimeout(async () => {
  const root = document.documentElement
  if (root.classList.contains('no-glass')) return
  if ((await probeFps(500)) < 48) root.classList.add('no-glass')
}, 1600)
