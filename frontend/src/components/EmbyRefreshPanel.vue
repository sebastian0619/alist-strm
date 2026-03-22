<template>
  <div class="emby-monitor-panel">
    <a-card class="monitor-shell" :bordered="false">
      <div class="monitor-top">
        <div>
          <div class="monitor-kicker">Media Library Watch</div>
          <h2>Emby 监控</h2>
          <p>把最近扫描、最近刷新、候选项目和 Emby 日志集中在一个页面里处理。</p>
        </div>
        <a-space>
          <a-button @click="loadMonitor" :loading="monitorLoading">刷新监控</a-button>
          <a-button type="primary" @click="scanLatestItems" :loading="scanningLatest" :disabled="!embyEnabled">
            扫描最近项目
          </a-button>
        </a-space>
      </div>

      <a-alert
        v-if="!embyEnabled"
        type="warning"
        banner
        message="Emby 刷库功能未启用"
        description="请先在基本配置中启用 Emby，并填写 API 地址与密钥。"
        class="monitor-alert"
      />

      <div class="monitor-grid">
        <div class="status-tile">
          <span>服务状态</span>
          <strong :class="embyEnabled ? 'ok' : 'warn'">{{ embyEnabled ? '已启用' : '未启用' }}</strong>
          <p>{{ monitorData.api_url || '未配置 Emby API 地址' }}</p>
        </div>
        <div class="status-tile">
          <span>最近扫描</span>
          <strong>{{ monitorData.last_scan?.time || '暂无记录' }}</strong>
          <p>最近 {{ monitorData.last_scan?.hours || '-' }} 小时，共 {{ monitorData.last_scan?.summary?.total_found || 0 }} 个项目</p>
        </div>
        <div class="status-tile">
          <span>STRM 命中</span>
          <strong>{{ monitorData.last_scan?.summary?.strm_count || 0 }}</strong>
          <p>最近一次 Emby 扫描中识别为 STRM 路径的项目数量。</p>
        </div>
        <div class="status-tile">
          <span>最近刷新</span>
          <strong>{{ monitorData.last_refresh?.count || 0 }}</strong>
          <p>{{ monitorData.last_refresh?.time || '还没有刷新记录' }}</p>
        </div>
      </div>

      <div class="monitor-board">
        <a-card class="board-card" title="最近扫描候选" :bordered="false">
          <template #extra>
            <a-space>
              <a-button size="small" @click="selectAllItems" :disabled="allSelected || scanResults.items.length === 0">全选</a-button>
              <a-button size="small" @click="deselectAllItems" :disabled="noneSelected || scanResults.items.length === 0">清空</a-button>
              <a-button
                type="primary"
                size="small"
                @click="refreshSelectedItems"
                :loading="refreshing"
                :disabled="selectedItems.length === 0"
              >
                刷新选中项
              </a-button>
            </a-space>
          </template>

          <a-empty v-if="scanResults.items.length === 0" description="还没有扫描结果" />
          <div v-else class="scan-list">
            <div v-for="item in scanResults.items" :key="item.id" class="scan-item">
              <div class="scan-item-head">
                <a-checkbox v-model:checked="item.selected" @change="updateSelectedCount" />
                <div class="scan-item-title">
                  <strong>{{ item.name }}</strong>
                  <span>{{ item.created }}</span>
                </div>
                <a-space>
                  <a-tag :color="getEmbyTypeColor(item.type ? item.type.toLowerCase() : 'unknown')">
                    {{ getEmbyTypeLabel(item.type ? item.type.toLowerCase() : 'unknown') }}
                  </a-tag>
                  <a-tag :color="item.is_strm ? 'green' : 'gold'">{{ item.is_strm ? 'STRM' : '普通' }}</a-tag>
                </a-space>
              </div>
              <div class="scan-item-path">{{ item.path || '无路径' }}</div>
              <div class="scan-item-meta">
                <span>{{ item.year || '未知年份' }}</span>
                <span>{{ item.hoursAgo }} 小时前</span>
              </div>
            </div>
          </div>
        </a-card>

        <a-card class="board-card" title="最近刷新记录" :bordered="false">
          <template #extra>
            <a-dropdown>
              <template #overlay>
                <a-menu>
                  <a-menu-item key="remove-tag" @click="showTagRemoveModal">
                    删除标签
                  </a-menu-item>
                </a-menu>
              </template>
              <a-button size="small">
                更多功能
                <DownOutlined />
              </a-button>
            </a-dropdown>
          </template>

          <a-empty
            v-if="refreshResults.refreshed_items.length === 0 && !(monitorData.last_refresh?.items || []).length"
            description="没有刷新记录"
          />
          <div v-else class="refresh-list">
            <div
              v-for="item in displayRefreshItems"
              :key="item.id"
              class="refresh-item"
            >
              <a-tag :color="getEmbyTypeColor(item.type ? item.type.toLowerCase() : 'unknown')">
                {{ getEmbyTypeLabel(item.type ? item.type.toLowerCase() : 'unknown') }}
              </a-tag>
              <span>{{ item.name }}</span>
            </div>
          </div>
        </a-card>
      </div>

      <div class="monitor-board bottom-board">
        <a-card class="board-card" title="最近扫描摘要" :bordered="false">
          <div class="summary-lines">
            <div class="summary-line">
              <span>扫描时间</span>
              <strong>{{ monitorData.last_scan?.time || '暂无记录' }}</strong>
            </div>
            <div class="summary-line">
              <span>扫描窗口</span>
              <strong>{{ monitorData.last_scan?.hours || '-' }} 小时</strong>
            </div>
            <div class="summary-line">
              <span>项目数量</span>
              <strong>{{ monitorData.last_scan?.count || 0 }}</strong>
            </div>
            <div class="summary-line">
              <span>路径映射</span>
              <strong>{{ monitorData.strm_root_path || '未配置' }} -> {{ monitorData.emby_root_path || '未配置' }}</strong>
            </div>
          </div>
        </a-card>

        <a-card class="board-card" title="Emby 相关日志" :bordered="false">
          <a-empty v-if="recentLogs.length === 0" description="暂无 Emby 日志" />
          <div v-else class="log-list">
            <div v-for="(log, index) in recentLogs" :key="index" class="log-item">{{ log }}</div>
          </div>
        </a-card>
      </div>
    </a-card>

    <a-modal
      v-model:visible="tagRemoveModalVisible"
      title="删除 Emby 标签"
      :confirm-loading="removingTag"
      @ok="removeTag"
      okText="删除"
      cancelText="取消"
    >
      <a-form :model="tagRemoveForm" layout="vertical">
        <a-form-item
          label="标签名称"
          name="tagName"
          help="将从所有电影和剧集中删除这个标签。"
        >
          <a-input v-model:value="tagRemoveForm.tagName" placeholder="输入要删除的标签名称" allow-clear />
        </a-form-item>
        <a-alert type="warning" message="此操作不可逆，请确认标签名称无误。" />
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { notification } from 'ant-design-vue'
import { DownOutlined } from '@ant-design/icons-vue'
import axios from 'axios'

