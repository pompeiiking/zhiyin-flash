import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const source = resolve(root, '../contracts/openapi.json')
const spec = JSON.parse(readFileSync(source, 'utf8'))
const schemas = spec.components.schemas
const queue = ['NoteView', 'NoteCreateRequest', 'NoteDoneRequest', 'AcademicPanelView', 'AcademicImportRequest', 'AcademicImportAck', 'ConversationMaterialView', 'TaskSessionView', 'SessionListView', 'MessageRequest', 'GuideOptionView', 'ConversationTurnView', 'ProfileFieldView', 'IntelListView', 'IntelItemView', 'CalendarNodeView', 'AchievementListView', 'ActionPlanView', 'ActionTaskDoneRequest', 'DirectionPlanListView', 'ReportFullTextView', 'AssetVersionView', 'TrackEventView', 'BootstrapView', 'TheoryCardView']
queue.push("TaskEdit", "PhaseEdit", "Preferences", "Semester", "ReviewEdit", "NotificationEdit", "MeasurementEdit", "MeasurementRecordView", "DirectionWeights", "PreferencesEdit", "SemesterEdit", "DirectionWeightsEdit")
const seen = new Set()
queue.push('WorkspacePageView', 'ExportResultView', 'LoginResult', 'AuthRequest', 'CoachNotificationView', 'PortalView')
function type(s = {}) {
  if (s.$ref) { const name = s.$ref.split('/').at(-1); if (!queue.includes(name)) queue.push(name); return name }
  if (s.const !== undefined) return JSON.stringify(s.const)
  if (s.enum) return s.enum.map(v => JSON.stringify(v)).join(' | ')
  if (s.anyOf || s.oneOf) return '(' + (s.anyOf || s.oneOf).map(type).join(' | ') + ')'
  if (s.allOf) return '(' + s.allOf.map(type).join(' & ') + ')'
  if (s.type === 'null') return 'null'
  if (s.type === 'array') return 'Array<' + type(s.items) + '>'
  if (s.type === 'integer' || s.type === 'number') return 'number'
  if (s.type === 'string' || s.type === 'boolean') return s.type
  if (s.type === 'object' || s.properties) {
    if (!s.properties) return 'Record<string, ' + (s.additionalProperties && typeof s.additionalProperties === 'object' ? type(s.additionalProperties) : 'unknown') + '>'
    return '{\n' + Object.entries(s.properties).map(([k, v]) => '  ' + JSON.stringify(k) + ((s.required || []).includes(k) ? '' : '?') + ': ' + type(v) + '\n').join('') + '}'
  }
  return 'unknown'
}
let output = '// Generated from ../contracts/openapi.json. Run npm run sync:backend. Do not hand edit.\n\n'
for (let i = 0; i < queue.length; i++) {
  const name = queue[i]
  if (seen.has(name)) continue
  if (!schemas[name]) throw new Error('Missing backend schema: ' + name)
  seen.add(name)
  output += 'export type ' + name + ' = ' + type(schemas[name]) + '\n\n'
}
const target = resolve(root, 'src/api/backend-types.ts')
if (process.argv.includes('--check')) {
  if (readFileSync(target, 'utf8').replace(/\r\n/g, '\n') !== output) throw new Error('Backend types changed. Run npm run sync:backend.')
} else { mkdirSync(dirname(target), { recursive: true }); writeFileSync(target, output) }
console.log('Backend contract: ' + seen.size + ' schemas synchronized.')
const dataRoot = resolve(root, '../data/registry')
const readRegistry = name => JSON.parse(readFileSync(resolve(dataRoot, name + '.json'), 'utf8'))
const registry = {
  taskEntries: readRegistry('task_entries').items,
  theoryCards: readRegistry('theory_cards').items,
  badgeRules: readRegistry('badge_rules').items,
  modules: ['action_progress', 'achievements'].map(id => {
    const manifest = JSON.parse(readFileSync(resolve(root, '../zhiyin-modules/zhiyin_modules', id, 'manifest.json'), 'utf8'))
    return { id: manifest.id, name: manifest.name, description: manifest.description, kind: manifest.kind, actions: manifest.actions }
  }),
}
const registryTarget = resolve(root, 'src/data/backend-registry.json')
const registryOutput = JSON.stringify(registry, null, 2) + '\n'
if (process.argv.includes('--check')) {
  if (readFileSync(registryTarget, 'utf8').replace(/\r\n/g, '\n') !== registryOutput) throw new Error('Backend registry changed. Run npm run sync:backend.')
} else writeFileSync(registryTarget, registryOutput)
