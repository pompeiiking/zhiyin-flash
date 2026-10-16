export function localDateTime(value?: string | null): string
export function reviewDraft(task?: {text?: string; due_date?: string | null}): {text: string; due: string}
export function measurementPercent(measurement: {value: number; minimum?: number; maximum?: number}): number | null
