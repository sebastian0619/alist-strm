<template>
  <div class="moviepilot-panel">
    <a-card class="moviepilot-shell" :bordered="false">
      <div class="panel-top">
        <div>
          <div class="panel-kicker">Source Recovery Desk</div>
          <h2>MoviePilot 补源订阅</h2>
          <p>当 STRM 对应的源视频在 Alist 上彻底消失后，缺口会进入这里，等待自动或手动发起订阅。</p>
        </div>
        <a-space>
          <a-button @click="loadPanel" :loading="loading">刷新面板</a-button>
          <a-button @click="$emit('navigate', 'config')">打开配置</a-button>
        </a-space>
      </div>

      <a-alert
        v-if="!status.enabled"
        type="warning"
        banner
        class="panel-alert"
        message="MoviePilot 未启用"
        description="请先在基本配置里填写地址、用户名密码或 API Key；如果开启了两步验证，还需要补上 OTP Secret。"
      />

      <div class="summary-grid">
        <div class="summary-tile">
          <span>服务状态</span>
          <strong :class="status.enabled ? 'ok' : 'warn'">{{ status.enabled ? '已启用' : '未启用' }}</strong>
        </div>
        <div class="summary-tile">
          <span>服务连通</span>
          <strong :class="status.server_ok ? 'ok' : 'warn'">{{ status.server_ok ? '正常' : '异常' }}</strong>
        </div>
        <div class="summary-tile">
          <span>认证状态</span>
          <strong :class="status.auth_ok ? 'ok' : 'warn'">{{ status.auth_ok ? '通过' : '失败' }}</strong>
        </div>
        <div class="summary-tile">
          <span>认证方式</span>
          <strong>{{ authModeText }}</strong>
        </div>
        <div class="summary-tile">
          <span>自动提交</span>
          <strong :class="status.auto_submit ? 'ok' : 'muted'">{{ status.auto_submit ? '已开启' : '仅入队' }}</strong>
        </div>
        <div class="summary-tile">
          <span>队列总数</span>
          <strong>{{ queue.length }}</strong>
        </div>
      </div>

      <div class="board-grid">
        <a-card class="board-card" title="队列分布" :bordered="false">
          <div class="summary-lines">
            <div class="summary-line">
              <span>待提交</span>
              <strong>{{ pendingCount }}</strong>
            </div>
            <div class="summary-line">
              <span>单集下载中</span>
              <strong>{{ downloadingCount }}</strong>
            </div>
            <div class="summary-line">
              <span>已订阅</span>
              <strong>{{ subscribedCount }}</strong>
            </div>
            <div class="summary-line">
              <span>提交失败</span>
              <strong>{{ failedCount }}</strong>
            </div>
            <div class="summary-line">
              <span>接口地址</span>
              <strong>{{ status.base_url || '未配置' }}</strong>
            </div>
          </div>
        </a-card>

        <a-card class="board-card" title="最近失败原因" :bordered="false">
          <a-empty v-if="failedItems.length === 0" description="当前没有失败项" />
          <div v-else class="reason-list">
            <div v-for="item in failedItems.slice(0, 5)" :key="item.id" class="reason-item">
              <strong>{{ item.title }}</strong>
              <p>{{ item.message || '未知错误' }}</p>
            </div>
          </div>
        </a-card>
      </div>

      <div class="queue-head">
        <div>
          <h3>缺源订阅队列</h3>
          <p>失败项可重试，待提交项可以手动立刻发给 MoviePilot。</p>
        </div>
        <a-tag color="blue">{{ queue.length }} 项</a-tag>
      </div>

      <a-empty v-if="queue.length === 0" description="当前没有缺源订阅任务" />

      <div v-else class="queue-list">
        <a-card v-for="item in queue" :key="item.id" class="queue-card">
          <div class="queue-card-head">
            <div>
              <div class="queue-title">{{ formatItemName(item) }}</div>
              <div class="queue-subtitle">
                <span>{{ item.media_type === 'tv' ? '剧集' : '电影' }}</span>
                <span v-if="item.year">{{ item.year }}</span>
                <span v-if="item.season">Season {{ item.season }}</span>
              </div>
            </div>
            <a-tag :color="getStatusColor(item.status)">{{ getStatusText(item.status) }}</a-tag>
          </div>

          <div class="queue-info-grid">
            <div class="info-block">
              <span>源视频路径</span>
              <strong>{{ item.video_path }}</strong>
            </div>
            <div class="info-block">
              <span>触发来源</span>
              <strong>{{ item.reason || '未记录' }}</strong>
            </div>
            <div class="info-block">
              <span>TMDB ID</span>
              <strong>{{ item.tmdb_id || '未匹配' }}</strong>
            </div>
            <div class="info-block">
              <span>补源策略</span>
              <strong>{{ item.match_mode === 'single_episode_download' ? '单集直下' : item.match_mode === 'season_subscription' ? '整季订阅' : '待匹配' }}</strong>
            </div>
            <div class="info-block">
              <span>参考版本</span>
              <strong>{{ formatReferenceProfile(item.reference_profile) }}</strong>
            </div>
            <div class="info-block">
              <span>已选资源</span>
              <strong>{{ item.selected_resource || '尚未选择' }}</strong>
            </div>
            <div class="info-block">
              <span>最后更新</span>
              <strong>{{ formatTime(item.updated_at) }}</strong>
            </div>
          </div>

          <div v-if="item.message" class="queue-message">
            {{ item.message }}
          </div>

          <div class="queue-actions">
            <a-button
              type="primary"
              :loading="submittingId === item.id"
              :disabled="!status.enabled || item.status === 'subscribed' || item.status === 'downloading'"
              @click="submitItem(item)"
            >
              {{ item.status === 'subscribed' ? '已订阅' : item.status === 'downloading' ? '下载已创建' : '提交补源' }}
            </a-button>
            <a-button v-if="item.trigger_path" @click="$emit('navigate', 'health')">查看健康页</a-button>
          </div>
        </a-card>
      </div>
    </a-card>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'

