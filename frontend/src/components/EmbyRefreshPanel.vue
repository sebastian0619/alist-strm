<template>
  <div class="emby-refresh-panel">
    <a-card class="emby-card" :bordered="false">
      <div class="emby-header">
        <div class="emby-title">
          <h2>Emby刷库队列管理</h2>
          <a-alert v-if="nextRefreshTime" :type="embyLoading ? 'warning' : 'info'" class="refresh-status-alert">
            <template #message>
              <span>下次刷新检查时间：{{ formatTime(nextRefreshTime) }}</span>
            </template>
          </a-alert>
        </div>
        <div class="emby-actions">
          <a-space>
            <a-button type="primary" @click="refreshEmbyStatus" :loading="embyLoading">
              刷新状态
            </a-button>
            <a-tooltip title="手动触发所有待处理项的刷新">
              <a-button type="primary" @click="processAllPendingItems" :loading="processingAll">
                处理所有待处理项
              </a-button>
            </a-tooltip>
          </a-space>
        </div>
      </div>

      <!-- Emby状态概览 -->
      <a-row :gutter="16" class="emby-stats">
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
      
      <!-- 队列筛选工具栏 -->
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
              <a-select-option value="added_time">添加时间</a-select-option>
              <a-select-option value="refresh_time">刷新时间</a-select-option>
              <a-select-option value="next_retry">下次重试时间</a-select-option>
            </a-select>
          </a-col>
          <a-col :span="8">
            <a-select 
              v-model:value="queueFilter.sortOrder" 
              style="width: 100%"
              placeholder="排序顺序"
              @change="loadEmbyQueue"
            >
              <a-select-option value="desc">从新到旧</a-select-option>
              <a-select-option value="asc">从旧到新</a-select-option>
            </a-select>
          </a-col>
        </a-row>
      </div>
      
      <!-- 队列列表 -->
      <a-tabs v-model:activeKey="embyActiveTab">
        <!-- 待处理项目 -->
        <a-tab-pane key="pending" tab="待处理项目">
          <div v-if="embyStatus.queue && embyStatus.queue.pending && embyStatus.queue.pending.length > 0">
            <a-list
              size="small"
              :data-source="embyStatus.queue.pending"
              :pagination="{ pageSize: 10 }"
            >
              <template #renderItem="{ item }">
                <a-list-item>
                  <a-card style="width: 100%; margin-bottom: 8px" :bodyStyle="{ padding: '12px' }">
                    <a-row>
                      <a-col :span="16">
                        <div>
                          <a-space>
                            <clock-circle-outlined style="color: #1890ff" />
                            <a-tag :color="getEmbyTypeColor(item.type)">{{ getEmbyTypeLabel(item.type) }}</a-tag>
                            <span style="font-weight: bold">{{ item.display_name || formatPath(item.path) }}</span>
                          </a-space>
                        </div>
                        <div style="margin-top: 4px; color: #666;">
                          <span>路径: {{ item.path }}</span>
                        </div>
                      </a-col>
                      <a-col :span="8" style="text-align: right">
                        <div style="margin-bottom: 4px;">添加时间: {{ formatTime(item.added_time) }}</div>
                        <div style="display: flex; justify-content: flex-end; align-items: center;">
                          <span style="margin-right: 16px;">
                            预计处理: {{ formatTime(item.scheduled_time) }}
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
          <a-empty v-else description="暂无待处理项目" />
        </a-tab-pane>
        
        <!-- 最近成功刷新项目 -->
        <a-tab-pane key="success" tab="成功项目">
          <div v-if="embyStatus.queue && embyStatus.queue.success && embyStatus.queue.success.length > 0">
            <a-list
              size="small"
              :data-source="embyStatus.queue.success"
              :pagination="{ pageSize: 10 }"
            >
              <template #renderItem="{ item }">
                <a-list-item>
                  <a-row style="width: 100%">
                    <a-col :span="16">
                      <a-space>
                        <check-circle-outlined style="color: #52c41a" />
                        <a-tag :color="getEmbyTypeColor(item.type)">{{ getEmbyTypeLabel(item.type) }}</a-tag>
                        <span>{{ item.display_name || formatPath(item.path) }}</span>
                      </a-space>
                      <div style="margin-top: 4px; color: #666;">
                        <span>路径: {{ item.path }}</span>
                      </div>
                    </a-col>
                    <a-col :span="8" style="text-align: right">
                      <div>刷新时间: {{ formatTime(item.refresh_time) }}</div>
                      <div>添加时间: {{ formatTime(item.added_time) }}</div>
                    </a-col>
                  </a-row>
                </a-list-item>
              </template>
            </a-list>
          </div>
          <a-empty v-else description="暂无成功刷新项目" />
        </a-tab-pane>
        
        <!-- 失败项目 -->
        <a-tab-pane key="failed" tab="失败项目">
          <div v-if="embyStatus.queue && embyStatus.queue.failed && embyStatus.queue.failed.length > 0">
            <a-list
              size="small"
              :data-source="embyStatus.queue.failed"
              :pagination="{ pageSize: 10 }"
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
                            <span style="font-weight: bold">{{ item.display_name || formatPath(item.path) }}</span>
                          </a-space>
                        </div>
                        <div style="margin-top: 4px; color: #666;">
                          <span>路径: {{ item.path }}</span>
                        </div>
                        <div style="margin-top: 4px; color: #cf1322;">
                          <span>错误: {{ item.error }}</span>
                        </div>
                      </a-col>
                      <a-col :span="8" style="text-align: right">
                        <div style="margin-bottom: 4px;">失败时间: {{ formatTime(item.failed_time) }}</div>
                        <div style="display: flex; justify-content: flex-end; align-items: center;">
                          <span style="margin-right: 16px;">
                            重试次数: {{ item.retry_count }}/{{ item.max_retries }}
                            <br />
                            下次重试: {{ formatTime(item.next_retry) }}
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

        <!-- 所有队列项 -->
        <a-tab-pane key="all" tab="所有项目">
          <div v-if="embyStatus.queue && embyStatus.all_items && embyStatus.all_items.length > 0">
            <a-list
              size="small"
              :data-source="embyStatus.all_items"
              :pagination="{ pageSize: 10 }"
            >
              <template #renderItem="{ item }">
                <a-list-item>
                  <a-card style="width: 100%; margin-bottom: 8px" :bodyStyle="{ padding: '12px' }">
                    <a-row>
                      <a-col :span="16">
                        <div>
                          <a-space>
                            <a-tag :color="getStatusColor(item.status)">{{ getStatusLabel(item.status) }}</a-tag>
                            <a-tag :color="getEmbyTypeColor(item.type)">{{ getEmbyTypeLabel(item.type) }}</a-tag>
                            <span style="font-weight: bold">{{ item.display_name || formatPath(item.path) }}</span>
                          </a-space>
                        </div>
                        <div style="margin-top: 4px; color: #666;">
                          <span>路径: {{ item.path }}</span>
                        </div>
                        <div v-if="item.error" style="margin-top: 4px; color: #cf1322;">
                          <span>错误: {{ item.error }}</span>
                        </div>
                      </a-col>
                      <a-col :span="8" style="text-align: right">
                        <div style="margin-bottom: 4px;">
                          添加时间: {{ formatTime(item.added_time) }}
                          <br/>
                          {{ getTimeLabel(item) }}: {{ formatTime(getTimeValue(item)) }}
                        </div>
                        <div style="display: flex; justify-content: flex-end; align-items: center;">
                          <a-button 
                            v-if="item.status !== 'success'"
                            type="primary" 
                            size="small"
                            @click="forceRefreshEmbyItem(item.path)"
                            :loading="refreshingItem === item.path"
                          >
                            立即刷新
                          </a-button>
                          <a-button
                            v-if="item.status === 'failed' || item.status === 'success'"
                            type="danger"
                            size="small"
                            @click="removeQueueItem(item.path)"
                            :loading="removingItem === item.path"
                            style="margin-left: 8px;"
                          >
                            移除
                          </a-button>
                        </div>
                      </a-col>
                    </a-row>
                  </a-card>
                </a-list-item>
              </template>
            </a-list>
          </div>
          <a-empty v-else description="暂无队列项目" />
        </a-tab-pane>
      </a-tabs>

      <!-- 手动刷新 -->
      <a-card title="手动刷新" style="margin-top: 20px;">
        <a-form layout="vertical">
          <a-form-item label="STRM文件路径">
            <a-textarea
              v-model:value="manualRefresh.path"
              placeholder="输入STRM文件的绝对路径，例如: /media/strm/movies/film.strm"
              :rows="3"
            />
          </a-form-item>

          <a-form-item>
            <a-button
              type="primary"
              @click="forceRefreshEmbyItem(manualRefresh.path)"
              :loading="refreshingItem === manualRefresh.path"
              :disabled="!manualRefresh.path"
            >
              立即刷新
            </a-button>
          </a-form-item>
        </a-form>
      </a-card>
    </a-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue';
