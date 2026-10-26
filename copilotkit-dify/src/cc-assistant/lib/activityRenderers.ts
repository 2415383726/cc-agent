import { z } from 'zod'
import { createA2UIMessageRenderer, type VueActivityMessageRenderer } from '@copilotkit/vue/v2'
import ActivityCard from '../components/activity/ActivityCard.vue'
import CompressionActivityCard from '../components/activity/CompressionActivityCard.vue'
import PermissionActivityCard from '../components/activity/PermissionActivityCard.vue'
import ScriptActivityCard from '../components/activity/ScriptActivityCard.vue'
import SkillActivityCard from '../components/activity/SkillActivityCard.vue'
import UploadedFilesActivityCard from '../components/activity/UploadedFilesActivityCard.vue'
import WorkspaceActivityCard from '../components/activity/WorkspaceActivityCard.vue'

export const CC_AGENT_ACTIVITY_TYPES = [
  'cc_agent.skill_apply',
  'cc_agent.guard_triggered',
  'cc_agent.compression',
  'cc_agent.workspace',
  'cc_agent.skill_artifact',
  'cc_agent.uploaded_files',
  'cc_agent.script_run',
  'cc_agent.permission_decision',
] as const

export function createCcActivityRenderers(): VueActivityMessageRenderer<any>[] {
  return [
    createA2UIMessageRenderer({ theme: {} }),
    {
      activityType: 'cc_agent.skill_apply',
      content: z.any(),
      render: SkillActivityCard as any,
    },
    {
      activityType: 'cc_agent.guard_triggered',
      content: z.any(),
      render: ActivityCard as any,
    },
    {
      activityType: 'cc_agent.compression',
      content: z.any(),
      render: CompressionActivityCard as any,
    },
    {
      activityType: 'cc_agent.workspace',
      content: z.any(),
      render: WorkspaceActivityCard as any,
    },
    {
      activityType: 'cc_agent.skill_artifact',
      content: z.any(),
      render: WorkspaceActivityCard as any,
    },
    {
      activityType: 'cc_agent.uploaded_files',
      content: z.any(),
      render: UploadedFilesActivityCard as any,
    },
    {
      activityType: 'cc_agent.script_run',
      content: z.any(),
      render: ScriptActivityCard as any,
    },
    {
      activityType: 'cc_agent.permission_decision',
      content: z.any(),
      render: PermissionActivityCard as any,
    },
  ]
}