defineEmits(['navigate'])

const loading = ref(false)
const submittingId = ref('')
const status = ref({
  enabled: false,
  server_ok: false,
  auth_ok: false,
  auth_mode: 'disabled',
  queue_count: 0,
  auto_submit: false,
  base_url: '',
})
const queue = ref([])
let timer = null

const authModeText = computed(() => {
  if (status.value.auth_mode === 'password') return '用户名 + OTP'
  if (status.value.auth_mode === 'api_key') return 'API Key'
  return '未启用'
})

const pendingCount = computed(() => queue.value.filter((item) => item.status === 'pending').length)
const downloadingCount = computed(() => queue.value.filter((item) => item.status === 'downloading').length)
const subscribedCount = computed(() => queue.value.filter((item) => item.status === 'subscribed').length)
const failedCount = computed(() => queue.value.filter((item) => item.status === 'failed').length)
const failedItems = computed(() => queue.value.filter((item) => item.status === 'failed'))

const loadPanel = async () => {
  loading.value = true
  try {
    const [statusRes, queueRes] = await Promise.all([
      fetch('/api/moviepilot/status').then((r) => r.json()),
      fetch('/api/moviepilot/queue').then((r) => r.json()),
    ])

    status.value = statusRes.success ? statusRes.data : {
      enabled: false,
      server_ok: false,
      auth_ok: false,
      auth_mode: 'disabled',
      queue_count: 0,
      auto_submit: false,
      base_url: '',
    }
    queue.value = queueRes.success ? (queueRes.data || []) : []
  } catch (error) {
    message.error(`加载 MoviePilot 面板失败: ${error.message}`)
  } finally {
    loading.value = false
  }
}

const submitItem = async (item) => {
  submittingId.value = item.id
  try {
    const response = await fetch('/api/moviepilot/queue/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_id: item.id }),
    })
    const payload = await response.json()
    if (!response.ok || payload.success === false) {
      throw new Error(payload.message || payload.detail || '提交订阅失败')
    }

    message.success(`已提交订阅: ${formatItemName(item)}`)
    await loadPanel()
  } catch (error) {
    message.error(`提交订阅失败: ${error.message}`)
  } finally {
    submittingId.value = ''
  }
}