import { 
  CheckCircleOutlined,
  WarningOutlined,
  ClockCircleOutlined
} from '@ant-design/icons-vue';
import { notification } from 'ant-design-vue';
import axios from 'axios';

// Emby队列状态
const embyStatus = reactive({
  enabled: false,
  queue: {
    pending: [],
    success: [],
    failed: []
  },
  all_items: [],
  queue_stats: {
    total: 0,
    pending: 0,
    success: 0,
    failed: 0
  }
});

// 控制状态
const embyLoading = ref(false);
const refreshingItem = ref('');
const removingItem = ref('');
const processingAll = ref(false);
const nextRefreshTime = ref(null);
const embyActiveTab = ref('pending');
const manualRefresh = reactive({
  path: ''
});

// 过滤器
const queueFilter = reactive({
  status: '',
  sortBy: 'added_time',
  sortOrder: 'desc'
});

// 加载Emby状态
const refreshEmbyStatus = async () => {
  embyLoading.value = true;
  try {
    const response = await axios.get('/api/health/emby/refresh/status');
    if (response.data.success) {
      // 更新状态
      embyStatus.enabled = response.data.data.enabled;
      embyStatus.queue_stats = response.data.data.stats;
      
      // 更新队列
      embyStatus.queue.pending = response.data.data.pending || [];
      embyStatus.queue.success = response.data.data.success || [];
      embyStatus.queue.failed = response.data.data.failed || [];
      
      // 合并所有队列项
      embyStatus.all_items = [
        ...(embyStatus.queue.pending || []),
        ...(embyStatus.queue.success || []),
        ...(embyStatus.queue.failed || [])
      ];
      
      // 设置下次刷新时间
      if (response.data.data.next_check) {
        nextRefreshTime.value = new Date(response.data.data.next_check * 1000);
      }
    } else {
      notification.error({
        message: '加载失败',
        description: response.data.message
      });
    }
  } catch (error) {
    notification.error({
      message: '请求错误',
      description: error.message
    });
  } finally {
    embyLoading.value = false;
  }
};

