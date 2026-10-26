import type { AttachmentUploadResult } from '@copilotkit/shared'

interface UploadCapableAgent {
  uploadFile?: (file: File) => Promise<any>
}

export async function buildDifyAttachmentUploadResult(agent: UploadCapableAgent | null | undefined, file: File): Promise<AttachmentUploadResult> {
  if (!agent?.uploadFile) throw new Error('Current agent does not support file upload')
  const uploaded = await agent.uploadFile(file)
  const id = stringValue(uploaded?.id || uploaded?.upload_file_id || uploaded?.uploadFileId)
  if (!id) throw new Error('Dify file upload did not return an upload id')

  const mimeType = stringValue(uploaded?.mimeType || uploaded?.mime_type || file.type)
  const name = stringValue(uploaded?.name || file.name)
  const type = stringValue(uploaded?.type || (mimeType.toLowerCase().startsWith('image/') ? 'image' : 'document'))
  const size = numberValue(uploaded?.size ?? file.size)

  return {
    type: 'url',
    value: `dify-file://${id}`,
    mimeType: mimeType || undefined,
    metadata: {
      upload_file_id: id,
      uploadFileId: id,
      filename: name,
      name,
      type,
      mimeType,
      size,
    },
  }
}

function stringValue(value: unknown) {
  return value == null ? '' : String(value)
}

function numberValue(value: unknown) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}
