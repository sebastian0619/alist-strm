<template>
  <div class="health-workbench">
    <section class="health-hero">
      <div>
        <p class="hero-kicker">STRM Diagnostics</p>
        <h2>健康检测工作台</h2>
        <p class="hero-description">
          先看扫描状态，再处理无效 STRM、缺失映射和输出目录里的遗留文件。
        </p>
      </div>
      <div class="hero-status-card">
        <span class="hero-status-label">当前状态</span>
        <strong>{{ isScanning ? '检测进行中' : '等待操作' }}</strong>
        <span>{{ getLastScanMessage() }}</span>
      </div>
    </section>

    <a-card class="control-card" :bordered="false">
      <div class="scan-toolbar">
        <div class="scan-alert-wrap">
          <a-alert v-if="lastScanTime || isScanning" :type="isScanning ? 'warning' : 'info'" show-icon>
            <template #message>
              <span>{{ getLastScanMessage() }}</span>
            </template>
          </a-alert>
        </div>
        <a-form layout="inline" class="scan-form">
          <a-form-item label="扫描类型">
            <a-select v-model:value="scanType" style="width: 190px" :disabled="isScanning">
              <a-select-option value="all">全面检测</a-select-option>
              <a-select-option value="strm_validity">STRM 文件有效性</a-select-option>
              <a-select-option value="video_coverage">视频文件覆盖检测</a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="扫描模式">
            <a-select v-model:value="scanMode" style="width: 160px" :disabled="isScanning">
              <a-select-option value="full">完整扫描</a-select-option>
              <a-select-option value="incremental">增量扫描</a-select-option>
              <a-select-option value="problems_only">仅检查问题</a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item>
            <a-button type="primary" size="large" :disabled="isScanning" @click="startScan">
              开始检测
            </a-button>
          </a-form-item>
        </a-form>
      </div>

      <div class="stats-grid" v-if="stats">
        <article class="metric-card">
          <span>STRM 总数</span>
          <strong>{{ stats.totalStrmFiles }}</strong>
          <small>输出目录当前已生成的全部 STRM 文件</small>
        </article>
        <article class="metric-card danger">
          <span>无效 STRM</span>
          <strong>{{ stats.invalidStrmFiles }}</strong>
          <small>链接失效或内容异常，优先处理</small>
        </article>
        <article class="metric-card">
          <span>视频文件总数</span>
          <strong>{{ stats.totalVideoFiles }}</strong>
          <small>纳入健康检测的源视频规模</small>
        </article>
        <article class="metric-card warn">
          <span>缺失 STRM</span>
          <strong>{{ stats.missingStrmFiles }}</strong>
          <small>源视频存在，但还没有对应 STRM</small>
        </article>
      </div>

      <div v-if="isScanning" class="scan-progress-panel">
        <a-progress :percent="scanProgress" status="active" />
        <p>{{ scanStatus }}</p>
      </div>
    </a-card>

    <a-card class="problem-card-shell" :bordered="false">
      <div class="section-head">
        <div>
          <p class="section-kicker">Problem Queue</p>
          <h3>问题列表</h3>
        </div>
        <div class="section-tools">
          <a-radio-group v-model:value="problemFilter" button-style="solid">
            <a-radio-button value="all">全部</a-radio-button>
            <a-radio-button value="invalid_strm">无效 STRM</a-radio-button>
            <a-radio-button value="missing_strm">缺失 STRM</a-radio-button>
          </a-radio-group>
          <a-button @click="getProblems" :loading="loadingProblems">刷新列表</a-button>
        </div>
      </div>

      <div v-if="problems.length > 0" class="problem-list-wrap">
        <a-list :data-source="filteredProblems" :pagination="{ pageSize: 8 }">
          <template #renderItem="{ item }">
            <a-list-item>
              <div class="problem-row">
                <div class="problem-copy">
                  <div class="problem-topline">
                    <a-tag :color="getTagColor(item.type)">{{ getProblemTypeName(item.type) }}</a-tag>
                    <span class="problem-path">{{ item.path }}</span>
                  </div>
                  <p class="problem-details">{{ item.details }}</p>
                  <div class="problem-meta">
                    <span>发现时间: {{ formatTime(item.discoveryTime) }}</span>
                    <span v-if="item.firstDetectedAt && item.firstDetectedAt !== item.discoveryTime">
                      首次发现: {{ formatTime(item.firstDetectedAt) }}
                    </span>
                  </div>
                </div>
                <div class="problem-actions">
                  <a-button type="primary" @click="repairProblem(item)" :loading="repairing[item.id]">
                    {{ getRepairText(item.type) }}
                  </a-button>
                  <a-button
                    v-if="item.type === 'invalid_strm'"
                    danger
                    @click="deleteStrmFile(item)"
                    :loading="deletingItem === item.id"
                  >
                    删除 STRM
                  </a-button>
                </div>
              </div>
            </a-list-item>
          </template>
        </a-list>

        <div class="batch-actions" v-if="filteredProblems.length > 0">
          <a-button type="primary" @click="repairAllProblems" :loading="repairingAll" :disabled="isScanning">
            批量{{ getRepairText(problemFilter === 'all' ? '' : problemFilter) }}
          </a-button>
          <a-button
            v-if="problemFilter === 'invalid_strm'"
            danger
            @click="deleteAllInvalidStrmFiles"
            :loading="deletingAll"
            :disabled="isScanning"
          >
            批量删除无效 STRM
          </a-button>
        </div>
      </div>

      <div v-else-if="!isScanning && hasScanned" class="empty-state-shell">
        <a-alert
          v-if="stats && (stats.invalidStrmFiles > 0 || stats.missingStrmFiles > 0)"
          type="warning"
          show-icon
          message="统计显示仍有问题，但列表为空"
          description="这通常是上一轮状态还没完全刷新，可以直接再点一次刷新列表。"
        >
          <template #action>
            <a-button type="primary" @click="getProblems">刷新问题列表</a-button>
          </template>
        </a-alert>
        <a-empty v-else description="未检测到问题">
          <template #description>
            <span>当前 STRM 映射状态正常，视频覆盖也没有发现缺口。</span>
          </template>
        </a-empty>
      </div>
    </a-card>

    <a-card class="cleanup-card" :bordered="false">
      <div class="section-head compact">
        <div>
          <p class="section-kicker">Cleanup</p>
          <h3>清理非远程文件</h3>
        </div>
        <a-space>
          <a-button @click="previewCleanup" :loading="cleanupLoading" :disabled="isScanning">预览清理</a-button>
          <a-button type="primary" danger @click="executeCleanup" :loading="cleanupLoading" :disabled="isScanning">
            执行清理
          </a-button>
        </a-space>
      </div>

      <a-alert type="info" show-icon class="cleanup-alert">
        <template #message>
          <span>只会清理 STRM 输出目录里没有 <code>@remote(网盘)</code> 标识的元数据和字幕文件。</span>
        </template>
        <template #description>
          <span>不会扫描你的源视频目录，也不会删除 `.mkv`、`.mp4` 这类媒体文件。</span>
        </template>
      </a-alert>

      <div v-if="cleanupResult" class="cleanup-summary-grid">
        <article class="cleanup-stat">
          <span>发现文件</span>
          <strong>{{ cleanupResult.data?.found_files?.length || 0 }}</strong>
        </article>
        <article class="cleanup-stat success">
          <span>删除文件</span>
          <strong>{{ cleanupResult.data?.deleted_files?.length || 0 }}</strong>
        </article>
        <article class="cleanup-stat danger">
          <span>失败文件</span>
          <strong>{{ cleanupResult.data?.failed_files?.length || 0 }}</strong>
        </article>
        <article class="cleanup-stat accent">
          <span>释放空间</span>
          <strong>{{ cleanupResult.data?.total_size_formatted || '0 B' }}</strong>
        </article>
      </div>

      <div v-if="cleanupResult?.data?.found_files?.length > 0" class="cleanup-list-shell">
        <a-collapse>
          <a-collapse-panel key="files" header="查看本次匹配到的文件列表">
            <a-list size="small" :data-source="cleanupResult.data.found_files" :pagination="{ pageSize: 10 }">
              <template #renderItem="{ item }">
                <a-list-item>
                  <a-space>
                    <file-outlined />
                    <span>{{ item.path }}</span>
                    <a-tag>{{ item.size_formatted }}</a-tag>
                  </a-space>
                </a-list-item>
              </template>
            </a-list>
          </a-collapse-panel>
        </a-collapse>
      </div>
    </a-card>

    <div class="advanced-actions" v-if="!isScanning">
      <a-popconfirm title="确定要清空健康检测数据吗？这将删除所有记录的问题和状态信息。" @confirm="clearHealthData">
        <a-button danger>清空健康数据</a-button>
      </a-popconfirm>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { FileOutlined } from '@ant-design/icons-vue'

