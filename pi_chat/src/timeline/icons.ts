/*
 * 内联产品图标。SVG path 数据逐字取自上游 ui-primitives icons/artwork.ts
 * （MIT，`regular` 描边 ICON_REGULAR_STROKE = 1，viewBox 0 0 16 16，
 * fill=none、stroke=currentColor）。上游通过 icon sprite 引用；此处改为
 * 内联常量以避免引入 sprite 装配层（取材黑名单），glyph 数据未改写。
 */

function stroke1(svg: string): string {
  return svg.replace(/\$\{strokeWidth\}/g, '1')
}

const COPY_OUTLINE = stroke1(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke-width="${strokeWidth}"><rect x="1.52075" y="4.07373" width="10.3932" height="10.3932" rx="2" stroke="currentColor"></rect><path d="M11.9792 1.53296C13.36 1.53296 14.4792 2.65225 14.4792 4.03296V9.42847C14.4792 10.3756 13.9521 11.1987 13.1755 11.6228V10.3298C13.3652 10.0787 13.4792 9.7674 13.4792 9.42847V4.03296C13.4792 3.20453 12.8077 2.53296 11.9792 2.53296H6.58374C6.27966 2.53301 5.99684 2.6235 5.7605 2.77905H4.42358C4.85652 2.03463 5.66056 1.53304 6.58374 1.53296H11.9792Z" fill="currentColor"></path></svg>',
)

const CHECK_OUTLINE = stroke1(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke-width="${strokeWidth}"><path d="M2.25 8.5L5.49732 11.7473C5.90519 12.1552 6.57263 12.1344 6.95426 11.7018L13.75 4" stroke="currentColor"></path></svg>',
)

const THINK_OUTLINE = stroke1(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke-width="${strokeWidth}"><path d="M10.2854 5.71481C12.9673 8.39663 14.1182 11.5938 12.8562 12.8559C11.5942 14.1179 8.39706 12.9669 5.71518 10.2851C3.03333 7.60323 1.88236 4.40608 3.14441 3.14403C4.40644 1.882 7.6036 3.03297 10.2854 5.71481Z" stroke="currentColor"></path><path d="M10.2854 10.2851C7.6036 12.9669 4.40644 14.1179 3.14441 12.8559C1.88236 11.5938 3.03333 8.39663 5.71518 5.71481C8.39706 3.03297 11.5942 1.882 12.8562 3.14403C14.1182 4.40608 12.9673 7.60323 10.2854 10.2851Z" stroke="currentColor"></path><path d="M8.86291 8.0002C8.86291 8.47549 8.47762 8.86087 8.00224 8.86087C7.52694 8.86087 7.1416 8.47549 7.1416 8.0002C7.1416 7.52485 7.52694 7.13953 8.00224 7.13953C8.47762 7.13953 8.86291 7.52485 8.86291 8.0002Z" fill="currentColor"></path></svg>',
)

const CHEVRON_DOWN_OUTLINE = stroke1(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke-width="${strokeWidth}"><path d="M4 6L7.29289 9.29289C7.68342 9.68342 8.31658 9.68342 8.70711 9.29289L12 6" stroke="currentColor"></path></svg>',
)

const CHEVRON_UP_OUTLINE = stroke1(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke-width="${strokeWidth}"><path d="M12 10L8.70711 6.70711C8.31658 6.31658 7.68342 6.31658 7.29289 6.70711L4 10" stroke="currentColor"></path></svg>',
)

const CHEVRON_LEFT_OUTLINE = stroke1(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke-width="${strokeWidth}"><path d="M10 4L6.70711 7.29289C6.31658 7.68342 6.31658 8.31658 6.70711 8.70711L10 12" stroke="currentColor"></path></svg>',
)

const CHEVRON_RIGHT_OUTLINE = stroke1(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke-width="${strokeWidth}"><path d="M6 12L9.29289 8.70711C9.68342 8.31658 9.68342 7.68342 9.29289 7.29289L6 4" stroke="currentColor"></path></svg>',
)

const CLOSE_OUTLINE = stroke1(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke-width="${strokeWidth}"><path d="M2.5 2.5L13.5 13.5" stroke="currentColor"></path><path d="M13.5 2.5L2.5 13.5" stroke="currentColor"></path></svg>',
)

/* 工具变体图标（票据 04）：api（命令行）、browse（读取）、search、sparkle（通用工具）、
   skill（加载技能）、edit（写入/编辑）。path 数据逐字取自上游 artwork.ts。 */
const API_OUTLINE = stroke1(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke-width="${strokeWidth}"><path d="M3 4L7 8L3 12" stroke="currentColor"></path><path d="M9 12H13" stroke="currentColor"></path></svg>',
)

