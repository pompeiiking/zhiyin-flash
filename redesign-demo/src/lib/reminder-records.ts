import { reactive, watch } from 'vue'
import { demo } from '../store'
import { rememberSession } from './session-cache'
import type { Notice } from '../data/types'
export interface ReminderRecord { id: string; title: string; body: string; result: string; state?: 'read'|'later'|'done'; kind?: string; at?: string; until?: string; original?: Notice }
export const reminderRecords = reactive({ account: demo.state.account, items: [] as ReminderRecord[] })
rememberSession('reminder-records', reminderRecords, ['account', 'items'])
if (reminderRecords.account !== demo.state.account) { reminderRecords.account = demo.state.account; reminderRecords.items = [] }
watch(() => demo.state.account, account => { reminderRecords.account = account; reminderRecords.items = [] })
