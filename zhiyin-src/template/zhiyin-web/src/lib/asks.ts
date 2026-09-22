/*
 * AI 推荐的"下一个动作"。
 *
 * 这个产品的核心机制不是"用户去哪找功能"，而是**AI 在旁边看着，然后指一下**：
 * 现在最需要采集什么、最该做哪一步，就在对应的地方冒出一句话，点它就能直接做。
 * 所以"下一步"不是每个组件自己编的文案 —— 它得有一个**统一来源**，
 * 否则同一个时刻，画像块说"去补画像"、待办块说"去做任务"，用户根本不知道该听谁的。
 *
 * 优先级口径（从上到下，先到先得）：
 *
 *   1. 后端刚给的行为引导 BehaviorGuide —— 这是编排器的权威判定，
 *      它连"该怎么问"都写好了（`question` / `options` / `task` / `reminder`）；
 *   2. 画像缺口 —— 没有引导时，退到"哪条信息最卡后面的判断"；
 *   3. 什么都没有 —— 那就是还没开始，推一次"先聊两句"，把画像立起来。
 *
 * 注意第 2、3 条是**回落**，不是平级来源：只要有后端引导，就以它为准。
 * 这样"AI 在编排用户的下一个动作"这件事才是真的，而不是前端在演。
 */

/** 后端 BehaviorGuide.question / options / task / reminder 的取值形状 */
export interface GuideOption {
  option_id?: string
  label: string
  value?: unknown
}

export interface GuideTask {
  task_id?: string
  text: string
}

export interface GuideReminder {
  title: string
  detail?: string
}

/** 与后端 `zhiyin_business.contracts.common.BehaviorGuide` 一一对应 */
export interface BehaviorGuide {
  kind: 'question' | 'options' | 'task' | 'reminder'
  text: string
  question?: string | null
  options?: GuideOption[]
  task?: GuideTask | null
  reminder?: GuideReminder | null
}

/** 一个动作要去哪儿 */
export type AskTarget =
  /** 去对话，并且把"要回答的那一句"带过去 —— 见下方说明 */
  | { to: 'chat'; prompt: string; options: GuideOption[] }
  | { to: 'tasks' }
  | { to: 'details'; title: string; body: string }

export interface Ask {
  /** 稳定标识：同一时刻各处的"下一步"是同一个动作，靠它对得上 */
  id: string
  /** 用户读到的那句话 —— AI 想让他做的下一步 */
  label: string
  /** 动词短语，做成可点的那个词（对话 / 现在做 / 看一眼） */
  cta: string
  /** 谁在等这一步（主理展示名）。人对着人说话，比"系统建议"可信 */
  who: string
  /** 为什么是现在 —— 一句话，别让人猜 */
  why: string
  target: AskTarget
}

export interface AskInput {
  guide: BehaviorGuide | null
  /** 后端回包里的主理展示名 */
  leadName: string
  profile: { gaps: { id: string; name: string; question: string; suggested?: string }[] } | null
  hasAnyProfile: boolean
}

const KIND_CTA: Record<BehaviorGuide['kind'], string> = {
  question: '回答这一句',
  options: '选一个',
  task: '现在做',
  reminder: '看一眼',
}

/**
 * 把当前状态收成**一个**下一步。
 *
 * 只返回一个，是刻意的：同时推三件事，等于什么都没推。
 */
export function buildAsk({ guide, leadName, profile, hasAnyProfile }: AskInput): Ask | null {
  const who = leadName || '职业顾问'

  if (guide) {
    // 1. 编排器的权威引导
    if (guide.kind === 'question' && (guide.question || guide.text)) {
      // 预填它自己写好的那句追问：用户点进来就已经站在问题上，
      // 而不是进来面对一个空输入框，再自己想把问题重复一遍。
      return {
        id: 'guide.question',
        label: guide.question || guide.text,
        cta: KIND_CTA.question,
        who,
        why: guide.text,
        // 带过去的是**问题**，不是要填进输入框的文字：
        // 用户要回答它，不是要复述它。所以它显示在输入框上方，光标落在输入框里。
        target: { to: 'chat', prompt: guide.question || guide.text, options: [] },
      }
    }
    if (guide.kind === 'options' && guide.options?.length) {
      return {
        id: 'guide.options',
        label: guide.options.map((o) => o.label).join(' / '),
        cta: KIND_CTA.options,
        who,
        why: guide.text,
        // 选项直接带过去变成可以点的按钮：让人回答的成本低到一次点击
        target: { to: 'chat', prompt: guide.text, options: guide.options },
      }
    }
    if (guide.kind === 'task' && guide.task) {
      return {
        id: 'guide.task',
        label: guide.task.text,
        cta: KIND_CTA.task,
        who,
        why: guide.text,
        target: { to: 'tasks' },
      }
    }
    if (guide.kind === 'reminder' && guide.reminder) {
      return {
        id: 'guide.reminder',
        label: guide.reminder.title,
        cta: KIND_CTA.reminder,
        who,
        why: guide.reminder.detail || guide.text,
        target: {
          to: 'details',
          title: guide.reminder.title,
          body: guide.reminder.detail || guide.text,
        },
      }
    }
  }

  // 2. 回落：画像里最卡人的那条缺口 —— 采集阶段真正的"下一步"
  const gap = profile?.gaps?.[0]
  if (gap) {
    return {
      id: `gap.${gap.id}`,
      label: gap.suggested || gap.question || `还缺「${gap.name}」`,
      cta: '说一句补上',
      who,
      why: '这条缺口挡着后面的判断，补上它，方案会跟着重算。',
      target: { to: 'chat', prompt: gap.question || `说说「${gap.name}」`, options: [] },
    }
  }

  // 3. 还什么都没有：把"开始"这件事本身变成下一步
  if (!hasAnyProfile) {
    return {
      id: 'start.chat',
      label: '先聊两句，把你这个人立起来',
      cta: '开始对话',
      who,
      why: '现在画像还是空的 —— 没有画像，后面每一步都算不准。',
      target: { to: 'chat', prompt: '你想先聊什么？一句话就行。', options: [] },
    }
  }

  return null
}
