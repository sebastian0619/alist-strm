<template>
  <div class="archive-panel">
    <a-card title="网盘归档" :bordered="false">
      <!-- 基本配置 -->
      <a-form layout="vertical">
        <a-form-item label="启用归档">
          <a-switch
            v-model:checked="config.archive_enabled"
            :checked-children="'开启'"
            :un-checked-children="'关闭'"
          />
          <a-tooltip>
            <template #title>
              是否启用归档功能
            </template>
            <info-circle-outlined style="margin-left: 8px" />
          </a-tooltip>
        </a-form-item>

        <template v-if="config.archive_enabled">
          <!-- 基本配置 -->
          <a-divider>基本配置</a-divider>
          
          <a-form-item label="源目录（本地路径）">
            <a-input
              v-model:value="config.archive_source_root"
              placeholder="请输入源目录的本地路径，用于扫描文件时间"
            />
            <a-tooltip>
              <template #title>
                需要归档的文件所在的本地路径，用于扫描文件的创建时间和修改时间
              </template>
              <info-circle-outlined style="margin-left: 8px" />
            </a-tooltip>
          </a-form-item>

          <a-form-item label="源目录（Alist路径）">
            <a-input
              v-model:value="config.archive_source_alist"
              placeholder="请输入源目录在Alist中的路径"
            />
            <a-tooltip>
              <template #title>
                源目录在Alist中的路径，用于文件复制操作，例如: /local/video
              </template>
              <info-circle-outlined style="margin-left: 8px" />
            </a-tooltip>
          </a-form-item>

          <a-form-item label="目标目录（Alist路径）">
            <a-input
              v-model:value="config.archive_target_root"
              placeholder="请输入目标目录在Alist中的路径"
            />
            <a-tooltip>
              <template #title>
                文件归档后在Alist中存放的路径
              </template>
              <info-circle-outlined style="margin-left: 8px" />
            </a-tooltip>
          </a-form-item>

          <a-form-item label="自动STRM扫描">
            <a-switch
              v-model:checked="config.archive_auto_strm"
              :checked-children="'开启'"
              :un-checked-children="'关闭'"
            />
            <a-tooltip>
              <template #title>
                归档完成后自动执行STRM扫描
              </template>
              <info-circle-outlined style="margin-left: 8px" />
            </a-tooltip>
          </a-form-item>

          <a-form-item label="删除源文件">
            <a-switch
              v-model:checked="config.archive_delete_source"
              :checked-children="'开启'"
              :un-checked-children="'关闭'"
            />
            <a-tooltip>
              <template #title>
                归档完成后删除源文件
              </template>
              <info-circle-outlined style="margin-left: 8px" />
            </a-tooltip>
          </a-form-item>

          <a-form-item label="定时归档">
            <a-switch
              v-model:checked="config.archive_schedule_enabled"
              :checked-children="'开启'"
              :un-checked-children="'关闭'"
            />
            <a-tooltip>
              <template #title>
                是否启用定时自动归档功能
              </template>
              <info-circle-outlined style="margin-left: 8px" />
            </a-tooltip>
          </a-form-item>

          <a-form-item 
            label="定时表达式" 
            :help="getCronDescription(config.archive_schedule_cron)"
          >
            <a-input 
              v-model:value="config.archive_schedule_cron" 
              placeholder="Cron表达式，例如: 0 3 * * * (每天凌晨3点执行)"
              :disabled="!config.archive_schedule_enabled"
            />
            <a-tooltip>
              <template #title>
                Cron表达式格式：分 时 日 月 星期
                例如：
                0 3 * * * (每天凌晨3点执行)
                0 */12 * * * (每12小时执行一次)
              </template>
              <info-circle-outlined style="margin-left: 8px" />
            </a-tooltip>
          </a-form-item>

          <a-form-item label="排除文件扩展名">
            <a-input
              v-model:value="config.archive_excluded_extensions"
              placeholder="请输入要排除的文件扩展名，用逗号分隔"
            />
            <a-tooltip>
              <template #title>
                要排除的文件扩展名（不检查这些文件的修改时间），用逗号分隔，例如: .mp4,.mkv,.avi
              </template>
              <info-circle-outlined style="margin-left: 8px" />
            </a-tooltip>
          </a-form-item>

          <!-- 媒体类型配置 -->
          <a-divider>媒体类型配置</a-divider>
          
          <div class="media-types-header">
            <a-space>
              <a-button type="primary" @click="showAddTypeModal">
                添加媒体类型
              </a-button>
              <a-tooltip>
                <template #title>
                  类型的顺序决定了匹配优先级，可拖动调整顺序。
                  排在前面的类型优先匹配，例如：
                  "电影/外语电影" 应该排在 "电影" 之前
                </template>
                <info-circle-outlined />
              </a-tooltip>
            </a-space>
          </div>

          <draggable 
            v-model="mediaTypesList" 
            item-key="name"
            handle=".drag-handle"
            @end="handleDragEnd"
          >
            <template #item="{ element }">
              <div class="media-type-item">
                <a-space align="start">
                  <a-card :title="element.name" size="small" style="width: 100%; margin-bottom: 16px">
                    <template #extra>
                      <a-space>
                        <menu-outlined class="drag-handle" style="cursor: move" />
                        <a-button 
                          type="link" 
                          @click="saveMediaType(element)"
                          :loading="element.saving"
                        >
                          保存到archive.json
                        </a-button>
                        <a-button type="link" danger @click="removeMediaType(element.name)">
                          删除
                        </a-button>
                      </a-space>
                    </template>
                    
                    <div class="settings-item mt-2">
                      <div class="label">目录</div>
                      <a-input
                        v-model:value="element.config.dir"
                        placeholder="请输入目录名称，支持多级目录，如: 电影 或 电影/外语"
                        @change="() => handleMediaTypeChange(element.name)"
                      />
                    </div>
                    
                    <div class="settings-item mt-2">
                      <div class="label">阈值设置</div>
                      <a-input-group compact>
                        <a-form-item label="创建时间" style="margin-bottom: 0">
                          <a-input
                            v-model:value="element.config.creation_days" 
                            type="number"
                            min="0"
                            style="width: 120px"
                            addon-after="天"
                            @change="() => handleMediaTypeChange(element.name)"
                          />
                        </a-form-item>
                        <a-form-item label="修改时间" style="margin-bottom: 0; margin-left: 8px">
                          <a-input
                            v-model:value="element.config.mtime_days"
                            type="number"
                            min="0"
                            style="width: 120px"
                            addon-after="天"
                            @change="() => handleMediaTypeChange(element.name)"
                          />
                        </a-form-item>
                      </a-input-group>
                    </div>

                    <div class="save-tip" v-if="element.hasChanges" style="color: #ff4d4f; font-size: 12px; margin-top: 8px;">
                      * 配置已修改，请点击保存按钮保存到 archive.json
                    </div>
                  </a-card>
                </a-space>
              </div>
            </template>
          </draggable>

          <a-form-item>
            <a-space>
              <a-button type="primary" @click="saveConfig">
                保存配置
              </a-button>
              <a-button @click="startArchive" :loading="archiving">
                开始归档
              </a-button>
              <a-button @click="testArchive" :loading="testing">
                测试归档
              </a-button>
              <a-button @click="stopArchive" :disabled="!archiving && !testing">
                停止归档
              </a-button>
            </a-space>
          </a-form-item>
        </template>
      </a-form>
    </a-card>

    <!-- 测试结果对话框 -->
    <a-modal
      v-model:visible="testResultVisible"
      :title="archiveResultTitle"
      width="800px"
      @ok="testResultVisible = false"
    >
      <template v-if="testResult">
        <div class="test-result">
          <div class="summary">{{ testResult.summary }}</div>
          <a-divider />
          <div class="results">
            <div v-for="(result, index) in testResult.results" :key="index" class="result-item">
              <a-tag :color="getResultColor(result)">
                {{ result.success ? '通过' : '失败' }}
              </a-tag>
              {{ result.message }}
            </div>
          </div>
        </div>
      </template>
    </a-modal>

    <!-- 添加媒体类型对话框 -->
    <a-modal
      v-model:visible="addTypeModalVisible"
      title="添加媒体类型"
      width="800px"
      @ok="handleAddType"
      @cancel="handleCancelAdd"
    >
      <a-form layout="vertical">
        <a-form-item label="类型名称">
          <a-input
            v-model:value="newTypeName"
            placeholder="请输入媒体类型名称（如：电影、电视剧等）"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { InfoCircleOutlined, MenuOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import axios from 'axios'
import draggable from 'vuedraggable/src/vuedraggable'
import cronstrue from 'cronstrue'

const config = ref({
  archive_enabled: false,
  archive_source_root: '',
  archive_source_alist: '',
  archive_target_root: '',
  archive_auto_strm: false,
  archive_delete_source: false,
  archive_schedule_enabled: false,
  archive_schedule_cron: '0 3 * * *',
  archive_excluded_extensions: '.nfo,.ass,.srt,.jpg,.jpeg,.png',
  archive_media_types: ''
})

const originalConfig = ref({})

const mediaTypes = ref({})
const archiving = ref(false)
const testing = ref(false)
const testResultVisible = ref(false)
const testResult = ref(null)
const addTypeModalVisible = ref(false)
const newTypeName = ref('')

// 获取结果标签颜色
const getResultColor = (result) => {
  if (!result.message) return 'default';
  
  if (result.message.startsWith('[测试]')) return 'blue';
  if (result.message.startsWith('[归档]')) return 'green';
  if (result.message.startsWith('[跳过]')) return 'orange';
  if (result.message.startsWith('[错误]')) return 'red';
  
  return result.success ? 'green' : 'red';
}

// 添加媒体类型相关
const showAddTypeModal = () => {
  newTypeName.value = ''
  addTypeModalVisible.value = true
}

const handleAddType = () => {
  if (!newTypeName.value) {
    message.error('请输入类型名称')
    return
  }
  
  if (mediaTypes.value[newTypeName.value]) {
    message.error('该类型名称已存在')
    return
  }
  
  mediaTypes.value[newTypeName.value] = {
    dir: '',
    creation_days: 30,
    mtime_days: 7
  }
  
  addTypeModalVisible.value = false
}

const handleCancelAdd = () => {
  addTypeModalVisible.value = false
}

const removeMediaType = (name) => {
  if (window.confirm(`确定要删除类型"${name}"吗？`)) {
    delete mediaTypes.value[name]
  }
}

// 保存配置
const saveConfig = async () => {
  try {
    // 遍历配置项，逐个更新
    for (const [key, value] of Object.entries(config.value)) {
      if (JSON.stringify(value) !== JSON.stringify(originalConfig.value[key])) {
        const response = await axios.post('/api/config', {
          key: key,
          value: value
        })
        if (!response.data.status === 'success') {
          throw new Error(`保存配置 ${key} 失败`)
        }
      }
    }
    
    // 更新原始配置
    originalConfig.value = JSON.parse(JSON.stringify(config.value))
    message.success('基本配置保存成功')
  } catch (error) {
    message.error('配置保存失败: ' + error.message)
  }
}

// 加载配置
const loadConfig = async () => {
  try {
    // 加载基本配置
    const configResponse = await axios.get('/api/config')
    if (!configResponse.data) {
      throw new Error('加载配置失败')
    }
    config.value = configResponse.data
    originalConfig.value = JSON.parse(JSON.stringify(configResponse.data))
    
    // 加载媒体类型配置
    await loadMediaTypes()
  } catch (error) {
    message.error('加载配置失败: ' + error.message)
  }
}

// 归档控制
const startArchive = async () => {
  try {
    archiving.value = true
    const response = await axios.post('/api/archive/start')
    if (response.data.success && response.data.data) {
      // 展示归档结果
      testResult.value = response.data.data
      testResultVisible.value = true
    }
    message.success('归档任务已完成')
  } catch (error) {
    message.error('启动归档失败: ' + error.message)
  } finally {
    archiving.value = false
  }
}

const testArchive = async () => {
  try {
    testing.value = true
    const response = await axios.post('/api/archive/test')
    testResult.value = response.data.data
    testResultVisible.value = true
    message.success('归档测试完成')
  } catch (error) {
    message.error('归档测试失败: ' + error.message)
  } finally {
    testing.value = false
  }
}

const stopArchive = async () => {
  try {
    await axios.post('/api/archive/stop')
    message.success('归档任务已停止')
    archiving.value = false
    testing.value = false
  } catch (error) {
    message.error('停止归档失败: ' + error.message)
  }
}

// 获取Cron表达式描述
const getCronDescription = (cron) => {
  if (!cron) return ''
  const parts = cron.split(' ')
  if (parts.length !== 5) return '无效的Cron表达式'
  
  try {
    return cronstrue.toString(cron, { locale: 'zh_CN' })
  } catch (error) {
    if (parts[1] === '*/6' && parts[2] === '*' && parts[3] === '*' && parts[4] === '*') {
      return '每6小时执行一次'
    }
    if (parts[1] === '0' && parts[2] === '*' && parts[3] === '*' && parts[4] === '*') {
      return '每小时执行一次'
    }
    if (parts[1] === '0' && parts[2] === '0' && parts[3] === '*' && parts[4] === '*') {
      return '每天0点执行'
    }
    if (parts[1] === '0' && parts[2] === '3' && parts[3] === '*' && parts[4] === '*') {
      return '每天凌晨3点执行'
    }
    if (parts[1] === '0' && parts[2] === '*/12' && parts[3] === '*' && parts[4] === '*') {
      return '每12小时执行一次'
    }
    return '自定义执行计划'
  }
}

// 将对象转换为数组以支持拖拽排序
const mediaTypesList = computed({
  get: () => Object.entries(mediaTypes.value).map(([name, config]) => ({
    name,
    config: { ...config },
    hasChanges: false,
    saving: false
  })),
  set: (list) => {
    const newTypes = {}
    list.forEach(item => {
      newTypes[item.name] = item.config
    })
    mediaTypes.value = newTypes
  }
})

const handleDragEnd = () => {
  // 拖拽结束后自动保存
  saveConfig()
}

const handleMediaTypeChange = (name) => {
  const mediaType = mediaTypesList.value.find(item => item.name === name)
  if (mediaType) {
    mediaType.hasChanges = true
  }
}

const saveMediaType = async (mediaType) => {
  try {
    mediaType.saving = true
    
    // 构建媒体类型配置对象
    const mediaTypesData = {}
    mediaTypesList.value.forEach(type => {
      // 确保数值类型正确，避免字符串数值引起的问题
      // 明确转换为数字类型，但保留用户输入的值，不进行四舍五入或格式化
      const creation_days = type.name === mediaType.name 
        ? Number(mediaType.config.creation_days)
        : Number(type.config.creation_days)
        
      const mtime_days = type.name === mediaType.name 
        ? Number(mediaType.config.mtime_days)
        : Number(type.config.mtime_days)
      
      mediaTypesData[type.name] = {
        dir: type.config.dir,
        creation_days: creation_days,
        mtime_days: mtime_days
      }
    })

    console.log('发送媒体类型数据:', JSON.stringify(mediaTypesData, null, 2))

    // 调用API保存到archive.json
    const response = await axios.post('/api/archive/media_types', mediaTypesData)
    if (!response.data.success) {
      throw new Error(response.data.message)
    }
    
    console.log('保存媒体类型响应:', response.data)
    
    // 更新状态而不改变值
    mediaType.hasChanges = false
    message.success(`媒体类型 "${mediaType.name}" 已保存到 archive.json`)
  } catch (error) {
    console.error('保存媒体类型失败:', error)
    message.error(`保存失败: ${error.message || '未知错误'}`)
  } finally {
    mediaType.saving = false
  }
}

const loadMediaTypes = async () => {
  try {
    const response = await axios.get('/api/archive/media_types')
    if (!response.data.success) {
      throw new Error(response.data.message)
    }
    mediaTypes.value = response.data.data || {}
  } catch (error) {
    console.error('加载媒体类型失败:', error)
    message.error('加载媒体类型失败: ' + error.message)
  }
}

const archiveResultTitle = computed(() => {
  if (!testResult.value) return '归档结果';
  // 根据summary字段判断是测试还是正常归档
  return testResult.value.summary.includes('测试') ? '归档测试结果' : '归档处理结果';
});

// 在组件挂载时加载配置
onMounted(() => {
  loadConfig()
})
</script>

<style scoped>
.archive-panel {
  margin: 24px;
}

.test-result {
  max-height: 500px;
  overflow-y: auto;
}

.summary {
  font-weight: bold;
  margin-bottom: 16px;
  white-space: pre-line;
}

.result-item {
  margin-bottom: 8px;
}

.result-item :deep(.ant-tag) {
  min-width: 48px;
  text-align: center;
  margin-right: 8px;
}
</style> 