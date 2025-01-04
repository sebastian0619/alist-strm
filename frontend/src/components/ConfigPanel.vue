<template>
  <div class="config-panel">
    <div v-if="error" class="error-message">
      <a-alert
        :message="error"
        type="error"
        show-icon
        closable
        @close="error = ''"
      />
    </div>

    <a-card title="Alist STRM 配置" :bordered="false">
      <!-- 运行模式配置 -->
      <a-divider>运行模式</a-divider>
      <a-form-item label="运行模式">
        <a-switch
          v-model:checked="config.run_after_startup"
          :checked-children="'启动时执行'"
          :un-checked-children="'手动执行'"
        />
        <a-tooltip>
          <template #title>
            启动时执行：程序启动后自动开始扫描
            手动执行：需要手动点击开始按钮
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>

      <a-form-item label="日志级别">
        <a-select v-model:value="config.log_level" style="width: 100%">
          <a-select-option value="INFO">INFO</a-select-option>
          <a-select-option value="DEBUG">DEBUG</a-select-option>
          <a-select-option value="WARNING">WARNING</a-select-option>
          <a-select-option value="ERROR">ERROR</a-select-option>
        </a-select>
        <a-tooltip>
          <template #title>
            DEBUG: 显示所有日志
            INFO: 显示一般信息
            WARNING: 只显示警告和错误
            ERROR: 只显示错误
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>

      <a-form-item label="慢速模式">
        <a-switch
          v-model:checked="config.slow_mode"
          :checked-children="'开启'"
          :un-checked-children="'关闭'"
        />
        <a-tooltip>
          <template #title>
            开启后会在处理文件之间添加延迟，减轻服务器负担
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>

      <!-- 基本配置 -->
      <a-divider>基本配置</a-divider>
      <a-form-item label="启动时自动运行">
        <a-switch v-model:checked="config.run_after_startup" />
        <a-tooltip>
          <template #title>
            容器启动时是否自动开始扫描
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>
      <a-form-item label="慢速模式">
        <a-switch v-model:checked="config.slow_mode" />
        <a-tooltip>
          <template #title>
            启用后会降低扫描速度，减少对系统资源的占用
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>
      <a-form-item label="日志级别">
        <a-select v-model:value="config.log_level">
          <a-select-option value="DEBUG">DEBUG</a-select-option>
          <a-select-option value="INFO">INFO</a-select-option>
          <a-select-option value="WARNING">WARNING</a-select-option>
          <a-select-option value="ERROR">ERROR</a-select-option>
        </a-select>
      </a-form-item>

      <!-- 定时任务配置 -->
      <a-divider>定时任务配置</a-divider>
      <a-form-item label="启用定时扫描">
        <a-switch v-model:checked="config.schedule_enabled" />
        <a-tooltip>
          <template #title>
            是否启用定时自动扫描功能
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>
      <a-form-item 
        label="定时表达式" 
        :help="getCronDescription(config.schedule_cron)"
      >
        <a-input 
          v-model:value="config.schedule_cron" 
          placeholder="Cron表达式，例如: 0 */6 * * * (每6小时执行一次)"
          :disabled="!config.schedule_enabled"
        />
        <a-tooltip>
          <template #title>
            Cron表达式格式：分 时 日 月 星期
            例如：
            0 */6 * * * (每6小时执行一次)
            0 0 * * * (每天0点执行)
            0 */12 * * * (每12小时执行一次)
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>

      <!-- Alist配置 -->
      <a-divider>Alist 配置</a-divider>
      <a-form-item label="Alist 服务器地址" required>
        <a-input
          v-model:value="config.alist_url"
          placeholder="http://localhost:5244"
        />
        <a-button 
          type="link" 
          :loading="testingConnection"
          @click="testConnection"
          style="margin-left: 8px"
        >
          测试连接
        </a-button>
      </a-form-item>

      <a-form-item label="Alist Token">
        <a-input-password
          v-model:value="config.alist_token"
          placeholder="请输入Alist Token"
        />
        <a-tooltip>
          <template #title>
            在Alist管理面板中获取，用于访问需要认证的文件
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>

      <a-form-item label="扫描路径" required>
        <a-input
          v-model:value="config.alist_scan_path"
          placeholder="/path/to/scan"
        />
        <a-tooltip>
          <template #title>
            需要生成STRM文件的Alist目录路径
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>

      <!-- 文件处理配置 -->
      <a-divider>文件处理配置</a-divider>
      <a-form-item label="URL编码">
        <a-switch
          v-model:checked="config.encode"
          :checked-children="'开启'"
          :un-checked-children="'关闭'"
        />
        <a-tooltip>
          <template #title>
            对URL进行编码，解决中文路径问题
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>

      <a-form-item label="下载字幕">
        <a-switch
          v-model:checked="config.is_down_sub"
          :checked-children="'开启'"
          :un-checked-children="'关闭'"
        />
        <a-tooltip>
          <template #title>
            自动下载视频对应的字幕文件
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>

      <a-form-item label="下载元数据">
        <a-switch
          v-model:checked="config.is_down_meta"
          :checked-children="'开启'"
          :un-checked-children="'关闭'"
        />
        <a-tooltip>
          <template #title>
            下载NFO、海报等媒体元数据文件
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>

      <a-form-item label="最小文件大小(MB)">
        <a-input-number
          v-model:value="config.min_file_size"
          :min="0"
          style="width: 100%"
        />
        <a-tooltip>
          <template #title>
            小于此大小的视频文件将被忽略
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>

      <a-form-item label="输出目录" required>
        <a-input
          v-model:value="config.output_dir"
          placeholder="data"
        />
        <a-tooltip>
          <template #title>
            生成的STRM文件保存位置
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>

      <!-- 按钮组 -->
      <div class="button-group">
        <a-button 
          type="primary" 
          @click="saveConfig" 
          :loading="saving"
          :disabled="!hasChanges"
        >
          保存配置
        </a-button>
        <a-button 
          @click="loadConfig" 
          :loading="loading" 
          style="margin-left: 8px"
        >
          重新加载
        </a-button>
        <a-button 
          type="primary"
          :loading="scanning"
          @click="scanning ? stopScan() : startScan()"
          style="margin-left: 16px"
          :danger="scanning"
        >
          {{ scanning ? '停止扫描' : '开始扫描' }}
        </a-button>
      </div>
    </a-card>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, onUnmounted } from 'vue'
import { InfoCircleOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { ref, onMounted } from 'vue';
import { message } from 'ant-design-vue';
import axios from 'axios';

const config = ref({})
const error = ref('')
const loading = ref(false)
const saving = ref(false)
const scanning = ref(false)

// 检查配置是否有变更
const hasChanges = ref(false)
const originalConfig = ref({})

const checkChanges = () => {
  const currentConfig = JSON.stringify(config.value)
  const originalConfigStr = JSON.stringify(originalConfig.value)
  hasChanges.value = currentConfig !== originalConfigStr
}

// 监听配置变化
const watchConfig = () => {
  const handler = () => {
    checkChanges()
  }
  // 为每个配置项添加监听
  Object.keys(config.value).forEach(key => {
    watch(() => config.value[key], handler)
  })
}

const loadConfig = async () => {
  loading.value = true
  error.value = ''
  try {
    const response = await fetch('/api/config')
    if (!response.ok) {
      throw new Error(`配置加载失败: ${response.statusText}`)
    }
    const data = await response.json()
    if (data.code === 200) {
      // 使用后端返回的配置
      config.value = data.data
      // 保存原始配置用于比较
      originalConfig.value = { ...config.value }
      hasChanges.value = false
      message.success('配置加载成功')
    } else {
      throw new Error(data.message || '配置加载失败')
    }
  } catch (err) {
    error.value = `配置加载失败: ${err.message}`
    message.error(error.value)
  } finally {
    loading.value = false
  }
}

const saveConfig = async () => {
  // 验证配置
  if (!validateConfig()) {
    return
  }

  saving.value = true
  error.value = ''
  try {
    // 保存每个配置项
    for (const [key, value] of Object.entries(config.value)) {
      if (JSON.stringify(value) !== JSON.stringify(originalConfig.value[key])) {
        const response = await fetch('/api/config', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            key: key,
            value: value
          })
        })
        
        if (!response.ok) {
          throw new Error(`保存配置 ${key} 失败: ${response.statusText}`)
        }
        
        const data = await response.json()
        if (!data.message) {
          throw new Error(data.message || `保存配置 ${key} 失败`)
        }
      }
    }
    
    // 更新原始配置
    originalConfig.value = { ...config.value }
    hasChanges.value = false
    message.success('配置保存成功')
    
    // 如果定时任务配置发生变化，显示提示信息
    if (config.value.schedule_enabled) {
      message.info(`定时任务已设置为${getCronDescription(config.value.schedule_cron)}`)
    }
  } catch (err) {
    error.value = `配置保存失败: ${err.message}`
    message.error(error.value)
  } finally {
    saving.value = false
  }
}

