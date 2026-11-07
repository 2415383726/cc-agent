import { createApp } from 'vue'
import App from './App.vue'
/* 令牌基座先行：vendored ui-theme（令牌/字体/滚动条/焦点环），随后挂载默认。 */
import './vendor/dsh/theme.css'
import './styles/base.css'

createApp(App).mount('#app')
