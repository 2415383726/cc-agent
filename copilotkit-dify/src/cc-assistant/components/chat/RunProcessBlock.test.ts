import { describe, expect, it } from 'vitest'
import { createSSRApp, defineComponent } from 'vue'
import { renderToString } from '@vue/server-renderer'
import RunProcessBlock from './RunProcessBlock.vue'

function renderBlock(props: Record<string, unknown>, slot = '<div data-testid="process-stream">过程内容</div>') {
  const Host = defineComponent({
    components: { RunProcessBlock },
    setup() {
      return { props }
    },
    template: `<RunProcessBlock v-bind="props">${slot}</RunProcessBlock>`,
  })
  return renderToString(createSSRApp(Host))
}

describe('RunProcessBlock', () => {
  it('marks the process shell as aligned with assistant content', async () => {
    const html = await renderBlock({
      mode: 'collapsed',
      summary: '已处理 4s · 调用 1 个工具 · 2 步',
      defaultExpanded: false,
    })

    expect(html).toContain('data-align="assistant"')
  })

  it('renders the process stream immediately while expanded', async () => {
    const html = await renderBlock({
      mode: 'expanded',
      summary: '处理中 · 调用 1 个工具 · 2 步',
      defaultExpanded: true,
    })

    expect(html).toContain('data-testid="run-process-summary" open')
    expect(html).toContain('data-testid="run-process-content"')
    expect(html).toContain('data-testid="process-stream"')
    expect(html).toContain('处理中 · 调用 1 个工具 · 2 步')
  })

  it('renders only the summary row after completion by default', async () => {
    const html = await renderBlock({
      mode: 'collapsed',
      summary: '已处理 5s · 调用 1 个工具 · 2 步',
      defaultExpanded: false,
    })

    expect(html).toContain('data-testid="run-process-summary"')
    expect(html).not.toContain('data-testid="run-process-content"')
    expect(html).not.toContain('data-testid="process-stream"')
    expect(html).toContain('已处理 5s · 调用 1 个工具 · 2 步')
  })

  it('restores the full process stream when an old run is expanded', async () => {
    const html = await renderBlock({
      mode: 'collapsed',
      summary: '已处理 5s · 调用 1 个工具 · 2 步',
      defaultExpanded: true,
    })

    expect(html).toContain('data-testid="run-process-summary" open')
    expect(html).toContain('data-testid="run-process-content"')
    expect(html).toContain('过程内容')
  })

  it('renders permission actions with the backend decision values', async () => {
    const html = await renderBlock({
      mode: 'expanded',
      summary: '处理中 · 1 步',
      defaultExpanded: true,
      interruptState: {
        result: {
          id: 'call_1',
          purpose: 'permission',
          question: 'Allow run_python?\nTool: run_python',
          options: [],
          allowCustomInput: false,
          multiSelect: false,
        },
        resolve: () => undefined,
      },
    })

    expect(html).toContain('操作授权')
    expect(html).toContain('将要执行：run_python')
    expect(html).toContain('允许一次')
    expect(html).toContain('本会话允许')
    expect(html).toContain('拒绝')
    expect(html).toContain('value="allow_once"')
    expect(html).toContain('value="allow_conversation"')
    expect(html).toContain('value="deny"')
  })
})