const formatTime = (timestamp) => {
  if (!timestamp) return '未知时间'
  return new Date(timestamp * 1000).toLocaleString()
}

const formatItemName = (item) => {
  if (!item) return '未命名任务'
  if (item.media_type === 'tv' && item.season) {
    return `${item.title} - Season ${item.season}${item.episode ? ` - E${String(item.episode).padStart(2, '0')}` : ''}`
  }
  return item.title || item.video_path || '未命名任务'
}

const formatReferenceProfile = (profile) => {
  if (!profile) return '无参考画像'
  const parts = [
    profile.team,
    profile.source,
    profile.resolution,
    profile.video_codec,
    profile.effect,
  ].filter(Boolean)
  return parts.length ? parts.join(' / ') : '无参考画像'
}

const getStatusColor = (statusValue) => {
  if (statusValue === 'downloading') return 'processing'
  if (statusValue === 'subscribed') return 'green'
  if (statusValue === 'failed') return 'red'
  return 'blue'
}

const getStatusText = (statusValue) => {
  if (statusValue === 'downloading') return '下载中'
  if (statusValue === 'subscribed') return '已订阅'
  if (statusValue === 'failed') return '提交失败'
  return '待提交'
}

onMounted(() => {
  loadPanel()
  timer = window.setInterval(loadPanel, 20000)
})

onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<style scoped>
.moviepilot-panel {
  max-width: 1180px;
  margin: 0 auto;
}

.moviepilot-shell {
  padding: 8px;
}

.panel-top,
.queue-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.panel-kicker {
  color: #2e7d66;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.panel-top h2,
.queue-head h3 {
  margin: 12px 0 8px;
  color: #173127;
}

.panel-top p,
.queue-head p {
  margin: 0;
  color: #507366;
}

.panel-alert {
  margin-top: 18px;
}

.summary-grid,
.board-grid {
  display: grid;
  gap: 18px;
  margin-top: 20px;
}

.summary-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.board-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.summary-tile,
.queue-card,
.board-card :deep(.ant-card-body) {
  border-radius: 20px;
}

.summary-tile {
  padding: 18px 20px;
  background: linear-gradient(180deg, rgba(232, 246, 241, 0.94), rgba(248, 253, 251, 0.94));
  border: 1px solid rgba(38, 117, 91, 0.1);
}

.summary-tile span,
.info-block span,
.summary-line span {
  display: block;
  color: #5b7d70;
  font-size: 12px;
}

.summary-tile strong,
.info-block strong,
.summary-line strong {
  display: block;
  margin-top: 8px;
  color: #173127;
  word-break: break-word;
}

.ok {
  color: #276e53;
}

.warn {
  color: #b4542f;
}

.muted {
  color: #68877a;
}

.summary-lines,
.reason-list {
  display: grid;
  gap: 12px;
}

.summary-line,
.reason-item {
  padding: 12px 0;
  border-bottom: 1px solid rgba(23, 49, 39, 0.08);
}

.summary-line:last-child,
.reason-item:last-child {
  border-bottom: 0;
}

.reason-item strong {
  color: #173127;
}

.reason-item p {
  margin: 6px 0 0;
  color: #5b7d70;
  line-height: 1.6;
}

.queue-head {
  margin-top: 24px;
}

.queue-list {
  display: grid;
  gap: 16px;
  margin-top: 16px;
}

.queue-card {
  border: 1px solid rgba(23, 49, 39, 0.08);
  background: rgba(253, 255, 254, 0.92);
}

.queue-card-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.queue-title {
  color: #173127;
  font-size: 18px;
  font-weight: 700;
}

.queue-subtitle {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 6px;
  color: #5b7d70;
  font-size: 13px;
}

.queue-info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px 18px;
  margin-top: 16px;
}

.info-block {
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(241, 248, 245, 0.92);
}

.queue-message {
  margin-top: 14px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(180, 84, 47, 0.12);
  color: #8d4428;
  line-height: 1.6;
}

.queue-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}

@media (max-width: 960px) {
  .panel-top,
  .queue-head,
  .queue-card-head,
  .queue-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .summary-grid,
  .board-grid,
  .queue-info-grid {
    grid-template-columns: 1fr;
  }
}
</style>