const BROWSE_OUTLINE = stroke1(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke-width="${strokeWidth}"><path d="M4.9375 5.90295H11.0625" stroke="currentColor"></path><path d="M4.9375 9.02991H8.27841" stroke="currentColor"></path><path d="M12.5 1.32617C13.3039 1.32617 14 1.95171 14 2.77637V13.2246C13.9996 14.0489 13.3036 14.6738 12.5 14.6738H3.5C2.69637 14.6738 2.00042 14.0489 2 13.2246V2.77637C2 1.95171 2.69613 1.32617 3.5 1.32617H12.5ZM3.5 2.32617C3.1993 2.32617 3 2.55186 3 2.77637V13.2246C3.00044 13.4489 3.19963 13.6738 3.5 13.6738H12.5C12.8004 13.6738 12.9996 13.4489 13 13.2246V2.77637C13 2.55186 12.8007 2.32617 12.5 2.32617H3.5Z" fill="currentColor"></path></svg>',
)

const SEARCH_OUTLINE = stroke1(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke-width="${strokeWidth}"><path d="M6.58727 11.8586C9.55061 11.8586 11.9529 9.45637 11.9529 6.49304C11.9529 3.5297 9.55061 1.12744 6.58727 1.12744C3.62394 1.12744 1.22168 3.5297 1.22168 6.49304C1.22168 9.45637 3.62394 11.8586 6.58727 11.8586Z" stroke="currentColor"></path><path d="M10.2991 10.3933L14.7783 14.8725" stroke="currentColor"></path></svg>',
)

const SPARKLE_REGULAR = stroke1(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke-width="${strokeWidth}"><path d="M5.875 3C5.875 6.33333 7.54167 8 10.875 8C7.54167 8 5.875 9.66667 5.875 13C5.875 9.66667 4.20833 8 0.875 8C4.20833 8 5.875 6.33333 5.875 3Z" stroke="currentColor"></path><path d="M12.375 1.55823C12.375 3.39156 13.2917 4.30823 15.125 4.30823C13.2917 4.30823 12.375 5.22489 12.375 7.05823C12.375 5.22489 11.4583 4.30823 9.625 4.30823C11.4583 4.30823 12.375 3.39156 12.375 1.55823Z" stroke="currentColor"></path><path d="M12.375 10.4418C12.375 11.7751 13.0417 12.4418 14.375 12.4418C13.0417 12.4418 12.375 13.1084 12.375 14.4418C12.375 13.1084 11.7083 12.4418 10.375 12.4418C11.7083 12.4418 12.375 11.7751 12.375 10.4418Z" stroke="currentColor"></path></svg>',
)

const SKILL_OUTLINE = stroke1(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 17 17" fill="none" stroke-width="${strokeWidth}"><path d="M4.57788 5.77124H10.7029" stroke="currentColor"></path><path d="M4.57788 8.89819H7.91879" stroke="currentColor"></path><path d="M12.1404 1.19446C12.9442 1.19446 13.6404 1.81999 13.6404 2.64465V8.89856H12.6404V2.64465C12.6404 2.42015 12.4411 2.19446 12.1404 2.19446H3.14038C2.83968 2.19446 2.64038 2.42015 2.64038 2.64465V13.0929C2.64082 13.3172 2.84001 13.5421 3.14038 13.5421H8.88159V14.5421H3.14038C2.33675 14.5421 1.6408 13.9172 1.64038 13.0929V2.64465C1.64038 1.81999 2.33651 1.19446 3.14038 1.19446H12.1404Z" fill="currentColor"></path><path d="M12.0051 15.1056C12.0051 13.6395 10.8166 12.451 9.35059 12.451C10.8166 12.451 12.0051 11.2626 12.0051 9.79651C12.0051 11.2626 13.1936 12.451 14.6597 12.451C13.1936 12.451 12.0051 13.6395 12.0051 15.1056Z" stroke="currentColor"></path></svg>',
)

const EDIT_OUTLINE = stroke1(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke-width="${strokeWidth}"><path d="M8.85596 2.69971H4.19971C3.37141 2.69971 2.69992 3.37146 2.69971 4.19971V11.8003C2.69992 12.6285 3.37141 13.3003 4.19971 13.3003H11.8003C12.6283 13.2999 13.3001 12.6283 13.3003 11.8003V7.89893H14.3003V11.8003C14.3001 13.1806 13.1806 14.2999 11.8003 14.3003H4.19971C2.81913 14.3003 1.69992 13.1808 1.69971 11.8003V4.19971C1.69992 2.81918 2.81913 1.69971 4.19971 1.69971H8.85596V2.69971Z" fill="currentColor"></path><path d="M7.7849 8.23878L13.888 2.13574" stroke="currentColor"></path></svg>',
)

const CODE_OUTLINE = stroke1(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke-width="${strokeWidth}"><path d="M6.27612 1.5L4.52612 14.5" stroke="currentColor"></path><path d="M11.4739 1.5L9.72388 14.5" stroke="currentColor"></path><path d="M2.39868 5.5H14.0681" stroke="currentColor"></path><path d="M1.93188 10.5H13.6013" stroke="currentColor"></path></svg>',
)

/* 侧栏折叠开关与新会话（上游 SidebarRoot 用），path 逐字取自 artwork.ts。
   new-chat 的 medium 变体（1.3px 描边）由 NEW_CHAT_MEDIUM 单独固化。 */
