<template>
  <div class="strm-health-panel">
    <a-card class="health-card" :bordered="false">
      <!-- 扫描状态展示 -->
      <div class="scan-header">
        <div class="scan-title">
          <h2>STRM健康检测</h2>
          <a-alert v-if="lastScanTime" :type="isScanning ? 'warning' : 'info'" class="scan-status-alert">
            <template #message>
              <span>{{ getLastScanMessage() }}</span>
            </template>
          </a-alert>
        </div>
        <div class="scan-controls">
          <a-form layout="inline">
            <a-form-item label="扫描类型">
              <a-select
                v-model:value="scanType"
                style="width: 180px"
                :disabled="isScanning"
              >
                <a-select-option value="all">全面检测</a-select-option>
                <a-select-option value="strm_validity">STRM文件有效性检测</a-select-option>
                <a-select-option value="video_coverage">视频文件覆盖检测</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item label="扫描模式">
              <a-select
                v-model:value="scanMode"
                style="width: 150px"
                :disabled="isScanning"
              >
                <a-select-option value="full">完整扫描</a-select-option>
                <a-select-option value="incremental">增量扫描</a-select-option>
                <a-select-option value="problems_only">仅检查问题</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item>
              <a-button
                type="primary"
                :disabled="isScanning"
                @click="startScan"
              >
                开始检测
              </a-button>
            </a-form-item>
          </a-form>
        </div>
      </div>

      <!-- 统计信息展示 -->
      <div class="stats-section" v-if="stats">
        <a-row :gutter="16">
          <a-col :span="12">
            <a-statistic title="STRM文件总数" :value="stats.totalStrmFiles" />
          </a-col>
          <a-col :span="12">
            <a-statistic 
              title="无效STRM文件" 
              :value="stats.invalidStrmFiles" 
              :valueStyle="{ color: stats.invalidStrmFiles > 0 ? '#cf1322' : '#3f8600' }"
            />
          </a-col>
        </a-row>
        <a-row :gutter="16" style="margin-top: 16px;">
          <a-col :span="12">
            <a-statistic title="视频文件总数" :value="stats.totalVideoFiles" />
          </a-col>
          <a-col :span="12">
            <a-statistic 
              title="缺失STRM文件"
              :value="stats.missingStrmFiles"
              :valueStyle="{ color: stats.missingStrmFiles > 0 ? '#f5a623' : '#3f8600' }"
            />
          </a-col>
        </a-row>
      </div>
      
      <!-- 进度展示 -->
      <div v-if="isScanning" class="scan-progress">
        <a-progress :percent="scanProgress" status="active" />
        <p class="scan-status">{{ scanStatus }}</p>
      </div>
      
      <!-- 问题列表 -->
      <div class="problem-list" v-if="problems.length > 0">
        <div class="list-header">
          <h3>检测到的问题 ({{ problems.length }})</h3>
          <div class="filter-controls">
            <a-radio-group v-model:value="problemFilter" button-style="solid">
              <a-radio-button value="all">全部</a-radio-button>
              <a-radio-button value="invalid_strm">无效STRM</a-radio-button>
              <a-radio-button value="missing_strm">缺失STRM</a-radio-button>
            </a-radio-group>
            <a-button 
              type="primary"
              @click="getProblems"
              :loading="loadingProblems"
              style="margin-left: 16px"
            >
              刷新列表
            </a-button>
          </div>
        </div>
        
        <a-list
          class="problem-list-items"
          :data-source="filteredProblems"
          :pagination="{ pageSize: 10 }"
        >
          <template #renderItem="{ item }">
            <a-list-item>
              <a-card class="problem-card" :bodyStyle="{ padding: '12px' }">
                <div class="problem-info">
                  <a-tag :color="getTagColor(item.type)">{{ getProblemTypeName(item.type) }}</a-tag>
                  <div class="problem-path">{{ item.path }}</div>
                  <div class="problem-details">{{ item.details }}</div>
                  <div class="problem-time">
                    <span>发现时间: {{ formatTime(item.discoveryTime) }}</span>
                    <span v-if="item.firstDetectedAt && item.firstDetectedAt !== item.discoveryTime">
                      首次发现: {{ formatTime(item.firstDetectedAt) }}
                    </span>
                  </div>
                </div>
                <div class="problem-actions">
                  <a-button
                    type="primary"
                    @click="repairProblem(item)"
                    :loading="repairing[item.id]"
                  >
                    {{ getRepairText(item.type) }}
                  </a-button>
                  
                  <!-- 添加删除按钮，仅对无效STRM文件显示 -->
                  <a-button
                    v-if="item.type === 'invalid_strm'"
                    type="primary"
                    danger
                    @click="deleteStrmFile(item)"
                    :loading="deletingItem === item.id"
                    style="margin-left: 8px"
                  >
                    删除STRM
                  </a-button>
                </div>
              </a-card>
            </a-list-item>
          </template>
        </a-list>
        
        <div class="batch-actions" v-if="filteredProblems.length > 0">
          <a-button
            type="primary"
            @click="repairAllProblems"
            :loading="repairingAll"
            :disabled="isScanning"
          >
            批量{{ getRepairText(problemFilter === 'all' ? '' : problemFilter) }}
          </a-button>
          
          <!-- 添加删除按钮，仅当筛选为无效STRM文件时显示 -->
          <a-button
            v-if="problemFilter === 'invalid_strm'"
            type="primary"
            danger
            @click="deleteAllInvalidStrmFiles"
            :loading="deletingAll"
            :disabled="isScanning"
            style="margin-left: 16px"
          >
            批量删除无效STRM文件
          </a-button>
        </div>
        
        <!-- 清理非远程文件功能 -->
        <div class="cleanup-section" style="margin-top: 20px;">
          <a-card title="清理非远程文件" :bordered="false">
            <template #extra>
              <a-space>
                <a-button
                  type="default"
                  @click="previewCleanup"
                  :loading="cleanupLoading"
                  :disabled="isScanning"
                >
                  预览清理
                </a-button>
                <a-button
                  type="primary"
                  danger
                  @click="executeCleanup"
                  :loading="cleanupLoading"
                  :disabled="isScanning"
                >
                  执行清理
                </a-button>
              </a-space>
            </template>
            
            <div class="cleanup-info">
              <a-alert type="info" show-icon style="margin-bottom: 16px;">
                <template #message>
                  <span>清理功能将删除没有@remote(网盘)标识的nfo、mediainfo.json、ass、srt文件</span>
                </template>
                <template #description>
                  <span>这些文件通常是本地生成的元数据文件，清理后可以释放存储空间</span>
                </template>
              </a-alert>
              
              <div v-if="cleanupResult" class="cleanup-result">
                <a-row :gutter="16">
                  <a-col :span="6">
                    <a-statistic
                      title="发现文件"
                      :value="cleanupResult.data?.found_files?.length || 0"
                      :value-style="{ color: '#1890ff' }"
                    />
                  </a-col>
                  <a-col :span="6">
                    <a-statistic
                      title="删除文件"
                      :value="cleanupResult.data?.deleted_files?.length || 0"
                      :value-style="{ color: '#3f8600' }"
                    />
                  </a-col>
                  <a-col :span="6">
                    <a-statistic
                      title="失败文件"
                      :value="cleanupResult.data?.failed_files?.length || 0"
                      :value-style="{ color: '#cf1322' }"
                    />
                  </a-col>
                  <a-col :span="6">
                    <a-statistic
                      title="释放空间"
                      :value="cleanupResult.data?.total_size_formatted || '0 B'"
                      :value-style="{ color: '#722ed1' }"
                    />
                  </a-col>
                </a-row>
                
                <div v-if="cleanupResult.data?.found_files?.length > 0" style="margin-top: 16px;">
                  <a-collapse>
                    <a-collapse-panel key="files" header="查看文件列表">
                      <a-list
                        size="small"
                        :data-source="cleanupResult.data.found_files"
                        :pagination="{ pageSize: 10 }"
                      >
                        <template #renderItem="{ item }">
                          <a-list-item>
                            <a-space>
                              <file-outlined />
                              <span>{{ item.path }}</span>
                              <a-tag>{{ item.size_formatted }}</a-tag>
                            </a-space>
                          </a-list-item>
                        </template>
                      </a-list>
                    </a-collapse-panel>
                  </a-collapse>
                </div>
              </div>
            </div>
          </a-card>
        </div>
      </div>
      
      <!-- 无问题状态 -->
      <div v-else-if="!isScanning && hasScanned" class="no-problems">
        <div v-if="stats && (stats.invalidStrmFiles > 0 || stats.missingStrmFiles > 0)">
          <a-alert type="warning" show-icon>
            <template #message>
              <span>统计显示有问题文件，但问题列表为空。请尝试刷新页面或重新扫描。</span>
            </template>
            <template #description>
              <a-button type="primary" @click="getProblems">刷新问题列表</a-button>
            </template>
          </a-alert>
        </div>
        <a-empty v-else description="未检测到问题">
          <template #description>
            <span>太棒了！所有STRM文件都是有效的，并且所有视频文件都有对应的STRM文件。</span>
          </template>
        </a-empty>
      </div>

      <!-- 清空数据按钮 -->
      <div class="advanced-actions" v-if="!isScanning">
        <a-popconfirm
          title="确定要清空健康检测数据吗？这将删除所有记录的问题和状态信息。"
          @confirm="clearHealthData"
        >
          <a-button danger>清空健康数据</a-button>
        </a-popconfirm>
      </div>

      <!-- Emby刷新队列状态 -->
      <a-card v-if="embyStatus.enabled" title="Emby刷新队列" style="margin-top: 20px;" :loading="embyLoading">
        <a-statistic-countdown 
          v-if="nextRefreshTime"
          title="下次检查时间" 
          :value="nextRefreshTime" 
          format="HH:mm:ss" 
          style="margin-bottom: 16px"
        />
        
        <a-row :gutter="16">
          <a-col :span="6">
            <a-statistic
              title="总队列数"
              :value="embyStatus.queue_stats?.total || 0"
            />
          </a-col>
          <a-col :span="6">
            <a-statistic
              title="待处理"
              :value="embyStatus.queue_stats?.pending || 0"
              :value-style="{ color: '#1890ff' }"
            />
          </a-col>
          <a-col :span="6">
            <a-statistic
              title="成功"
              :value="embyStatus.queue_stats?.success || 0"
              :value-style="{ color: '#3f8600' }"
            />
          </a-col>
          <a-col :span="6">
            <a-statistic
              title="失败"
              :value="embyStatus.queue_stats?.failed || 0"
              :value-style="embyStatus.queue_stats?.failed > 0 ? { color: '#cf1322' } : {}"
            />
          </a-col>
        </a-row>
        
        <a-divider />
        
        <!-- 切换标签页 -->
        <a-tabs v-model:activeKey="embyActiveTab">
          <!-- 最近成功刷新项目 -->
          <a-tab-pane key="success" tab="最近成功项目">
            <div v-if="embyStatus.recent_success && embyStatus.recent_success.length > 0">
              <a-list
                size="small"
                :data-source="embyStatus.recent_success"
              >
                <template #renderItem="{ item }">
                  <a-list-item>
                    <a-row style="width: 100%">
                      <a-col :span="16">
                        <a-space>
                          <check-circle-outlined style="color: #52c41a" />
                          <span>
                            <a-tag :color="getEmbyTypeColor(item.type)">{{ getEmbyTypeLabel(item.type) }}</a-tag>
                            {{ item.display_name }}
                          </span>
                        </a-space>
                      </a-col>
                      <a-col :span="8" style="text-align: right">
                        <span>{{ item.refresh_time }}</span>
                      </a-col>
                    </a-row>
                  </a-list-item>
                </template>
              </a-list>
            </div>
            <a-empty v-else description="暂无成功刷新项目" />
          </a-tab-pane>
          
          <!-- 最近失败刷新项目 -->
          <a-tab-pane key="failed" tab="失败项目">
            <div v-if="embyStatus.recent_failed && embyStatus.recent_failed.length > 0">
              <a-list
                size="small"
                :data-source="embyStatus.recent_failed"
              >
                <template #renderItem="{ item }">
                  <a-list-item>
                    <a-card style="width: 100%; margin-bottom: 8px" :bodyStyle="{ padding: '12px' }">
                      <a-row>
                        <a-col :span="16">
                          <div>
                            <a-space>
                              <warning-outlined style="color: #fa8c16" />
                              <a-tag :color="getEmbyTypeColor(item.type)">{{ getEmbyTypeLabel(item.type) }}</a-tag>
                              <span style="font-weight: bold">{{ item.display_name }}</span>
                            </a-space>
                          </div>
                          <div style="margin-top: 4px; color: #cf1322;">
                            <span>错误: {{ item.error }}</span>
                          </div>
                        </a-col>
                        <a-col :span="8" style="text-align: right">
                          <div style="margin-bottom: 4px;">失败时间: {{ item.failed_time }}</div>
                          <div style="display: flex; justify-content: flex-end; align-items: center;">
                            <span style="margin-right: 16px;">
                              重试次数: {{ item.retry_count }}/{{ item.max_retries }}
                              <br />
                              下次重试: {{ item.next_retry }}
                            </span>
                            <a-button 
                              type="primary" 
                              size="small"
                              @click="forceRefreshEmbyItem(item.path)"
                              :loading="refreshingItem === item.path"
                            >
                              立即刷新
                            </a-button>
                          </div>
                        </a-col>
                      </a-row>
                    </a-card>
                  </a-list-item>
                </template>
              </a-list>
            </div>
            <a-empty v-else description="暂无失败刷新项目" />
          </a-tab-pane>
          
          <!-- 全部队列 -->
          <a-tab-pane key="queue" tab="完整队列">
            <div class="queue-filter" style="margin-bottom: 16px;">
              <a-row :gutter="16">
                <a-col :span="8">
                  <a-select 
                    v-model:value="queueFilter.status" 
                    style="width: 100%"
                    placeholder="状态筛选"
                    @change="loadEmbyQueue"
                  >
                    <a-select-option value="">全部状态</a-select-option>
                    <a-select-option value="pending">待处理</a-select-option>
                    <a-select-option value="processing">处理中</a-select-option>
                    <a-select-option value="success">成功</a-select-option>
                    <a-select-option value="failed">失败</a-select-option>
                  </a-select>
                </a-col>
                <a-col :span="8">
                  <a-select 
                    v-model:value="queueFilter.sortBy" 
                    style="width: 100%"
                    placeholder="排序方式"
                    @change="loadEmbyQueue"
                  >
                    <a-select-option value="timestamp">时间</a-select-option>
                    <a-select-option value="path">路径</a-select-option>
                    <a-select-option value="status">状态</a-select-option>
                  </a-select>
                </a-col>
                <a-col :span="8">
                  <a-select 
                    v-model:value="queueFilter.sortOrder" 
                    style="width: 100%"
                    placeholder="排序顺序"
                    @change="loadEmbyQueue"
                  >
                    <a-select-option value="desc">降序</a-select-option>
                    <a-select-option value="asc">升序</a-select-option>
                  </a-select>
                </a-col>
              </a-row>
            </div>
            
            <div v-if="embyQueue.items && embyQueue.items.length > 0">
              <a-list
                size="small"
                :data-source="embyQueue.items"
              >
                <template #renderItem="{ item }">
                  <a-list-item>
                    <a-card style="width: 100%; margin-bottom: 8px" :bodyStyle="{ padding: '12px' }">
                      <a-row>
                        <a-col :span="16">
                          <div>
                            <a-space>
                              <check-circle-outlined v-if="item.status === 'success'" style="color: #52c41a" />
                              <warning-outlined v-else-if="item.status === 'failed'" style="color: #fa8c16" />
                              <loading-outlined v-else-if="item.status === 'processing'" style="color: #1890ff" />
                              <clock-circle-outlined v-else style="color: #8c8c8c" />
                              
                              <a-tag :color="getStatusColor(item.status)">{{ getStatusLabel(item.status) }}</a-tag>
                              <a-tag :color="getEmbyTypeColor(item.media_type || item.emby_type)">
                                {{ getEmbyTypeLabel(item.media_type || item.emby_type) }}
                              </a-tag>
                              <span style="font-weight: bold">{{ item.display_name }}</span>
                            </a-space>
                          </div>
                          <div v-if="item.status === 'failed'" style="margin-top: 4px; color: #cf1322;">
                            <span>错误: {{ item.error }}</span>
                          </div>
                          <div style="margin-top: 4px; color: #8c8c8c; font-size: 12px;">
                            <span>路径: {{ item.path }}</span>
                          </div>
                        </a-col>
                        <a-col :span="8" style="text-align: right">
                          <div style="margin-bottom: 4px;">{{ item.time_str }}</div>
                          <div v-if="item.status === 'failed'" style="display: flex; justify-content: flex-end; align-items: center;">
                            <span style="margin-right: 16px;">
                              重试次数: {{ item.retry_count }}/{{ item.max_retries }}
                              <br />
                              下次重试: {{ item.next_retry_str || '不再重试' }}
                            </span>
                            <a-button 
                              type="primary" 
                              size="small"
                              @click="forceRefreshEmbyItem(item.path)"
                              :loading="refreshingItem === item.path"
                            >
                              立即刷新
                            </a-button>
                          </div>
                          <div v-else-if="item.status === 'success'">
                            <a-button 
                              type="primary" 
                              size="small"
                              @click="forceRefreshEmbyItem(item.path)"
                              :loading="refreshingItem === item.path"
                            >
                              重新刷新
                            </a-button>
                          </div>
                        </a-col>
                      </a-row>
                    </a-card>
                  </a-list-item>
                </template>
              </a-list>
              
              <!-- 分页 -->
              <div style="text-align: center; margin-top: 16px;">
                <a-pagination
                  v-model:current="queueFilter.page"
                  :total="embyQueue.total"
                  :pageSize="queueFilter.pageSize"
                  @change="loadEmbyQueue"
                  showSizeChanger
                  :pageSizeOptions="['10', '20', '50', '100']"
                  @showSizeChange="onPageSizeChange"
                />
              </div>
            </div>
            <a-empty v-else-if="!queueLoading" description="暂无队列项目" />
            <div v-else style="text-align: center; padding: 20px;">
              <a-spin />
            </div>
          </a-tab-pane>
        </a-tabs>
        
        <a-divider />
        
        <div style="display: flex; justify-content: center; gap: 16px;">
          <a-button 
            type="primary" 
            @click="refreshEmbyStatus" 
            :loading="embyLoading"
          >
            刷新状态
          </a-button>
          <a-button 
            type="primary" 
            @click="forceRefreshAllFailedItems" 
            :loading="refreshingAllItems"
            :disabled="!embyStatus.recent_failed || embyStatus.recent_failed.length === 0"
            danger
          >
            重新刷新失败项
          </a-button>
          <a-popconfirm
            title="确定要清空刷新队列吗？这将移除所有待处理和失败的项目。"
            @confirm="clearEmbyQueue"
          >
            <a-button 
              danger
              :loading="clearingQueue"
            >
              清空刷新队列
            </a-button>
          </a-popconfirm>
        </div>
      </a-card>
    </a-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { message } from 'ant-design-vue'
