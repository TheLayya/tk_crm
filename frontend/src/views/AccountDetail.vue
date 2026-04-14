<template>
  <div class="account-detail">
    <el-page-header @back="goBack" title="返回">
      <template #content>
        <span class="page-title">账号详情</span>
      </template>
    </el-page-header>

    <div v-loading="loading" class="content">
      <!-- Account Info Card -->
      <el-card class="info-card">
        <template #header>
          <div class="card-header">
            <span>基本信息</span>
            <el-button type="primary" size="small" @click="handleCheck">
              <el-icon><Refresh /></el-icon>
              立即检查
            </el-button>
          </div>
        </template>
        
        <el-descriptions :column="3" border v-if="account">
          <el-descriptions-item label="用户名">{{ account.username }}</el-descriptions-item>
          <el-descriptions-item label="昵称">{{ account.nickname || '-' }}</el-descriptions-item>
          <el-descriptions-item label="所属项目">{{ account.project_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="粉丝数">{{ formatNumber(account.follower_count) }}</el-descriptions-item>
          <el-descriptions-item label="点赞数">{{ formatNumber(account.like_count) }}</el-descriptions-item>
          <el-descriptions-item label="视频数">{{ formatNumber(account.video_count) }}</el-descriptions-item>
          <el-descriptions-item label="关注数">{{ formatNumber(account.following_count) }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="account.is_active ? 'success' : 'info'">
              {{ account.is_active ? '激活' : '禁用' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="最后检查">
            {{ formatDate(account.last_checked_at) }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- Trend Chart Card -->
      <el-card class="chart-card">
        <template #header>
          <div class="card-header">
            <span>数据趋势</span>
            <el-radio-group v-model="chartMetric" size="small">
              <el-radio-button value="followers">粉丝数</el-radio-button>
              <el-radio-button value="following">关注数</el-radio-button>
              <el-radio-button value="likes">点赞数</el-radio-button>
              <el-radio-button value="videos">视频数</el-radio-button>
            </el-radio-group>
          </div>
        </template>
        
        <div ref="chartRef" class="chart-container"></div>
      </el-card>

      <!-- History Table Card -->
      <el-card class="history-card">
        <template #header>
          <span>历史记录</span>
        </template>
        
        <el-table :data="history" max-height="400">
          <el-table-column prop="checked_at" label="检查时间" width="180">
            <template #default="{ row }">
              {{ formatDate(row.checked_at) }}
            </template>
          </el-table-column>
          <el-table-column prop="follower_count" label="粉丝数" width="120">
            <template #default="{ row }">
              {{ formatNumber(row.follower_count) }}
            </template>
          </el-table-column>
          <el-table-column prop="like_count" label="点赞数" width="120">
            <template #default="{ row }">
              {{ formatNumber(row.like_count) }}
            </template>
          </el-table-column>
          <el-table-column prop="video_count" label="视频数" width="100">
            <template #default="{ row }">
              {{ formatNumber(row.video_count) }}
            </template>
          </el-table-column>
          <el-table-column prop="following_count" label="关注数" width="100">
            <template #default="{ row }">
              {{ formatNumber(row.following_count) }}
            </template>
          </el-table-column>
          <el-table-column prop="check_status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.check_status === 'success' ? 'success' : 'danger'" size="small">
                {{ row.check_status === 'success' ? '成功' : '失败' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="error_message" label="错误信息" />
        </el-table>
      </el-card>

      <!-- Videos Card (if video monitoring enabled) -->
      <el-card class="videos-card" v-if="account && account.enable_video_monitoring">
        <template #header>
          <div class="card-header">
            <div class="video-info">
              <span>已记录视频：{{ videoTotal }} 个</span>
            </div>
            <el-button type="primary" size="small" @click="handleCheck">
              <el-icon><Refresh /></el-icon>
              立即检查视频
            </el-button>
          </div>
        </template>
        
        <el-table :data="videos" max-height="600">
          <el-table-column label="封面" width="120">
            <template #default="{ row }">
              <el-image
                v-if="row.cover_url"
                :src="row.cover_url + '&t=' + (row.imageRetryKey || 0)"
                fit="cover"
                style="width: 80px; height: 100px; border-radius: 4px"
                :preview-teleported="false"
                preview-disabled
              >
                <template #error>
                  <div style="width: 80px; height: 100px; background: #f5f7fa; border-radius: 4px; display: flex; align-items: center; justify-content: center; flex-direction: column; font-size: 10px; color: #909399; padding: 5px">
                    <el-icon :size="20" color="#909399"><Picture /></el-icon>
                    <span style="margin-top: 3px; text-align: center">加载失败</span>
                    <el-button 
                      size="small" 
                      type="primary" 
                      link
                      style="margin-top: 3px; font-size: 10px; padding: 0"
                      @click.stop="retryLoadImage(row)"
                    >
                      <el-icon :size="12"><Refresh /></el-icon>
                      重试
                    </el-button>
                  </div>
                </template>
              </el-image>
              <div v-else style="width: 80px; height: 100px; background: #f5f7fa; border-radius: 4px; display: flex; align-items: center; justify-content: center">
                <el-icon :size="30" color="#909399"><VideoCamera /></el-icon>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="video_id" label="视频ID" width="150" />
          <el-table-column prop="title" label="短题" show-overflow-tooltip min-width="200" />
          <el-table-column prop="published_at" label="发布时间" width="180">
            <template #default="{ row }">
              {{ formatPublishDate(row.published_at) }}
            </template>
          </el-table-column>
          <el-table-column prop="play_count" label="播放数" width="120">
            <template #default="{ row }">
              {{ formatNumber(row.play_count) }}
            </template>
          </el-table-column>
          <el-table-column prop="like_count" label="点赞数" width="120">
            <template #default="{ row }">
              {{ formatNumber(row.like_count) }}
            </template>
          </el-table-column>
          <el-table-column prop="comment_count" label="评论数" width="120">
            <template #default="{ row }">
              {{ formatNumber(row.comment_count) }}
            </template>
          </el-table-column>
          <el-table-column prop="share_count" label="分享数" width="120">
            <template #default="{ row }">
              {{ formatNumber(row.share_count) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="viewVideo(row)">
                <el-icon><Link /></el-icon>
                查看
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        
        <div class="pagination">
          <el-pagination
            v-model:current-page="videoPage"
            v-model:page-size="videoPageSize"
            :total="videoTotal"
            layout="total, prev, pager, next"
            @current-change="loadVideos"
          />
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh, Picture, VideoCamera, Link } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { getAccount, triggerCheck } from '@/api/accounts'
import { getAccountHistory } from '@/api/history'
import { getAccountVideos } from '@/api/videos'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const account = ref(null)
const history = ref([])
const videos = ref([])
const videoPage = ref(1)
const videoPageSize = ref(20)
const videoTotal = ref(0)
const chartRef = ref(null)
const chartInstance = ref(null)
const chartMetric = ref('followers')

const formatNumber = (num) => {
  if (num == null) return '-'
  return num.toLocaleString()
}

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  // 后端存储 UTC 时间，加 Z 转为本地时间显示
  const s = dateStr.endsWith('Z') ? dateStr : dateStr + 'Z'
  return new Date(s).toLocaleString('zh-CN')
}

// 视频发布时间：TikTok 时间戳已含时区，直接显示不做转换
const formatPublishDate = (dateStr) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

const goBack = () => {
  router.back()
}

const loadAccount = async () => {
  loading.value = true
  try {
    const accountId = route.params.id
    account.value = await getAccount(accountId)
  } catch (error) {
    console.error('Failed to load account:', error)
    ElMessage.error('加载账号信息失败')
  } finally {
    loading.value = false
  }
}

const loadHistory = async () => {
  try {
    const accountId = route.params.id
    history.value = await getAccountHistory(accountId, {
      limit: 100
    })
    
    // Update chart after history is loaded
    await nextTick()
    updateChart()
  } catch (error) {
    console.error('Failed to load history:', error)
  }
}

const loadVideos = async () => {
  if (!account.value?.enable_video_monitoring) return
  
  try {
    const accountId = route.params.id
    const response = await getAccountVideos(accountId, {
      skip: (videoPage.value - 1) * videoPageSize.value,
      limit: videoPageSize.value
    })
    
    // Handle both old format (array) and new format (object with items/total)
    if (Array.isArray(response)) {
      videos.value = response
      videoTotal.value = response.length
    } else {
      videos.value = response.items || []
      videoTotal.value = response.total || 0
    }
  } catch (error) {
    console.error('Failed to load videos:', error)
  }
}

const handleCheck = async () => {
  try {
    const accountId = route.params.id
    await triggerCheck(accountId)
    ElMessage.success('检查任务已触发')
    
    // Reload data after a delay
    setTimeout(() => {
      loadAccount()
      loadHistory()
      loadVideos()
    }, 2000)
  } catch (error) {
    console.error('Failed to trigger check:', error)
  }
}

const retryLoadImage = (row) => {
  // 增加重试计数，强制刷新图片
  row.imageRetryKey = (row.imageRetryKey || 0) + 1
}

const viewVideo = (row) => {
  // 打开 TikTok 视频链接
  const url = `https://www.tiktok.com/@${account.value.username}/video/${row.video_id}`
  window.open(url, '_blank')
}

const initChart = () => {
  if (!chartRef.value) return
  
  chartInstance.value = echarts.init(chartRef.value)
  updateChart()
  
  // Handle window resize
  window.addEventListener('resize', () => {
    chartInstance.value?.resize()
  })
}

const updateChart = () => {
  if (!chartInstance.value || !history.value.length) return
  
  // Reverse history to show oldest to newest
  const data = [...history.value].reverse()
  
  const metricMap = {
    followers: { key: 'follower_count', name: '粉丝数' },
    following: { key: 'following_count', name: '关注数' },
    likes: { key: 'like_count', name: '点赞数' },
    videos: { key: 'video_count', name: '视频数' }
  }
  
  const metric = metricMap[chartMetric.value]
  
  const option = {
    title: {
      text: `${metric.name}趋势`,
      left: 'center'
    },
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const point = params[0]
        return `${point.name}<br/>${metric.name}: ${formatNumber(point.value)}`
      }
    },
    xAxis: {
      type: 'category',
      data: data.map(item => {
        const date = new Date(item.checked_at)
        return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`
      }),
      axisLabel: {
        rotate: 45
      }
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        formatter: (value) => {
          if (value >= 10000) {
            return (value / 10000).toFixed(1) + 'w'
          }
          return value
        }
      }
    },
    series: [
      {
        name: metric.name,
        type: 'line',
        data: data.map(item => item[metric.key]),
        smooth: true,
        itemStyle: {
          color: '#409eff'
        },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(64, 158, 255, 0.3)' },
              { offset: 1, color: 'rgba(64, 158, 255, 0.05)' }
            ]
          }
        }
      }
    ],
    grid: {
      left: '3%',
      right: '4%',
      bottom: '15%',
      containLabel: true
    }
  }
  
  chartInstance.value.setOption(option)
}

watch(chartMetric, () => {
  updateChart()
})

onMounted(async () => {
  await loadAccount()
  await loadHistory()
  await loadVideos()
  
  await nextTick()
  initChart()
})
</script>

<style scoped>
.account-detail {
  padding: 20px;
}

.page-title {
  font-size: 18px;
  font-weight: 500;
}

.content {
  margin-top: 20px;
}

.info-card,
.chart-card,
.history-card,
.videos-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.video-info {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #606266;
  font-size: 14px;
}

.chart-container {
  width: 100%;
  height: 400px;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
