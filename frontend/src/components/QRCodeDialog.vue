<template>
  <el-dialog
    v-model="dialogVisible"
    :title="title || '二维码'"
    width="min(90vw, 400px)"
    destroy-on-close
    @closed="clearCanvas"
  >
    <div class="qr-dialog-body">
      <div class="qr-canvas-wrap">
        <canvas ref="canvasRef" class="qr-canvas" />
      </div>
      <el-input
        :model-value="uri"
        type="textarea"
        :rows="3"
        readonly
        class="qr-uri"
      />
      <el-button type="primary" class="copy-button" @click="copyUri">
        复制 URI
      </el-button>
    </div>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import QRCode from 'qrcode'

const props = defineProps({
  visible: { type: Boolean, default: false },
  uri: { type: String, default: '' },
  title: { type: String, default: '二维码' }
})

const emit = defineEmits(['update:visible'])

const canvasRef = ref(null)

// v-model 双向契约：关闭按钮与父状态同步
const dialogVisible = computed({
  get: () => props.visible,
  set: (value) => emit('update:visible', value)
})

function clearCanvas() {
  const canvas = canvasRef.value
  if (!canvas) return
  const context = canvas.getContext('2d')
  context?.clearRect(0, 0, canvas.width, canvas.height)
}

async function renderQRCode() {
  if (!props.visible || !props.uri) {
    clearCanvas()
    return
  }

  await nextTick()
  const canvas = canvasRef.value
  if (!canvas) return

  clearCanvas()
  try {
    await QRCode.toCanvas(canvas, props.uri, {
      errorCorrectionLevel: 'M',
      margin: 2,
      width: 260
    })
  } catch {
    clearCanvas()
    ElMessage.error('二维码生成失败')
  }
}

async function copyUri() {
  if (!props.uri) return
  try {
    await navigator.clipboard.writeText(props.uri)
    ElMessage.success('URI 已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}

watch(() => [props.visible, props.uri], renderQRCode, { immediate: true })
</script>

<style scoped>
.qr-dialog-body {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 14px;
}

.qr-canvas-wrap {
  display: flex;
  justify-content: center;
}

.qr-canvas {
  width: 260px;
  height: 260px;
  max-width: 100%;
}

.qr-uri {
  width: 100%;
}

.copy-button {
  width: 100%;
}
</style>
