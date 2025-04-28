<template>
  <div class="strm-replace-panel">
    <a-card class="replace-card" :bordered="false">
      <div class="panel-header">
        <h2>STRM文件批量替换</h2>
        <p>批量替换STRM文件中的链接地址，可用于更新服务器地址或修复无效链接</p>
      </div>

      <a-form layout="vertical">
        <a-form-item label="查找内容">
          <a-textarea 
            v-model:value="batchReplace.searchText" 
            placeholder="输入要查找的文本内容，例如：http://old-server/d/" 
            :rows="2"
          />
        </a-form-item>
        
        <a-form-item label="替换为">
          <a-textarea 
            v-model:value="batchReplace.replaceText" 
            placeholder="输入替换后的文本内容，例如：http://new-server/d/" 
            :rows="2"
          />
        </a-form-item>
        
        <a-form-item>
          <a-checkbox v-model:checked="batchReplace.previewOnly">仅预览更改（不实际修改文件）</a-checkbox>
        </a-form-item>
        
        <a-form-item>
          <a-checkbox v-model:checked="batchReplace.onlyInvalid">仅处理当前无效的STRM文件</a-checkbox>
          <a-tooltip>
            <template #title>
              <span>选中后将只处理被标记为无效的STRM文件，需要先在健康检测中执行扫描</span>
            </template>
            <question-circle-outlined style="margin-left: 8px" />
          </a-tooltip>
        </a-form-item>
        
        <a-form-item>
          <a-button 
            type="primary" 
            @click="batchReplace.previewOnly ? previewBatchReplace() : executeBatchReplace()"
            :loading="batchReplace.loading" 
            :disabled="!batchReplace.searchText"
          >
            {{ batchReplace.previewOnly ? '预览替换结果' : '执行批量替换' }}
          </a-button>
        </a-form-item>
      </a-form>
      
      <!-- 预览结果展示 -->
      <div v-if="batchReplace.preview && batchReplace.preview.preview_results && batchReplace.preview.preview_results.length > 0" style="margin-top: 20px;">
        <a-divider>预览结果（显示前10个）</a-divider>
        
        <a-list
          class="preview-list"
          :data-source="batchReplace.preview.preview_results"
        >
          <template #header>
            <div>
              <p>共有 <strong>{{ batchReplace.preview.total }}</strong> 个文件，
                其中 <strong>{{ batchReplace.preview.matches }}</strong> 个文件需要替换
              </p>
              <a-button 
                v-if="batchReplace.previewOnly" 
                type="primary"
                @click="executeBatchReplace"
                :loading="batchReplace.loading"
                danger
              >
                确认执行替换
              </a-button>
            </div>
          </template>
          
          <template #renderItem="{ item }">
            <a-list-item>
              <a-card style="width: 100%" :bodyStyle="{ padding: '12px' }">
                <p><strong>文件：</strong>{{ item.path }}</p>
                <a-divider style="margin: 8px 0" />
                <p><strong>原内容：</strong><code>{{ item.original }}</code></p>
                <p><strong>替换后：</strong><code style="color: #52c41a">{{ item.new }}</code></p>
              </a-card>
            </a-list-item>
          </template>
        </a-list>
      </div>
      
      <!-- 替换结果展示 -->
      <div v-if="batchReplace.result && !batchReplace.preview" style="margin-top: 20px;">
        <a-divider>替换结果</a-divider>
        
        <a-result
          :status="batchReplace.result.replaced > 0 ? 'success' : 'info'"
          :title="batchReplace.result.message"
        >
          <template #extra>
            <a-statistic-group>
              <a-statistic title="总文件数" :value="batchReplace.result.total" />
              <a-statistic 
                title="已替换" 
                :value="batchReplace.result.replaced"
                :valueStyle="{ color: batchReplace.result.replaced > 0 ? '#3f8600' : '' }"
              />
              <a-statistic 
                title="未变更" 
                :value="batchReplace.result.unchanged"
              />
              <a-statistic 
                title="失败" 
                :value="batchReplace.result.failed"
                :valueStyle="{ color: batchReplace.result.failed > 0 ? '#cf1322' : '' }"
              />
            </a-statistic-group>
            
            <a-button 
              type="primary" 
              @click="scanHealth" 
              style="margin-top: 16px"
            >
              重新进行健康扫描
            </a-button>
          </template>
        </a-result>
        
        <!-- 如果有替换文件，显示部分 -->
        <div v-if="batchReplace.result.replaced_files && batchReplace.result.replaced_files.length > 0">
          <a-divider>已替换文件（前10个）</a-divider>
          <a-list
            size="small"
            bordered
            :data-source="batchReplace.result.replaced_files"
          >
            <template #renderItem="{ item }">
              <a-list-item>
                {{ item }}
              </a-list-item>
            </template>
          </a-list>
        </div>
        
        <!-- 如果有失败文件，显示部分 -->
        <div v-if="batchReplace.result.failed_details && batchReplace.result.failed_details.length > 0">
          <a-divider>失败文件</a-divider>
          <a-list
            size="small"
            bordered
            :data-source="batchReplace.result.failed_details"
          >
            <template #renderItem="{ item }">
              <a-list-item>
                <strong>{{ item.path }}</strong>: {{ item.reason }}
              </a-list-item>
            </template>
          </a-list>
        </div>
      </div>
      
      <!-- 常见替换模式提示 -->
      <a-card title="常见替换模式" style="margin-top: 20px;">
        <a-collapse ghost>
          <a-collapse-panel key="1" header="Alist服务器地址变更">
            <p><strong>查找内容:</strong> <code>http://旧服务器地址/d</code></p>
            <p><strong>替换为:</strong> <code>http://新服务器地址/d</code></p>
            <a-button type="link" @click="applyPattern('server')">应用此模式</a-button>
          </a-collapse-panel>
          <a-collapse-panel key="2" header="HTTP切换到HTTPS">
            <p><strong>查找内容:</strong> <code>http://</code></p>
            <p><strong>替换为:</strong> <code>https://</code></p>
            <a-button type="link" @click="applyPattern('https')">应用此模式</a-button>
          </a-collapse-panel>
          <a-collapse-panel key="3" header="修正URL编码问题">
            <p><strong>查找内容:</strong> <code>%2F</code></p>
            <p><strong>替换为:</strong> <code>/</code></p>
            <a-button type="link" @click="applyPattern('encoding')">应用此模式</a-button>
          </a-collapse-panel>
        </a-collapse>
      </a-card>
    </a-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'

