import { createHash } from 'node:crypto'
import { readFile, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))
const path = join(root, 'src/visualize/manifest.json')
const manifest = JSON.parse(await readFile(path, 'utf8'))
if (manifest.protocolVersion !== '1' || manifest.kitMajor !== '1' || manifest.kitVersion !== '1.0.0') throw new Error('Unsupported visualization release version')
const update = process.argv.includes('--write')
for (const resource of manifest.resources) {
  for (const [field, hashField] of [['file', 'sha256'], ['licenseFile', 'licenseSha256']]) {
    if (!resource[field]) continue
    const bytes = await readFile(join(root, 'public', resource[field]))
    const hash = createHash('sha256').update(bytes).digest('hex')
    if (update && resource.kind !== 'library' && field === 'file') {
      resource.bytes = bytes.length
      resource[hashField] = hash
    } else if (hash !== resource[hashField] || (field === 'file' && bytes.length !== resource.bytes)) {
      throw new Error(`Visualization asset mismatch: ${resource[field]}`)
    }
  }
}
if (update) await writeFile(path, JSON.stringify(manifest, null, 2) + '\n')
console.log(`Visualization kit ${manifest.kitVersion}: ${manifest.resources.length} local assets verified`)
