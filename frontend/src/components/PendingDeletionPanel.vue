<template>
  <div class="pending-deletion-panel">
    <a-card class="pending-shell" :bordered="false">
      <div class="panel-top">
        <div>
          <div class="panel-kicker">Deletion Queue</div>
          <h2>待删除队列</h2>
          <p>确认源路径、归档目标和迁移状态，避免误删仍在迁移中的目录。</p>
        </div>
        <a-button @click="loadPendingItems" :loading="loading">刷新列表</a-button>
      </div>

      <div class="summary-grid">
        <div class="summary-tile">
          <span>待删除项目</span>
          <strong>{{ pendingItems.length }}</strong>
        </div>
        <div class="summary-tile">
          <span>等待迁移确认</span>
          <strong>{{ waitingMoveCount }}</strong>
        </div>
        <div class="summary-tile">
          <span>已确认迁移</span>
          <strong>{{ confirmedMoveCount }}</strong>
        </div>
        <div class="summary-tile">
          <span>延迟天数</span>
          <strong>{{ delayDays }}</strong>
        </div>
      </div>

      <a-alert type="info" show-icon class="queue-alert">
        <template #message>
          当前共有 {{ pendingItems.length }} 个待删除项目。只有确认迁移完成后，队列才会进入实际删除。
        </template>
        <template #description>
          <div class="delay-editor">
            <span>调整延迟天数</span>
            <a-input-number v-model:value="newDelayDays" :min="1" :max="365" />
            <a-button type="primary" @click="updateDelayDays" :loading="updating">保存</a-button>
          </div>
        </template>
      </a-alert>

      <div class="bulk-actions">
        <a-space>
          <a-popconfirm title="确定要立即删除所有待删除项目吗？此操作不可撤销。" @confirm="deleteAllNow">
            <a-button type="primary" danger>立即删除全部</a-button>
          </a-popconfirm>
          <a-popconfirm title="确定要清空整个待删除列表吗？" @confirm="clearAllItems">
            <a-button>清空待删除列表</a-button>
          </a-popconfirm>
        </a-space>
      </div>

      <a-spin :spinning="loading">
        <a-empty v-if="pendingItems.length === 0" description="暂无待删除文件" />

        <div v-else class="queue-list">
          <a-card v-for="item in pendingItems" :key="`${item.path}-${item.timestamp}`" class="queue-card">
            <div class="queue-card-head">
              <div>
                <div class="queue-title">{{ item.name }}</div>
                <div class="queue-path">{{ item.path }}</div>
              </div>
              <div class="queue-tags">
                <a-tag :color="item.move_success ? 'green' : 'orange'">
                  {{ item.move_success ? '已确认迁移' : '等待迁移确认' }}
                </a-tag>
                <a-tag :color="getDaysColor(item.days_left)">剩余 {{ item.days_left }} 天</a-tag>
              </div>
            </div>

            <div class="queue-info-grid">
              <div class="info-block">
                <span>预计删除时间</span>
                <strong>{{ item.delete_time }}</strong>
              </div>
              <div class="info-block">
                <span>云盘源路径</span>
                <strong>{{ item.cloud_path || '未记录' }}</strong>
              </div>
              <div class="info-block">
                <span>归档目标路径</span>
                <strong>{{ item.archive_path || '未记录' }}</strong>
              </div>
            </div>

            <div class="queue-actions">
              <a-popconfirm title="确定要立即删除这个项目吗？" @confirm="deleteNow(item)">
                <a-button type="primary" danger>立即删除</a-button>
              </a-popconfirm>
              <a-popconfirm title="确定要取消这个项目的删除计划吗？" @confirm="removeItem(item)">
                <a-button>取消删除</a-button>
              </a-popconfirm>
            </div>
          </a-card>
        </div>
      </a-spin>
    </a-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'

const pendingItems = ref([])
const loading = ref(true)
const delayDays = ref(7)
const newDelayDays = ref(7)
const updating = ref(false)

const waitingMoveCount = computed(() => pendingItems.value.filter((item) => !item.move_success).length)
const confirmedMoveCount = computed(() => pendingItems.value.filter((item) => item.move_success).length)
const seasonPattern = /season\s*\d+|s\d+|第.+?季/i

onMounted(() => {
  loadPendingItems()
  loadDelayDays()
})

const loadPendingItems = async () => {
  loading.value = true
  try {
    const response = await fetch('/api/archive/pending-deletions')
    const data = await response.json()

    if (data.success) {
      pendingItems.value = (data.data || []).map((item) => {
        const deleteTimestamp = item.delete_time * 1000
        const deleteDate = new Date(deleteTimestamp)
        const now = new Date()
        const msPerDay = 24 * 60 * 60 * 1000

        return {
          ...item,
          name: formatItemName(item.path),
          delete_time: formatDate(deleteDate),
          days_left: Math.ceil((deleteTimestamp - now.getTime()) / msPerDay),
          timestamp: deleteTimestamp,
        }
      })
    } else {
      message.error(data.message || '加载待删除列表失败')
    }
  } catch (error) {
    message.error(`加载待删除列表失败: ${error.message}`)
  } finally {
    loading.value = false
  }
}

const loadDelayDays = async () => {
  try {
    const response = await fetch('/api/archive/deletion-delay')
    const data = await response.json()
    if (data.success) {
      delayDays.value = data.data.days
      newDelayDays.value = data.data.days
    }
  } catch (error) {
    console.error('加载延迟删除天数失败:', error)
  }
}

