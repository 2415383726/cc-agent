import { describe, expect, it } from 'vitest'
import { buildDifyAttachmentUploadResult } from './difyAttachments'

describe('difyAttachments', () => {
  it('returns structured-clone-safe metadata for uploaded files', async () => {
    const uploadedProxy = new Proxy({
      id: 'upload_1',
      type: 'document',
      name: 'brief.pdf',
      mimeType: 'application/pdf',
      size: 123,
    }, {})
    const agent = {
      uploadFile: async () => uploadedProxy,
    }
    const file = new File(['hello'], 'brief.pdf', { type: 'application/pdf' })

    const result = await buildDifyAttachmentUploadResult(agent, file)

    expect(() => structuredClone(result)).not.toThrow()
    expect(result).toEqual({
      type: 'url',
      value: 'dify-file://upload_1',
      mimeType: 'application/pdf',
      metadata: {
        upload_file_id: 'upload_1',
        uploadFileId: 'upload_1',
        filename: 'brief.pdf',
        name: 'brief.pdf',
        type: 'document',
        mimeType: 'application/pdf',
        size: 123,
      },
    })
  })
})
