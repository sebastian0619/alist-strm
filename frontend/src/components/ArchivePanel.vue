<template>
  <div class="archive-panel">
    <a-card title="归档管理" :bordered="false">
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
          <a-form-item label="源目录">
            <a-input
              v-model:value="config.archive_source_dir"
              placeholder="请输入源目录路径"
            />
            <a-tooltip>
              <template #title>
                需要归档的视频文件所在目录
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
                归档后的文件存放目录
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
                归档完成后是否自动执行STRM扫描
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
                归档完成且验证成功后是否删除源文件
              </template>
              <info-circle-outlined style="margin-left: 8px" />
            </a-tooltip>
          </a-form-item>

          <!-- 定时任务配置 -->
          <a-divider>定时任务</a-divider>

          <a-form-item label="启用定时归档">
            <a-switch
              v-model:checked="config.archive_schedule_enabled"
              :checked-children="'开启'"
              :un-checked-children="'关闭'"
            />
            <a-tooltip>
              <template #title>
                是否启用定时归档功能
              </template>
              <info-circle-outlined style="margin-left: 8px" />
            </a-tooltip>
          </a-form-item>

          <a-form-item v-if="config.archive_schedule_enabled" label="执行计划">
            <a-input
              v-model:value="config.archive_schedule_cron"
              placeholder="请输入Cron表达式，例如：0 3 * * *"
            />
            <a-tooltip>
              <template #title>
                使用Cron表达式设置定时归档的执行时间，默认每天凌晨3点执行
              </template>
              <info-circle-outlined style="margin-left: 8px" />
            </a-tooltip>
          </a-form-item>

          <!-- 操作按钮 -->
          <a-form-item>
            <a-space>
              <a-button
                type="primary"
                :loading="isArchiving"
                @click="startArchive"
              >
                开始归档
              </a-button>
              <a-button
                danger
                :disabled="!isArchiving"
                @click="stopArchive"
              >
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
import { ref, onMounted } from 'vue'
import { InfoCircleOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import axios from 'axios'

const config = ref({
  archive_enabled: false,
  archive_source_dir: '',
  archive_target_dir: '',
  archive_auto_strm: false,
  archive_delete_source: false,
  archive_schedule_enabled: false,
  archive_schedule_cron: '0 3 * * *'
})

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