<template>
  <div class="strm-panel">
    <el-form :model="form" label-width="120px">
      <el-form-item label="扫描路径">
        <el-input v-model="form.path" placeholder="输入要扫描的路径" />
      </el-form-item>

      <el-form-item>
        <el-button type="primary" @click="generateStrm" :loading="loading">
          生成 STRM 文件
        </el-button>
      </el-form-item>
    </el-form>

    <el-divider>处理日志</el-divider>

    <div class="log-container" ref="logContainer">
      <pre v-for="(log, index) in logs" :key="index" :class="log.type">{{ log.message }}</pre>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

const form = ref({
  path: '/115/video'
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
    ElMessage.warning('请输入扫描路径')
    return
  }

  loading.value = true
  logs.value = []
  addLog(`开始处理路径: ${form.value.path}`)

  try {
    const response = await axios.post('/api/strm/generate', {
      path: form.value.path
    })
    
    if (response.data.success) {
      addLog('STRM 文件生成成功', 'success')
      ElMessage.success('STRM 文件生成成功')
    } else {
      addLog(`处理失败: ${response.data.message}`, 'error')
      ElMessage.error('STRM 文件生成失败')
    }
  } catch (error) {
    addLog(`发生错误: ${error.message}`, 'error')
    ElMessage.error('操作失败: ' + error.message)
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
  color: #ff4949;
}

.log-container .success {
  color: #67c23a;
}

.log-container .info {
  color: #909399;
}
</style> 