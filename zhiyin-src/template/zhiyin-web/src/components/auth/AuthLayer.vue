<script setup lang="ts">
/**
 * 登录浮层。
 *
 * 它不是一页，是随时能掀起来的一层：门户点"开始"掀起来，令牌过期也掀起来。
 * 用的就是全站那一套浮层（Overlay）：同样从你点的那颗按钮长出来，
 * 同样的玻璃薄片、同样的 ESC 收回与焦点回退 —— 登录不该是全站唯一的例外页面。
 *
 * 左边那张更安静的薄片回答"为什么先做这一步"，右边才是表单：
 * 一上来就甩两个输入框，用户不知道自己在换什么。
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import Overlay from '@/components/console/Overlay.vue'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const router = useRouter()

const account = ref('')
const password = ref('')
const reveal = ref(false)
const local = ref('')

const isRegister = computed(() => session.authMode === 'register')
const ready = computed(() => account.value.trim().length > 0 && password.value.length >= 6)

/** 切登录/注册时把上一次的报错清掉，别让"账号已存在"挂在新表单上 */
watch(
  () => session.authMode,
  () => {
    local.value = ''
  }
)

async function submit() {
  if (session.authBusy) return
  if (!ready.value) {
    local.value = account.value.trim() ? '密码至少 6 位。' : '先写账号。'
    return
  }
  local.value = ''
  // 登录成功就直接进控制台：登录和"开始用"是同一动作，中间不该再有一步
  if (await session.signIn(account.value, password.value)) router.push('/')
}
</script>

<template>
  <Overlay
    size="mid"
    tone="accent"
    :title="isRegister ? '建一个账号' : '登录职引'"
    :subtitle="isRegister ? '账号即你的常用名 · 之后能用它找回这里的一切' : '你的画像、方案与记录，都挂在账号下'"
    from="portal-cta"
    @close="session.closeAuth()"
  >
    <div class="wrap">
      <!-- 左：这一步是干什么的 -->
      <aside class="pitch sheet sheet--quiet">
        <p class="label">这一步是干什么的</p>
        <h3 class="pitch__t">先认人，<br>再谈方法。</h3>

        <ul class="pitch__list">
          <li>
            <span class="label">数据归属</span>
            <p>画像、方案、对话全部按账号隔离 —— 这台机器上的其他账号看不到你这一份。</p>
          </li>
          <li>
            <span class="label">不用重复说</span>
            <p>下次进来，之前建立的画像与推进记录都还在，不用从头讲一遍。</p>
          </li>
          <li>
            <span class="label">随时能走</span>
            <p>退出登录只清掉这台设备上的登录状态，你的画像与记录都还在。</p>
          </li>
        </ul>

        <p class="label pitch__foot">没有第三方账号体系 · 不需要手机号</p>
      </aside>

      <!-- 右：表单 -->
      <section class="auth sheet">
        <form class="form" novalidate @submit.prevent="submit">
          <label class="field">
            <span class="label">账号</span>
            <input
              v-model="account"
              type="text"
              name="account"
              autocomplete="username"
              placeholder="你的学号，或一个顺手的名字"
              :disabled="session.authBusy"
            >
          </label>

          <label class="field">
            <span class="label">密码</span>
            <span class="field__grip">
              <input
                v-model="password"
                :type="reveal ? 'text' : 'password'"
                name="password"
                :autocomplete="isRegister ? 'new-password' : 'current-password'"
                placeholder="至少 6 位"
                :disabled="session.authBusy"
              >
              <button
                class="eye"
                type="button"
                :aria-pressed="reveal"
                aria-label="显示或隐藏密码"
                @click="reveal = !reveal"
              >
                {{ reveal ? '隐藏' : '显示' }}
              </button>
            </span>
          </label>

          <p v-if="local || session.authError" class="err" role="alert">
            <span class="err__dot" aria-hidden="true" />
            {{ local || session.authError }}
          </p>

          <button class="btn primary submit" type="submit" :disabled="session.authBusy">
            {{ session.authBusy ? '正在进入…' : isRegister ? '注册并进入' : '登录并进入' }}
          </button>

          <div class="switch">
            <button class="link" type="button" @click="session.switchAuthMode()">
              {{ isRegister ? '已经有账号？去登录' : '还没有账号？建一个' }}
            </button>
            <span class="label switch__note">
              {{ isRegister ? '账号名一旦定下就是你的标识' : '忘记密码：重新注册一个账号即可' }}
            </span>
          </div>
        </form>
      </section>
    </div>
  </Overlay>