// 加载队列（带筛选）
const loadEmbyQueue = async () => {
  embyLoading.value = true;
  try {
    const params = {
      status: queueFilter.status,
      sort_by: queueFilter.sortBy,
      sort_order: queueFilter.sortOrder
    };
    
    const response = await axios.get('/api/health/emby/refresh/queue', { params });
    if (response.data.success) {
      embyStatus.all_items = response.data.data.items || [];
      embyStatus.queue_stats = response.data.data.stats;
    } else {
      notification.error({
        message: '加载失败',
        description: response.data.message
      });
    }
  } catch (error) {
    notification.error({
      message: '请求错误',
      description: error.message
    });
  } finally {
    embyLoading.value = false;
  }
};

// 强制刷新指定项目
const forceRefreshEmbyItem = async (path) => {
  if (!path) {
    notification.warning({
      message: '路径为空',
      description: '请输入有效的STRM文件路径'
    });
    return;
  }
  
  refreshingItem.value = path;
  try {
    const response = await axios.post('/api/health/emby/refresh/force', { path });
    if (response.data.success) {
      notification.success({
        message: '刷新请求已发送',
        description: response.data.message
      });
      // 刷新队列状态
      refreshEmbyStatus();
    } else {
      notification.error({
        message: '刷新失败',
        description: response.data.message
      });
    }
  } catch (error) {
    notification.error({
      message: '请求错误',
      description: error.message
    });
  } finally {
    refreshingItem.value = '';
  }
};

