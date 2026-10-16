<template>
  <el-dialog :model-value="modelValue" :title="title" width="min(680px, 94vw)" :close-on-click-modal="!locked" :close-on-press-escape="!locked" :show-close="!locked" :before-close="beforeClose" @update:model-value="updateVisible" @closed="onClosed">
    <p v-if="targetLabel" class="failure-target">{{ targetLabel }}</p>
    <p class="failure-hint">请至少添加一张失败截图；说明可选，方便团队核实和联系上游售后。</p>
    <el-alert v-if="error || localError" class="failure-error" :title="error || localError" type="error" :closable="false" />
    <div @paste="onPaste">
      <el-input v-model="remark" aria-label="失败说明" type="textarea" :rows="4" maxlength="2000" show-word-limit :disabled="locked" placeholder="失败说明（选填），例如：兑换报错、上游回复或售后处理进度" />
      <div class="failure-paste-area" tabindex="0" role="group" aria-label="粘贴失败截图" @paste.stop="onPaste">
        <strong>Ctrl + V 粘贴截图</strong><span>也可上传多张 PNG、JPEG、WebP 图片；最多 5 张，单张 3 MiB，合计 10 MiB</span>
        <el-button size="small" :disabled="locked" @click="fileInput?.click()">选择截图</el-button>
        <input ref="fileInput" class="failure-file-input" aria-label="上传失败截图" type="file" multiple accept="image/png,image/jpeg,image/webp" :disabled="locked" @change="onFiles" />
      </div>
    </div>
    <div v-if="screenshots.length" class="failure-previews">
      <figure v-for="(shot, index) in screenshots" :key="shot.preview"><img :src="shot.preview" :alt="shot.name" /><figcaption><span :title="shot.name">{{ shot.name }}</span><el-button link type="danger" :disabled="locked" :aria-label="`移除截图 ${index + 1}`" @click="remove(index)">移除</el-button></figcaption></figure>
    </div>
    <template #footer><el-button :disabled="locked" @click="updateVisible(false)">取消</el-button><el-button type="primary" :loading="locked" :disabled="locked" @click="submit">保存失败记录</el-button></template>
  </el-dialog>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({ modelValue: Boolean, title: { type: String, default: '报告失败' }, targetLabel: { type: String, default: '' }, busy: Boolean, error: { type: String, default: '' } })
const emit = defineEmits(['update:modelValue', 'submit'])
const remark = ref('')
const screenshots = ref([])
const fileInput = ref(null)
const reading = ref(false)
const localError = ref('')
const locked = computed(() => props.busy || reading.value)
const allowedTypes = ['image/png', 'image/jpeg', 'image/webp']
let generation = 0
const clear = () => { generation++; screenshots.value.forEach(shot => URL.revokeObjectURL(shot.preview)); screenshots.value = []; remark.value = ''; localError.value = ''; reading.value = false; if (fileInput.value) fileInput.value.value = '' }
const updateVisible = visible => { if (!visible && locked.value) return; emit('update:modelValue', visible) }
const beforeClose = done => { if (!locked.value) { emit('update:modelValue', false); done() } }
const onClosed = () => { if (!props.modelValue) clear() }
const readFile = file => new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.onerror = () => reject(new Error('截图读取失败，请重新选择')); reader.readAsDataURL(file) })
const addFiles = async files => {
  if (locked.value) return
  localError.value = ''
  const candidates = Array.from(files)
  if (!candidates.length) return
  if (screenshots.value.length + candidates.length > 5) { localError.value = '最多添加 5 张截图，请先移除多余图片'; return }
  if (candidates.some(file => !allowedTypes.includes(file.type))) { localError.value = '请选择 PNG、JPEG 或 WebP 图片'; return }
  if (candidates.some(file => file.size > 3 * 1024 * 1024)) { localError.value = '单张截图最多 3 MiB，请缩小图片后重新添加'; return }
  if (screenshots.value.reduce((sum, shot) => sum + shot.size, 0) + candidates.reduce((sum, file) => sum + file.size, 0) > 10 * 1024 * 1024) { localError.value = '截图合计最多 10 MiB，请移除部分图片'; return }
  const version = generation
  reading.value = true
  try {
    const encoded = await Promise.all(candidates.map(readFile))
    const items = candidates.map((file, index) => ({ name: file.name || `截图-${screenshots.value.length + index + 1}.png`, content_type: file.type, data: encoded[index], size: file.size, preview: URL.createObjectURL(file) }))
    if (version === generation && props.modelValue) screenshots.value.push(...items)
    else items.forEach(shot => URL.revokeObjectURL(shot.preview))
  } catch (error) { if (version === generation) localError.value = error.message || '截图读取失败，请重新选择' }
  finally { if (version === generation) reading.value = false }
}
const onFiles = event => { addFiles(event.target.files); event.target.value = '' }
const onPaste = event => {
  const files = Array.from(event.clipboardData?.items || []).filter(item => item.kind === 'file' && item.type.startsWith('image/')).map(item => item.getAsFile()).filter(Boolean)
  if (files.length) { event.preventDefault(); addFiles(files) }
}
const remove = index => { if (locked.value) return; URL.revokeObjectURL(screenshots.value[index].preview); screenshots.value.splice(index, 1); localError.value = '' }
const submit = () => {
  if (locked.value) return
  if (!screenshots.value.length) { localError.value = '请至少添加一张失败截图'; return }
  localError.value = ''
  emit('submit', { remark: remark.value.trim(), screenshots: screenshots.value.map(({ name, content_type, data }) => ({ name, content_type, data })) })
}
watch(() => props.modelValue, visible => { if (visible) clear() })
onBeforeUnmount(clear)
</script>

<style scoped>
.failure-target { margin-top:0; color:#203047; overflow-wrap:anywhere; font-weight:600; }
.failure-hint,.failure-paste-area span { color:#64748b; font-size:12px; line-height:1.6; }
.failure-error { margin-bottom:12px; }
.failure-paste-area { display:flex; flex-direction:column; align-items:center; gap:8px; margin-top:14px; padding:20px 12px; border:1px dashed #a8bbd3; border-radius:8px; background:#f8fafc; text-align:center; }
.failure-paste-area:focus-visible { outline:2px solid var(--el-color-primary); outline-offset:2px; }
.failure-file-input { display:none; }
.failure-previews { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin-top:14px; }
.failure-previews figure { margin:0; overflow:hidden; border:1px solid #e2e8f0; border-radius:6px; }
.failure-previews img { display:block; width:100%; height:120px; object-fit:contain; background:#f1f5f9; }
.failure-previews figcaption { display:flex; align-items:center; gap:6px; padding:4px 8px; }
.failure-previews figcaption span { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:12px; color:#64748b; }
@media(max-width:600px) { .failure-previews { grid-template-columns:repeat(2,minmax(0,1fr)); } }
</style>