const scanType = ref('all')
const scanMode = ref('full')
const isScanning = ref(false)
const scanProgress = ref(0)
const scanStatus = ref('')
const lastScanTime = ref(null)
const lastScanTimeStr = ref('')
const hasScanned = ref(false)
const stats = ref(null)

const problems = ref([])
const problemFilter = ref('all')
const repairing = ref({})
const repairingAll = ref(false)
const loadingProblems = ref(false)

const deletingAll = ref(false)
const deletingItem = ref(null)

const cleanupLoading = ref(false)
const cleanupResult = ref(null)

const filteredProblems = computed(() => {
  if (problemFilter.value === 'all') {
    return problems.value
  }
  return problems.value.filter((problem) => problem.type === problemFilter.value)
})

onMounted(async () => {
  await getStatus()
  await getProblems()
})

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
    stats.value = data.stats || null

    if (data.lastScanTime) {
      hasScanned.value = true
    }

    if (data.isScanning) {
      setTimeout(getStatus, 2000)
    }
  } catch (error) {
    console.error('获取扫描状态失败:', error)
  }
}

const getProblems = async () => {
  try {
    loadingProblems.value = true
    const response = await fetch(`/api/health/problems?type=${problemFilter.value === 'all' ? '' : problemFilter.value}`)
    const data = await response.json()

    problems.value = data.problems || []
    if (data.stats) {
      stats.value = data.stats
    }

    if ((stats.value?.invalidStrmFiles > 0 || stats.value?.missingStrmFiles > 0) && problems.value.length === 0) {
      setTimeout(getProblems, 5000)
    }
  } catch (error) {
    console.error('获取问题列表失败:', error)
    message.error('获取问题列表失败，请刷新页面重试')
  } finally {
    loadingProblems.value = false
  }
}