import { 
  CheckCircleOutlined, 
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  WarningOutlined,
  QuestionCircleOutlined,
  LoadingOutlined,
  ClockCircleOutlined,
  FileOutlined
} from '@ant-design/icons-vue'

// 扫描参数
const scanType = ref('all')
const scanMode = ref('full')

// 扫描状态
const isScanning = ref(false)
const scanProgress = ref(0)
const scanStatus = ref('')
const lastScanTime = ref(null)
const lastScanTimeStr = ref('')
const hasScanned = ref(false)
const stats = ref(null)

// 问题相关
const problems = ref([])
const problemFilter = ref('all')
const repairing = ref({})
const repairingAll = ref(false)
const loadingProblems = ref(false)

// 计算筛选后的问题列表
const filteredProblems = computed(() => {
  if (problemFilter.value === 'all') {
    return problems.value
  }
  return problems.value.filter(problem => problem.type === problemFilter.value)
})

// 删除相关状态
const deletingAll = ref(false)
const deletingItem = ref(null)

// 清理非远程文件相关状态
const cleanupLoading = ref(false)
const cleanupResult = ref(null)

// Emby刷新队列相关
const embyStatus = ref({})
const embyLoading = ref(false)
const nextRefreshTime = ref(null)
const refreshTimer = ref(null)
const refreshingAllItems = ref(false)
const refreshingItem = ref(null)
const clearingQueue = ref(false)
const embyActiveTab = ref('success')

