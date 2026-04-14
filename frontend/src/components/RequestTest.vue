<template>
  <div class="request-test">
    <h3>Axios 配置测试</h3>
    <el-space direction="vertical">
      <el-button @click="testSuccess">测试成功请求</el-button>
      <el-button @click="test404">测试 404 错误</el-button>
      <el-button @click="test409">测试 409 冲突</el-button>
      <el-button @click="test422">测试 422 验证错误</el-button>
      <el-button @click="test500">测试 500 服务器错误</el-button>
      <el-button @click="testNetwork">测试网络错误</el-button>
    </el-space>
  </div>
</template>

<script setup>
import request from '../api/request'

const testSuccess = async () => {
  try {
    const data = await request.get('/projects')
    console.log('成功响应:', data)
  } catch (error) {
    console.error('请求失败:', error)
  }
}

const test404 = async () => {
  try {
    await request.get('/nonexistent-endpoint')
  } catch (error) {
    console.log('404 错误已捕获')
  }
}

const test409 = async () => {
  try {
    await request.post('/projects', { name: 'duplicate-name' })
  } catch (error) {
    console.log('409 错误已捕获')
  }
}

const test422 = async () => {
  try {
    await request.post('/accounts', { invalid: 'data' })
  } catch (error) {
    console.log('422 错误已捕获')
  }
}

const test500 = async () => {
  try {
    await request.get('/trigger-error')
  } catch (error) {
    console.log('500 错误已捕获')
  }
}

const testNetwork = async () => {
  try {
    await request.get('http://invalid-domain-that-does-not-exist.com/api')
  } catch (error) {
    console.log('网络错误已捕获')
  }
}
</script>

<style scoped>
.request-test {
  padding: 20px;
}
</style>
