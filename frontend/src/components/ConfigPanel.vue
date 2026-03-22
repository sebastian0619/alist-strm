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

    <a-card class="config-shell" :bordered="false">
      <div class="config-hero">
        <div>
          <div class="hero-kicker">Configuration Center</div>
          <h2>基础配置</h2>
          <p>把运行参数按职责拆开管理，减少在长表单里来回滚动。</p>
        </div>
        <div class="hero-metrics">
          <div class="metric-pill">
            <span>变更状态</span>
            <strong>{{ hasChanges ? '未保存' : '已同步' }}</strong>
          </div>
          <div class="metric-pill">
            <span>扫描状态</span>
            <strong>{{ scanning ? '运行中' : '空闲' }}</strong>
          </div>
          <div class="metric-pill">
            <span>日志级别</span>
            <strong>{{ config.log_level || 'INFO' }}</strong>
          </div>
        </div>
      </div>

      <a-collapse v-model:activeKey="activeSections" ghost class="config-collapse">
        <a-collapse-panel key="runtime" header="运行与调度">
          <div class="section-grid">
            <a-form-item label="运行模式">
              <a-switch
                v-model:checked="config.run_after_startup"
                :checked-children="'启动时执行'"
                :un-checked-children="'手动执行'"
              />
              <a-tooltip>
                <template #title>
                  启动时执行：程序启动后自动开始扫描；手动执行：需要手动点击开始按钮。
                </template>
                <info-circle-outlined class="tip-icon" />
              </a-tooltip>
            </a-form-item>

            <a-form-item label="日志级别">
              <a-select v-model:value="config.log_level" style="width: 100%">
                <a-select-option value="INFO">INFO</a-select-option>
                <a-select-option value="DEBUG">DEBUG</a-select-option>
                <a-select-option value="WARNING">WARNING</a-select-option>
                <a-select-option value="ERROR">ERROR</a-select-option>
              </a-select>
            </a-form-item>

            <a-form-item label="慢速模式">
              <a-switch
                v-model:checked="config.slow_mode"
                :checked-children="'开启'"
                :un-checked-children="'关闭'"
              />
            </a-form-item>

            <a-form-item label="启用定时扫描">
              <a-switch v-model:checked="config.schedule_enabled" />
            </a-form-item>

            <a-form-item
              class="span-2"
              label="定时表达式"
              :help="getCronDescription(config.schedule_cron)"
            >
              <a-input
                v-model:value="config.schedule_cron"
                placeholder="Cron表达式，例如: 0 */6 * * *"
                :disabled="!config.schedule_enabled"
              />
            </a-form-item>
          </div>
        </a-collapse-panel>

        <a-collapse-panel key="alist" header="Alist 与 STRM">
          <div class="section-grid">
            <a-form-item class="span-2" label="Alist 服务器地址" required>
              <div class="inline-with-action">
                <a-input
                  v-model:value="config.alist_url"
                  placeholder="http://localhost:5244"
                />
                <a-button
                  type="link"
                  :loading="testingConnection"
                  @click="testConnection"
                >
                  测试连接
                </a-button>
              </div>
            </a-form-item>

            <a-form-item class="span-2" label="Alist Token">
              <a-input-password
                v-model:value="config.alist_token"
                placeholder="请输入Alist Token"
              />
            </a-form-item>

            <a-form-item label="外部访问地址">
              <a-input
                v-model:value="config.alist_external_url"
                placeholder="https://example.com"
              />
            </a-form-item>

            <a-form-item label="STRM使用外部地址">
              <a-switch
                v-model:checked="config.use_external_url"
                :checked-children="'开启'"
                :un-checked-children="'关闭'"
              />
            </a-form-item>

            <a-form-item class="span-2" label="扫描路径" required>
              <a-input
                v-model:value="config.alist_scan_path"
                placeholder="/path/to/scan"
              />
            </a-form-item>

            <a-form-item label="URL编码">
              <a-switch
                v-model:checked="config.encode"
                :checked-children="'开启'"
                :un-checked-children="'关闭'"
              />
            </a-form-item>

            <a-form-item label="删除空文件夹">
              <a-switch
                v-model:checked="config.remove_empty_dirs"
                :checked-children="'开启'"
                :un-checked-children="'关闭'"
              />
            </a-form-item>

            <a-form-item label="下载字幕">
              <a-switch
                v-model:checked="config.is_down_sub"
                :checked-children="'开启'"
                :un-checked-children="'关闭'"
              />
            </a-form-item>

            <a-form-item label="下载元数据">
              <a-switch
                v-model:checked="config.download_metadata"
                :checked-children="'开启'"
                :un-checked-children="'关闭'"
              />
            </a-form-item>

            <a-form-item v-if="config.download_metadata" class="span-2" label="元数据文件扩展名">
              <a-input
                v-model:value="config.metadata_extensions"
                placeholder=".ass,.ssa,.srt,.png,.nfo,.jpg,.jpeg,.json,.bif"
              />
            </a-form-item>

            <a-form-item label="最小文件大小(MB)">
              <a-input-number
                v-model:value="config.min_file_size"
                :min="0"
                style="width: 100%"
              />
            </a-form-item>

            <a-form-item label="输出目录" required>
              <a-input
                v-model:value="config.output_dir"
                placeholder="data"
              />
            </a-form-item>
          </div>
        </a-collapse-panel>

        <a-collapse-panel key="rules" header="跳过规则">
          <div class="section-grid">
            <a-form-item class="span-2" label="跳过文件模式">
              <a-input
                v-model:value="config.skip_patterns"
                placeholder="支持正则，多个规则用逗号分隔，例如: sample,trailer,预告片"
              />
            </a-form-item>

            <a-form-item label="跳过文件夹">
              <a-input
                v-model:value="config.skip_folders"
                placeholder="例如: extras,花絮,番外,特典"
              />
            </a-form-item>

            <a-form-item label="跳过扩展名">
              <a-input
                v-model:value="config.skip_extensions"
                placeholder="例如: .iso,.mka"
              />
            </a-form-item>
          </div>
        </a-collapse-panel>

        <a-collapse-panel key="notify" header="Telegram 通知">
          <div class="section-grid">
            <a-form-item label="启用Telegram通知">
              <a-switch
                v-model:checked="config.tg_enabled"
                :checked-children="'开启'"
                :un-checked-children="'关闭'"
              />
            </a-form-item>

            <a-form-item v-if="config.tg_enabled" class="span-2" label="Bot Token">
              <a-input-password
                v-model:value="config.tg_token"
                placeholder="请输入Telegram Bot Token"
              />
            </a-form-item>

            <a-form-item v-if="config.tg_enabled" label="Chat ID">
              <a-input
                v-model:value="config.tg_chat_id"
                placeholder="请输入Telegram Chat ID"
              />
            </a-form-item>

            <a-form-item v-if="config.tg_enabled" label="代理地址">
              <a-input
                v-model:value="config.tg_proxy_url"
                placeholder="例如: http://127.0.0.1:7890"
              />
            </a-form-item>
          </div>
        </a-collapse-panel>

        <a-collapse-panel key="emby" header="Emby 映射与刷新">
          <div class="section-grid">
            <a-form-item label="启用Emby刷库">
              <a-switch
                v-model:checked="config.emby_enabled"
                :checked-children="'开启'"
                :un-checked-children="'关闭'"
              />
            </a-form-item>

            <a-form-item v-if="config.emby_enabled" class="span-2" label="Emby API地址">
              <div class="inline-with-action">
                <a-input
                  v-model:value="config.emby_api_url"
                  placeholder="http://localhost:8096/emby"
                />
                <a-button
                  type="link"
                  :loading="testingEmby"
                  @click="testEmbyConnection"
                >
                  测试连接
                </a-button>
              </div>
            </a-form-item>

            <a-form-item v-if="config.emby_enabled" class="span-2" label="API密钥">
              <a-input-password
                v-model:value="config.emby_api_key"
                placeholder="请输入Emby API密钥"
              />
            </a-form-item>

            <a-form-item v-if="config.emby_enabled" label="STRM文件根路径">
              <a-input
                v-model:value="config.strm_root_path"
                placeholder="/path/to/strm/files"
              />
            </a-form-item>

            <a-form-item v-if="config.emby_enabled" label="Emby媒体库根路径">
              <a-input
                v-model:value="config.emby_root_path"
                placeholder="/path/to/emby/media"
              />
            </a-form-item>
          </div>
        </a-collapse-panel>

        <a-collapse-panel key="tmdb" header="TMDB 与缓存">
          <div class="section-grid">
            <a-form-item label="TMDB缓存目录">
              <a-input
                v-model:value="config.tmdb_cache_dir"
                placeholder="cache/tmdb"
              />
            </a-form-item>
          </div>
        </a-collapse-panel>
      </a-collapse>

      <div class="action-bar">
        <div class="action-summary">
          <strong>{{ hasChanges ? '存在未保存变更' : '当前配置已同步' }}</strong>
          <span>{{ scanning ? '扫描任务正在运行中。' : '当前没有运行中的扫描任务。' }}</span>
        </div>
        <a-space wrap>
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
          >
            重新加载
          </a-button>
          <a-button
            type="primary"
            :loading="scanning"
            @click="scanning ? stopScan() : startScan()"
            :danger="scanning"
          >
            {{ scanning ? '停止扫描' : '开始扫描' }}
          </a-button>
          <a-button
            @click="clearCache"
            :loading="clearingCache"
          >
            清除缓存
          </a-button>
        </a-space>
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
    const activeSections = ref(['runtime', 'alist', 'emby'])

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

    const saveConfig = async () => {
      saving.value = true
      try {
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

    const hasChanges = computed(() => {
      return JSON.stringify(config.value) !== JSON.stringify(originalConfig.value)
    })

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
        emit('scan-started')
      } catch (e) {
        message.error('启动扫描失败: ' + e.message)
      }
    }

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

    const testEmbyConnection = async () => {
      testingEmby.value = true
      try {
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

    onMounted(() => {
      loadConfig()
      checkScanStatus()
      const statusInterval = setInterval(checkScanStatus, 5000)
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
      activeSections,
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
  max-width: 1120px;
  margin: 0 auto;
  padding: 12px;
}

.config-shell {
  padding: 8px;
}

.error-message {
  margin-bottom: 16px;
}

.config-hero {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 18px;
  margin-bottom: 22px;
}

.hero-kicker {
  color: #b4542f;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.config-hero h2 {
  margin: 10px 0 8px;
  font-size: 30px;
  color: #241d15;
}

.config-hero p {
  margin: 0;
  color: #665747;
}

.hero-metrics {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.metric-pill {
  min-width: 130px;
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.62);
  border: 1px solid rgba(36, 29, 21, 0.06);
}

.metric-pill span {
  display: block;
  color: #766756;
  font-size: 12px;
}

.metric-pill strong {
  display: block;
  margin-top: 8px;
  color: #241d15;
  font-size: 18px;
}

.config-collapse :deep(.ant-collapse-item) {
  margin-bottom: 14px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.54);
  border: 1px solid rgba(36, 29, 21, 0.06);
  overflow: hidden;
}

.config-collapse :deep(.ant-collapse-header) {
  font-size: 16px;
  font-weight: 700;
  color: #2b2017;
}

.config-collapse :deep(.ant-collapse-content-box) {
  padding-top: 8px;
}

.section-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 18px;
}

.span-2 {
  grid-column: span 2;
}

.inline-with-action {
  display: flex;
  align-items: center;
  gap: 10px;
}

.action-bar {
  position: sticky;
  bottom: 0;
  z-index: 2;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-top: 20px;
  padding: 16px 18px;
  border-radius: 22px;
  background: rgba(255, 252, 246, 0.95);
  border: 1px solid rgba(36, 29, 21, 0.08);
  box-shadow: 0 -10px 30px rgba(67, 54, 39, 0.06);
  backdrop-filter: blur(10px);
}

.action-summary {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.action-summary strong {
  color: #241d15;
}

.action-summary span {
  color: #766756;
  font-size: 13px;
}

.tip-icon {
  margin-left: 8px;
}

:deep(.ant-form-item) {
  margin-bottom: 16px;
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

@media (max-width: 960px) {
  .config-hero,
  .action-bar,
  .inline-with-action {
    flex-direction: column;
    align-items: stretch;
  }

  .hero-metrics {
    justify-content: flex-start;
  }

  .section-grid {
    grid-template-columns: 1fr;
  }

  .span-2 {
    grid-column: span 1;
  }
}
</style>
