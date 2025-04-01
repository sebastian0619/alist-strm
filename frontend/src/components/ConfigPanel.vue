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

      <a-form-item label="删除空文件夹">
        <a-switch
          v-model:checked="config.remove_empty_dirs"
          :checked-children="'开启'"
          :un-checked-children="'关闭'"
        />
        <a-tooltip>
          <template #title>
            扫描完成后删除不包含STRM文件的空文件夹
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

      <!-- 跳过规则配置 -->
      <a-divider>跳过规则配置</a-divider>
      <a-form-item label="跳过文件模式">
        <a-input
          v-model:value="config.skip_patterns"
          placeholder="支持正则表达式，多个规则用逗号分隔，例如: sample,trailer,预告片"
        />
        <a-tooltip>
          <template #title>
            支持正则表达式，多个规则用逗号分隔
            例如：sample,trailer,预告片
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>

      <a-form-item label="跳过文件夹">
        <a-input
          v-model:value="config.skip_folders"
          placeholder="多个文件夹用逗号分隔，例如: extras,花絮,番外,特典"
        />
        <a-tooltip>
          <template #title>
            指定要跳过的文件夹名称，多个用逗号分隔
            例如：extras,花絮,番外,特典
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>

      <a-form-item label="跳过扩展名">
        <a-input
          v-model:value="config.skip_extensions"
          placeholder="多个扩展名用逗号分隔（包含点号），例如: .iso,.mka"
        />
        <a-tooltip>
          <template #title>
            指定要跳过的文件扩展名，多个用逗号分隔（包含点号）
            例如：.iso,.mka
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>

      <!-- Telegram配置 -->
      <a-divider>Telegram 通知配置</a-divider>
      <a-form-item label="启用Telegram通知">
        <a-switch
          v-model:checked="config.tg_enabled"
          :checked-children="'开启'"
          :un-checked-children="'关闭'"
        />
        <a-tooltip>
          <template #title>
            是否启用Telegram通知功能
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>

      <a-form-item label="Bot Token" v-if="config.tg_enabled">
        <a-input-password
          v-model:value="config.tg_token"
          placeholder="请输入Telegram Bot Token"
        />
        <a-tooltip>
          <template #title>
            从 @BotFather 获取的Bot Token
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>

      <a-form-item label="Chat ID" v-if="config.tg_enabled">
        <a-input
          v-model:value="config.tg_chat_id"
          placeholder="请输入Telegram Chat ID"
        />
        <a-tooltip>
          <template #title>
            接收通知的Chat ID，可以从 @userinfobot 获取
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>

      <a-form-item label="代理地址" v-if="config.tg_enabled">
        <a-input
          v-model:value="config.tg_proxy_url"
          placeholder="代理地址，例如: http://127.0.0.1:7890"
        />
        <a-tooltip>
          <template #title>
            如果无法直接访问Telegram API，可以配置代理地址
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>

      <!-- Emby配置 -->
      <a-divider>Emby 刷库配置</a-divider>
      <a-form-item label="启用Emby刷库">
        <a-switch
          v-model:checked="config.emby_enabled"
          :checked-children="'开启'"
          :un-checked-children="'关闭'"
        />
        <a-tooltip>
          <template #title>
            是否启用Emby元数据刷新功能，生成STRM文件后会自动刷新对应的媒体库项目
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>

      <a-form-item label="Emby API地址" v-if="config.emby_enabled">
        <a-input
          v-model:value="config.emby_api_url"
          placeholder="http://localhost:8096/emby"
        />
        <a-button 
          type="link" 
          :loading="testingEmby"
          @click="testEmbyConnection"
          style="margin-left: 8px"
        >
          测试连接
        </a-button>
        <a-tooltip>
          <template #title>
            Emby服务器的API地址，例如: http://localhost:8096/emby
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>

      <a-form-item label="API密钥" v-if="config.emby_enabled">
        <a-input-password
          v-model:value="config.emby_api_key"
          placeholder="请输入Emby API密钥"
        />
        <a-tooltip>
          <template #title>
            从Emby管理面板中获取的API密钥
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>

      <a-form-item label="STRM文件根路径" v-if="config.emby_enabled">
        <a-input
          v-model:value="config.strm_root_path"
          placeholder="/path/to/strm/files"
        />
        <a-tooltip>
          <template #title>
            STRM文件的根路径，系统生成的STRM文件存放位置
          </template>
          <info-circle-outlined style="margin-left: 8px" />
        </a-tooltip>
      </a-form-item>

      <a-form-item label="Emby媒体库根路径" v-if="config.emby_enabled">
        <a-input
          v-model:value="config.emby_root_path"
          placeholder="/path/to/emby/media"
        />
        <a-tooltip>
          <template #title>
            Emby媒体库中的对应路径，用于路径映射
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
        <a-button
          @click="clearCache"
          :loading="clearingCache"
          style="margin-left: 8px"
        >
          清除缓存
        </a-button>
      </div>
    </a-card>
  </div>
</template>

