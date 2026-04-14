import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import router from './router'
import App from './App.vue'
import permission from './directives/permission'
import './styles/responsive.css'

const app = createApp(App)
app.use(createPinia())
app.use(ElementPlus)
app.use(router)
app.directive('permission', permission)
app.mount('#app')