// Emby队列状态和筛选
const embyQueue = ref({
  items: [],
  total: 0,
  page: 1,
  pageSize: 20,
  total_pages: 1
})
const queueLoading = ref(false)
const queueFilter = ref({
  status: '',
  page: 1,
  pageSize: 20,
  sortBy: 'timestamp',
  sortOrder: 'desc'
})

// 初始化：获取状态和问题列表
onMounted(async () => {
  await getStatus()
  await getProblems()
  await refreshEmbyStatus()
})

// 获取扫描状态
const getStatus = async () => {
  try {
    const response = await fetch('/api/health/status')
    const data = await response.json()
    
    isScanning.value = data.isScanning
    scanProgress.value = data.progress
    scanStatus.value = data.status
    lastScanTime.value = data.lastScanTime
    lastScanTimeStr.value = data.lastScanTimeStr
    scanType.value = data.scanType || 'all'
    scanMode.value = data.scanMode || 'full'
    
    // 更新统计信息
    stats.value = data.stats || null
    
    if (data.lastScanTime) {
      hasScanned.value = true
    }
    
    // 如果正在扫描，每5秒更新一次状态
    if (data.isScanning) {
      setTimeout(getStatus, 2000)
    }
  } catch (error) {
    console.error('获取扫描状态失败:', error)
  }
}