const embyEnabled = ref(false)
const monitorLoading = ref(false)
const scanningLatest = ref(false)
const refreshing = ref(false)
const monitorData = ref({
  enabled: false,
  api_url: '',
  strm_root_path: '',
  emby_root_path: '',
  last_refresh: { items: [] },
  last_scan: { summary: {}, items: [] },
  recent_logs: [],
})

const scanResults = ref({ items: [] })
const refreshResults = ref({ refreshed_items: [] })
const selectedItems = ref([])

const tagRemoveModalVisible = ref(false)
const removingTag = ref(false)
const tagRemoveForm = ref({ tagName: '' })
let monitorTimer = null

const recentLogs = computed(() => monitorData.value.recent_logs || [])
const displayRefreshItems = computed(() => {
  if (refreshResults.value.refreshed_items?.length) return refreshResults.value.refreshed_items
  return monitorData.value.last_refresh?.items || []
})

const allSelected = computed(() => scanResults.value.items.length > 0 && scanResults.value.items.every((item) => item.selected))
const noneSelected = computed(() => scanResults.value.items.length === 0 || scanResults.value.items.every((item) => !item.selected))

const updateSelectedCount = () => {
  selectedItems.value = scanResults.value.items.filter((item) => item.selected)
}

const selectAllItems = () => {
  scanResults.value.items.forEach((item) => {
    item.selected = true
  })
  updateSelectedCount()
}

const deselectAllItems = () => {
  scanResults.value.items.forEach((item) => {
    item.selected = false
  })
  updateSelectedCount()
}

const loadMonitor = async () => {
  monitorLoading.value = true
  try {
    const response = await axios.get('/api/health/emby/monitor?limit=20')
    const payload = response.data?.data || {}
    monitorData.value = payload
    embyEnabled.value = payload.enabled === true

    if (!scanResults.value.items.length && Array.isArray(payload.last_scan?.items)) {
      scanResults.value = {
        items: payload.last_scan.items.map((item) => ({
          ...item,
          selected: Boolean(item.selected),
        })),
      }
      updateSelectedCount()
    }
  } catch (error) {
    console.error('加载 Emby 监控失败:', error)
    notification.error({
      message: '加载监控失败',
      description: error.message,
    })
    embyEnabled.value = false
  } finally {
    monitorLoading.value = false
  }
}

const scanLatestItems = async () => {
  scanningLatest.value = true
  try {
    const response = await axios.post('/api/health/emby/scan?hours=12')
    if (response.data.success) {
      scanResults.value = {
        items: (response.data.items || []).map((item) => ({
          ...item,
          selected: Boolean(item.selected),
        })),
      }
      updateSelectedCount()
      notification.success({
        message: '扫描完成',
        description: response.data.message,
      })
      await loadMonitor()
    } else {
      notification.error({
        message: '扫描失败',
        description: response.data.message || '请求成功但返回错误',
      })
    }
  } catch (error) {
    notification.error({
      message: '扫描失败',
      description: error.message,
    })
  } finally {
    scanningLatest.value = false
  }
}

