import type { AssistantSkill } from './assistantCatalog'
import { submitLauncherMessage } from './homeLauncher'

export interface LaunchWithMessageOptions {
  files?: any[]
  selectedSkill?: AssistantSkill | null
}

export type LaunchWithMessage = (
  text: string,
  options?: LaunchWithMessageOptions
) => Promise<boolean>

export interface AssistantLauncherDependencies {
  getAgent: () => any
  runAgent: (input: { agent: any }) => Promise<unknown>
  openDrawer: () => void
  getDisabledReason?: () => string
  prepareConversation?: () => any | Promise<any>
}

export function createAssistantLauncher({
  getAgent,
  runAgent,
  openDrawer,
  getDisabledReason = () => '',
  prepareConversation,
}: AssistantLauncherDependencies) {
  return {
    launchWithMessage(text: string, options: LaunchWithMessageOptions = {}) {
      return submitLauncherMessage({
        text,
        selectedSkill: options.selectedSkill || null,
        agent: getAgent(),
        runAgent,
        openDrawer,
        disabledReason: getDisabledReason(),
        files: options.files || [],
        prepareConversation,
      })
    },
  }
}
