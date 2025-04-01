<template>
  <div class="strm-health-panel">
    <a-card class="health-card" :bordered="false">
      <!-- 扫描状态展示 -->
      <div class="scan-header">
        <div class="scan-title">
          <h2>STRM健康检测</h2>
          <a-alert v-if="lastScanTime" :type="isScanning ? 'warning' : 'info'" class="scan-status-alert">
            <template #message>
              <span>{{ getLastScanMessage() }}</span>
            </template>
          </a-alert>
        </div>
        <div class="scan-controls">
          <a-form layout="inline">
            <a-form-item label="扫描类型">
              <a-select
                v-model:value="scanType"
                style="width: 180px"
                :disabled="isScanning"
              >
                <a-select-option value="all">全面检测</a-select-option>
                <a-select-option value="strm_validity">STRM文件有效性检测</a-select-option>
                <a-select-option value="video_coverage">视频文件覆盖检测</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item label="扫描模式">
              <a-select
                v-model:value="scanMode"
                style="width: 150px"
                :disabled="isScanning"
              >
                <a-select-option value="full">完整扫描</a-select-option>
                <a-select-option value="incremental">增量扫描</a-select-option>
                <a-select-option value="problems_only">仅检查问题</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item>
              <a-button
                type="primary"
                :disabled="isScanning"
                @click="startScan"
              >
                开始检测
              </a-button>
            </a-form-item>
          </a-form>
        </div>
      </div>

      <!-- 统计信息展示 -->
      <div class="stats-section" v-if="stats">
        <a-row :gutter="16">
          <a-col :span="12">
            <a-statistic title="STRM文件总数" :value="stats.totalStrmFiles" />
          </a-col>
          <a-col :span="12">
            <a-statistic 
              title="无效STRM文件" 
              :value="stats.invalidStrmFiles" 
              :valueStyle="{ color: stats.invalidStrmFiles > 0 ? '#cf1322' : '#3f8600' }"
            />
          </a-col>
        </a-row>
        <a-row :gutter="16" style="margin-top: 16px;">
          <a-col :span="12">
            <a-statistic title="视频文件总数" :value="stats.totalVideoFiles" />
          </a-col>
          <a-col :span="12">
            <a-statistic 
              title="缺失STRM文件"
              :value="stats.missingStrmFiles"
              :valueStyle="{ color: stats.missingStrmFiles > 0 ? '#f5a623' : '#3f8600' }"
            />
          </a-col>
        </a-row>
      </div>
      
      <!-- 进度展示 -->
      <div v-if="isScanning" class="scan-progress">
        <a-progress :percent="scanProgress" status="active" />
        <p class="scan-status">{{ scanStatus }}</p>
      </div>
      
      <!-- 问题列表 -->
      <div class="problem-list" v-if="problems.length > 0">
        <div class="list-header">
          <h3>检测到的问题 ({{ problems.length }})</h3>
          <div class="filter-controls">
            <a-radio-group v-model:value="problemFilter" button-style="solid">
              <a-radio-button value="all">全部</a-radio-button>
              <a-radio-button value="invalid_strm">无效STRM</a-radio-button>
              <a-radio-button value="missing_strm">缺失STRM</a-radio-button>
            </a-radio-group>
          </div>
        </div>
        
        <a-list
          class="problem-list-items"
          :data-source="filteredProblems"
          :pagination="{ pageSize: 10 }"
        >
          <template #renderItem="{ item }">
            <a-list-item>
              <a-card class="problem-card" :bodyStyle="{ padding: '12px' }">
                <div class="problem-info">
                  <a-tag :color="getTagColor(item.type)">{{ getProblemTypeName(item.type) }}</a-tag>
                  <div class="problem-path">{{ item.path }}</div>
                  <div class="problem-details">{{ item.details }}</div>
                  <div class="problem-time">
                    <span>发现时间: {{ formatTime(item.discoveryTime) }}</span>
                    <span v-if="item.firstDetectedAt && item.firstDetectedAt !== item.discoveryTime">
                      首次发现: {{ formatTime(item.firstDetectedAt) }}
                    </span>
                  </div>
                </div>
                <div class="problem-actions">
                  <a-button
                    type="primary"
                    @click="repairProblem(item)"
                    :loading="repairing[item.id]"
                  >
                    {{ getRepairText(item.type) }}
                  </a-button>
                </div>
              </a-card>
            </a-list-item>
          </template>
        </a-list>
        
        <div class="batch-actions" v-if="filteredProblems.length > 0">
          <a-button
            type="primary"
            @click="repairAllProblems"
            :loading="repairingAll"
            :disabled="isScanning"
          >
            批量{{ getRepairText(problemFilter === 'all' ? '' : problemFilter) }}
          </a-button>
        </div>
      </div>
      
      <!-- 无问题状态 -->
      <div v-else-if="!isScanning && hasScanned" class="no-problems">
        <a-empty description="未检测到问题">
          <template #description>
            <span>太棒了！所有STRM文件都是有效的，并且所有视频文件都有对应的STRM文件。</span>
          </template>
        </a-empty>
      </div>

      <!-- 清空数据按钮 -->
      <div class="advanced-actions" v-if="!isScanning">
        <a-popconfirm
          title="确定要清空健康检测数据吗？这将删除所有记录的问题和状态信息。"
          @confirm="clearHealthData"
        >
          <a-button danger>清空健康数据</a-button>
        </a-popconfirm>
      </div>

      <!-- Emby刷新队列状态 -->
      <a-card v-if="embyStatus.enabled" title="Emby刷新队列" style="margin-top: 20px;" :loading="embyLoading">
        <a-statistic-countdown 
          v-if="nextRefreshTime"
          title="下次检查时间" 
          :value="nextRefreshTime" 
          format="HH:mm:ss" 
          style="margin-bottom: 16px"
        />
        
        <a-row :gutter="16">
          <a-col :span="6">
            <a-statistic
              title="总队列数"
              :value="embyStatus.queue_stats?.total || 0"
            />
          </a-col>
          <a-col :span="6">
            <a-statistic
              title="待处理"
              :value="embyStatus.queue_stats?.pending || 0"
              :value-style="{ color: '#1890ff' }"
            />
          </a-col>
          <a-col :span="6">
            <a-statistic
              title="成功"
              :value="embyStatus.queue_stats?.success || 0"
              :value-style="{ color: '#3f8600' }"
            />
          </a-col>
          <a-col :span="6">
            <a-statistic
              title="失败"
              :value="embyStatus.queue_stats?.failed || 0"
              :value-style="embyStatus.queue_stats?.failed > 0 ? { color: '#cf1322' } : {}"
            />
          </a-col>
        </a-row>
        
        <a-divider />
        
        <!-- 最近成功刷新项目 -->
        <div v-if="embyStatus.recent_success && embyStatus.recent_success.length > 0">
          <h4>最近成功刷新项目</h4>
          <a-list
            size="small"
            :data-source="embyStatus.recent_success"
          >
            <template #renderItem="{ item }">
              <a-list-item>
                <a-space>
                  <check-circle-outlined style="color: #52c41a" />
                  <span>{{ item.name }}</span>
                </a-space>
                <span>{{ item.refresh_time }}</span>
              </a-list-item>
            </template>
          </a-list>
        </div>
        
        <!-- 最近失败刷新项目 -->
        <div v-if="embyStatus.recent_failed && embyStatus.recent_failed.length > 0" style="margin-top: 16px;">
          <h4>最近失败刷新项目</h4>
          <a-list
            size="small"
            :data-source="embyStatus.recent_failed"
          >
            <template #renderItem="{ item }">
              <a-list-item>
                <a-space>
                  <warning-outlined style="color: #fa8c16" />
                  <span>{{ item.path.split('/').pop() }}</span>
                  <span style="color: #cf1322;">{{ item.error }}</span>
                </a-space>
                <span>下次尝试: {{ item.next_retry }}</span>
              </a-list-item>
            </template>
          </a-list>
        </div>
        
        <a-divider />
        
        <div style="display: flex; justify-content: center;">
          <a-button 
            type="primary" 
            @click="refreshEmbyStatus" 
            :loading="embyLoading"
          >
            刷新状态
          </a-button>
        </div>
      </a-card>
    </a-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { message } from 'ant-design-vue'
