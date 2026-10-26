export interface FileView {
  key: string
  id: string
  name: string
  type: string
  mimeType: string
  sizeLabel: string
  href: string
}

export function normalizeFileView(file: any, index: number, baseUrl = ''): FileView {
  const id = stringValue(file?.id || file?.dify_file_id || file?.upload_file_id || file?.uploadFileId)
  const name = stringValue(file?.name || file?.filename || file?.document_name || file?.path || `file-${index + 1}`)
  const mimeType = stringValue(file?.mimeType || file?.mime_type || file?.mime)
  const type = stringValue(file?.type || fileTypeFromMime(mimeType))
  const size = Number(file?.size || 0)
  return {
    key: stringValue(id || file?.path || file?.workspace_path || name || index),
    id,
    name,
    type,
    mimeType,
    sizeLabel: `${Number.isFinite(size) ? size : 0} bytes`,
    href: resolveUserFileUrl(firstUserFileUrl(file), baseUrl),
  }
}

export function firstUserFileUrl(file: any) {
  const candidates = [
    file?.download_data_url,
    file?.downloadDataUrl,
    file?.download_url,
    file?.downloadUrl,
    file?.preview_url,
    file?.previewUrl,
    file?.url,
    file?.remote_url,
  ]
  for (const value of candidates) {
    const url = stringValue(value).trim()
    if (url && !url.startsWith('workspace://') && !url.startsWith('dify-file://')) return url
  }
  return ''
}

export function resolveUserFileUrl(url: string, baseUrl: string) {
  if (!url) return ''
  if (/^https?:\/\//i.test(url)) return url
  if (/^data:[^,]+,/i.test(url)) return url
  if (url.startsWith('/') && baseUrl) {
    try {
      return new URL(url, baseUrl).toString()
    } catch (_) {
      return ''
    }
  }
  return ''
}

function fileTypeFromMime(mimeType: string) {
  return mimeType.toLowerCase().startsWith('image/') ? 'image' : 'document'
}

function stringValue(value: unknown) {
  return value == null ? '' : String(value)
}
