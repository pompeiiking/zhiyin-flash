import { mkdir, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

// Read-only research. Raw third-party documents stay in the local temporary cache.
const output = dirname(fileURLToPath(import.meta.url))
const cache = join(tmpdir(), 'zhiyin-design-research-2026-10-13')
await mkdir(cache, { recursive: true })
const catalogUrl = 'https://registry.directory/items.json'
const catalogResponse = await fetch(catalogUrl, { signal: AbortSignal.timeout(45000) })
if (!catalogResponse.ok) throw new Error(`Catalog returned ${catalogResponse.status}`)
const catalog = await catalogResponse.json()
if (!Array.isArray(catalog.items)) throw new Error('Catalog did not contain items')
const sources = [
  ...['sidebar', 'dashboard-group', 'dashboard-panel', 'dashboard-navbar', 'page', 'page-columns', 'blog-post', 'blog-posts', 'chat-message', 'chat-messages', 'chat-prompt', 'chat-suggestion', 'file-upload', 'form-field', 'timeline', 'stepper', 'calendar', 'command-palette', 'slideover', 'empty', 'table', 'auth-form', 'toast', 'navigation-menu'].map(name => ({ id: `nuxt-${name}`, url: `https://ui.nuxt.com/raw/docs/components/${name}.md` })),
  ...['message', 'bubble', 'message-scroller', 'attachment', 'questionnaire', 'sidebar', 'item', 'field', 'input-group', 'empty', 'data-table', 'stepper', 'sheet', 'sonner', 'calendar', 'radio-group', 'tabs', 'command', 'skeleton', 'marker'].map(name => ({ id: `shadcn-vue-${name}`, url: `https://www.shadcn-vue.com/docs/components/${name}` })),
  { id: 'shadcn-vue-typeset', url: 'https://www.shadcn-vue.com/docs/typeset' },
  { id: 'shadcn-vue-changelog', url: 'https://www.shadcn-vue.com/docs/changelog' },
  ...['calendar', 'dialog', 'drawer', 'combobox', 'toast', 'radio-group', 'field', 'tabs', 'progress', 'checkbox'].map(name => ({ id: `reka-${name}`, url: `https://reka-ui.com/docs/components/${name}.md` })),
  ...['fileupload', 'timeline', 'datatable', 'skeleton'].map(name => ({ id: `primevue-${name}`, url: `https://primevue.dev/${name}/` })),
  { id: 'fullcalendar-vue', url: 'https://fullcalendar.io/docs/vue' },
  { id: 'schedule-x-vue', url: 'https://schedule-x.dev/docs/frameworks/vue' },
  { id: 'motion-vue', url: 'https://motion.dev/docs/vue' },
  { id: 'motion-layout', url: 'https://motion.dev/docs/vue-layout-animations' },
  { id: 'ant-proximity', url: 'https://ant.design/docs/spec/proximity.md' },
  { id: 'ant-alignment', url: 'https://ant.design/docs/spec/alignment.md' },
  { id: 'ant-hierarchy', url: 'https://ant.design/docs/spec/contrast.md' },
  { id: 'echarts-examples', url: 'https://echarts.apache.org/examples/en/index.html' },
  { id: 'vue-echarts', url: 'https://raw.githubusercontent.com/ecomfe/vue-echarts/main/README.md' },
  { id: 'ai-elements-sources', url: 'https://elements.ai-sdk.dev/components/sources' },
  { id: 'ai-elements-plan', url: 'https://elements.ai-sdk.dev/components/plan' },
  { id: '21st-newest', url: 'https://21st.dev/community/components/newest' },
  { id: '21st-ai-chat', url: 'https://21st.dev/community/components/s/ai-chat.md' },
  { id: '21st-sidebar', url: 'https://21st.dev/community/components/s/sidebar.md' },
  { id: '21st-forms', url: 'https://21st.dev/community/components/s/form.md' },
  { id: 'inspira-directory', url: 'https://inspira-ui.com/components' },
]
function plain(body) {
  if (!body.trimStart().startsWith('<')) return body
  const main = body.match(/<main\b[^>]*>([\s\S]*?)<\/main>/i)?.[1] ?? body
  return main.replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1>/gi, '').replace(/<[^>]+>/g, ' ').replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/\s+/g, ' ').trim()
}
async function capture(source) {
  try {
    const response = await fetch(source.url, { signal: AbortSignal.timeout(18000) })
    const body = await response.text()
    const text = plain(body)
    const title = body.trimStart().startsWith('<')
      ? body.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1] ?? ''
      : body.match(/^#\s+(.+)$/m)?.[1] ?? ''
    await writeFile(join(cache, `${source.id}.txt`), text)
    const hasCodeExample = /```|<script setup|import .* from|v-model/.test(body)
    const valid = response.ok && (text.length > 1000 || (text.length > 500 && hasCodeExample)) && !/^(Not Found|404:|Internal Server Error)/i.test(text)
    return { ...source, status: response.status, contentType: response.headers.get('content-type'), finalUrl: response.url, title, chars: text.length, valid, hasCodeExample }
  } catch (error) { return { ...source, valid: false, error: String(error) } }
}
const results = []
for (let offset = 0; offset < sources.length; offset += 6) results.push(...await Promise.all(sources.slice(offset, offset + 6).map(capture)))
const packages = ['reka-ui', '@nuxt/ui', 'shadcn-vue', 'primevue', '@schedule-x/calendar', '@fullcalendar/vue3', 'vue-echarts', 'echarts', 'motion-v', '@tanstack/vue-table']
const versions = await Promise.all(packages.map(async name => {
  try {
    const response = await fetch(`https://registry.npmjs.org/${encodeURIComponent(name)}`, { signal: AbortSignal.timeout(18000) })
    const info = await response.json()
    const version = info['dist-tags']?.latest
    return { name, version, publishedAt: info.time?.[version], license: info.versions?.[version]?.license, repository: info.repository, source: `https://registry.npmjs.org/${encodeURIComponent(name)}` }
  } catch (error) { return { name, error: String(error) } }
}))
const picks = [
  ['/keenthemes/reui', 'ai-chat-9'], ['/keenthemes/reui', 'c-calendar-22'],
  ['/vercel/ai', 'prompt-input'], ['/vercel/ai', 'sources'],
  ['/kokonut-labs/kokonutui', 'file-upload'], ['/henriquegpb/microkit', 'focus-input'],
]
const registryItems = catalog.items.filter(item => picks.some(([path, name]) => item.registry.basePath === path && item.name === name))
const registrySource = await Promise.all(registryItems.map(async item => {
  const url = `https://registry.directory/api/markdown${item.registry.basePath}/${item.name}`
  const result = await capture({ id: `registry-${item.name}`, url })
  return { ...result, registry: item.registry.name, name: item.name, description: item.description }
}))
const evidence = { checkedAt: new Date().toISOString(), cache, catalog: { items: catalog.items.length, registries: new Set(catalog.items.map(i => i.registry.basePath)).size, source: 'https://registry.directory/items.json', componentDatesAvailable: false }, versions, sources: [...results, ...registrySource] }
await writeFile(join(output, 'evidence.json'), `${JSON.stringify(evidence, null, 2)}\n`)
console.log(JSON.stringify({ valid: results.filter(r => r.valid).length, total: results.length, failures: results.filter(r => !r.valid), versions, registrySource }, null, 2))