import { 
  CheckCircleOutlined, 
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  WarningOutlined,
  QuestionCircleOutlined
} from '@ant-design/icons-vue'

// 扫描参数
const scanType = ref('all')
const scanMode = ref('full')

// 扫描状态
const isScanning = ref(false)
const scanProgress = ref(0)
const scanStatus = ref('')
const lastScanTime = ref(null)
const lastScanTimeStr = ref('')
const hasScanned = ref(false)
const stats = ref(null)

// 问题相关
const problems = ref([])
const problemFilter = ref('all')
const repairing = ref({})
const repairingAll = ref(false)

// 计算筛选后的问题列表
const filteredProblems = computed(() => {
  if (problemFilter.value === 'all') {
    return problems.value
  }
  return problems.value.filter(problem => problem.type === problemFilter.value)
})

// 初始化：获取状态和问题列表
onMounted(async () => {
  await getStatus()
  await getProblems()
  await refreshEmbyStatus()
})

// 获取扫描状态
const getStatus = async () => {
  try {
    const response = await fetch('/api/health/status')
    const data = await response.json()
    
    isScanning.value = data.isScanning
    scanProgress.value = data.progress
    scanStatus.value = data.status
    lastScanTime.value = data.lastScanTime
    lastScanTimeStr.value = data.lastScanTimeStr
    scanType.value = data.scanType || 'all'
    scanMode.value = data.scanMode || 'full'
    
    // 更新统计信息
    stats.value = data.stats || null
    
    if (data.lastScanTime) {
      hasScanned.value = true
    }
    
    // 如果正在扫描，每5秒更新一次状态
    if (data.isScanning) {
      setTimeout(getStatus, 2000)
    }
  } catch (error) {
    console.error('获取扫描状态失败:', error)
  }
}