<script>
import { ref, onMounted, computed, onUnmounted } from 'vue'
import { InfoCircleOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

export default {
  components: {
    InfoCircleOutlined
  },
  
  emits: ['scan-started'],
  
  setup(props, { emit }) {
    const config = ref({})
    const originalConfig = ref({})
    const loading = ref(false)
    const saving = ref(false)
    const error = ref('')
    const scanning = ref(false)
    const testingConnection = ref(false)
    const testingEmby = ref(false)
    const clearingCache = ref(false)
    
    // 加载配置
    const loadConfig = async () => {
      loading.value = true
      error.value = ''
      try {
        const response = await fetch('/api/config')
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`)
        }
        const data = await response.json()
        config.value = data
        originalConfig.value = JSON.parse(JSON.stringify(data))
        error.value = ''
      } catch (e) {
        console.error('加载配置失败:', e)
        error.value = '配置加载失败'
        message.error('配置加载失败: ' + e.message)
      } finally {
        loading.value = false
      }
    }
    
    // 保存配置
    const saveConfig = async () => {
      saving.value = true
      try {
        // 遍历配置项，逐个更新
        for (const [key, value] of Object.entries(config.value)) {
          if (JSON.stringify(value) !== JSON.stringify(originalConfig.value[key])) {
            const response = await fetch('/api/config', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({
                key: key,
                value: value
              })
            })
            
            if (!response.ok) {
              throw new Error(`保存配置 ${key} 失败`)
            }
          }
        }
        
        // 更新原始配置
        originalConfig.value = JSON.parse(JSON.stringify(config.value))
        message.success('配置保存成功')
        error.value = ''
      } catch (e) {
        console.error('保存配置失败:', e)
        error.value = '保存配置失败'
        message.error('保存配置失败: ' + e.message)
      } finally {
        saving.value = false
      }
    }
    
    // 检查配置是否有变化
    const hasChanges = computed(() => {
      return JSON.stringify(config.value) !== JSON.stringify(originalConfig.value)
    })
    
    // 测试连接
    const testConnection = async () => {
      testingConnection.value = true
      try {
        const response = await fetch(config.value.alist_url + '/api/fs/list', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': config.value.alist_token
          },
          body: JSON.stringify({
            path: '/',
            password: '',
            page: 1,
            per_page: 1,
            refresh: false
          })
        })
        
        if (response.ok) {
          message.success('连接成功')
        } else {
          throw new Error('连接失败')
        }
      } catch (e) {
        message.error('连接失败: ' + e.message)
      } finally {
        testingConnection.value = false
      }
    }
    
    // 开始扫描
    const startScan = async () => {
      try {
        const response = await fetch('/api/strm/start', {
          method: 'POST'
        })
        if (!response.ok) {
          throw new Error('启动扫描失败')
        }
        scanning.value = true
        message.success('扫描已开始')
        // 立即触发日志显示
        emit('scan-started')
      } catch (e) {
        message.error('启动扫描失败: ' + e.message)
      }
    }
    
    // 停止扫描
    const stopScan = async () => {
      try {
        const response = await fetch('/api/strm/stop', {
          method: 'POST'
        })
        if (!response.ok) {
          throw new Error('停止扫描失败')
        }
        scanning.value = false
        message.success('扫描已停止')
      } catch (e) {
        message.error('停止扫描失败: ' + e.message)
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
      } catch (e) {
        console.error('检查扫描状态失败:', e)
      }
    }
    
    // 获取Cron表达式描述
    const getCronDescription = (cron) => {
      if (!cron) return ''
      const parts = cron.split(' ')
      if (parts.length !== 5) return '无效的Cron表达式'
      
      if (parts[1] === '*/6' && parts[2] === '*' && parts[3] === '*' && parts[4] === '*') {
        return '每6小时执行一次'
      }
      if (parts[1] === '0' && parts[2] === '*' && parts[3] === '*' && parts[4] === '*') {
        return '每小时执行一次'
      }
      if (parts[1] === '0' && parts[2] === '0' && parts[3] === '*' && parts[4] === '*') {
        return '每天0点执行'
      }
      return '自定义执行计划'
    }
    
    // 清除缓存
    const clearCache = async () => {
      clearingCache.value = true
      try {
        const response = await fetch('/api/strm/clear-cache', {
          method: 'POST'
        })
        if (!response.ok) {
          throw new Error('清除缓存失败')
        }
        const data = await response.json()
        if (data.status === 'success') {
          message.success('缓存已清除')
        } else {
          throw new Error(data.message || '清除缓存失败')
        }
      } catch (e) {
        message.error(e.message)
      } finally {
        clearingCache.value = false
      }
    }
    
    // 测试Emby连接
    const testEmbyConnection = async () => {
      testingEmby.value = true
      try {
        // 验证是否配置了必要参数
        if (!config.value.emby_api_url || !config.value.emby_api_key) {
          throw new Error('请先填写Emby API地址和API密钥')
        }
        
        const response = await fetch('/api/config/test_emby', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            url: config.value.emby_api_url,
            api_key: config.value.emby_api_key
          })
        })
        
        const data = await response.json()
        
        if (data.success) {
          message.success(data.message)
        } else {
          throw new Error(data.message)
        }
      } catch (e) {
        message.error('Emby连接测试失败: ' + e.message)
      } finally {
        testingEmby.value = false
      }
    }
    
    // 组件挂载时加载配置
    onMounted(() => {
      loadConfig()
      checkScanStatus()
      // 定期检查扫描状态
      const statusInterval = setInterval(checkScanStatus, 5000)
      // 组件卸载时清理定时器
      onUnmounted(() => {
        clearInterval(statusInterval)
      })
    })
    
    return {
      config,
      loading,
      saving,
      error,
      scanning,
      testingConnection,
      testingEmby,
      clearingCache,
      loadConfig,
      saveConfig,
      hasChanges,
      testConnection,
      testEmbyConnection,
      startScan,
      stopScan,
      getCronDescription,
      clearCache
    }
  }
}
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