const refreshSelectedItems = async () => {
  if (!selectedItems.value.length) {
    notification.warning({
      message: '未选择项目',
      description: '请至少选择一个项目进行刷新。',
    })
    return
  }

  refreshing.value = true
  try {
    const response = await axios.post('/api/health/emby/refresh', {
      item_ids: selectedItems.value.map((item) => item.id),
    })

    if (response.data.success) {
      refreshResults.value = response.data
      notification.success({
        message: '刷新完成',
        description: response.data.message,
      })
      await loadMonitor()
    } else {
      notification.error({
        message: '刷新失败',
        description: response.data.message || '请求成功但返回错误',
      })
    }
  } catch (error) {
    notification.error({
      message: '刷新失败',
      description: error.message,
    })
  } finally {
    refreshing.value = false
  }
}

const showTagRemoveModal = () => {
  tagRemoveModalVisible.value = true
}

const removeTag = async () => {
  if (!tagRemoveForm.value.tagName.trim()) {
    notification.warning({
      message: '请输入标签名称',
      description: '标签名称不能为空。',
    })
    return
  }

  removingTag.value = true
  try {
    const response = await axios.post('/api/health/emby/tags/remove', {
      tag_name: tagRemoveForm.value.tagName.trim(),
    })
    if (response.data.success) {
      notification.success({
        message: '标签删除完成',
        description: response.data.message,
      })
      tagRemoveModalVisible.value = false
      tagRemoveForm.value.tagName = ''
      await loadMonitor()
    } else {
      notification.error({
        message: '标签删除失败',
        description: response.data.message || '请求成功但返回错误',
      })
    }
  } catch (error) {
    notification.error({
      message: '标签删除失败',
      description: error.message,
    })
  } finally {
    removingTag.value = false
  }
}

const getEmbyTypeColor = (type) => {
  const colorMap = {
    movie: 'blue',
    series: 'purple',
    season: 'magenta',
    episode: 'cyan',
    unknown: 'default',
  }
  return colorMap[type] || 'default'
}

const getEmbyTypeLabel = (type) => {
  const labelMap = {
    movie: '电影',
    series: '剧集',
    season: '季',
    episode: '集',
    unknown: '未知',
  }
  return labelMap[type] || '未知'
}

onMounted(() => {
  loadMonitor()
  monitorTimer = window.setInterval(loadMonitor, 30000)
})

onBeforeUnmount(() => {
  if (monitorTimer) {
    window.clearInterval(monitorTimer)
  }
})
</script>

<style scoped>
.monitor-shell {
  padding: 8px;
}

.monitor-top {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: flex-start;
  margin-bottom: 20px;
}

.monitor-kicker {
  color: #b4542f;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.monitor-top h2 {
  margin: 10px 0 8px;
  font-size: 30px;
  color: #241d15;
}

.monitor-top p {
  margin: 0;
  color: #665747;
}

.monitor-alert {
  margin-bottom: 20px;
}

.monitor-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.status-tile {
  padding: 18px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.58);
  border: 1px solid rgba(36, 29, 21, 0.06);
}

.status-tile span {
  display: block;
  color: #766756;
  font-size: 13px;
}

.status-tile strong {
  display: block;
  margin-top: 10px;
  color: #241d15;
  font-size: 28px;
}

.status-tile p {
  margin: 10px 0 0;
  color: #665747;
  line-height: 1.5;
}

.ok {
  color: #4d6b2d;
}

.warn {
  color: #b4542f;
}

.monitor-board {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  margin-bottom: 18px;
}

.board-card {
  min-height: 420px;
}

.scan-list,
.refresh-list,
.log-list {
  display: grid;
  gap: 12px;
}

.scan-item,
.refresh-item,
.log-item {
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.58);
  border: 1px solid rgba(36, 29, 21, 0.06);
}

.scan-item-head {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 12px;
  align-items: center;
}

.scan-item-title strong {
  display: block;
  color: #241d15;
}

.scan-item-title span {
  color: #8d7d6d;
  font-size: 12px;
}

.scan-item-path {
  margin-top: 12px;
  color: #665747;
  word-break: break-all;
}

.scan-item-meta {
  display: flex;
  gap: 12px;
  margin-top: 10px;
  color: #8d7d6d;
  font-size: 12px;
}

.refresh-item {
  display: flex;
  gap: 10px;
  align-items: center;
}

.summary-lines {
  display: grid;
  gap: 14px;
}

.summary-line {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(36, 29, 21, 0.08);
}

.summary-line:last-child {
  border-bottom: 0;
}

.summary-line span {
  color: #766756;
}

.summary-line strong {
  color: #241d15;
  text-align: right;
}

.log-item {
  color: #5d5145;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
}

@media (max-width: 1200px) {
  .monitor-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .monitor-board {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .monitor-top,
  .scan-item-head {
    grid-template-columns: 1fr;
    flex-direction: column;
  }

  .monitor-top {
    display: flex;
  }

  .monitor-grid {
    grid-template-columns: 1fr;
  }
}
</style>
