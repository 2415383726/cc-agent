import { describe, expect, it } from 'vitest'
import { createSSRApp, ref } from 'vue'
import { renderToString } from '@vue/server-renderer'
import WorkspaceActivityCard from './WorkspaceActivityCard.vue'

describe('WorkspaceActivityCard', () => {
  it('renders Dify file URLs against the configured Dify base URL', async () => {
    const app = createSSRApp(WorkspaceActivityCard, {
      content: {
        message: 'File generated: report.md',
        files: [
          {
            name: 'report.md',
            size: 128,
            preview_url: '/files/file_1/file-preview',
            status: 'uploaded',
          },
        ],
      },
    })
    app.provide('difyBaseUrl', ref('http://localhost/v1'))

    const html = await renderToString(app)

    expect(html).toContain('href="http://localhost/files/file_1/file-preview"')
    expect(html).toContain('Download')
    expect(html).not.toContain('localhost:5173')
  })

  it('prefers inline download data over Dify preview links', async () => {
    const app = createSSRApp(WorkspaceActivityCard, {
      content: {
        message: 'File generated: report.md',
        files: [
          {
            name: 'report.md',
            size: 128,
            preview_url: '/files/file_1/file-preview',
            download_url: 'http://localhost/files/file_1/file-preview',
            download_data_url: 'data:text/markdown;base64,cmVwb3J0',
            status: 'uploaded',
          },
        ],
      },
    })

    const html = await renderToString(app)

    expect(html).toContain('href="data:text/markdown;base64,cmVwb3J0"')
    expect(html).toContain('download="report.md"')
    expect(html).not.toContain('href="http://localhost/files/file_1/file-preview"')
  })

  it('renders MinIO presigned download URLs without exposing workspace references', async () => {
    const app = createSSRApp(WorkspaceActivityCard, {
      content: {
        message: 'Workspace files updated.',
        files: [
          {
            name: 'answer.md',
            size: 512,
            mime_type: 'text/markdown',
            status: 'ready',
            workspace_path: 'workspace://outputs/answer.md',
            download_url: 'https://minio.example/objects/sha256/aa/hash?X-Amz-Expires=3600',
          },
        ],
      },
    })

    const html = await renderToString(app)

    expect(html).toContain('href="https://minio.example/objects/sha256/aa/hash?X-Amz-Expires=3600"')
    expect(html).toContain('Download ready')
    expect(html).not.toContain('workspace://outputs/answer.md')
  })

  it('does not render workspace URLs as user-download links', async () => {
    const app = createSSRApp(WorkspaceActivityCard, {
      content: {
        files: [
          {
            name: 'report.md',
            size: 128,
            workspace_path: 'workspace://report.md',
            status: 'local',
          },
        ],
      },
    })

    const html = await renderToString(app)

    expect(html).toContain('Saved in workspace')
    expect(html).not.toContain('href=')
    expect(html).not.toContain('workspace://report.md')
  })

  it('renders upload failure details when Dify upload fails', async () => {
    const app = createSSRApp(WorkspaceActivityCard, {
      content: {
        files: [
          {
            name: 'report.md',
            size: 128,
            status: 'upload_failed',
            error: 'upload file failed, status code: 403',
            download_data_url: 'data:text/markdown;base64,cmVwb3J0',
          },
        ],
      },
    })

    const html = await renderToString(app)

    expect(html).toContain('Upload failed')
    expect(html).toContain('upload file failed, status code: 403')
    expect(html).toContain('href="data:text/markdown;base64,cmVwb3J0"')
    expect(html).toContain('Download')
  })

  it('renders attached skill artifacts without implying a workspace download URL', async () => {
    const app = createSSRApp(WorkspaceActivityCard, {
      content: {
        message: 'Generated files were attached to this chat response.',
        files: [
          {
            name: 'slides.pptx',
            size: 4096,
            mime_type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            status: 'attached',
          },
        ],
      },
    })

    const html = await renderToString(app)

    expect(html).toContain('Generated files were attached to this chat response.')
    expect(html).toContain('slides.pptx')
    expect(html).toContain('Attached to chat')
    expect(html).not.toContain('Saved in workspace')
    expect(html).not.toContain('href=')
  })
})