// 移除队列项
const removeQueueItem = async (path) => {
  removingItem.value = path;
  try {
    const response = await axios.post('/api/health/emby/refresh/remove', { path });
    if (response.data.success) {
      notification.success({
        message: '移除成功',
        description: response.data.message
      });
      // 刷新队列状态
      refreshEmbyStatus();
    } else {
      notification.error({
        message: '移除失败',
        description: response.data.message
      });
    }
  } catch (error) {
    notification.error({
      message: '请求错误',
      description: error.message
    });
  } finally {
    removingItem.value = '';
  }
};

// 处理所有待处理项
const processAllPendingItems = async () => {
  processingAll.value = true;
  try {
    const response = await axios.post('/api/health/emby/refresh/process_all');
    if (response.data.success) {
      notification.success({
        message: '处理请求已发送',
        description: response.data.message
      });
      // 刷新队列状态
      refreshEmbyStatus();
    } else {
      notification.error({
        message: '处理失败',
        description: response.data.message
      });
    }
  } catch (error) {
    notification.error({
      message: '请求错误',
      description: error.message
    });
  } finally {
    processingAll.value = false;
  }
};

// 格式化时间
const formatTime = (timestamp) => {
  if (!timestamp) return '未指定';
  
  let date;
  if (timestamp instanceof Date) {
    date = timestamp;
  } else if (typeof timestamp === 'number') {
    date = new Date(timestamp * 1000);
  } else {
    date = new Date(timestamp);
  }
  
  // 检查日期是否有效
  if (isNaN(date.getTime())) {
    return '无效日期';
  }
  
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  });
};

// 格式化路径
const formatPath = (path) => {
  if (!path) return '未知路径';
  
  // 只显示路径的最后部分
  const parts = path.split('/');
  return parts[parts.length - 1].replace('.strm', '');
};

// 获取Emby类型颜色
const getEmbyTypeColor = (type) => {
  const colorMap = {
    'movie': 'blue',
    'series': 'purple',
    'season': 'purple',
    'episode': 'cyan',
    'unknown': 'grey'
  };
  return colorMap[type] || 'grey';
};

// 获取Emby类型标签
const getEmbyTypeLabel = (type) => {
  const labelMap = {
    'movie': '电影',
    'series': '剧集',
    'season': '季',
    'episode': '集',
    'unknown': '未知'
  };
  return labelMap[type] || '未知';
};

// 获取状态颜色
const getStatusColor = (status) => {
  const colorMap = {
    'pending': 'blue',
    'processing': 'orange',
    'success': 'green',
    'failed': 'red'
  };
  return colorMap[status] || 'grey';
};

// 获取状态标签
const getStatusLabel = (status) => {
  const labelMap = {
    'pending': '待处理',
    'processing': '处理中',
    'success': '成功',
    'failed': '失败'
  };
  return labelMap[status] || '未知';
};

// 获取时间标签
const getTimeLabel = (item) => {
  if (item.status === 'pending') return '预计处理';
  if (item.status === 'success') return '刷新时间';
  if (item.status === 'failed') return '失败时间';
  return '更新时间';
};

// 获取时间值
const getTimeValue = (item) => {
  if (item.status === 'pending') return item.scheduled_time;
  if (item.status === 'success') return item.refresh_time;
  if (item.status === 'failed') return item.failed_time;
  return item.added_time;
};

// 初始化加载
onMounted(() => {
  refreshEmbyStatus();
});
</script>

<style scoped>
.emby-refresh-panel {
  padding: 20px;
}

.emby-card {
  margin-bottom: 24px;
}

.emby-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.emby-title {
  display: flex;
  flex-direction: column;
}

.refresh-status-alert {
  margin-top: 8px;
  width: 300px;
}

.emby-stats {
  margin-top: 20px;
  margin-bottom: 20px;
}
</style> 