// 获取问题列表
const getProblems = async () => {
  try {
    const response = await fetch(`/api/health/problems?type=${problemFilter.value === 'all' ? '' : problemFilter.value}`)
    const data = await response.json()
    
    problems.value = data.problems || []
    
    // 如果获取了新的统计信息，更新它
    if (data.stats) {
      stats.value = data.stats
    }
  } catch (error) {
    console.error('获取问题列表失败:', error)
  }
}

// 开始扫描
const startScan = async () => {
  try {
    isScanning.value = true
    scanProgress.value = 0
    scanStatus.value = '正在初始化扫描...'
    
    const response = await fetch('/api/health/start', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        type: scanType.value,
        mode: scanMode.value
      })
    })
    
    const data = await response.json()
    
    if (data.status === 'scanning') {
      message.success('已开始健康扫描')
      getStatus()
      
      // 定时检查扫描是否完成
      checkScanCompleted()
    } else {
      message.error('启动扫描失败')
      isScanning.value = false
    }
  } catch (error) {
    console.error('启动扫描失败:', error)
    message.error('启动扫描失败: ' + error.message)
    isScanning.value = false
  }
}

// 定时检查扫描是否完成
const checkScanCompleted = () => {
  setTimeout(async () => {
    if (isScanning.value) {
      await getStatus()
      if (isScanning.value) {
        checkScanCompleted()
      } else {
        // 扫描完成后，获取问题列表
        await getProblems()
        message.success('扫描完成')
      }
    }
  }, 2000)
}

