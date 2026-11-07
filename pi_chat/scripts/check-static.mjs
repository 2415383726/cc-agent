#!/usr/bin/env node
// 静态构建门：产物零网络运行时资产、零追踪器、零旧后端/SDK 残留。
// 机制照搬 pi_workbench/scripts/check-static.mjs：哈希全部产物文件，
// 扫描文本产物中的禁用模式，写 dist/static-report.json，违例即非零退出。
import { createHash } from 'node:crypto'
import { readFile, readdir, stat, writeFile } from 'node:fs/promises'
import { join, relative } from 'node:path'
import { scanText, TEXT_EXTENSIONS } from './static-scan.mjs'

const ROOT = new URL('..', import.meta.url).pathname
const DIST = join(ROOT, 'dist')

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
  violations.push(...scanText(bytes.toString('utf8')).map((violation) => ({ file: relativePath, ...violation })))
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
