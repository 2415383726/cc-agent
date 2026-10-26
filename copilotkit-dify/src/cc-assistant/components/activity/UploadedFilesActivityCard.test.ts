import { describe, expect, it } from 'vitest'
import { createSSRApp, ref } from 'vue'
import { renderToString } from '@vue/server-renderer'
import UploadedFilesActivityCard from './UploadedFilesActivityCard.vue'

describe('UploadedFilesActivityCard', () => {
  it('renders uploaded file metadata without requiring a URL', async () => {
    const app = createSSRApp(UploadedFilesActivityCard, {
      content: {
        files: [
          { id: 'upload_1', name: 'PLAN.md', type: 'document', mimeType: 'text/markdown', size: 4714 },
        ],
      },
    })

    const html = await renderToString(app)

    expect(html).toContain('附件 (1)')
    expect(html).toContain('PLAN.md')
    expect(html).toContain('Document')
    expect(html).toContain('4.6 KB')
    expect(html).not.toContain('href=')
  })

  it('renders relative Dify file metadata without turning uploaded attachments into links', async () => {
    const app = createSSRApp(UploadedFilesActivityCard, {
      content: {
        files: [
          {
            id: 'file_1',
            name: 'brief.pdf',
            mime_type: 'application/pdf',
            size: 1024,
            url: '/files/file_1/file-preview',
          },
        ],
      },
    })
    app.provide('difyBaseUrl', ref('http://localhost/v1'))

    const html = await renderToString(app)

    expect(html).toContain('brief.pdf')
    expect(html).toContain('Document')
    expect(html).toContain('1 KB')
    expect(html).not.toContain('href=')
    expect(html).not.toContain('/files/file_1/file-preview')
    expect(html).not.toContain('localhost:5173')
  })

  it('does not render internal file references as clickable links', async () => {
    const app = createSSRApp(UploadedFilesActivityCard, {
      content: {
        files: [
          { id: 'upload_1', name: 'PLAN.md', url: 'dify-file://upload_1' },
          { id: 'workspace_1', name: 'report.md', preview_url: 'workspace://generated/report.md' },
        ],
      },
    })

    const html = await renderToString(app)

    expect(html).toContain('PLAN.md')
    expect(html).toContain('report.md')
    expect(html).not.toContain('href=')
    expect(html).not.toContain('dify-file://upload_1')
    expect(html).not.toContain('workspace://generated/report.md')
  })
})