// 获取问题列表
const getProblems = async () => {
  try {
    loadingProblems.value = true
    const response = await fetch(`/api/health/problems?type=${problemFilter.value === 'all' ? '' : problemFilter.value}`)
    const data = await response.json()
    
    if (data.problems) {
      problems.value = data.problems
      console.log(`获取到 ${problems.value.length} 个健康问题`)
    } else {
      problems.value = []
      console.log('未获取到健康问题')
    }
    
    // 如果获取了新的统计信息，更新它
    if (data.stats) {
      stats.value = data.stats
    }
    
    // 如果统计信息显示有问题，但问题列表为空，尝试重新获取
    if ((stats.value?.invalidStrmFiles > 0 || stats.value?.missingStrmFiles > 0) && problems.value.length === 0) {
      console.warn('统计数据表明有问题，但问题列表为空，5秒后重试获取')
      setTimeout(getProblems, 5000)
    }
  } catch (error) {
    console.error('获取问题列表失败:', error)
    message.error('获取问题列表失败，请刷新页面重试')
  } finally {
    loadingProblems.value = false
  }
}

// 开始扫描
const startScan = async () => {
  try {
    isScanning.value = true
    scanProgress.value = 0
    scanStatus.value = '正在初始化扫描...'
    
    const response = await fetch('/api/health/start', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        type: scanType.value,
        mode: scanMode.value
      })
    })
    
    const data = await response.json()
    
    if (data.status === 'scanning') {
      message.success('已开始健康扫描')
      getStatus()
      
      // 定时检查扫描是否完成
      checkScanCompleted()
    } else {
      message.error('启动扫描失败')
      isScanning.value = false
    }
  } catch (error) {
    console.error('启动扫描失败:', error)
    message.error('启动扫描失败: ' + error.message)
    isScanning.value = false
  }
}

