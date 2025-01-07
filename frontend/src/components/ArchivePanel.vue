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
          
          <a-form-item label="源目录">
            <a-input
              v-model:value="config.archive_source_dir"
              placeholder="请输入源目录路径"
            />
            <a-tooltip>
              <template #title>
                需要归档的文件所在的根目录
              </template>
              <info-circle-outlined style="margin-left: 8px" />
            </a-tooltip>
          </a-form-item>

          <a-form-item label="目标目录">
            <a-input
              v-model:value="config.archive_target_dir"
              placeholder="请输入目标目录路径"
            />
            <a-tooltip>
              <template #title>
                文件归档后存放的根目录
              </template>
              <info-circle-outlined style="margin-left: 8px" />
            </a-tooltip>
          </a-form-item>

          <a-form-item label="视频文件扩展名">
            <a-input
              v-model:value="config.archive_video_extensions"
              placeholder="请输入视频文件扩展名，用逗号分隔"
            />
            <a-tooltip>
              <template #title>
                支持的视频文件扩展名，用逗号分隔，例如: .mp4,.mkv,.avi
              </template>
              <info-circle-outlined style="margin-left: 8px" />
            </a-tooltip>
          </a-form-item>

          <!-- 媒体类型配置 -->
          <a-divider>媒体类型配置</a-divider>

          <div class="media-types-header">
            <a-button type="primary" @click="addMediaType">
              添加媒体类型
            </a-button>
          </div>

          <div v-for="(type, name) in mediaTypes" :key="name" class="media-type-item">
            <a-space align="start">
              <a-card :title="name" size="small" style="width: 100%; margin-bottom: 16px">
                <template #extra>
                  <a-button type="link" danger @click="removeMediaType(name)">
                    删除
                  </a-button>
                </template>
                
                <a-form-item label="目录名称">
                  <a-input
                    v-model:value="type.dir"
                    placeholder="请输入目录名称，支持多级目录，如: 电影 或 电影/外语"
                  />
                </a-form-item>
                
                <a-form-item label="阈值设置">
                  <a-input-group compact>
                    <a-form-item label="创建时间" style="margin-bottom: 0">
                      <a-input-number
                        v-model:value="type.creation_days"
                        :min="0"
                        addon-after="天"
                        style="width: 120px"
                      />
                    </a-form-item>
                    <a-form-item label="修改时间" style="margin-bottom: 0; margin-left: 8px">
                      <a-input-number
                        v-model:value="type.mtime_days"
                        :min="0"
                        addon-after="天"
                        style="width: 120px"
                      />
                    </a-form-item>
                  </a-input-group>
                </a-form-item>
              </a-card>
            </a-space>
          </div>

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
      title="归档测试结果"
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
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { InfoCircleOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import axios from 'axios'

const config = ref({
  archive_enabled: false,
  archive_source_dir: '',
  archive_target_dir: '',
  archive_auto_strm: false,
  archive_delete_source: false,
  archive_schedule_enabled: false,
  archive_schedule_cron: '0 3 * * *',
  archive_video_extensions: '',
  archive_media_types: ''
})

const mediaTypes = ref({})
const archiving = ref(false)
const testing = ref(false)
const testResultVisible = ref(false)
const testResult = ref(null)

// 获取结果标签颜色
const getResultColor = (result) => {
  if (result.message.startsWith('[测试]')) return 'blue'
  if (result.message.startsWith('[跳过]')) return 'orange'
  if (result.message.startsWith('[错误]')) return 'red'
  return 'green'
}

// 添加媒体类型相关
const addMediaType = () => {
  const typeName = `类型${Object.keys(mediaTypes.value).length + 1}`
  mediaTypes.value[typeName] = {
    dir: '',
    creation_days: 30,
    mtime_days: 7
  }
}

const removeMediaType = (name) => {
  delete mediaTypes.value[name]
}

// 保存配置
const saveConfig = async () => {
  try {
    // 保存基本配置
    const configResponse = await axios.post('/api/config/save', config.value)
    if (!configResponse.data.success) {
      throw new Error(configResponse.data.message)
    }
    
    // 保存媒体类型配置
    const mediaTypesResponse = await axios.post('/api/archive/media_types', mediaTypes.value)
    if (!mediaTypesResponse.data.success) {
      throw new Error(mediaTypesResponse.data.message)
    }
    
    message.success('配置保存成功')
  } catch (error) {
    message.error('配置保存失败: ' + error.message)
  }
}

// 加载配置
const loadConfig = async () => {
  try {
    // 加载基本配置
    const configResponse = await axios.get('/api/config/load')
    if (!configResponse.data.success) {
      throw new Error(configResponse.data.message)
    }
    config.value = configResponse.data.data
    
    // 加载媒体类型配置
    const mediaTypesResponse = await axios.get('/api/archive/media_types')
    if (!mediaTypesResponse.data.success) {
      throw new Error(mediaTypesResponse.data.message)
    }
    mediaTypes.value = mediaTypesResponse.data.data
  } catch (error) {
    message.error('加载配置失败: ' + error.message)
  }
}

// 归档控制
const startArchive = async () => {
  try {
    archiving.value = true
    await axios.post('/api/archive/start')
    message.success('归档任务已启动')
  } catch (error) {
    message.error('启动归档失败: ' + error.message)
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