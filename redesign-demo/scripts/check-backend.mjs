import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const paths = JSON.parse(readFileSync(resolve(root, '../zhiyin-src/template/contracts/openapi.json'), 'utf8')).paths
const operations = JSON.parse(readFileSync(resolve(root, 'src/api/operations.json'), 'utf8'))
for (const [name, operation] of Object.entries(operations)) {
  if (!paths['/api/v1' + operation.path]?.[operation.method.toLowerCase()]) throw new Error('Backend operation not found: ' + name + ' ' + operation.method + ' ' + operation.path)
}
const sync = spawnSync(process.execPath, [resolve(root, 'scripts/sync-backend-types.mjs'), '--check'], { encoding: 'utf8' })
if (sync.status !== 0) throw new Error(sync.stderr || sync.stdout)
process.stdout.write(sync.stdout)
console.log('Backend alignment: ' + Object.keys(operations).length + ' student operations match OpenAPI.')
