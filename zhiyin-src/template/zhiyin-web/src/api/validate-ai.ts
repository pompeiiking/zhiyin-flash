// SSE envelopes are checked at the rendering boundary as well as by the service.
type ObjectValue = Record<string, unknown>
const object = (v: unknown): v is ObjectValue => v !== null && typeof v === 'object' && !Array.isArray(v)
const strings = (v: ObjectValue, names: string[]) => names.every(k => typeof v[k] === 'string')
const list = (v: unknown, fields: string[]) => Array.isArray(v) && v.every(p => object(p) && strings(p, fields))
export function validAiData(key: string, data: unknown): boolean {
  if (key === 'noteSuggestions') return list(data, ['id','label','why','from','when'])
  if (!object(data)) return false
  switch (key) {
    case 'portraitAnalysis':
    case 'academicAnalysis': return strings(data,['headline','reading']) && ['strengths','watchouts','next'].every(k=>list(data[k],['label','why']))
    case 'dimension': return strings(data,['id','name','conclusion','reading','next']) && Array.isArray(data.trend) && data.trend.every(p=>object(p)&&strings(p,['at','why'])&&typeof p.v==='number')
    case 'gap': return strings(data,['question','whyNow']) && list(data.options,['label','why'])
    case 'careerMatch': return list(data.ranking,['track','gap','why']) && Array.isArray(data.cells) && data.cells.every(p=>object(p)&&strings(p,['track','skill'])&&typeof p.need==='number'&&typeof p.have==='number') && object(data.recommend) && strings(data.recommend,['title','body']) && Array.isArray(data.recommend.because) && data.recommend.because.every(p=>typeof p==='string')
    case 'reportSummary': return strings(data,['headline']) && Array.isArray(data.paragraphs) && data.paragraphs.every(p=>typeof p==='string') && list(data.moves,['label','why'])
    case 'brief': return strings(data,['headline','ifYouSkip']) && list(data.because,['text','from']) && list(data.changed,['text','at']) && list(data.next,['id','label','why'])
    case 'dayAdvice': return strings(data,['date','headline','reading','watch']) && list(data.plan,['label','why'])
    case 'timetable': return strings(data,['headline']) && list(data.windows,['day','slot','why']) && list(data.moves,['at','what','why'])
    case 'chsi': return list(data.steps,['id','label','detail','source']) && Array.isArray(data.courses) && list(data.lifted,['dim','because'])
    default: return true
  }
}
