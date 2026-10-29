#!/usr/bin/env node
// Static build gate: no network runtime assets, no Pi Agent SDK, no bundled Node backend.
import { createHash } from 'node:crypto'
import { readFile, readdir, stat, writeFile } from 'node:fs/promises'
import { join, relative } from 'node:path'

const ROOT = new URL('..', import.meta.url).pathname
const DIST = join(ROOT, 'dist')
const FORBIDDEN = [
  /\bsrc\s*=\s*["']https?:/i,
  /\bhref\s*=\s*["']https?:/i,
  /url\(\s*["']?https?:/i,
  /\bfetch\(\s*["'`]https?:/i,
  /\bimport\(\s*["'`]https?:/i,
  /wss?:\/\//i,
  /pi-coding-agent/i,
  /@earendil-works/i,
  /\/api\/pi\//i,
  /fonts\.googleapis\.com/i,
  /cdn\.jsdelivr\.net/i,
  /unpkg\.com/i,
  /google-analytics/i,
]
const TEXT_EXTENSIONS = new Set(['.html', '.js', '.css', '.json', '.svg', '.txt', '.map'])

async function walk(dir) {
  const entries = []
  for (const name of await readdir(dir)) {
    const path = join(dir, name)
    const info = await stat(path)
    if (info.isDirectory()) entries.push(...(await walk(path)))
    else entries.push(path)
  }
  return entries
}

const files = await walk(DIST)
const report = []
const violations = []
for (const file of files) {
  const relativePath = relative(DIST, file)
  const extension = file.slice(file.lastIndexOf('.'))
  const bytes = await readFile(file)
  const sha256 = createHash('sha256').update(bytes).digest('hex')
  report.push({ file: relativePath, bytes: bytes.length, sha256 })
  if (!TEXT_EXTENSIONS.has(extension)) continue
  const text = bytes.toString('utf8')
  for (const pattern of FORBIDDEN) {
    const match = text.match(pattern)
    if (match) violations.push({ file: relativePath, pattern: String(pattern), match: match[0].slice(0, 80) })
  }
}

const publishedKit = JSON.parse(await readFile(join(DIST, 'visualize/manifest.json'), 'utf8'))
const expectedKit = JSON.parse(await readFile(join(ROOT, 'src/visualize/manifest.json'), 'utf8'))
if (JSON.stringify(publishedKit) !== JSON.stringify(expectedKit)) {
  violations.push({ file: 'visualize/manifest.json', reason: 'Published kit differs from the supported source manifest' })
}
for (const resource of publishedKit.resources) {
  for (const [field, hashField] of [['file', 'sha256'], ['licenseFile', 'licenseSha256']]) {
    if (!resource[field]) continue
    const entry = report.find((item) => item.file === resource[field])
    if (!entry || entry.sha256 !== resource[hashField] || (field === 'file' && entry.bytes !== resource.bytes)) {
      violations.push({ file: resource[field], reason: 'Published visualization resource failed manifest verification' })
    }
  }
}

const output = {
  generatedAt: new Date().toISOString(),
  fileCount: files.length,
  totalBytes: report.reduce((sum, item) => sum + item.bytes, 0),
  files: report.sort((left, right) => left.file.localeCompare(right.file)),
  violations,
}
await writeFile(join(DIST, 'static-report.json'), JSON.stringify(output, null, 2))
console.log(JSON.stringify({ fileCount: output.fileCount, totalBytes: output.totalBytes, violations }, null, 2))
if (violations.length) process.exitCode = 1