// 修复单个问题
const repairProblem = async (problem) => {
  try {
    repairing.value[problem.id] = true
    
    const endpoint = problem.type === 'invalid_strm' ? 'repair/invalid_strm' : 'repair/missing_strm'
    
    const response = await fetch(`/api/health/${endpoint}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        paths: [problem.path],
        type: problem.type
      })
    })
    
    const data = await response.json()
    
    if (data.success) {
      message.success(data.message)
      
      // 从列表中移除已修复的问题
      problems.value = problems.value.filter(p => p.id !== problem.id)
      
      // 获取最新状态和统计信息
      await getStatus()
    } else {
      message.error(data.message || '修复失败')
    }
  } catch (error) {
    console.error('修复问题失败:', error)
    message.error('修复失败: ' + error.message)
  } finally {
    repairing.value[problem.id] = false
  }
}

// 批量修复问题
const repairAllProblems = async () => {
  if (filteredProblems.value.length === 0) return
  
  try {
    repairingAll.value = true
    
    // 按类型分组问题
    const invalidStrm = filteredProblems.value.filter(p => p.type === 'invalid_strm').map(p => p.path)
    const missingStrm = filteredProblems.value.filter(p => p.type === 'missing_strm').map(p => p.path)
    
    let hasErrors = false
    
    // 修复无效STRM文件
    if (invalidStrm.length > 0 && (problemFilter.value === 'all' || problemFilter.value === 'invalid_strm')) {
      const invalidResponse = await fetch('/api/health/repair/invalid_strm', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          paths: invalidStrm,
          type: 'invalid_strm'
        })
      })
      
      const invalidData = await invalidResponse.json()
      
      if (invalidData.success) {
        message.success(invalidData.message)
      } else {
        message.error(invalidData.message || '修复无效STRM文件失败')
        hasErrors = true
      }
    }
    
    // 修复缺失STRM文件
    if (missingStrm.length > 0 && (problemFilter.value === 'all' || problemFilter.value === 'missing_strm')) {
      const missingResponse = await fetch('/api/health/repair/missing_strm', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          paths: missingStrm,
          type: 'missing_strm'
        })
      })
      
      const missingData = await missingResponse.json()
      
      if (missingData.success) {
        message.success(missingData.message)
      } else {
        message.error(missingData.message || '修复缺失STRM文件失败')
        hasErrors = true
      }
    }
    
    if (!hasErrors) {
      message.success('所有问题已成功修复')
    }
    
    // 重新获取问题列表和状态
    await getProblems()
    await getStatus()
    
  } catch (error) {
    console.error('批量修复问题失败:', error)
    message.error('批量修复失败: ' + error.message)
  } finally {
    repairingAll.value = false
  }
}

// 清空健康数据
const clearHealthData = async () => {
  try {
    const response = await fetch('/api/health/clear_data', {
      method: 'POST'
    })
    
    const data = await response.json()
    
    if (data.success) {
      message.success('健康数据已清空')
      problems.value = []
      await getStatus()
    } else {
      message.error(data.message || '清空数据失败')
    }
  } catch (error) {
    console.error('清空健康数据失败:', error)
    message.error('清空数据失败: ' + error.message)
  }
}

// 格式化时间戳
const formatTime = (timestamp) => {
  if (!timestamp) return ''
  const date = new Date(timestamp * 1000)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

// 获取最后扫描时间消息
const getLastScanMessage = () => {
  if (isScanning.value) {
    return `正在进行${getScanTypeName(scanType.value)}，模式：${getScanModeName(scanMode.value)}`
  }
  
  if (!lastScanTime.value) {
    return '尚未进行过健康检测'
  }
  
  return `上次${getScanTypeName(scanType.value)}：${lastScanTimeStr.value}`
}

// 获取扫描类型名称
const getScanTypeName = (type) => {
  const types = {
    'all': '全面检测',
    'strm_validity': 'STRM文件有效性检测',
    'video_coverage': '视频文件覆盖检测'
  }
  return types[type] || '未知检测'
}

// 获取扫描模式名称
const getScanModeName = (mode) => {
  const modes = {
    'full': '完整扫描',
    'incremental': '增量扫描',
    'problems_only': '仅检查问题'
  }
  return modes[mode] || '未知模式'
}

// 获取问题类型名称
const getProblemTypeName = (type) => {
  return type === 'invalid_strm' ? '无效STRM' : '缺失STRM'
}

// 获取标签颜色
const getTagColor = (type) => {
  return type === 'invalid_strm' ? 'red' : 'orange'
}

// 获取修复按钮文本
const getRepairText = (type) => {
  if (type === 'invalid_strm') return '清理无效STRM'
  if (type === 'missing_strm') return '生成STRM'
  return '修复所有问题'
}

// Emby刷新队列相关
const embyStatus = ref({})
const embyLoading = ref(false)
const nextRefreshTime = ref(null)
const refreshTimer = ref(null)

// 获取Emby刷新状态
const refreshEmbyStatus = async () => {
  embyLoading.value = true
  try {
    const response = await fetch('/api/health/emby/refresh/status')
    if (response.ok) {
      const data = await response.json()
      embyStatus.value = data
      
      // 设置下次刷新时间（60秒后）
      nextRefreshTime.value = Date.now() + 60000
      
      // 设置定时器，60秒后自动刷新
      if (refreshTimer.value) {
        clearTimeout(refreshTimer.value)
      }
      refreshTimer.value = setTimeout(() => {
        refreshEmbyStatus()
      }, 60000)
    } else {
      message.error('获取Emby刷新状态失败')
    }
  } catch (e) {
    console.error('获取Emby刷新状态失败:', e)
    message.error('获取Emby刷新状态失败: ' + e.message)
  } finally {
    embyLoading.value = false
  }
}

// 强制刷新STRM文件
const forceRefreshEmbyItem = async (path) => {
  try {
    const response = await fetch(`/api/health/emby/refresh/force?path=${encodeURIComponent(path)}`, {
      method: 'POST'
    })
    
    if (response.ok) {
      const data = await response.json()
      if (data.success) {
        message.success(data.message)
        // 刷新状态
        setTimeout(() => {
          refreshEmbyStatus()
        }, 1000)
      } else {
        message.error(data.message)
      }
    } else {
      message.error('强制刷新失败')
    }
  } catch (e) {
    console.error('强制刷新失败:', e)
    message.error('强制刷新失败: ' + e.message)
  }
}

// 组件卸载时清理定时器
onUnmounted(() => {
  if (refreshTimer.value) {
    clearTimeout(refreshTimer.value)
  }
})
</script>

<style scoped>
.strm-health-panel {
  padding: 20px;
}

.health-card {
  min-height: 500px;
}

.scan-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.scan-title {
  flex: 1;
  margin-right: 20px;
  margin-bottom: 20px;
}

.scan-status-alert {
  margin-top: 10px;
}

.scan-controls {
  display: flex;
  align-items: flex-start;
}

.scan-progress {
  margin: 20px 0;
}

.scan-status {
  margin-top: 8px;
  color: #666;
}

.stats-section {
  margin-bottom: 24px;
  padding: 16px;
  background-color: #f9f9f9;
  border-radius: 4px;
}

.problem-list {
  margin-top: 20px;
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.filter-controls {
  margin-left: auto;
}

.problem-card {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.problem-info {
  flex: 1;
}

.problem-path {
  font-weight: bold;
  margin: 8px 0;
  word-break: break-all;
}

.problem-details {
  color: #666;
  margin-bottom: 8px;
}

.problem-time {
  font-size: 12px;
  color: #999;
  display: flex;
  flex-direction: column;
}

.problem-actions {
  margin-left: 16px;
}

.no-problems {
  margin: 40px 0;
  text-align: center;
}

.batch-actions {
  margin-top: 20px;
  text-align: right;
}

.advanced-actions {
  margin-top: 30px;
  border-top: 1px solid #f0f0f0;
  padding-top: 20px;
  text-align: right;
}

@media (max-width: 768px) {
  .scan-header {
    flex-direction: column;
  }
  
  .scan-title, .scan-controls {
    width: 100%;
  }
  
  .problem-card {
    flex-direction: column;
    align-items: flex-start;
  }
  
  .problem-actions {
    margin-left: 0;
    margin-top: 12px;
    align-self: flex-end;
  }
}
</style> 