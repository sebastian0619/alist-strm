<template>
  <div class="emby-refresh-panel">
    <a-card class="emby-card" :bordered="false">
      <!-- 添加Emby功能未启用警告 -->
      <a-alert 
        v-if="!embyStatus.enabled" 
        type="warning" 
        banner
        message="Emby刷库功能未启用"
        description="请在基本配置页面启用Emby刷库功能，并确保配置正确的API地址和密钥"
        style="margin-bottom: 16px;"
      />

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
            <a-button 
              type="primary" 
              @click="refreshEmbyStatus" 
              :loading="embyLoading"
            >
              刷新状态
            </a-button>
            <a-button 
              @click="getLastRefreshInfo" 
              :loading="lastRefreshLoading"
            >
              查看最近刷新
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
      
      <!-- Emby刷新队列主体内容 -->
      <a-card class="emby-card" v-if="embyStatus.enabled">
        <!-- Tab内容 -->
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
          
          <!-- 成功项目 -->
          <a-tab-pane key="success" tab="成功项目">
            <a-card class="emby-card">
              <a-collapse v-model:activeKey="activeCollapseKey">
                <!-- 刷新成功的项目 -->
                <a-collapse-panel key="1" :header="`刷新成功的项目 (${embyStatus.queue.success.length})`">
                  <a-empty v-if="embyStatus.queue.success.length === 0" description="无刷新成功的项目" />
                  <!-- 成功项目列表 -->
                </a-collapse-panel>
                
                <!-- 刷新失败的项目 -->
                <a-collapse-panel key="2" :header="`刷新失败的项目 (${embyStatus.queue.failed.length})`">
                  <a-empty v-if="embyStatus.queue.failed.length === 0" description="无刷新失败的项目" />
                  <!-- 失败项目列表 -->
                </a-collapse-panel>
              </a-collapse>
            </a-card>
          </a-tab-pane>
          
          <!-- 失败项目 -->
          <a-tab-pane key="failed" tab="失败项目">
            <!-- Content for failed tab -->
          </a-tab-pane>
        </a-tabs>
      </a-card>
      
      <!-- 最近一次刷新结果卡片 -->
      <a-card title="最近一次刷新信息" class="emby-card" v-if="embyStatus.enabled && lastRefreshInfo">
        <a-spin :spinning="lastRefreshLoading">
          <div v-if="lastRefreshInfo && lastRefreshInfo.has_refresh">
            <p>刷新时间: {{ lastRefreshInfo.time }}</p>
            <p>刷新项目数: {{ lastRefreshInfo.total_count }} 个</p>
            
            <a-divider>刷新项目列表</a-divider>
            
            <a-list size="small">
              <a-list-item v-for="item in lastRefreshInfo.items" :key="item.id">
                <a-space>
                  <a-tag :color="getEmbyTypeColor(item.type ? item.type.toLowerCase() : 'unknown')">
                    {{ getEmbyTypeLabel(item.type ? item.type.toLowerCase() : 'unknown') }}
                  </a-tag>
                  <span>{{ item.name }}</span>
                  <a-tag :color="getStatusColor(item.status)">
                    {{ getStatusLabel(item.status) }}
                  </a-tag>
                  <span v-if="item.error" style="color: #ff4d4f;">{{ item.error }}</span>
                </a-space>
              </a-list-item>
            </a-list>
          </div>
          <a-empty v-else description="尚未执行过刷新" />
        </a-spin>
      </a-card>
    </a-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue';
import { 
  CheckCircleOutlined,
  WarningOutlined,
  ClockCircleOutlined
} from '@ant-design/icons-vue';
import { notification, Modal } from 'ant-design-vue';
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
    processing: 0,
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
const lastRequestTime = ref('未请求');
const lastResponse = ref(null);
const lastRefreshInfo = ref(null);
const lastRefreshLoading = ref(false);

// 过滤器
const queueFilter = reactive({
  status: '',
  sortBy: 'added_time',
  sortOrder: 'desc'
});

