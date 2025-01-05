<template>
  <div class="app-container">
    <a-layout>
      <a-layout-header class="header">
        <h1>Alist STRM 配置</h1>
      </a-layout-header>
      <a-layout-content class="main-content">
        <config-panel @scan-started="showLogModal" />
      </a-layout-content>
    </a-layout>

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
        if (response.ok) {
          const text = await response.text()
          logs.value = text || '暂无日志'
        }
      } catch (e) {
        console.error('获取日志失败:', e)
      }
      
      // 如果弹窗可见，继续轮询
      if (logModalVisible.value) {
        setTimeout(pollLogs, 1000)  // 每秒轮询一次
      }
    }

    // 监听弹窗关闭
    const closeLogModal = () => {
      logModalVisible.value = false
      logs.value = ''
    }

    return {
      logModalVisible,
      logs,
      showLogModal,
      closeLogModal
    }
  }
}
</script>

<style>
.app-container {
  min-height: 100vh;
  background-color: #f0f2f5;
}

.header {
  background: #fff;
  padding: 0;
  text-align: center;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.header h1 {
  margin: 0;
  line-height: 64px;
  color: #1890ff;
}

.main-content {
  padding: 24px;
  min-height: calc(100vh - 64px);
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