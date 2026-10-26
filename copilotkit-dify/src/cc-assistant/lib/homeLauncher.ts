import { randomUUID } from '@copilotkit/shared'
import type { AssistantSkill } from './assistantCatalog'
import { buildSubmittedText } from './assistantComposer'

export interface SubmitLauncherMessageOptions {
  text: string
  selectedSkill?: AssistantSkill | null
  agent: any
  runAgent: (input: { agent: any }) => Promise<unknown>
  openDrawer: () => void
  disabledReason?: string
  files?: any[]
  prepareConversation?: () => any | Promise<any>
}

export async function submitLauncherMessage({
  text,
  selectedSkill = null,
  agent,
  runAgent,
  openDrawer,
  disabledReason = '',
  files = [],
  prepareConversation,
}: SubmitLauncherMessageOptions) {
  const content = buildSubmittedText(text, selectedSkill)
  if (!content || disabledReason || !agent) return false

  const activeAgent = await prepareConversation?.() || agent
  openDrawer()
  activeAgent.addMessage({
    id: randomUUID(),
    role: 'user',
    content,
    files,
  })
  await runAgent({ agent: activeAgent })
  return true
}
