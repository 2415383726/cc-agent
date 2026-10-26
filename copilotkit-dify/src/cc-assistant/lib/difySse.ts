export async function* streamDifySse(body: ReadableStream<Uint8Array>) {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      while (true) {
        const boundary = buffer.indexOf('\n\n')
        if (boundary < 0) break
        const chunk = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)

        const lines = chunk
          .split(/\r?\n/)
          .map((line) => line.trim())
          .filter(Boolean)

        const dataLines = lines
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trim())

        if (!dataLines.length) continue
        const payload = dataLines.join('\n')
        if (!payload || payload === '[DONE]') continue

        try {
          yield JSON.parse(payload)
        } catch (_) {
          continue
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}
