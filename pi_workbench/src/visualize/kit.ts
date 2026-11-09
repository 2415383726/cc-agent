import manifest from './manifest.json'

export const supportedLibraries = manifest.resources.filter((item) => item.kind === 'library').map((item) => item.id)
export const sandboxPolicy = "default-src 'none'; script-src 'unsafe-inline'; script-src-attr 'none'; style-src 'unsafe-inline'; img-src data:; font-src 'none'; connect-src 'none'; media-src 'none'; frame-src blob:; worker-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"

export function hasSandboxPolicy(headers: Headers): boolean {
  // Require the same reviewed response policy; a meta element cannot replace it.
  return headers.get('Connection-Allowlist')?.trim() === '()' &&
    headers.get('Content-Security-Policy')?.trim() === sandboxPolicy
}

export interface KitAssets { css: string; runtime: string; libraries: Array<{ id: string; code: string }> }

/** The parent loads only fixed local files. Nothing in the opaque frame fetches dependencies. */
export async function loadKit(libraries: string[]): Promise<KitAssets> {
  if (libraries.some((id) => !supportedLibraries.includes(id))) throw new Error('不支持的本地库。')
  const resources = manifest.resources.filter((item) => item.kind !== 'library' || libraries.includes(item.id))
  const loaded = await Promise.all(resources.map(async (item) => {
    const url = new URL(`${import.meta.env.BASE_URL}${item.file}`, window.location.href)
    const integrity = 'sha256-' + btoa(String.fromCharCode(...item.sha256.match(/../g)!.map((hex) => parseInt(hex, 16))))
    let response: Response
    try { response = await fetch(url, { credentials: 'omit', redirect: 'error', integrity }) }
    catch { throw new Error('本地可视化资源无法加载或校验失败，请联系维护者检查部署。') }
    if (!response.ok) throw new Error('本地可视化资源缺失，请联系维护者检查部署。')
    const bytes = await response.arrayBuffer()
    if (bytes.byteLength !== item.bytes) throw new Error('本地可视化资源校验失败，请联系维护者检查部署。')
    return { ...item, code: new TextDecoder().decode(bytes) }
  }))
  return {
    css: loaded.find((item) => item.kind === 'style')!.code,
    runtime: loaded.find((item) => item.kind === 'runtime')!.code,
    libraries: loaded.filter((item) => item.kind === 'library').map(({ id, code }) => ({ id, code })),
  }
}

const colors = {
  background: ['--bg', '#0d0d0d'], text: ['--text', '#ececec'],
  surface: ['--panel', '#191919'], raised: ['--panel-strong', '#2a2a2a'],
  muted: ['--muted-strong', '#afafaf'], border: ['--viz-control-border', '#70707a'],
  primary: ['--accent', '#8a78ff'], onPrimary: ['--viz-on-primary', '#0d0d0d'],
  input: ['--panel-soft', '#1f1f1f'], focus: ['--accent', '#8a78ff'],
  danger: ['--viz-danger', '#fca5a5'],
  series1: ['--viz-series-1', '#a99aff'], series2: ['--viz-series-2', '#73c9e8'],
  series3: ['--viz-series-3', '#83d7ae'], series4: ['--viz-series-4', '#f3bf70'],
  series5: ['--viz-series-5', '#ed97bd'], series6: ['--viz-series-6', '#c5b5e8'],
} as const

/** Resolve real CSS colors before sending them; canvas cannot consume CSS variables itself. */
export function readHostTheme() {
  const style = getComputedStyle(document.documentElement)
  const probe = document.createElement('span')
  probe.style.display = 'none'
  document.body.append(probe)
  const resolved = Object.fromEntries(Object.entries(colors).map(([key, [property, fallback]]) => {
    probe.style.color = fallback
    probe.style.color = style.getPropertyValue(property).trim() || fallback
    return [key, getComputedStyle(probe).color]
  }))
  probe.remove()
  return { mode: document.documentElement.dataset.theme === 'light' ? 'light' : 'dark', colors: resolved }
}