const startScan = async () => {
  try {
    isScanning.value = true
    scanProgress.value = 0
    scanStatus.value = '正在初始化扫描...'

    const response = await fetch('/api/health/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type: scanType.value,
        mode: scanMode.value,
      }),
    })

    const data = await response.json()

    if (data.status === 'scanning') {
      message.success('已开始健康扫描')
      getStatus()
      checkScanCompleted()
    } else {
      message.error('启动扫描失败')
      isScanning.value = false
    }
  } catch (error) {
    console.error('启动扫描失败:', error)
    message.error(`启动扫描失败: ${error.message}`)
    isScanning.value = false
  }
}

const checkScanCompleted = () => {
  setTimeout(async () => {
    if (isScanning.value) {
      await getStatus()
      if (isScanning.value) {
        checkScanCompleted()
      } else {
        await getProblems()
        message.success('扫描完成')
      }
    }
  }, 2000)
}

const repairProblem = async (problem) => {
  try {
    repairing.value[problem.id] = true
    const endpoint = problem.type === 'invalid_strm' ? 'repair/invalid_strm' : 'repair/missing_strm'

    const response = await fetch(`/api/health/${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        paths: [problem.path],
        type: problem.type,
      }),
    })

    const data = await response.json()

    if (data.success) {
      message.success(data.message)
      problems.value = problems.value.filter((p) => p.id !== problem.id)
      await getStatus()
    } else {
      message.error(data.message || '修复失败')
    }
  } catch (error) {
    console.error('修复问题失败:', error)
    message.error(`修复失败: ${error.message}`)
  } finally {
    repairing.value[problem.id] = false
  }
}

const repairAllProblems = async () => {
  if (filteredProblems.value.length === 0) {
    return
  }

  repairingAll.value = true

  try {
    const currentFilter = problemFilter.value
    const invalidStrm = filteredProblems.value.filter((p) => p.type === 'invalid_strm').map((p) => p.path)
    const missingStrm = filteredProblems.value.filter((p) => p.type === 'missing_strm').map((p) => p.path)
    let hasErrors = false

    if (invalidStrm.length > 0 && (currentFilter === 'all' || currentFilter === 'invalid_strm')) {
      const response = await fetch('/api/health/repair/invalid_strm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'invalid_strm', paths: invalidStrm }),
      })
      const data = await response.json()
      if (data.success) {
        message.success(data.message || '成功修复无效STRM文件')
      } else {
        message.error(data.message || '修复无效STRM文件失败')
        hasErrors = true
      }
    }

    if (missingStrm.length > 0 && (currentFilter === 'all' || currentFilter === 'missing_strm')) {
      const response = await fetch('/api/health/repair/missing_strm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'missing_strm', paths: missingStrm }),
      })
      const data = await response.json()
      if (data.success) {
        message.success(data.message || '成功为缺失文件生成STRM')
      } else {
        message.error(data.message || '生成STRM文件失败')
        hasErrors = true
      }
    }

    if (!hasErrors && (invalidStrm.length > 0 || missingStrm.length > 0)) {
      message.success('所有问题已成功修复')
    }

    await getProblems()
    await getStatus()
  } catch (error) {
    console.error('批量修复失败:', error)
    message.error(`批量修复失败: ${error.message || '未知错误'}`)
  } finally {
    repairingAll.value = false
  }
}

const deleteAllInvalidStrmFiles = async () => {
  if (!window.confirm(`确定要删除所有 ${filteredProblems.value.length} 个无效的STRM文件吗？此操作不可撤销。`)) {
    return
  }

  deletingAll.value = true

  try {
    const paths = filteredProblems.value
      .filter((problem) => problem.type === 'invalid_strm')
      .map((problem) => problem.path)

    if (paths.length === 0) {
      message.info('没有无效的STRM文件需要删除')
      deletingAll.value = false
      return
    }

    const response = await fetch('/api/health/strm/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(paths),
    })

    const data = await response.json()

    if (data.status === 'success' || data.status === 'partial_success') {
      message.success(data.message || `成功删除 ${data.deleted.length} 个无效STRM文件`)
      if (data.failed && data.failed.length > 0) {
        message.warning(`有 ${data.failed.length} 个文件删除失败`)
      }
      await getProblems()
      await getStatus()
    } else {
      message.error(data.message || '删除文件失败')
    }
  } catch (error) {
    console.error('批量删除文件失败:', error)
    message.error(`批量删除文件失败: ${error.message || '未知错误'}`)
  } finally {
    deletingAll.value = false
  }
}

const clearHealthData = async () => {
  try {
    const response = await fetch('/api/health/clear_data', { method: 'POST' })
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
    message.error(`清空数据失败: ${error.message}`)
  }
}

const formatTime = (timestamp) => {
  if (!timestamp) return ''
  const date = new Date(timestamp * 1000)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

const getLastScanMessage = () => {
  if (isScanning.value) {
    return `正在进行${getScanTypeName(scanType.value)}，模式：${getScanModeName(scanMode.value)}`
  }
  if (!lastScanTime.value) {
    return '尚未进行过健康检测'
  }
  return `上次${getScanTypeName(scanType.value)}：${lastScanTimeStr.value}`
}

const getScanTypeName = (type) => ({
  all: '全面检测',
  strm_validity: 'STRM文件有效性检测',
  video_coverage: '视频文件覆盖检测',
}[type] || '未知检测')

const getScanModeName = (mode) => ({
  full: '完整扫描',
  incremental: '增量扫描',
  problems_only: '仅检查问题',
}[mode] || '未知模式')

const getProblemTypeName = (type) => (type === 'invalid_strm' ? '无效STRM' : '缺失STRM')
const getTagColor = (type) => (type === 'invalid_strm' ? 'red' : 'orange')

const getRepairText = (type) => {
  if (type === 'invalid_strm') return '清理无效STRM'
  if (type === 'missing_strm') return '生成STRM'
  return '修复所有问题'
}

const deleteStrmFile = async (item) => {
  if (!window.confirm(`确定要删除STRM文件 "${item.path}" 吗？此操作不可撤销。`)) {
    return
  }

  deletingItem.value = item.id

  try {
    const response = await fetch('/api/health/strm/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify([item.path]),
    })

    const data = await response.json()
    if (data.status === 'success' || data.status === 'partial_success') {
      message.success(data.message || '成功删除STRM文件')
      await getProblems()
      await getStatus()
    } else {
      message.error(data.message || '删除文件失败')
    }
  } catch (error) {
    console.error('删除文件失败:', error)
    message.error(`删除文件失败: ${error.message || '未知错误'}`)
  } finally {
    deletingItem.value = null
  }
}

const previewCleanup = async () => {
  try {
    cleanupLoading.value = true
    cleanupResult.value = null
    const response = await fetch('/api/health/cleanup/non-remote-files', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preview_only: true }),
    })
    const data = await response.json()
    if (data.success) {
      cleanupResult.value = data
      message.success(data.message)
    } else {
      message.error(data.message || '预览清理失败')
    }
  } catch (error) {
    console.error('预览清理失败:', error)
    message.error(`预览清理失败: ${error.message || '未知错误'}`)
  } finally {
    cleanupLoading.value = false
  }
}

const executeCleanup = async () => {
  if (!window.confirm('确定要删除所有没有@remote(网盘)标识的nfo、mediainfo.json、ass、srt文件吗？此操作不可撤销。')) {
    return
  }

  try {
    cleanupLoading.value = true
    cleanupResult.value = null
    const response = await fetch('/api/health/cleanup/non-remote-files', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preview_only: false }),
    })
    const data = await response.json()
    if (data.success) {
      cleanupResult.value = data
      message.success(data.message)
    } else {
      message.error(data.message || '执行清理失败')
    }
  } catch (error) {
    console.error('执行清理失败:', error)
    message.error(`执行清理失败: ${error.message || '未知错误'}`)
  } finally {
    cleanupLoading.value = false
  }
}
</script>

<style scoped>
.health-workbench {
  display: flex;
  flex-direction: column;
  gap: 22px;
  padding: 8px;
}

.health-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 18px;
  padding: 28px;
  border-radius: 28px;
  background:
    radial-gradient(circle at top right, rgba(74, 163, 255, 0.18), transparent 36%),
    linear-gradient(135deg, rgba(14, 23, 41, 0.98), rgba(18, 39, 69, 0.94));
  color: #f5f9ff;
  box-shadow: 0 22px 50px rgba(10, 18, 33, 0.26);
}

.hero-kicker,
.section-kicker {
  margin: 0 0 10px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: rgba(204, 223, 255, 0.72);
}

.health-hero h2,
.section-head h3 {
  margin: 0;
  font-size: 30px;
  line-height: 1.05;
}

.hero-description {
  max-width: 720px;
  margin: 14px 0 0;
  color: rgba(227, 236, 252, 0.82);
  font-size: 15px;
}

.hero-status-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 22px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.12);
  backdrop-filter: blur(10px);
}

.hero-status-label {
  color: rgba(204, 223, 255, 0.72);
  font-size: 12px;
}

.hero-status-card strong {
  font-size: 22px;
}

.control-card,
.problem-card-shell,
.cleanup-card {
  border-radius: 26px;
}

.scan-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}

.scan-alert-wrap {
  flex: 1;
  min-width: 320px;
}

.scan-form {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px 0;
}

.stats-grid,
.cleanup-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-top: 22px;
}

.metric-card,
.cleanup-stat {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 18px;
  border-radius: 20px;
  background: linear-gradient(180deg, rgba(242, 247, 255, 0.98), rgba(232, 239, 251, 0.78));
  border: 1px solid rgba(86, 113, 152, 0.12);
}

.metric-card span,
.cleanup-stat span {
  color: #5f6f87;
  font-size: 13px;
}

.metric-card strong,
.cleanup-stat strong {
  color: #12213a;
  font-size: 28px;
  line-height: 1;
}

.metric-card small {
  color: #7c8aa0;
}

.metric-card.danger,
.cleanup-stat.danger {
  background: linear-gradient(180deg, rgba(255, 242, 243, 0.96), rgba(255, 232, 236, 0.88));
}

.metric-card.warn {
  background: linear-gradient(180deg, rgba(255, 248, 237, 0.96), rgba(255, 240, 219, 0.88));
}

.cleanup-stat.success {
  background: linear-gradient(180deg, rgba(239, 255, 246, 0.96), rgba(226, 247, 236, 0.88));
}

.cleanup-stat.accent {
  background: linear-gradient(180deg, rgba(240, 245, 255, 0.96), rgba(224, 234, 255, 0.88));
}

.scan-progress-panel {
  margin-top: 20px;
  padding: 18px 20px;
  border-radius: 18px;
  background: rgba(17, 34, 58, 0.04);
}

.scan-progress-panel p {
  margin: 10px 0 0;
  color: #5b6d85;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.section-head.compact {
  margin-bottom: 16px;
}

.section-tools {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.problem-list-wrap {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.problem-row {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  width: 100%;
  padding: 18px;
  border-radius: 20px;
  background: linear-gradient(180deg, rgba(250, 252, 255, 0.98), rgba(241, 246, 255, 0.9));
  border: 1px solid rgba(86, 113, 152, 0.12);
}

.problem-copy {
  min-width: 0;
  flex: 1;
}

.problem-topline {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.problem-path {
  color: #12213a;
  font-weight: 700;
  word-break: break-all;
}

.problem-details {
  margin: 10px 0 0;
  color: #5a6b84;
}

.problem-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 18px;
  margin-top: 12px;
  color: #7d8aa0;
  font-size: 12px;
}

.problem-actions,
.batch-actions,
.advanced-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.problem-actions {
  align-items: center;
  justify-content: flex-end;
}

.batch-actions {
  justify-content: flex-end;
  margin-top: 18px;
}

.empty-state-shell {
  padding: 12px 0 2px;
}

.cleanup-alert {
  border-radius: 16px;
}

.cleanup-list-shell {
  margin-top: 18px;
}

.advanced-actions {
  justify-content: flex-end;
}

@media (max-width: 1100px) {
  .health-hero {
    grid-template-columns: 1fr;
  }

  .stats-grid,
  .cleanup-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .health-workbench {
    padding: 0;
  }

  .health-hero {
    padding: 22px;
  }

  .health-hero h2,
  .section-head h3 {
    font-size: 24px;
  }

  .section-head,
  .problem-row,
  .scan-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .problem-actions,
  .batch-actions,
  .advanced-actions {
    justify-content: flex-start;
  }

  .stats-grid,
  .cleanup-summary-grid {
    grid-template-columns: 1fr;
  }
}
</style>
