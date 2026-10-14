<script setup lang="ts">
import UiIcon from './UiIcon.vue'

/**
 * 编号依据。
 *
 * 【为什么不在这里写 `open`】
 * 上一轮为了修"详情被折叠成 0 高"（实测 ol 有 66px 而 details 是 714×0），
 * 用了"模板写死 open + summary 绝对定位裁剪"的办法。裁剪让 summary 只有
 * 1×32，虽然看不见，**却仍然在 Tab 焦点序里**——键盘用户会 Tab 到一个看不见的控件。
 * 那是绕过，不是修。
 *
 * 现在的形态（两种用法，都不再有隐形控件）：
 *   · `title` 有值 → 组件自己承担展开控件：summary 是一个**看得见、有名字、
 *     可聚焦**的行，`min-height: 44px`，浏览器原生支持回车 / 空格展开；
 *   · `title` 为空（对话页的卡片头已经写着"支持依据 N"）→ **根本不渲染 details**，
 *     只渲染一个列表。
 *
 * 最后那条是踩过坑的：一开始写的是"不渲染 summary 的 details"，但 **没有 summary 的
 * `<details>` 会被浏览器补一个它自己的 "Details" 摘要**——实测界面上直接露出英文
 * "Details"（`_shots/chat-v10/1280-2-依据展开.png` 可见两处）。一个本该"始终展开"的
 * 列表不需要 disclosure 语义，去掉 details 才是正确形态。
 */
const props = withDefaults(
  defineProps<{ items: readonly string[]; title?: string; open?: boolean }>(),
  { title: '', open: undefined },
)
/* 调用方没有明确指定时：有可见 summary 就默认收起，没有 summary 就默认展开 */
const isOpen = props.open ?? !props.title
</script>
<template>
  <!-- 有标题：组件自己承担展开控件 -->
  <details v-if="title" class="exp-evidence" :open="isOpen">
    <summary>
      <UiIcon name="report" :size="15" />
      <span class="exp-evidence__label">{{ title }}</span>
      <span class="exp-evidence__count">{{ items.length }}</span>
      <UiIcon name="chevron" :size="14" />
    </summary>
    <ol>
      <li v-for="(item, index) in items" :key="index"><span>{{ index + 1 }}</span><p>{{ item }}</p></li>
    </ol>
  </details>
  <!-- 无标题：外部（卡片头 + "展开其余 N 条依据"按钮）已经承担了标题与展开，
       这里就只是一个列表。包一层同名 class 是为了沿用既有样式。 -->
  <div v-else class="exp-evidence exp-evidence--plain">
    <ol>
      <li v-for="(item, index) in items" :key="index"><span>{{ index + 1 }}</span><p>{{ item }}</p></li>
    </ol>
  </div>
</template>