const updateDelayDays = async () => {
  if (!newDelayDays.value || newDelayDays.value < 1) {
    message.error('请输入大于等于 1 的天数')
    return
  }

  updating.value = true
  try {
    const response = await fetch('/api/archive/deletion-delay', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ days: newDelayDays.value }),
    })

    const data = await response.json()
    if (data.success) {
      delayDays.value = newDelayDays.value
      message.success('延迟删除天数已更新')
      await loadPendingItems()
    } else {
      message.error(data.message || '更新失败')
    }
  } catch (error) {
    message.error(`更新失败: ${error.message}`)
  } finally {
    updating.value = false
  }
}

const formatDate = (date) => {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day} ${hours}:${minutes}`
}

const formatItemName = (path) => {
  const parts = String(path || '').split('/').filter(Boolean)
  if (!parts.length) return path

  const leaf = parts[parts.length - 1]
  if (!seasonPattern.test(leaf)) {
    return leaf
  }

  const parent = parts[parts.length - 2]
  if (!parent) {
    return leaf
  }

  return `${parent} - ${leaf}`
}

const removeItem = async (item) => {
  loading.value = true
  try {
    const response = await fetch('/api/archive/clear-pending-deletion', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        path: item.path,
        delete_time: Math.floor(item.timestamp / 1000),
      }),
    })
    const data = await response.json()
    if (data.success) {
      message.success('已取消该删除计划')
      await loadPendingItems()
    } else {
      message.error(data.message || '操作失败')
    }
  } catch (error) {
    message.error(`操作失败: ${error.message}`)
  } finally {
    loading.value = false
  }
}

const getDaysColor = (days) => {
  if (days < 1) return 'red'
  if (days < 3) return 'orange'
  return 'green'
}

const deleteNow = async (item) => {
  loading.value = true
  try {
    const response = await fetch('/api/archive/delete-now', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        path: item.path,
        delete_time: Math.floor(item.timestamp / 1000),
      }),
    })
    const data = await response.json()
    if (data.success) {
      message.success('项目已立即删除')
      await loadPendingItems()
    } else {
      message.error(data.message || '删除失败')
    }
  } catch (error) {
    message.error(`删除失败: ${error.message}`)
  } finally {
    loading.value = false
  }
}

const deleteAllNow = async () => {
  loading.value = true
  try {
    const response = await fetch('/api/archive/delete-all-now', { method: 'POST' })
    const data = await response.json()
    if (data.success) {
      message.success(data.message || '已删除全部项目')
      await loadPendingItems()
    } else {
      const failedPreview = Array.isArray(data.failed_items) && data.failed_items.length
        ? `\n失败项示例:\n${data.failed_items.join('\n')}`
        : ''
      message.error(`${data.message || '删除失败'}${failedPreview}`)
      await loadPendingItems()
    }
  } catch (error) {
    message.error(`删除失败: ${error.message}`)
  } finally {
    loading.value = false
  }
}

const clearAllItems = async () => {
  loading.value = true
  try {
    const response = await fetch('/api/archive/clear-all-pending-deletions', { method: 'POST' })
    const data = await response.json()
    if (data.success) {
      message.success(data.message || '已清空待删除列表')
      await loadPendingItems()
    } else {
      message.error(data.message || '清空失败')
    }
  } catch (error) {
    message.error(`清空失败: ${error.message}`)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.pending-shell {
  padding: 8px;
}

.panel-top {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 20px;
}

.panel-kicker {
  color: #b4542f;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.panel-top h2 {
  margin: 10px 0 8px;
  font-size: 30px;
  color: #241d15;
}

.panel-top p {
  margin: 0;
  color: #665747;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.summary-tile {
  padding: 18px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(36, 29, 21, 0.06);
}

.summary-tile span {
  display: block;
  color: #766756;
  font-size: 13px;
}

.summary-tile strong {
  display: block;
  margin-top: 10px;
  color: #241d15;
  font-size: 34px;
}

.queue-alert {
  margin-bottom: 20px;
}

.delay-editor {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 10px;
}

.bulk-actions {
  margin-bottom: 20px;
}

.queue-list {
  display: grid;
  gap: 16px;
}

.queue-card {
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.56);
  border: 1px solid rgba(36, 29, 21, 0.06);
}

.queue-card-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.queue-title {
  color: #241d15;
  font-size: 18px;
  font-weight: 700;
}

.queue-path {
  margin-top: 6px;
  color: #665747;
  word-break: break-all;
}

.queue-tags {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.queue-info-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-top: 18px;
}

.info-block {
  padding: 14px;
  border-radius: 16px;
  background: rgba(250, 246, 239, 0.9);
}

.info-block span {
  display: block;
  color: #8d7d6d;
  font-size: 12px;
  margin-bottom: 8px;
}

.info-block strong {
  color: #2b2017;
  word-break: break-all;
}

.queue-actions {
  display: flex;
  gap: 10px;
  margin-top: 18px;
}

@media (max-width: 1100px) {
  .summary-grid,
  .queue-info-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .panel-top,
  .queue-card-head,
  .queue-actions {
    flex-direction: column;
  }

  .summary-grid,
  .queue-info-grid {
    grid-template-columns: 1fr;
  }

  .queue-tags {
    justify-content: flex-start;
  }
}
</style>
