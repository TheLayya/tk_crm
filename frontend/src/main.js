import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import router from './router'
import App from './App.vue'
import permission from './directives/permission'
import './styles/op-account-design.css'
import './styles/responsive.css'
import './styles/table-layout.css'
import CrmTable from './components/CrmTable.vue'

const app = createApp(App)
app.use(createPinia())
app.use(ElementPlus)
app.use(router)
app.directive('permission', permission)
app.component('CrmTable', CrmTable)
app.mount('#app')