// 测试Alist连接
const testingConnection = ref(false)
const testConnection = async () => {
  if (!config.value.alist_url) {
    message.error('请先输入Alist服务器地址')
    return
  }

  testingConnection.value = true
  try {
    const response = await fetch('/api/test_connection', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        url: config.value.alist_url,
        token: config.value.alist_token
      })
    })
    
    if (!response.ok) {
      throw new Error('连接测试失败')
    }
    
    const data = await response.json()
    if (data.code === 200) {
      message.success('Alist连接测试成功')
    } else {
      throw new Error(data.message || '连接测试失败')
    }
  } catch (err) {
    message.error(`Alist连接测试失败: ${err.message}`)
  } finally {
    testingConnection.value = false
  }
}

// 验证配置
const validateConfig = () => {
  if (!config.value.alist_url) {
    message.error('请输入Alist服务器地址')
    return false
  }
  if (!config.value.alist_url.startsWith('http://') && !config.value.alist_url.startsWith('https://')) {
    message.error('Alist服务器地址必须以http://或https://开头')
    return false
  }
  if (!config.value.alist_token) {
    message.warning('未设置Alist Token可能会导致访问受限')
  }
  if (!config.value.alist_scan_path) {
    message.error('请输入扫描路径')
    return false
  }
  if (!config.value.output_dir) {
    message.error('请输入输出目录')
    return false
  }
  
  // 验证定时任务配置
  if (config.value.schedule_enabled && !validateCron(config.value.schedule_cron)) {
    message.error('请输入有效的Cron表达式')
    return false
  }
  
  return true
}

// 验证Cron表达式
const validateCron = (cron) => {
  if (!cron) return false
  const parts = cron.split(' ')
  if (parts.length !== 5) return false
  
  // 简单的格式验证，实际应用中可能需要更复杂的验证
  const cronRegex = /^[0-9*/,-]+\s[0-9*/,-]+\s[0-9*/,-]+\s[0-9*/,-]+\s[0-9*/,-]+$/
  return cronRegex.test(cron)
}

const startScan = async () => {
  if (!validateConfig()) {
    return
  }
  
  try {
    const response = await fetch('/api/strm/start', { method: 'POST' })
    if (response.ok) {
      message.success('扫描已开始')
      scanning.value = true
      emit('scan-started')
    } else {
      const data = await response.json()
      message.error(data.detail || '启动扫描失败')
    }
  } catch (error) {
    console.error('启动扫描失败:', error)
    message.error('启动扫描失败')
  }
}

const stopScan = async () => {
  try {
    const response = await fetch('/api/strm/stop', { method: 'POST' })
    if (response.ok) {
      message.success('正在停止扫描')
      scanning.value = false
    } else {
      const data = await response.json()
      message.error(data.detail || '停止扫描失败')
    }
  } catch (error) {
    console.error('停止扫描失败:', error)
    message.error('停止扫描失败')
  }
}

// 检查扫描状态
const checkScanStatus = async () => {
  try {
    const response = await fetch('/api/strm/status')
    if (!response.ok) {
      return
    }
    const data = await response.json()
    scanning.value = data.status === 'scanning'
  } catch (err) {
    console.error('检查扫描状态失败:', err)
  }
}

function getCronDescription(cron) {
  // 简单的cron表达式说明
  const parts = cron.split(' ');
  if (parts.length !== 5) return '无效的cron表达式';

  let desc = '';
  if (parts[1].includes('*/')) {
    const hours = parts[1].replace('*/', '');
    desc = `每${hours}小时执行一次`;
  } else if (parts[1] === '0' && parts[2] === '*') {
    desc = '每天0点执行';
  } else {
    desc = '自定义执行时间';
  }
  return desc;
}

onMounted(() => {
  // 组件加载时立即获取配置和扫描状态
  loadConfig()
  watchConfig()
  checkScanStatus()
  
  // 定期检查扫描状态
  const statusInterval = setInterval(checkScanStatus, 5000)
  
  // 组件卸载时清理定时器
  onUnmounted(() => {
    clearInterval(statusInterval)
  })
})
</script>

<style scoped>
.config-panel {
  max-width: 800px;
  margin: 0 auto;
  padding: 20px;
}

.error-message {
  margin-bottom: 16px;
}

.button-group {
  margin-top: 24px;
  text-align: center;
}

:deep(.ant-form-item) {
  margin-bottom: 16px;
}

:deep(.ant-divider) {
  margin: 24px 0 16px;
  color: #1890ff;
  font-weight: 500;
}

:deep(.ant-form-item-required::before) {
  display: inline-block;
  margin-right: 4px;
  color: #ff4d4f;
  font-size: 14px;
  font-family: SimSun, sans-serif;
  line-height: 1;
  content: '*';
}
</style> 