<template>
  <div class="dashboard-panel">
    <section class="hero-grid">
      <a-card class="hero-card hero-card-main" :bordered="false">
        <div class="hero-copy">
          <div class="hero-badge">Live Control</div>
          <h2>先看状态，再做操作。</h2>
          <p>
            这里聚合了扫描、归档、待删除和 Emby 刷新状态。你可以先判断系统是否健康，再跳转到对应模块处理。
          </p>
        </div>
        <div class="hero-actions">
          <a-button type="primary" size="large" @click="$emit('navigate', 'health')">查看健康问题</a-button>
          <a-button size="large" @click="$emit('navigate', 'archive')">打开归档中心</a-button>
        </div>
      </a-card>

      <a-card class="hero-card hero-side-card" :bordered="false">
        <div class="mini-kicker">系统概览</div>
        <div class="hero-side-list">
          <div class="hero-side-item">
            <span>STRM 扫描</span>
            <strong :class="strmStatusClass">{{ strmStatusText }}</strong>
          </div>
          <div class="hero-side-item">
            <span>健康检测</span>
            <strong>{{ healthStatusText }}</strong>
          </div>
          <div class="hero-side-item">
            <span>Emby 服务</span>
            <strong :class="embyEnabled ? 'ok' : 'warn'">{{ embyEnabled ? '已启用' : '未启用' }}</strong>
          </div>
        </div>
        <a-button block @click="loadData" :loading="loading">刷新面板</a-button>
      </a-card>
    </section>

    <section class="metrics-grid">
      <a-card v-for="item in metrics" :key="item.key" class="metric-card" :bordered="false">
        <div class="metric-head">
          <span class="metric-label">{{ item.label }}</span>
          <span class="metric-state" :class="item.stateClass">{{ item.stateText }}</span>
        </div>
        <div class="metric-value">{{ item.value }}</div>
        <p class="metric-desc">{{ item.description }}</p>
      </a-card>
    </section>

    <section class="board-grid">
      <a-card class="board-card" title="最近扫描与归档信号" :bordered="false">
        <div class="signal-list">
          <div class="signal-item">
            <span>健康检测</span>
            <strong>{{ lastHealthScanText }}</strong>
          </div>
          <div class="signal-item">
            <span>无效 STRM</span>
            <strong>{{ healthStats.invalidStrmFiles || 0 }}</strong>
          </div>
          <div class="signal-item">
            <span>缺失 STRM</span>
            <strong>{{ healthStats.missingStrmFiles || 0 }}</strong>
          </div>
          <div class="signal-item">
            <span>待删除条目</span>
            <strong>{{ pendingItems.length }}</strong>
          </div>
        </div>
      </a-card>

      <a-card class="board-card" title="Emby 监控摘要" :bordered="false">
        <div class="signal-list">
          <div class="signal-item">
            <span>最近扫描</span>
            <strong>{{ embyLastScanText }}</strong>
          </div>
          <div class="signal-item">
            <span>最近刷新</span>
            <strong>{{ embyLastRefreshText }}</strong>
          </div>
          <div class="signal-item">
            <span>扫描命中项目</span>
            <strong>{{ embyMonitor.last_scan?.summary?.total_found || 0 }}</strong>
          </div>
          <div class="signal-item">
            <span>STRM 命中数</span>
            <strong>{{ embyMonitor.last_scan?.summary?.strm_count || 0 }}</strong>
          </div>
        </div>
        <a-button type="link" class="inline-link" @click="$emit('navigate', 'emby-refresh')">
          打开 Emby 监控
        </a-button>
      </a-card>
    </section>

    <section class="queue-grid">
      <a-card class="queue-card" title="待删除队列预览" :bordered="false">
        <a-empty v-if="pendingItems.length === 0" description="当前没有待删除项目" />
        <div v-else class="queue-list">
          <div v-for="item in pendingItems.slice(0, 5)" :key="item.path" class="queue-item">
            <div class="queue-path">{{ item.path }}</div>
            <div class="queue-meta">
              <a-tag :color="item.move_success ? 'green' : 'orange'">
                {{ item.move_success ? '已确认迁移' : '等待迁移确认' }}
              </a-tag>
              <span>{{ formatDate(item.delete_time) }}</span>
            </div>
          </div>
        </div>
      </a-card>

      <a-card class="queue-card" title="Emby 最近日志" :bordered="false">
        <a-empty v-if="recentLogs.length === 0" description="暂无 Emby 日志" />
        <div v-else class="log-list">
          <div v-for="(log, index) in recentLogs.slice(0, 8)" :key="index" class="log-item">
            {{ log }}
          </div>
        </div>
      </a-card>
    </section>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

