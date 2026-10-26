import { describe, expect, it } from 'vitest'
import { createDifyBlobAccumulator } from './difyBlob'

describe('difyBlob accumulator', () => {
  it('emits one skill artifact activity after all blob chunks arrive', () => {
    const accumulator = createDifyBlobAccumulator()

    const first = accumulator.ingest({
      type: 'blob_chunk',
      message: {
        id: 'blob_1',
        sequence: 0,
        total_length: 6,
        blob: 'cmVw',
        end: false,
      },
      meta: {
        filename: 'report.md',
        mime_type: 'text/markdown',
      },
    })
    const second = accumulator.ingest({
      type: 'blob_chunk',
      message: {
        id: 'blob_1',
        sequence: 1,
        total_length: 6,
        blob: 'b3J0',
        end: false,
      },
      meta: {
        filename: 'report.md',
        mime_type: 'text/markdown',
      },
    })
    const final = accumulator.ingest({
      type: 'blob_chunk',
      message: {
        id: 'blob_1',
        sequence: 2,
        total_length: 6,
        blob: '',
        end: true,
      },
      meta: {
        filename: 'report.md',
        mime_type: 'text/markdown',
      },
    })

    expect(first).toBeNull()
    expect(second).toBeNull()
    expect(final).toEqual({
      messageId: expect.stringMatching(/^skill_artifact_/),
      activityType: 'cc_agent.skill_artifact',
      content: {
        message: 'Generated files were attached to this chat response.',
        files: [
          {
            id: 'blob_1',
            name: 'report.md',
            mime_type: 'text/markdown',
            size: 6,
            status: 'attached',
            download_data_url: 'data:text/markdown;base64,cmVwb3J0',
          },
        ],
      },
    })
  })

  it('emits a downloadable artifact for a complete blob message', () => {
    const accumulator = createDifyBlobAccumulator()

    const activity = accumulator.ingest({
      type: 'blob',
      message: {
        blob: 'c2xpZGVz',
      },
      meta: {
        filename: 'slides.pptx',
        mime_type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      },
    })

    expect(activity).toMatchObject({
      activityType: 'cc_agent.skill_artifact',
      content: {
        files: [
          {
            name: 'slides.pptx',
            mime_type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            size: 6,
            status: 'attached',
            download_data_url: 'data:application/vnd.openxmlformats-officedocument.presentationml.presentation;base64,c2xpZGVz',
          },
        ],
      },
    })
  })
})
