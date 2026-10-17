<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import { auth } from '../lib/auth'
import InfoSheet from './InfoSheet.vue'
const emit=defineEmits<{close:[]}>()
const account=ref(''),password=ref(''),error=ref(''),busy=ref(false),mode=ref<'login'|'register'>('login')
const accountInput=ref<HTMLInputElement|null>(null)
/** 登录浮层打开后把焦点放到"账号"，键盘用户可以直接输入，不用先 Tab 过关闭按钮。 */
onMounted(()=>{void nextTick(()=>accountInput.value?.focus())})
async function submit(){
 if(busy.value)return
 if(account.value.trim().length<2||password.value.length<6){error.value='账号至少 2 个字符，密码至少 6 个字符。';return}
 busy.value=true;error.value=''
 try { await auth.login(mode.value,account.value.trim(),password.value);password.value='';emit('close') }
 catch(e){error.value=(e as Error).message}finally{busy.value=false}
}
</script>
<template><InfoSheet :open="true" :title="mode==='login'?'登录职引':'创建账号'" @close="!busy&&emit('close')">
<form class="sheet__body stack stack-4" @submit.prevent="submit">
<label class="field"><span class="field__label">账号</span><input ref="accountInput" v-model="account" class="field__input" autocomplete="username" minlength="2" maxlength="64" required :disabled="busy"/></label>
<label class="field"><span class="field__label">密码</span><input v-model="password" class="field__input" type="password" :autocomplete="mode==='login'?'current-password':'new-password'" minlength="6" maxlength="128" required :disabled="busy"/></label>
<p v-if="error" class="field__error" role="alert">{{error}}</p><p class="t-note">使用职引账号登录，无需填写学校或学信网密码。</p>
<button class="btn btn--primary" :disabled="busy">{{busy?'正在连接…':mode==='login'?'登录':'注册并登录'}}</button>
<button type="button" class="ws-text-button" :disabled="busy" @click="mode=mode==='login'?'register':'login';error=''">{{mode==='login'?'没有账号？注册':'已有账号？登录'}}</button>
</form></InfoSheet></template>
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