defineEmits(['navigate'])

const loading = ref(false)
const strmStatus = ref('idle')
const healthStatus = ref({})
const healthStats = ref({})
const pendingItems = ref([])
const embyMonitor = ref({
  enabled: false,
  last_scan: { summary: {}, items: [] },
  last_refresh: { items: [] },
  recent_logs: [],
})

let timer = null

const loadData = async () => {
  loading.value = true
  try {
    const [strmRes, healthRes, pendingRes, embyRes] = await Promise.all([
      fetch('/api/strm/status').then((r) => r.json()),
      fetch('/api/health/status').then((r) => r.json()),
      fetch('/api/archive/pending-deletions').then((r) => r.json()).catch(() => ({ success: false, data: [] })),
      fetch('/api/health/emby/monitor').then((r) => r.json()).catch(() => ({ success: false, data: {} })),
    ])

    strmStatus.value = strmRes.status || 'idle'
    healthStatus.value = healthRes || {}
    healthStats.value = healthRes.stats || {}
    pendingItems.value = pendingRes.success ? (pendingRes.data || []) : []
    embyMonitor.value = embyRes.success ? embyRes.data : {
      enabled: false,
      last_scan: { summary: {}, items: [] },
      last_refresh: { items: [] },
      recent_logs: [],
    }
  } finally {
    loading.value = false
  }
}

const strmStatusText = computed(() => strmStatus.value === 'scanning' ? '运行中' : '空闲')
const strmStatusClass = computed(() => strmStatus.value === 'scanning' ? 'ok' : 'muted')
const healthStatusText = computed(() => healthStatus.value.isScanning ? '检测中' : '待命')
const embyEnabled = computed(() => Boolean(embyMonitor.value.enabled))
const recentLogs = computed(() => embyMonitor.value.recent_logs || [])
const lastHealthScanText = computed(() => healthStatus.value.lastScanTimeStr || '尚未扫描')
const embyLastScanText = computed(() => embyMonitor.value.last_scan?.time || '暂无记录')
const embyLastRefreshText = computed(() => embyMonitor.value.last_refresh?.time || '暂无记录')

const metrics = computed(() => [
  {
    key: 'total-strm',
    label: 'STRM 文件',
    value: healthStats.value.totalStrmFiles || 0,
    description: '当前健康数据中登记的 STRM 文件总数。',
    stateText: strmStatusText.value,
    stateClass: strmStatus.value === 'scanning' ? 'state-live' : 'state-idle',
  },
  {
    key: 'invalid',
    label: '无效 STRM',
    value: healthStats.value.invalidStrmFiles || 0,
    description: '需要修复或删除的无效 STRM 文件数量。',
    stateText: (healthStats.value.invalidStrmFiles || 0) > 0 ? '需处理' : '正常',
    stateClass: (healthStats.value.invalidStrmFiles || 0) > 0 ? 'state-alert' : 'state-ok',
  },
  {
    key: 'missing',
    label: '缺失映射',
    value: healthStats.value.missingStrmFiles || 0,
    description: '视频存在但缺少 STRM 映射的文件数量。',
    stateText: (healthStats.value.missingStrmFiles || 0) > 0 ? '有缺口' : '完整',
    stateClass: (healthStats.value.missingStrmFiles || 0) > 0 ? 'state-warn' : 'state-ok',
  },
  {
    key: 'pending',
    label: '待删除队列',
    value: pendingItems.value.length,
    description: '已进入延迟删除阶段的本地源文件或目录数量。',
    stateText: pendingItems.value.some((item) => item.move_success === false) ? '待确认' : '已同步',
    stateClass: pendingItems.value.some((item) => item.move_success === false) ? 'state-warn' : 'state-ok',
  },
])

