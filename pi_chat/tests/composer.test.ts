import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ComposerBar from '../src/shell/ComposerBar.vue'
import type { FileRef } from '../src/projection/transcript'

/*
 * 组件 seam（票 08）：ComposerBar 的附件上传、Enter/IME、busy/停止按钮态。
 * 只断言外显行为（DOM 与 emit），不触内部实现。
 */

function makeFile(name: string, type: string, size: number): File {
  return new File([new Uint8Array(size)], name, { type })
}

async function pick(wrapper: ReturnType<typeof mount>, files: File[]): Promise<void> {
  const input = wrapper.find('input[type="file"]')
  Object.defineProperty(input.element, 'files', { value: files, configurable: true })
  await input.trigger('change')
  await flushPromises()
}

describe('ComposerBar 附件上传', () => {
  it('「+」激活文件选择：选择后调用 upload 并展示名称/类型/大小 chips（安全元数据）', async () => {
    const upload = vi.fn(async (file: File): Promise<FileRef | null> => ({
      id: 'file_1',
      name: file.name,
      mimeType: file.type,
      size: file.size,
    }))
    const wrapper = mount(ComposerBar, { props: { interactive: true, upload } })

    const add = wrapper.find('[data-testid="composer-add"]')
    expect(add.attributes('disabled')).toBeUndefined()
    await add.trigger('click')
    // 「+」点击触发的是隐藏 file input 的选择框（间接可观察：input 存在且被点击）
    expect(wrapper.find('input[type="file"]').exists()).toBe(true)

    await pick(wrapper, [makeFile('报告.pdf', 'application/pdf', 2048)])
    expect(upload).toHaveBeenCalledTimes(1)
    expect((upload.mock.calls[0] as unknown[])[0]).toBeInstanceOf(File)
    const chips = wrapper.findAll('[data-testid="composer-file-chip"]')
    expect(chips).toHaveLength(1)
    expect(chips[0].text()).toContain('报告.pdf')
    expect(chips[0].text()).toContain('application/pdf')
    expect(chips[0].text()).toContain('2.0 KB')
    // 安全元数据：不出现任何文件内容或链接
    expect(chips[0].text()).not.toContain('pdf-bytes')
    expect(chips[0].find('a').exists()).toBe(false)
  })

  it('上传中显示「上传中…」且禁止再次选择与发送；完成后状态消失', async () => {
    let release: ((value: FileRef | null) => void) | null = null
    const upload = vi.fn(
      (file: File) =>
        new Promise<FileRef | null>((resolve) => {
          release = resolve
        }),
    )
    const wrapper = mount(ComposerBar, { props: { interactive: true, upload } })
    const input = wrapper.find('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [makeFile('a.txt', 'text/plain', 3)], configurable: true })
    await input.trigger('change')

    expect(wrapper.find('[data-testid="composer-uploading"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="composer-add"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="composer-send"]').attributes('disabled')).toBeDefined()

    release?.({ id: 'f1', name: 'a.txt', mimeType: 'text/plain', size: 3 })
    await flushPromises()
    expect(wrapper.find('[data-testid="composer-uploading"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="composer-file-chip"]')).toHaveLength(1)
  })

  it('上传失败（upload 返回 null）不加入待发送列表，可继续发送文本', async () => {
    const upload = vi.fn(async (): Promise<FileRef | null> => null)
    const wrapper = mount(ComposerBar, { props: { interactive: true, upload } })
    await pick(wrapper, [makeFile('坏.png', 'image/png', 10)])
    expect(wrapper.findAll('[data-testid="composer-file-chip"]')).toHaveLength(0)
    // 文本仍可发送
    await wrapper.find('textarea').setValue('你好')
    await wrapper.find('textarea').trigger('keydown.enter')
    expect(wrapper.emitted('send')).toHaveLength(1)
  })

  it('「×」可移除待发送附件', async () => {
    const upload = vi.fn(async (file: File): Promise<FileRef | null> => ({
      id: 'file_9',
      name: file.name,
      mimeType: file.type,
      size: file.size,
    }))
    const wrapper = mount(ComposerBar, { props: { interactive: true, upload } })
    await pick(wrapper, [makeFile('a.txt', 'text/plain', 3)])
    await wrapper.find('[data-testid="chip-remove"]').trigger('click')
    expect(wrapper.findAll('[data-testid="composer-file-chip"]')).toHaveLength(0)
  })

  it('发送 payload 为 (文本, 附件数组)，随后清空草稿与附件', async () => {
    const upload = vi.fn(async (file: File): Promise<FileRef | null> => ({
      id: 'file_1',
      name: file.name,
      mimeType: file.type,
      size: file.size,
    }))
    const wrapper = mount(ComposerBar, { props: { interactive: true, upload } })
    await pick(wrapper, [makeFile('数据.csv', 'text/csv', 20480)])
    await wrapper.find('textarea').setValue('看附件')
    await wrapper.find('textarea').trigger('keydown.enter')

    const sent = wrapper.emitted('send')
    expect(sent).toHaveLength(1)
    const [text, files] = sent![0] as [string, FileRef[]]
    expect(text).toBe('看附件')
    expect(files).toHaveLength(1)
    expect(files[0]).toMatchObject({ id: 'file_1', name: '数据.csv', mimeType: 'text/csv', size: 20480 })
    expect((wrapper.find('textarea').element as HTMLTextAreaElement).value).toBe('')
    expect(wrapper.findAll('[data-testid="composer-file-chip"]')).toHaveLength(0)
  })

  it('只有附件没有文本不能发送（控制器要求非空 query，避免静默丢弃）', async () => {
    const upload = vi.fn(async (file: File): Promise<FileRef | null> => ({
      id: 'file_1',
      name: file.name,
      mimeType: file.type,
      size: file.size,
    }))
    const wrapper = mount(ComposerBar, { props: { interactive: true, upload } })
    await pick(wrapper, [makeFile('a.txt', 'text/plain', 3)])
    await wrapper.find('textarea').trigger('keydown.enter')
    await wrapper.find('[data-testid="composer-send"]').trigger('click')
    expect(wrapper.emitted('send')).toBeUndefined()
  })
})

describe('ComposerBar Enter / IME / busy', () => {
  it('Enter 发送；Shift+Enter 换行不发送；空草稿不发送', async () => {
    const wrapper = mount(ComposerBar, { props: { interactive: true } })
    await wrapper.find('textarea').trigger('keydown.enter')
    expect(wrapper.emitted('send')).toBeUndefined()

    await wrapper.find('textarea').setValue('第一行')
    await wrapper.find('textarea').trigger('keydown.enter.shift')
    expect(wrapper.emitted('send')).toBeUndefined()

    await wrapper.find('textarea').trigger('keydown.enter')
    expect(wrapper.emitted('send')).toHaveLength(1)
    expect(wrapper.emitted('send')![0][0]).toBe('第一行')
  })

  it('IME 组词期 Enter 不发送，组词结束后恢复', async () => {
    const wrapper = mount(ComposerBar, { props: { interactive: true } })
    const textarea = wrapper.find('textarea')
    await textarea.setValue('ni')
    await textarea.trigger('compositionstart')
    await textarea.trigger('keydown.enter')
    expect(wrapper.emitted('send')).toBeUndefined()

    await textarea.trigger('compositionend')
    await textarea.trigger('keydown.enter')
    expect(wrapper.emitted('send')).toHaveLength(1)
  })

  it('busy 时输入不发送、发送按钮不出现，停止按钮出现且可点；非运行时无停止按钮', async () => {
    const idle = mount(ComposerBar, { props: { interactive: true, busy: false } })
    expect(idle.find('[data-testid="composer-stop"]').exists()).toBe(false)
    expect(idle.find('[data-testid="composer-send"]').exists()).toBe(true)

    const busy = mount(ComposerBar, { props: { interactive: true, busy: true, stoppable: true } })
    await busy.find('textarea').setValue('排队文本')
    await busy.find('textarea').trigger('keydown.enter')
    expect(busy.emitted('send')).toBeUndefined()
    expect(busy.find('[data-testid="composer-send"]').exists()).toBe(false)
    const stop = busy.find('[data-testid="composer-stop"]')
    expect(stop.exists()).toBe(true)
    expect(stop.attributes('disabled')).toBeUndefined()
    await stop.trigger('click')
    expect(busy.emitted('stop')).toHaveLength(1)
  })

  it('停止请求已发出（stopping）时停止按钮禁用且为方块字形', async () => {
    const wrapper = mount(ComposerBar, {
      props: { interactive: false, busy: true, stoppable: true, stopping: true },
    })
    const stop = wrapper.find('[data-testid="composer-stop"]')
    // 停止钮内是 16px 圆角方块字形（上游 InputBar 同款）；文案只进 aria-label。
    expect(stop.find('svg rect').exists()).toBe(true)
    expect(stop.attributes('aria-label')).toBe('停止中')
    expect(stop.attributes('disabled')).toBeDefined()
  })

  it('按住 Enter 连发（event.repeat）不重复发送', async () => {
    const wrapper = mount(ComposerBar, { props: { interactive: true } })
    await wrapper.find('textarea').setValue('只发一次')
    await wrapper.find('textarea').trigger('keydown', { key: 'Enter', repeat: true })
    expect(wrapper.emitted('send')).toBeUndefined()
  })

  it('Ctrl/Cmd+Enter 加速发送', async () => {
    const wrapper = mount(ComposerBar, { props: { interactive: true } })
    await wrapper.find('textarea').setValue('加速')
    await wrapper.find('textarea').trigger('keydown', { key: 'Enter', metaKey: true })
    expect(wrapper.emitted('send')).toHaveLength(1)
  })

  it('非交互（未连接/回放）时「+」为禁用占位且不渲染 file input', () => {
    const wrapper = mount(ComposerBar, { props: {} })
    expect(wrapper.find('[data-testid="composer-add"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('input[type="file"]').exists()).toBe(false)
  })
})