// 加载Emby状态 - 改进的版本
const refreshEmbyStatus = async () => {
  embyLoading.value = true;
  try {
    const response = await axios.get('/api/health/emby/refresh/status');
    lastResponse.value = response.data; // 保存原始响应
    lastRequestTime.value = new Date().toLocaleString();
    console.log('[Emby刷库] API响应:', response.data);
    
    // 直接使用后端返回的数据
    if (response.data) {
      // 更新Emby启用状态
      embyStatus.enabled = response.data.enabled === true;
      
      // 更新统计数据
      embyStatus.queue_stats = response.data.queue_stats || {
        total: 0,
        pending: 0,
        processing: 0,
        success: 0,
        failed: 0
      };
      
      // 更新队列数据
      embyStatus.queue.pending = response.data.queue_items?.filter(item => item.status === 'pending') || [];
      embyStatus.queue.success = response.data.recent_success || [];
      embyStatus.queue.failed = response.data.recent_failed || [];
      
      // 更新所有项目
      embyStatus.all_items = response.data.queue_items || [];
      
      // 设置下次刷新时间
      nextRefreshTime.value = new Date(Date.now() + 30000); // 30秒后刷新
    } else {
      notification.warning({
        message: '加载失败',
        description: '获取Emby刷新队列状态失败 - 返回数据为空'
      });
    }
  } catch (error) {
    console.error('[Emby刷库] 请求错误:', error);
    notification.error({
      message: '请求出错',
      description: `请求Emby刷新队列状态时出错: ${error.message}`
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
    console.log('[Emby刷库] 加载队列响应:', response.data);
    
    if (response.data.success) {
      // 更新全部项目
      if (response.data.data.items) {
        embyStatus.all_items = response.data.data.items || [];
        
        // 如果返回了统计信息，也更新
        if (response.data.data.stats) {
          embyStatus.queue_stats = response.data.data.stats;
        }
        
        // 按状态重新分类
        embyStatus.queue.pending = embyStatus.all_items.filter(item => 
          item.status === 'pending' || !item.status);
        embyStatus.queue.success = embyStatus.all_items.filter(item => 
          item.status === 'success');
        embyStatus.queue.failed = embyStatus.all_items.filter(item => 
          item.status === 'failed');
      }
    } else {
      notification.warning({
        message: '加载队列失败',
        description: response.data.message || '请求成功但返回错误'
      });
    }
  } catch (error) {
    console.error('[Emby刷库] 加载队列错误:', error);
    notification.error({
      message: '请求错误',
      description: `加载队列数据时出错: ${error.message}`
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
    // 使用查询参数而不是请求体
    const response = await axios.post(`/api/health/emby/refresh/force?path=${encodeURIComponent(path)}`);
    console.log('[Emby刷库] 强制刷新响应:', response.data);
    
    if (response.data) {
      notification.success({
        message: '刷新请求已发送',
        description: response.data.message || '已将项目加入刷新队列'
      });
      // 刷新队列状态
      setTimeout(() => refreshEmbyStatus(), 500); // 稍微延迟刷新，给后端处理的时间
    } else {
      notification.error({
        message: '刷新失败',
        description: '请求成功但返回错误'
      });
    }
  } catch (error) {
    console.error('[Emby刷库] 强制刷新错误:', error);
    notification.error({
      message: '请求错误',
      description: `强制刷新时出错: ${error.message}`
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
    console.log('[Emby刷库] 移除队列项响应:', response.data);
    
    if (response.data.success) {
      notification.success({
        message: '移除成功',
        description: response.data.message || '已从队列中移除'
      });
      // 刷新队列状态
      setTimeout(() => refreshEmbyStatus(), 500); // 稍微延迟刷新
    } else {
      notification.error({
        message: '移除失败',
        description: response.data.message || '请求成功但返回错误'
      });
    }
  } catch (error) {
    console.error('[Emby刷库] 移除队列项错误:', error);
    notification.error({
      message: '请求错误',
      description: `移除队列项时出错: ${error.message}`
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
    console.log('[Emby刷库] 处理所有待处理项响应:', response.data);
    
    if (response.data.success) {
      notification.success({
        message: '处理请求已发送',
        description: response.data.message || '已开始处理所有待处理项'
      });
      // 刷新队列状态
      setTimeout(() => refreshEmbyStatus(), 800); // 稍微长点的延迟
    } else {
      notification.error({
        message: '处理失败',
        description: response.data.message || '请求成功但返回错误'
      });
    }
  } catch (error) {
    console.error('[Emby刷库] 处理所有待处理项错误:', error);
    notification.error({
      message: '请求错误',
      description: `处理所有待处理项时出错: ${error.message}`
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

// 调试功能 - 显示原始响应
const showRawResponse = () => {
  Modal.info({
    title: 'API原始响应数据',
    width: 800,
    content: h => {
      return h('div', {
        style: {
          maxHeight: '60vh',
          overflow: 'auto'
        }
      }, [
        h('pre', {
          style: {
            whiteSpace: 'pre-wrap'
          }
        }, JSON.stringify(lastResponse.value, null, 2))
      ]);
    }
  });
};

// 调试功能 - 测试API请求
const debugRequest = async () => {
  try {
    notification.info({
      message: '发送测试请求',
      description: '正在请求Emby刷新队列状态...'
    });
    
    const response = await axios.get('/api/health/emby/refresh/status');
    console.log('[Emby刷库调试] API响应原始数据:', response.data);
    
    Modal.info({
      title: 'API测试结果',
      width: 800,
      content: h => {
        return h('div', {
          style: {
            maxHeight: '60vh',
            overflow: 'auto'
          }
        }, [
          h('pre', {
            style: {
              whiteSpace: 'pre-wrap'
            }
          }, JSON.stringify(response.data, null, 2))
        ]);
      }
    });
  } catch (error) {
    console.error('[Emby刷库调试] API请求错误:', error);
    notification.error({
      message: '请求错误',
      description: `测试API请求失败: ${error.message}`
    });
  }
};

// 获取最近一次刷新的信息
const getLastRefreshInfo = async () => {
  lastRefreshLoading.value = true;
  try {
    const response = await axios.get('/api/health/emby/last_refresh');
    console.log('[Emby刷库] 最近刷新信息:', response.data);
    
    if (response.data.success) {
      lastRefreshInfo.value = response.data;
    } else {
      notification.warning({
        message: '获取失败',
        description: response.data.message || '请求成功但返回错误'
      });
    }
  } catch (error) {
    console.error('[Emby刷库] 获取最近刷新信息错误:', error);
    notification.error({
      message: '请求错误',
      description: `获取最近刷新信息时出错: ${error.message}`
    });
  } finally {
    lastRefreshLoading.value = false;
  }
};

// 页面加载和卸载逻辑
onMounted(() => {
  // 初始化时加载一次
  refreshEmbyStatus();
  getLastRefreshInfo();
  
  // 设置自动刷新（每30秒刷新一次状态）
  const interval = setInterval(() => {
    if (!document.hidden) { // 只在页面可见时刷新
      refreshEmbyStatus();
    }
  }, 30000);
  
  // 卸载时清除定时器
  onUnmounted(() => {
    clearInterval(interval);
  });
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