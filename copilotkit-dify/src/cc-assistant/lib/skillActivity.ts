export interface SkillActivityContent {
  skillName?: unknown
  [key: string]: unknown
}

export interface SkillActivityViewModel {
  name: string
  status: string
  label: string
}

export function skillActivityViewModel(content: SkillActivityContent | null | undefined): SkillActivityViewModel {
  const rawName = typeof content?.skillName === 'string' ? content.skillName.trim() : ''
  const name = rawName || 'skill'
  const status = '已启用'

  return {
    name,
    status,
    label: `${status} skill: ${name}`,
  }
}
