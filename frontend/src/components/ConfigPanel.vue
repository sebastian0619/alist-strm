<template>
  <div class="config-panel">
    <el-form :model="config" label-width="180px">
      <el-form-item label="运行模式">
        <el-switch
          v-model="config.run_after_startup"
          active-text="启动时执行"
          inactive-text="手动执行"
        />
      </el-form-item>

      <el-form-item label="日志级别">
        <el-select v-model="config.log_level">
          <el-option label="DEBUG" value="DEBUG" />
          <el-option label="INFO" value="INFO" />
          <el-option label="WARNING" value="WARNING" />
          <el-option label="ERROR" value="ERROR" />
        </el-select>
      </el-form-item>

      <el-form-item label="慢速模式">
        <el-switch
          v-model="config.slow_mode"
          active-text="开启"
          inactive-text="关闭"
        />
      </el-form-item>

      <el-divider>Alist 配置</el-divider>

      <el-form-item label="Alist 服务器地址">
        <el-input v-model="config.alist_url" placeholder="http://localhost:5244" />
      </el-form-item>

      <el-form-item label="Alist Token">
        <el-input v-model="config.alist_token" type="password" show-password />
      </el-form-item>

      <el-form-item label="扫描路径">
        <el-input v-model="config.alist_scan_path" placeholder="/path/to/scan" />
      </el-form-item>

      <el-divider>文件处理配置</el-divider>

      <el-form-item label="URL编码">
        <el-switch
          v-model="config.encode"
          active-text="开启"
          inactive-text="关闭"
        />
      </el-form-item>

      <el-form-item label="下载字幕">
        <el-switch
          v-model="config.is_down_sub"
          active-text="开启"
          inactive-text="关闭"
        />
      </el-form-item>

      <el-form-item label="最小文件大小(MB)">
        <el-input-number v-model="config.min_file_size" :min="0" />
      </el-form-item>

      <el-form-item label="输出目录">
        <el-input v-model="config.output_dir" placeholder="data" />
      </el-form-item>

      <el-form-item>
        <el-button type="primary" @click="saveConfig">保存配置</el-button>
        <el-button @click="loadConfig">加载配置</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

const config = ref({
  run_after_startup: true,
  log_level: 'INFO',
  slow_mode: false,
  alist_url: 'http://localhost:5244',
  alist_token: '',
  alist_scan_path: '/115/video',
  encode: true,
  is_down_sub: false,
  min_file_size: 100,
  output_dir: 'data'
})

const loadConfig = async () => {
  try {
    const response = await axios.get('/api/config')
    config.value = response.data
    ElMessage.success('配置加载成功')
  } catch (error) {
    ElMessage.error('配置加载失败: ' + error.message)
  }
}

const saveConfig = async () => {
  try {
    await axios.post('/api/config', config.value)
    ElMessage.success('配置保存成功')
  } catch (error) {
    ElMessage.error('配置保存失败: ' + error.message)
  }
}

onMounted(() => {
  loadConfig()
})
</script>

<style scoped>
.config-panel {
  max-width: 800px;
  margin: 0 auto;
}
</style> 