const formatDate = (timestamp) => {
  if (!timestamp) return '未知时间'
  return new Date(timestamp * 1000).toLocaleString()
}

onMounted(() => {
  loadData()
  timer = window.setInterval(loadData, 20000)
})

onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<style scoped>
.dashboard-panel {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.hero-grid,
.board-grid,
.queue-grid {
  display: grid;
  gap: 20px;
}

.hero-grid {
  grid-template-columns: 1.8fr 1fr;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 20px;
}

.board-grid,
.queue-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.hero-card {
  min-height: 240px;
}

.hero-card-main {
  background:
    linear-gradient(135deg, rgba(180, 84, 47, 0.16), rgba(255, 252, 246, 0.9)),
    linear-gradient(180deg, rgba(255, 255, 255, 0.6), rgba(255, 255, 255, 0.72));
}

.hero-copy h2 {
  margin: 14px 0 10px;
  font-size: 36px;
  line-height: 1.05;
  color: #2a1f16;
}

.hero-copy p {
  max-width: 640px;
  margin: 0;
  color: #665747;
  font-size: 15px;
}

.hero-badge,
.mini-kicker {
  color: #b4542f;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.hero-actions {
  display: flex;
  gap: 12px;
  margin-top: 28px;
}

.hero-side-list,
.signal-list {
  display: grid;
  gap: 12px;
}

.hero-side-item,
.signal-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px solid rgba(36, 29, 21, 0.08);
  color: #5d5145;
}

.hero-side-item:last-child,
.signal-item:last-child {
  border-bottom: 0;
}

.hero-side-item strong,
.signal-item strong {
  color: #251d15;
}

.ok {
  color: #4d6b2d;
}

.warn {
  color: #b4542f;
}

.muted {
  color: #8d7d6d;
}

.metric-card {
  min-height: 180px;
}

.metric-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.metric-label {
  color: #766756;
  font-size: 13px;
  font-weight: 600;
}

.metric-state {
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.state-live,
.state-ok {
  background: rgba(95, 107, 63, 0.14);
  color: #506036;
}

.state-idle {
  background: rgba(94, 82, 68, 0.12);
  color: #5d5145;
}

.state-alert {
  background: rgba(180, 84, 47, 0.16);
  color: #a04d2c;
}

.state-warn {
  background: rgba(196, 143, 37, 0.16);
  color: #9b6d19;
}

.metric-value {
  margin-top: 20px;
  font-size: 42px;
  font-weight: 700;
  color: #241d15;
}

.metric-desc {
  margin: 12px 0 0;
  color: #766756;
  line-height: 1.6;
}

.inline-link {
  padding-left: 0;
  margin-top: 12px;
}

.queue-list,
.log-list {
  display: grid;
  gap: 12px;
}

.queue-item,
.log-item {
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.55);
  border: 1px solid rgba(36, 29, 21, 0.06);
}

.queue-path {
  color: #251d15;
  font-weight: 600;
  word-break: break-all;
}

.queue-meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
  margin-top: 10px;
  color: #766756;
  font-size: 12px;
}

.log-item {
  color: #5d5145;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
}

@media (max-width: 1200px) {
  .metrics-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .hero-grid,
  .board-grid,
  .queue-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .metrics-grid {
    grid-template-columns: 1fr;
  }

  .hero-copy h2 {
    font-size: 28px;
  }

  .hero-actions {
    flex-direction: column;
  }
}
</style>
