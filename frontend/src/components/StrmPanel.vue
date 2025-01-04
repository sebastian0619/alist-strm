<template>
  <div class="strm-panel">
    <a-form :model="form" layout="vertical">
      <a-form-item label="扫描路径" required>
        <a-input v-model:value="form.path" placeholder="输入要扫描的路径" />
      </a-form-item>

      <a-form-item>
        <a-button type="primary" @click="generateStrm" :loading="loading">
          生成 STRM 文件
        </a-button>
      </a-form-item>
    </a-form>

    <a-divider>处理日志</a-divider>

    <div class="log-container" ref="logContainer">
      <pre v-for="(log, index) in logs" :key="index" :class="log.type">{{ log.message }}</pre>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { message } from 'ant-design-vue'

const form = ref({
  path: '/video'
})

const loading = ref(false)
const logs = ref([])
const logContainer = ref(null)

const addLog = (message, type = 'info') => {
  logs.value.push({ message, type })
  // 自动滚动到底部
  setTimeout(() => {
    if (logContainer.value) {
      logContainer.value.scrollTop = logContainer.value.scrollHeight
    }
  }, 100)
}

const generateStrm = async () => {
  if (!form.value.path) {
    message.warning('请输入扫描路径')
    return
  }

  loading.value = true
  logs.value = []
  addLog(`开始处理路径: ${form.value.path}`)

  try {
    const response = await fetch('/api/strm/start', {
      method: 'POST'
    })
    
    if (!response.ok) {
      throw new Error('请求失败')
    }
    
    const data = await response.json()
    if (data.code === 200) {
      addLog('STRM 文件生成成功', 'success')
      message.success('STRM 文件生成成功')
    } else {
      addLog(`处理失败: ${data.message}`, 'error')
      message.error('STRM 文件生成失败')
    }
  } catch (error) {
    addLog(`发生错误: ${error.message}`, 'error')
    message.error('操作失败: ' + error.message)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.strm-panel {
  max-width: 800px;
  margin: 0 auto;
}

.log-container {
  height: 400px;
  overflow-y: auto;
  background: #1e1e1e;
  border-radius: 4px;
  padding: 10px;
  font-family: monospace;
}

.log-container pre {
  margin: 0;
  padding: 5px 0;
  color: #fff;
}

.log-container .error {
  color: #ff4d4f;
}

.log-container .success {
  color: #52c41a;
}

.log-container .info {
  color: #8c8c8c;
}
</style> 