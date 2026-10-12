<script setup lang="ts">
import { ref } from 'vue'
import { demo } from '../store'
import { AUTH_COPY } from '../data/copy'

const emit = defineEmits<{ close: [] }>()

const account = ref('mid')
const password = ref('')
const error = ref('')

/** 登录拦截必须解释"为什么是现在"，并把"已答的内容不会丢"说清楚 */
const accounts = [
  { id: 'fresh', label: '全新空账号', note: '从零开始建档，真实性最强' },
  { id: 'mid', label: '已推进到诊断之后', note: '有报告、三套方向、行动计划' },
  { id: 'stale', label: '三天未动', note: '登录后主动消息会自己出现' },
]

function submit() {
  if (!password.value.trim()) {
    // 正式档：这是"你的数据去哪了"的说明，不用"随便填一个就行"这种口语
    error.value = '演示环境：密码可任意填写。'
    return
  }
  error.value = ''
  demo.signIn(account.value)
  emit('close')
}
</script>

<template>
  <div class="layer" @click.self="emit('close')">
    <div class="sheet" role="dialog" aria-modal="true" aria-label="登录">
      <header class="sheet__head">
        <div>
          <h2 class="t-h2">{{ AUTH_COPY.title }}</h2>
          <p class="t-note" style="margin-top: 6px">{{ AUTH_COPY.body }}</p>
        </div>
        <button class="sheet__close" aria-label="关闭" @click="emit('close')">✕</button>
      </header>

      <div class="sheet__body stack stack-4">
        <div class="field">
          <span class="field__label">选择演示账号</span>
          <div class="accounts">
            <button
              v-for="a in accounts"
              :key="a.id"
              class="account"
              :class="{ 'account--on': account === a.id }"
              @click="account = a.id"
            >
              <span class="account__id t-mono">{{ a.id }}</span>
              <span class="account__label">{{ a.label }}</span>
              <span class="account__note">{{ a.note }}</span>
            </button>
          </div>
        </div>

        <label class="field">
          <span class="field__label">密码</span>
          <input
            v-model="password"
            class="field__input"
            type="password"
            placeholder="演示环境，任意字符"
            @keyup.enter="submit"
          />
          <span v-if="error" class="field__error">{{ error }}</span>
          <span v-else class="field__hint">{{ AUTH_COPY.accountHint }}</span>
        </label>

        <div class="callout callout--plain">
          <span>门户永远公开。只有"任务与计划"和"评估报告"需要登录 —— 而且登录是浮层，不是一道墙。</span>
        </div>
      </div>

      <footer class="sheet__foot">
        <button class="btn" @click="emit('close')">稍后再说</button>
        <button class="btn btn--primary" @click="submit">{{ AUTH_COPY.action }}</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.layer {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: grid;
  place-items: center;
  padding: var(--sp-5);
  background: var(--overlay-mask);
}

.sheet {
  width: min(520px, 100%);
  background: var(--c-surface);
  border-radius: var(--r-lg);
  box-shadow: var(--e-3);
  overflow: hidden;
}

.sheet__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-4);
  padding: var(--sp-5) var(--sp-5) var(--sp-4);
  border-bottom: var(--bw-1) solid var(--c-border);
}

.sheet__close {
  width: 28px;
  height: 28px;
  flex: none;
  border-radius: var(--r-sm);
  color: var(--c-text-3);
}

.sheet__close:hover {
  background: var(--c-surface-3);
  color: var(--c-text);
}

.sheet__body {
  padding: var(--sp-5);
}

.sheet__foot {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-2);
  padding: var(--sp-4) var(--sp-5);
  border-top: var(--bw-1) solid var(--c-border);
  background: var(--c-surface-2);
}

.accounts {
  display: grid;
  gap: var(--sp-2);
}

.account {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 2px var(--sp-3);
  padding: var(--sp-3);
  text-align: left;
  border: var(--bw-1) solid var(--c-border-strong);
  border-radius: var(--r-md);
  transition: border-color var(--mo-fast) var(--mo-ease);
}

.account:hover {
  border-color: var(--c-primary-border);
}

.account--on {
  border-color: var(--c-primary);
  background: var(--c-primary-weak);
}

.account__id {
  grid-row: 1 / span 2;
  align-self: center;
  padding: 0 var(--sp-2);
  height: 22px;
  display: inline-flex;
  align-items: center;
  border-radius: var(--r-sm);
  background: var(--c-surface-3);
  font-size: var(--fs-12);
  color: var(--c-text-2);
}

.account--on .account__id {
  background: var(--c-primary);
  color: var(--c-on-primary);
}

.account__label {
  font-size: var(--fs-14);
  font-weight: var(--fw-medium);
}

.account__note {
  font-size: var(--fs-12);
  color: var(--c-text-3);
}
</style>