// 定时检查扫描是否完成
const checkScanCompleted = () => {
  setTimeout(async () => {
    if (isScanning.value) {
      await getStatus()
      if (isScanning.value) {
        checkScanCompleted()
      } else {
        // 扫描完成后，获取问题列表
        await getProblems()
        message.success('扫描完成')
      }
    }
  }, 2000)
}

// 修复单个问题
const repairProblem = async (problem) => {
  try {
    repairing.value[problem.id] = true
    
    const endpoint = problem.type === 'invalid_strm' ? 'repair/invalid_strm' : 'repair/missing_strm'
    
    const response = await fetch(`/api/health/${endpoint}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        paths: [problem.path],
        type: problem.type
      })
    })
    
    const data = await response.json()
    
    if (data.success) {
      message.success(data.message)
      
      // 从列表中移除已修复的问题
      problems.value = problems.value.filter(p => p.id !== problem.id)
      
      // 获取最新状态和统计信息
      await getStatus()
    } else {
      message.error(data.message || '修复失败')
    }
  } catch (error) {
    console.error('修复问题失败:', error)
    message.error('修复失败: ' + error.message)
  } finally {
    repairing.value[problem.id] = false
  }
}

// 批量修复问题
const repairAllProblems = async () => {
  // 如果没有问题，不执行任何操作
  if (filteredProblems.value.length === 0) {
    return
  }
  
  // 设置批量修复状态
  repairingAll.value = true
  
  try {
    // 判断是否按类型筛选
    const currentFilter = problemFilter.value
    
    // 按类型分组问题
    const invalidStrm = filteredProblems.value.filter(p => p.type === 'invalid_strm').map(p => p.path)
    const missingStrm = filteredProblems.value.filter(p => p.type === 'missing_strm').map(p => p.path)
    
    let hasErrors = false
    
    // 修复无效STRM文件
    if (invalidStrm.length > 0 && (currentFilter === 'all' || currentFilter === 'invalid_strm')) {
      const response = await fetch('/api/health/repair/invalid_strm', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          type: 'invalid_strm',
          paths: invalidStrm
        }),
      })
      
      const data = await response.json()
      
      if (data.success) {
        message.success(data.message || '成功修复无效STRM文件')
      } else {
        message.error(data.message || '修复无效STRM文件失败')
        hasErrors = true
      }
    }
    
    // 修复缺失STRM文件
    if (missingStrm.length > 0 && (currentFilter === 'all' || currentFilter === 'missing_strm')) {
      const response = await fetch('/api/health/repair/missing_strm', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          type: 'missing_strm',
          paths: missingStrm
        }),
      })
      
      const data = await response.json()
      
      if (data.success) {
        message.success(data.message || '成功为缺失文件生成STRM')
      } else {
        message.error(data.message || '生成STRM文件失败')
        hasErrors = true
      }
    }
    
    if (!hasErrors && (invalidStrm.length > 0 || missingStrm.length > 0)) {
      message.success('所有问题已成功修复')
    }
    
    // 重新获取问题列表和状态
    await getProblems()
    await getStatus()
  } catch (error) {
    console.error('批量修复失败:', error)
    message.error('批量修复失败: ' + (error.message || '未知错误'))
  } finally {
    repairingAll.value = false
  }
}

// 批量删除无效STRM文件
const deleteAllInvalidStrmFiles = async () => {
  // 确认对话框
  if (!window.confirm(`确定要删除所有 ${filteredProblems.value.length} 个无效的STRM文件吗？此操作不可撤销。`)) {
    return
  }
  
  // 设置批量删除状态
  deletingAll.value = true
  
  try {
    // 获取要删除的路径列表
    const paths = filteredProblems.value
      .filter(problem => problem.type === 'invalid_strm')
      .map(problem => problem.path)
    
    if (paths.length === 0) {
      message.info('没有无效的STRM文件需要删除')
      deletingAll.value = false
      return
    }
    
    // 调用删除接口
    const response = await fetch('/api/health/strm/delete', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(paths),
    })
    
    const data = await response.json()
    
    if (data.status === 'success' || data.status === 'partial_success') {
      message.success(data.message || `成功删除 ${data.deleted.length} 个无效STRM文件`)
      
      // 如果有失败的文件，显示详细信息
      if (data.failed && data.failed.length > 0) {
        console.error('部分文件删除失败:', data.failed)
        message.warning(`有 ${data.failed.length} 个文件删除失败`)
      }
      
      // 重新获取问题列表和状态
      await getProblems()
      await getStatus()
    } else {
      message.error(data.message || '删除文件失败')
    }
  } catch (error) {
    console.error('批量删除文件失败:', error)
    message.error('批量删除文件失败: ' + (error.message || '未知错误'))
  } finally {
    deletingAll.value = false
  }
}

// 清空健康数据
const clearHealthData = async () => {
  try {
    const response = await fetch('/api/health/clear_data', {
      method: 'POST'
    })
    
    const data = await response.json()
    
    if (data.success) {
      message.success('健康数据已清空')
      problems.value = []
      await getStatus()
    } else {
      message.error(data.message || '清空数据失败')
    }
  } catch (error) {
    console.error('清空健康数据失败:', error)
    message.error('清空数据失败: ' + error.message)
  }
}

// 格式化时间戳
const formatTime = (timestamp) => {
  if (!timestamp) return ''
  const date = new Date(timestamp * 1000)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

// 获取最后扫描时间消息
const getLastScanMessage = () => {
  if (isScanning.value) {
    return `正在进行${getScanTypeName(scanType.value)}，模式：${getScanModeName(scanMode.value)}`
  }
  
  if (!lastScanTime.value) {
    return '尚未进行过健康检测'
  }
  
  return `上次${getScanTypeName(scanType.value)}：${lastScanTimeStr.value}`
}

// 获取扫描类型名称
const getScanTypeName = (type) => {
  const types = {
    'all': '全面检测',
    'strm_validity': 'STRM文件有效性检测',
    'video_coverage': '视频文件覆盖检测'
  }
  return types[type] || '未知检测'
}

// 获取扫描模式名称
const getScanModeName = (mode) => {
  const modes = {
    'full': '完整扫描',
    'incremental': '增量扫描',
    'problems_only': '仅检查问题'
  }
  return modes[mode] || '未知模式'
}

// 获取问题类型名称
const getProblemTypeName = (type) => {
  return type === 'invalid_strm' ? '无效STRM' : '缺失STRM'
}

// 获取标签颜色
const getTagColor = (type) => {
  return type === 'invalid_strm' ? 'red' : 'orange'
}

// 获取修复按钮文本
const getRepairText = (type) => {
  if (type === 'invalid_strm') return '清理无效STRM'
  if (type === 'missing_strm') return '生成STRM'
  return '修复所有问题'
}

// 获取Emby刷新状态
const refreshEmbyStatus = async () => {
  embyLoading.value = true
  try {
    const response = await fetch('/api/health/emby/refresh/status')
    if (response.ok) {
      const data = await response.json()
      // 添加错误处理
      if (data.error) {
        console.error("获取刷新状态错误:", data.error);
        message.error("获取Emby刷新状态失败: " + data.error);
        return;
      }
      
      embyStatus.value = data
      
      // 设置下次刷新时间（60秒后）
      nextRefreshTime.value = Date.now() + 60000
      
      // 设置定时器，60秒后自动刷新
      if (refreshTimer.value) {
        clearTimeout(refreshTimer.value)
      }
      refreshTimer.value = setTimeout(() => {
        refreshEmbyStatus()
      }, 60000)
      
      // 如果当前在队列标签页，顺便刷新队列数据
      if (embyActiveTab.value === 'queue') {
        loadEmbyQueue()
      }
    } else {
      message.error('获取Emby刷新状态失败')
    }
  } catch (e) {
    console.error('获取Emby刷新状态失败:', e)
    message.error('获取Emby刷新状态失败: ' + (e.message || '未知错误'))
  } finally {
    embyLoading.value = false
  }
}

// 加载Emby刷新队列详情
const loadEmbyQueue = async () => {
  queueLoading.value = true
  try {
    const queryParams = new URLSearchParams({
      page: queueFilter.value.page,
      page_size: queueFilter.value.pageSize,
      sort_by: queueFilter.value.sortBy,
      sort_order: queueFilter.value.sortOrder
    })
    
    if (queueFilter.value.status) {
      queryParams.append('status', queueFilter.value.status)
    }
    
    const response = await fetch(`/api/health/emby/refresh/queue?${queryParams.toString()}`)
    if (response.ok) {
      const data = await response.json()
      embyQueue.value = data
    } else {
      message.error('获取Emby刷新队列失败')
    }
  } catch (e) {
    console.error('获取Emby刷新队列失败:', e)
    message.error('获取Emby刷新队列失败: ' + (e.message || '未知错误'))
  } finally {
    queueLoading.value = false
  }
}

// 监听标签页切换，自动加载队列数据
watch(embyActiveTab, (newTab) => {
  if (newTab === 'queue' && (!embyQueue.value.items || embyQueue.value.items.length === 0)) {
    loadEmbyQueue()
  }
})

// 分页大小变化处理
const onPageSizeChange = (page, pageSize) => {
  queueFilter.value.page = page
  queueFilter.value.pageSize = pageSize
  loadEmbyQueue()
}

// 获取状态标签和颜色
const getStatusLabel = (status) => {
  const labels = {
    'pending': '待处理',
    'processing': '处理中',
    'success': '成功',
    'failed': '失败'
  }
  return labels[status] || status
}

const getStatusColor = (status) => {
  const colors = {
    'pending': '#8c8c8c',
    'processing': '#1890ff',
    'success': '#52c41a',
    'failed': '#f5222d'
  }
  return colors[status] || '#8c8c8c'
}

// 获取Emby媒体类型标签和颜色
const getEmbyTypeLabel = (type) => {
  if (!type) return '未知类型';
  
  const labels = {
    'Movie': '电影',
    'Series': '剧集',
    'Season': '季',
    'Episode': '剧集',
    'MusicVideo': '音乐视频',
    'Audio': '音频',
    'Video': '视频',
    '已删除': '已删除'
  }
  return labels[type] || type || '未知'
}

const getEmbyTypeColor = (type) => {
  if (!type) return '#8c8c8c';
  
  const colors = {
    'Movie': '#722ed1',
    'Series': '#13c2c2',
    'Season': '#13c2c2',
    'Episode': '#13c2c2',
    'MusicVideo': '#eb2f96',
    'Audio': '#fa8c16',
    'Video': '#1890ff',
    '已删除': '#5c5c5c'
  }
  return colors[type] || '#8c8c8c'
}

// 强制刷新STRM文件
const forceRefreshEmbyItem = async (path) => {
  try {
    refreshingItem.value = path
    const response = await fetch(`/api/health/emby/refresh/force?path=${encodeURIComponent(path)}`, {
      method: 'POST'
    })
    
    if (response.ok) {
      const data = await response.json()
      if (data.success) {
        message.success(data.message)
        // 刷新状态
        setTimeout(() => {
          refreshEmbyStatus()
        }, 1000)
      } else {
        message.error(data.message)
      }
    } else {
      message.error('强制刷新失败')
    }
  } catch (e) {
    console.error('强制刷新失败:', e)
    message.error('强制刷新失败: ' + e.message)
  } finally {
    refreshingItem.value = null
  }
}

// 强制刷新所有失败项
const forceRefreshAllFailedItems = async () => {
  if (!embyStatus.value.recent_failed || embyStatus.value.recent_failed.length === 0) {
    return
  }
  
  try {
    refreshingAllItems.value = true
    
    // 获取所有失败项的路径
    const paths = embyStatus.value.recent_failed.map(item => item.path)
    
    // 使用批量API一次刷新所有项目
    const response = await fetch('/api/health/emby/refresh/batch', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(paths)
    })
    
    if (response.ok) {
      const data = await response.json()
      if (data.success) {
        message.success(data.message)
      } else {
        message.error(data.message)
      }
    } else {
      message.error('批量刷新失败')
    }
    
    // 刷新状态
    await refreshEmbyStatus()
  } catch (e) {
    console.error('重新刷新失败项失败:', e)
    message.error('重新刷新失败: ' + e.message)
  } finally {
    refreshingAllItems.value = false
  }
}

// 清空刷新队列
const clearEmbyQueue = async () => {
  try {
    clearingQueue.value = true
    const response = await fetch('/api/health/emby/refresh/clear', {
      method: 'POST'
    })
    
    if (response.ok) {
      const data = await response.json()
      if (data.status === 'success') {
        message.success(data.message || '刷新队列已清空')
        // 刷新状态
        await refreshEmbyStatus()
      } else {
        message.error(data.message || '清空队列失败')
      }
    } else {
      message.error('清空刷新队列失败')
    }
  } catch (e) {
    console.error('清空刷新队列失败:', e)
    message.error('清空队列失败: ' + (e.message || '未知错误'))
  } finally {
    clearingQueue.value = false
  }
}

// 删除单个STRM文件
const deleteStrmFile = async (item) => {
  // 确认对话框
  if (!window.confirm(`确定要删除STRM文件 "${item.path}" 吗？此操作不可撤销。`)) {
    return
  }
  
  // 设置删除状态
  deletingItem.value = item.id
  
  try {
    // 调用删除接口
    const response = await fetch('/api/health/strm/delete', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify([item.path]),
    })
    
    const data = await response.json()
    
    if (data.status === 'success' || data.status === 'partial_success') {
      message.success(data.message || '成功删除STRM文件')
      
      // 重新获取问题列表和状态
      await getProblems()
      await getStatus()
    } else {
      message.error(data.message || '删除文件失败')
    }
  } catch (error) {
    console.error('删除文件失败:', error)
    message.error('删除文件失败: ' + (error.message || '未知错误'))
  } finally {
    deletingItem.value = null
  }
}

// 预览清理非远程文件
const previewCleanup = async () => {
  try {
    cleanupLoading.value = true
    cleanupResult.value = null
    
    const response = await fetch('/api/health/cleanup/non-remote-files', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        preview_only: true
      }),
    })
    
    const data = await response.json()
    
    if (data.success) {
      cleanupResult.value = data
      message.success(data.message)
    } else {
      message.error(data.message || '预览清理失败')
    }
  } catch (error) {
    console.error('预览清理失败:', error)
    message.error('预览清理失败: ' + (error.message || '未知错误'))
  } finally {
    cleanupLoading.value = false
  }
}

// 执行清理非远程文件
const executeCleanup = async () => {
  // 确认对话框
  if (!window.confirm('确定要删除所有没有@remote(网盘)标识的nfo、mediainfo.json、ass、srt文件吗？此操作不可撤销。')) {
    return
  }
  
  try {
    cleanupLoading.value = true
    cleanupResult.value = null
    
    const response = await fetch('/api/health/cleanup/non-remote-files', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        preview_only: false
      }),
    })
    
    const data = await response.json()
    
    if (data.success) {
      cleanupResult.value = data
      message.success(data.message)
    } else {
      message.error(data.message || '执行清理失败')
    }
  } catch (error) {
    console.error('执行清理失败:', error)
    message.error('执行清理失败: ' + (error.message || '未知错误'))
  } finally {
    cleanupLoading.value = false
  }
}

// 组件卸载时清理定时器
onUnmounted(() => {
  if (refreshTimer.value) {
    clearTimeout(refreshTimer.value)
  }
})
</script>

<style scoped>
.strm-health-panel {
  padding: 20px;
}

.health-card {
  min-height: 500px;
}

.scan-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.scan-title {
  flex: 1;
  margin-right: 20px;
  margin-bottom: 20px;
}

.scan-status-alert {
  margin-top: 10px;
}

.scan-controls {
  display: flex;
  align-items: flex-start;
}

.scan-progress {
  margin: 20px 0;
}

.scan-status {
  margin-top: 8px;
  color: #666;
}

.stats-section {
  margin-bottom: 24px;
  padding: 16px;
  background-color: #f9f9f9;
  border-radius: 4px;
}

.problem-list {
  margin-top: 20px;
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.filter-controls {
  margin-left: auto;
}

.problem-card {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.problem-info {
  flex: 1;
}

.problem-path {
  font-weight: bold;
  margin: 8px 0;
  word-break: break-all;
}

.problem-details {
  color: #666;
  margin-bottom: 8px;
}

.problem-time {
  font-size: 12px;
  color: #999;
  display: flex;
  flex-direction: column;
}

.problem-actions {
  margin-left: 16px;
}

.no-problems {
  margin: 40px 0;
  text-align: center;
}

.batch-actions {
  margin-top: 20px;
  text-align: right;
}

.advanced-actions {
  margin-top: 30px;
  border-top: 1px solid #f0f0f0;
  padding-top: 20px;
  text-align: right;
}

@media (max-width: 768px) {
  .scan-header {
    flex-direction: column;
  }
  
  .scan-title, .scan-controls {
    width: 100%;
  }
  
  .problem-card {
    flex-direction: column;
    align-items: flex-start;
  }
  
  .problem-actions {
    margin-left: 0;
    margin-top: 12px;
    align-self: flex-end;
  }
}
</style> 