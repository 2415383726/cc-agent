import { defaultAssistantCatalog } from './assistantCatalog'

export interface DrawerEmptyStateItem {
  title: string
  description: string
  message: string
}

export interface DrawerEmptyStateSection {
  title: string
  items: DrawerEmptyStateItem[]
}

export const drawerEmptyStateSections: DrawerEmptyStateSection[] = [
  {
    title: '常用技能',
    items: defaultAssistantCatalog.skills.map((skill) => ({
      title: skill.label,
      description: skill.description,
      message: skill.name,
    })),
  },
]
