<template>
  <div class="container">
    <a-tabs v-model:activeKey="activeKey">
      <a-tab-pane key="1" tab="配置">
        <config-panel @scan-started="showLogModal" />
      </a-tab-pane>
    </a-tabs>

    <!-- 日志弹窗 -->
    <a-modal
      v-model:visible="logModalVisible"
      title="扫描日志"
      :footer="null"
      width="800px"
      :maskClosable="false"
    >
      <div class="log-container">
        <pre>{{ logs }}</pre>
      </div>
    </a-modal>
  </div>
</template>

<script>
import { ref } from 'vue'
import ConfigPanel from './components/ConfigPanel.vue'

export default {
  components: {
    ConfigPanel
  },
  setup() {
    const activeKey = ref('1')
    const logModalVisible = ref(false)
    const logs = ref('')

    const showLogModal = () => {
      logModalVisible.value = true
      logs.value = '开始扫描...\n'
      // 开始轮询日志
      pollLogs()
    }

    const pollLogs = async () => {
      try {
        const response = await fetch('/api/strm/logs')
        const data = await response.text()
        logs.value = data
        
        // 如果弹窗还在显示，继续轮询
        if (logModalVisible.value) {
          setTimeout(pollLogs, 1000)
        }
      } catch (error) {
        console.error('获取日志失败:', error)
      }
    }

    return {
      activeKey,
      logModalVisible,
      logs,
      showLogModal
    }
  }
}
</script>

<style scoped>
.container {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.log-container {
  max-height: 500px;
  overflow-y: auto;
  background-color: #1e1e1e;
  color: #fff;
  padding: 10px;
  border-radius: 4px;
  font-family: monospace;
}

.log-container pre {
  margin: 0;
  white-space: pre-wrap;
  word-wrap: break-word;
}
</style> 