</template>

<style scoped>
.wrap {
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-columns: 272px minmax(0, 1fr);
  gap: var(--s3);
}

/* 左片：比主片更安静、上下各缩一截，两张片子的轮廓不一样才不像"一个框被切开" */
.pitch {
  padding: var(--s4) var(--s4) var(--s5);
  margin: 36px 0 96px;
  display: flex; flex-direction: column; gap: var(--s4);
  animation: sheet-in-left 520ms var(--ease-expo) 70ms both;
  overflow: auto;
}
.pitch__t { font-size: var(--t-h4); line-height: 1.34; letter-spacing: var(--track-h); }
.pitch__list { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--s3); }
.pitch__list li { display: grid; gap: 3px; padding-top: var(--s3); border-top: 1px dashed var(--line-2); }
.pitch__list li:first-child { padding-top: 0; border-top: 0; }
.pitch__list p { font-size: var(--fs-small); line-height: 1.62; color: var(--ink-dim); }
.pitch__foot { margin-top: auto; color: var(--ink-faint); }

/* 主片：偏右、偏下，和左片错开 */
.auth {
  padding: var(--s6) var(--s6) var(--s5);
  margin: 0 0 40px;
  display: flex; flex-direction: column;
  animation: sheet-in 460ms var(--ease-expo) both;
  overflow: auto;
}
.form { display: flex; flex-direction: column; gap: var(--s4); max-width: 420px; }

.field { display: grid; gap: 6px; }
.field__grip { position: relative; display: block; }
.field input {
  width: 100%; height: 42px;
  padding: 0 var(--s3);
  border: var(--bw) solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--n-1);
  color: var(--ink-1);
  transition: border-color var(--dur-micro) var(--ease-out),
              box-shadow var(--dur-micro) var(--ease-out),
              background var(--dur-micro) var(--ease-out);
}
.field input:hover { border-color: var(--line-3); }
/*
 * 输入框的焦点：把套版线描成强调色，再补一圈 1px 的弱点。
 * 不用光晕 —— 光晕是"浮起来"的语言，这一稿的输入框是"凹进纸里的一格"。
 */
.field input:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent);
}
.field input:disabled { opacity: 0.6; }
.field__grip input { padding-right: 58px; }
.eye {
  position: absolute; right: 5px; top: 50%; transform: translateY(-50%);
  height: 30px; padding: 0 9px; border-radius: var(--r-pill);
  font-size: var(--t-xs); color: var(--ink-3);
  transition: color var(--dur-micro) var(--ease-out), background var(--dur-micro) var(--ease-out);
}
.eye:hover { color: var(--ink-1); background: var(--fill-hover); }

.err {
  display: flex; align-items: baseline; gap: var(--s2);
  padding: var(--s3) var(--s3);
  border: 1px solid var(--warn);
  border-radius: var(--r-sm);
  background: rgba(183, 77, 26, 0.06);
  font-size: var(--fs-small); color: var(--warn);
}
.err__dot { width: 6px; height: 6px; border-radius: 50%; background: var(--warn); flex: 0 0 auto; align-self: center; }

.submit { justify-content: center; height: 42px; }
.submit:disabled { opacity: 0.6; cursor: progress; }

.switch {
  display: grid; gap: 4px;
  padding-top: var(--s3); border-top: 1px solid var(--line-1);
}
.link { align-self: start; color: var(--accent); font-size: var(--fs-small); text-align: left; }
.link:hover { text-decoration: underline; }
.switch__note { color: var(--ink-faint); }

@media (max-width: 760px) {
  .wrap { grid-template-columns: minmax(0, 1fr); height: auto; }
  .pitch { margin: 0; order: 2; }
  .auth { margin: 0; padding: var(--s5) var(--s4) var(--s4); }
}
</style>