// 批量替换相关
const batchReplace = ref({
  searchText: '',
  replaceText: '',
  previewOnly: true,
  onlyInvalid: false,
  loading: false,
  preview: null,
  result: null
})

// 问题列表，用于筛选无效STRM文件
const problems = ref([])
const loadingProblems = ref(false)

// 初始化：获取问题列表，用于筛选无效STRM文件
const getProblems = async () => {
  try {
    loadingProblems.value = true
    const response = await fetch('/api/health/problems?type=invalid_strm')
    const data = await response.json()
    
    if (data.problems) {
      problems.value = data.problems
    } else {
      problems.value = []
    }
  } catch (error) {
    console.error('获取问题列表失败:', error)
    message.error('获取问题列表失败，无法使用"仅处理无效STRM文件"选项')
  } finally {
    loadingProblems.value = false
  }
}

// 应用预设替换模式
const applyPattern = (type) => {
  switch (type) {
    case 'server':
      batchReplace.value.searchText = 'http://旧服务器地址/d'
      batchReplace.value.replaceText = 'http://新服务器地址/d'
      message.info('请修改为实际的服务器地址')
      break
    case 'https':
      batchReplace.value.searchText = 'http://'
      batchReplace.value.replaceText = 'https://'
      break
    case 'encoding':
      batchReplace.value.searchText = '%2F'
      batchReplace.value.replaceText = '/'
      break
  }
}

// 预览批量替换
const previewBatchReplace = async () => {
  if (!batchReplace.value.searchText) {
    message.error('请输入要查找的文本内容')
    return
  }
  
  batchReplace.value.loading = true
  batchReplace.value.preview = null
  batchReplace.value.result = null
  
  try {
    // 确定处理的文件路径
    const targetPaths = batchReplace.value.onlyInvalid ? 
      problems.value.filter(p => p.type === 'invalid_strm').map(p => p.path) : 
      null
    
    const response = await fetch('/api/health/strm/replace', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        search_text: batchReplace.value.searchText,
        replace_text: batchReplace.value.replaceText,
        target_paths: targetPaths,
        preview_only: true
      }),
    })
    
    const data = await response.json()
    
    if (data.status === 'preview') {
      batchReplace.value.preview = data
      
      if (data.matches === 0) {
        message.info('没有找到匹配的内容需要替换')
      }
    } else {
      message.error(data.message || '预览失败')
    }
  } catch (error) {
    console.error('预览批量替换失败:', error)
    message.error('预览批量替换失败: ' + (error.message || '未知错误'))
  } finally {
    batchReplace.value.loading = false
  }
}

// 执行批量替换
const executeBatchReplace = async () => {
  if (!batchReplace.value.searchText) {
    message.error('请输入要查找的文本内容')
    return
  }
  
  // 如果是直接执行而不是从预览确认，需要二次确认
  if (!batchReplace.value.preview && !window.confirm('确定要批量替换所有STRM文件的内容吗？此操作不可撤销。')) {
    return
  }
  
  batchReplace.value.loading = true
  
  try {
    // 确定处理的文件路径
    const targetPaths = batchReplace.value.onlyInvalid ? 
      problems.value.filter(p => p.type === 'invalid_strm').map(p => p.path) : 
      null
    
    const response = await fetch('/api/health/strm/replace', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        search_text: batchReplace.value.searchText,
        replace_text: batchReplace.value.replaceText,
        target_paths: targetPaths,
        preview_only: false // 实际执行替换
      }),
    })
    
    const data = await response.json()
    
    if (data.status === 'success') {
      message.success(data.message || '批量替换成功')
      batchReplace.value.result = data
      batchReplace.value.preview = null
      
      // 如果有更改，获取最新的问题列表
      if (data.replaced > 0) {
        getProblems()
      }
    } else {
      message.error(data.message || '批量替换失败')
    }
  } catch (error) {
    console.error('批量替换失败:', error)
    message.error('批量替换失败: ' + (error.message || '未知错误'))
  } finally {
    batchReplace.value.loading = false
  }
}

// 触发健康扫描
const scanHealth = async () => {
  try {
    const response = await fetch('/api/health/start', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        type: 'strm_validity',
        mode: 'full'
      })
    })
    
    const data = await response.json()
    
    if (data.status === 'scanning') {
      message.success('已开始健康扫描，请切换到健康检测页面查看结果')
    } else {
      message.error('启动扫描失败')
    }
  } catch (error) {
    console.error('启动扫描失败:', error)
    message.error('启动扫描失败: ' + error.message)
  }
}

// 组件挂载时获取问题列表
getProblems()
</script>

<style scoped>
.strm-replace-panel {
  padding: 20px;
}

.replace-card {
  min-height: 500px;
}

.panel-header {
  margin-bottom: 24px;
}

.panel-header h2 {
  margin-bottom: 8px;
}

.panel-header p {
  color: #666;
}

@media (max-width: 768px) {
  .panel-header {
    text-align: center;
  }
}
</style> 