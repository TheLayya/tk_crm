import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import router from './router'
import App from './App.vue'
import permission from './directives/permission'
import './styles/op-account-design.css'
import './styles/responsive.css'
import './styles/table-layout.css'
import './styles/workspace.css'
import CrmTable from './components/CrmTable.vue'

const app = createApp(App)
app.use(createPinia())
app.use(ElementPlus, { locale: zhCn })
app.use(router)
app.directive('permission', permission)
app.component('CrmTable', CrmTable)
app.mount('#app')