const PANEL_LEFT_OUTLINE = stroke1(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke-width="${strokeWidth}"><path d="M13.5 1.5H2.5C1.94772 1.5 1.5 1.94772 1.5 2.5V13.5C1.5 14.0523 1.94772 14.5 2.5 14.5H13.5C14.0523 14.5 14.5 14.0523 14.5 13.5V2.5C14.5 1.94772 14.0523 1.5 13.5 1.5Z" stroke="currentColor"></path><path d="M5.5 1.5V14.5" stroke="currentColor"></path></svg>',
)

const NEW_CHAT_OUTLINE = stroke1(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke-width="${strokeWidth}"><path d="M2.37091 11.2501C1.58745 9.89288 1.32067 8.29835 1.61969 6.76006C1.91872 5.22177 2.76342 3.8433 3.99826 2.87846C5.2331 1.91362 6.77494 1.42737 8.33988 1.50925C9.90482 1.59113 11.3875 2.23562 12.5149 3.32406C13.6425 4.41269 14.3387 5.87206 14.4754 7.4334C14.612 8.99474 14.18 10.5529 13.2587 11.8209C12.3375 13.0888 10.9891 13.9813 9.46194 14.3337C8.18691 14.628 6.85895 14.5294 5.64989 14.0605C5.1712 13.8748 4.76962 13.4932 4.26534 13.3967C3.67413 13.2835 2.95257 13.5598 2.03794 14.3337" stroke="currentColor"></path><path d="M8 5V11" stroke="currentColor"></path><path d="M5 8H11" stroke="currentColor"></path></svg>',
)

const NEW_CHAT_MEDIUM = NEW_CHAT_OUTLINE.replace('stroke-width="1"', 'stroke-width="1.3"')
/** 上游 RunningWhaleTail.tsx 的 REST_PATH（静止鲸尾轮廓，动画帧不随行）。 */
const WHALE_TAIL_REST_PATH =
  'M8.844 13.742C8.967 12.328 8.45 10.4 8.45 9.65C8.45 8.94 8.88 8.43 9.6 8.43C11.285 8.43 12.106 8.281 12.685 8.104C13.71 7.791 14.585 6.768 15.055 5.945C15.137 5.803 14.99 5.641 14.829 5.671C13.829 5.86 12.828 5.376 11.827 4.978C10.659 4.514 9.491 4.707 8.935 4.876C8.805 4.915 8.658 4.819 8.636 4.686C8.468 3.643 7.405 2.615 5.498 2.238C4.54 2.048 3.748 1.574 3.347 1.202C3.252 1.113 3.088 1.125 3.03 1.242C2.628 2.059 2.168 3.82 5.248 6.115C5.82 6.494 6.31 6.785 6.574 7.637C6.72 8.104 6.157 9.168 6.061 9.368C5.157 11.27 5.089 12.19 4.926 13.742'

export function iconSvg(
  name:
    | 'copy'
    | 'check'
    | 'think'
    | 'chevron-down'
    | 'chevron-up'
    | 'chevron-left'
    | 'chevron-right'
    | 'close'
    | 'api'
    | 'browse'
    | 'search'
    | 'sparkle'
    | 'skill'
    | 'edit'
    | 'code'
    | 'panel-left'
    | 'new-chat'
    | 'new-chat-medium',
  /** 显式尺寸（像素）。上游 productIcon 组件总是输出 width/height；依赖
      CSS 定尺寸的 timeline 行不传（行为不变），问卷卡等依赖 glyph 固有
      尺寸的场景传入（上游默认：chevron 14，close/edit 16，check 12）。 */
  size?: number,
): string {
  const svg = (() => {
    switch (name) {
      case 'copy': return COPY_OUTLINE
      case 'check': return CHECK_OUTLINE
      case 'think': return THINK_OUTLINE
      case 'chevron-down': return CHEVRON_DOWN_OUTLINE
      case 'chevron-up': return CHEVRON_UP_OUTLINE
      case 'chevron-left': return CHEVRON_LEFT_OUTLINE
      case 'chevron-right': return CHEVRON_RIGHT_OUTLINE
      case 'close': return CLOSE_OUTLINE
      case 'api': return API_OUTLINE
      case 'browse': return BROWSE_OUTLINE
      case 'search': return SEARCH_OUTLINE
      case 'sparkle': return SPARKLE_REGULAR
      case 'skill': return SKILL_OUTLINE
      case 'edit': return EDIT_OUTLINE
      case 'code': return CODE_OUTLINE
      case 'panel-left': return PANEL_LEFT_OUTLINE
      case 'new-chat': return NEW_CHAT_OUTLINE
      case 'new-chat-medium': return NEW_CHAT_MEDIUM
    }
  })()
  if (size === undefined) return svg
  return svg.replace('<svg ', `<svg width="${size}" height="${size}" `)
}

export function whaleTailSvg(): string {
  return `<svg width="100%" height="100%" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="${WHALE_TAIL_REST_PATH}" stroke="currentColor" stroke-width="1"/></svg>`
}
