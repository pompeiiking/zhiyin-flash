<script setup lang="ts">
import { computed } from 'vue'
import CodeSnippet from './CodeSnippet.vue'
const props = defineProps<{ text: string }>()
type Block = { kind: 'paragraph' | 'heading' | 'quote' | 'list' | 'code'; text: string; items: string[]; ordered?: boolean; language?: string }
const blocks = computed(() => {
  const result: Block[] = []; let paragraph: string[] = [], code: string[] = [], fenced = false, language = ''
  const flush = () => { if (paragraph.length) result.push({ kind:'paragraph',text:paragraph.join('\n'),items:[] }); paragraph=[] }
  for (const line of props.text.replace(/\r\n/g,'\n').split('\n')) {
    if (/^\s*```/.test(line)) { flush(); if(fenced){result.push({kind:'code',text:code.join('\n'),items:[],language});code=[]}else language=line.replace(/^\s*```/, '').trim();fenced=!fenced;continue }
    if(fenced){code.push(line);continue}
    if(!line.trim()){flush();continue}
    if(/^#{1,3}\s+/.test(line)){flush();result.push({kind:'heading',text:line.replace(/^#{1,3}\s+/,''),items:[]});continue}
    if(/^>\s?/.test(line)){flush();result.push({kind:'quote',text:line.replace(/^>\s?/,''),items:[]});continue}
    const match=line.match(/^\s*(\d+[.)]|[-*•])\s+(.+)$/)
    if(match){flush();const ordered=/^\d/.test(match[1]);const last=result[result.length-1];if(last?.kind==='list'&&last.ordered===ordered)last.items.push(match[2]);else result.push({kind:'list',ordered,text:'',items:[match[2]]});continue}
    paragraph.push(line)
  }
  flush();if(code.length)result.push({kind:'code',text:code.join('\n'),items:[],language});return result
})
function inline(text:string){return text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map(part=>({strong:part.startsWith('**')&&part.endsWith('**'),text:part.startsWith('**')&&part.endsWith('**')?part.slice(2,-2):part}))}
</script>
<template><div class="readable-text"><template v-for="(block,index) in blocks" :key="index"><h3 v-if="block.kind==='heading'">{{ block.text }}</h3><CodeSnippet v-else-if="block.kind==='code'" :code="block.text" :language="block.language" /><blockquote v-else-if="block.kind==='quote'">{{ block.text }}</blockquote><component :is="block.ordered?'ol':'ul'" v-else-if="block.kind==='list'"><li v-for="(item,i) in block.items" :key="i"><template v-for="(part,j) in inline(item)" :key="j"><strong v-if="part.strong">{{ part.text }}</strong><template v-else>{{ part.text }}</template></template></li></component><p v-else><template v-for="(part,j) in inline(block.text)" :key="j"><strong v-if="part.strong">{{ part.text }}</strong><template v-else>{{ part.text }}</template></template></p></template></div></template>
<style scoped>
.readable-text { overflow-wrap: anywhere; }
.readable-text > * + * { margin-top: 16px; }
.readable-text h3 { font-size: var(--fs-16); font-weight: 600; line-height: 1.7; }
.readable-text p { white-space: pre-wrap; }
.readable-text ul { list-style: disc; padding-left: 22px; }
.readable-text ol { list-style: decimal; padding-left: 22px; }
.readable-text li + li { margin-top: 8px; }
.readable-text blockquote { padding: 12px 16px; background: var(--c-surface-2); border-radius: var(--r-md); font-size: var(--fs-14); }
.readable-text pre { padding: 16px; background: var(--c-surface-2); border-radius: var(--r-md); overflow-x: auto; font-size: var(--fs-14); line-height: 1.7; }
</style>
