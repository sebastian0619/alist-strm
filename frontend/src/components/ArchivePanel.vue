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
              <a-button @click="stopArchive" :disabled="!archiving">
                停止归档
              </a-button>
            </a-space>
          </a-form-item>
        </template>
      </a-form>
    </a-card>
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

// 添加媒体类型相关
const addTypeModalVisible = ref(false)
const newType = ref({
  name: '',
  dir: '',
  creation_days: 0,
  mtime_days: 0
})

const showAddTypeModal = () => {
  newType.value = {
    name: '',
    dir: '',
    creation_days: 0,
    mtime_days: 0
  }
  addTypeModalVisible.value = true
}

const handleAddType = () => {
  if (!newType.value.name || !newType.value.dir) {
    message.error('请填写完整信息')
    return
  }
  
  mediaTypes.value[newType.value.name] = {
    dir: newType.value.dir,
    creation_days: newType.value.creation_days,
    mtime_days: newType.value.mtime_days
  }
  
  // 更新配置
  updateMediaTypes()
  addTypeModalVisible.value = false
}

const removeMediaType = (name) => {
  delete mediaTypes.value[name]
  // 更新配置
  updateMediaTypes()
}

const updateMediaTypes = () => {
  config.value.archive_media_types = JSON.stringify(mediaTypes.value)
}

const isArchiving = ref(false)

// 开始归档
const startArchive = async () => {
  try {
    isArchiving.value = true
    await axios.post('/api/archive/start')
    message.success('归档任务已启动')
  } catch (error) {
    message.error(error.response?.data?.detail || '启动归档失败')
  }
}

// 停止归档
const stopArchive = async () => {
  try {
    await axios.post('/api/archive/stop')
    message.success('已发送停止归档信号')
    isArchiving.value = false
  } catch (error) {
    message.error(error.response?.data?.detail || '停止归档失败')
  }
}

// 加载配置
onMounted(async () => {
  try {
    const response = await axios.get('/api/config')
    config.value = { ...config.value, ...response.data }
    // 解析媒体类型配置
    if (config.value.archive_media_types) {
      mediaTypes.value = JSON.parse(config.value.archive_media_types)
    }
  } catch (error) {
    message.error('加载配置失败')
  }
})
</script>

<style scoped>
.archive-panel {
  margin: 24px;
}
</style> 