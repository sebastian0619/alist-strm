<template>
  <div class="strm-health-panel">
    <a-card title="STRM健康度检测" :bordered="false">
      <a-spin :spinning="loading">
        <div class="action-bar">
          <a-space>
            <a-dropdown>
              <template #overlay>
                <a-menu @click="handleScanTypeChange">
                  <a-menu-item key="strm_validity">STRM文件有效性检测</a-menu-item>
                  <a-menu-item key="video_coverage">视频文件覆盖检测</a-menu-item>
                  <a-menu-item key="all">全面检测 (两种模式)</a-menu-item>
                </a-menu>
              </template>
              <a-button type="primary">
                {{ getScanTypeName(scanType) }} <down-outlined />
              </a-button>
            </a-dropdown>
            <a-button type="primary" @click="startScan" :loading="scanning" :disabled="scanning">
              开始扫描
            </a-button>
            <a-button @click="repairAll" :disabled="!hasProblems || scanning" type="primary" danger>
              全部修复
            </a-button>
          </a-space>
          
          <a-radio-group v-model:value="filterType" button-style="solid" :disabled="scanning">
            <a-radio-button value="all">全部</a-radio-button>
            <a-radio-button value="invalid_strm">无效STRM</a-radio-button>
            <a-radio-button value="missing_strm">缺失STRM</a-radio-button>
          </a-radio-group>
        </div>

        <div v-if="lastScanTime" class="scan-info">
          <a-alert type="info">
            <template #message>
              <div>上次扫描：{{ formatTime(lastScanTime) }} ({{ getScanTypeName(lastScanType) }})</div>
              <div v-if="hasProblems">发现 {{ filteredProblems.length }} 个问题 (总共 {{ problems.length }} 个)</div>
              <div v-else>未发现问题</div>
            </template>
          </a-alert>
        </div>

        <div v-if="scanning" class="scan-progress">
          <a-progress :percent="scanProgress" status="active" />
          <div class="scan-status">{{ scanStatus }}</div>
        </div>

        <div v-if="!lastScanTime && !scanning" class="empty-state">
          <a-empty description="尚未进行扫描" />
          <div class="center-button">
            <a-button type="primary" @click="startScan">开始健康度扫描</a-button>
          </div>
        </div>

        <div v-else-if="!hasProblems && !scanning" class="empty-state">
          <a-result status="success" title="所有检测的文件状态良好">
            <template #extra>
              <a-button type="primary" @click="startScan">重新扫描</a-button>
            </template>
          </a-result>
        </div>

        <div v-else-if="hasProblems && !scanning" class="problem-list">
          <a-list
            :data-source="filteredProblems"
            :pagination="{
              pageSize: 10,
              showSizeChanger: true,
              pageSizeOptions: ['10', '20', '50', '100']
            }"
          >
            <template #header>
              <div class="list-header">
                <span>问题文件列表</span>
                <a-select
                  v-model:value="sortOrder"
                  style="width: 200px"
                  @change="handleSortChange"
                >
                  <a-select-option value="path_asc">路径 (升序)</a-select-option>
                  <a-select-option value="path_desc">路径 (降序)</a-select-option>
                  <a-select-option value="type_asc">问题类型 (升序)</a-select-option>
                  <a-select-option value="type_desc">问题类型 (降序)</a-select-option>
                  <a-select-option value="time_asc">发现时间 (最早)</a-select-option>
                  <a-select-option value="time_desc">发现时间 (最近)</a-select-option>
                </a-select>
              </div>
            </template>
            
            <template #renderItem="{ item }">
              <a-list-item>
                <a-card style="width: 100%">
                  <div class="problem-item">
                    <div class="problem-info">
                      <div class="problem-type">
                        <a-tag :color="getTagColor(item.type)">
                          {{ getProblemTypeName(item.type) }}
                        </a-tag>
                        <span class="discovery-time">发现时间: {{ formatTime(item.discoveryTime) }}</span>
                      </div>
                      <div class="problem-path">{{ item.path }}</div>
                      <div class="problem-details">
                        {{ item.details }}
                      </div>
                    </div>
                    <div class="problem-actions">
                      <a-space>
                        <a-button type="primary" @click="repairItem(item)">
                          {{ getRepairButtonText(item.type) }}
                        </a-button>
                        <a-button @click="ignoreItem(item)">
                          忽略
                        </a-button>
                      </a-space>
                    </div>
                  </div>
                </a-card>
              </a-list-item>
            </template>
          </a-list>
        </div>
      </a-spin>
    </a-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { message } from 'ant-design-vue';
import { DownOutlined } from '@ant-design/icons-vue';

// 状态变量
const loading = ref(false);
const scanning = ref(false);
const problems = ref([]);
const filterType = ref('all');
const sortOrder = ref('time_desc');
const lastScanTime = ref(null);
const lastScanType = ref('all');
const scanProgress = ref(0);
const scanStatus = ref('');
const ignoredItems = ref(new Set());
const scanType = ref('all'); // 默认全面检测

// 获取扫描类型名称
const getScanTypeName = (type) => {
  switch (type) {
    case 'strm_validity': return 'STRM文件有效性检测';
    case 'video_coverage': return '视频文件覆盖检测';
    case 'all': return '全面检测';
    default: return '全面检测';
  }
};

// 获取问题类型名称
const getProblemTypeName = (type) => {
  switch (type) {
    case 'invalid_strm': return 'STRM文件无效';
    case 'missing_strm': return '缺失STRM文件';
    default: return '未知问题';
  }
};

// 获取标签颜色
const getTagColor = (type) => {
  switch (type) {
    case 'invalid_strm': return 'red';
    case 'missing_strm': return 'orange';
    default: return 'blue';
  }
};

// 获取修复按钮文本
const getRepairButtonText = (type) => {
  switch (type) {
    case 'invalid_strm': return '清理无效STRM';
    case 'missing_strm': return '生成缺失STRM';
    default: return '修复';
  }
};

// 处理扫描类型变更
const handleScanTypeChange = (e) => {
  scanType.value = e.key;
};

// 计算属性
const hasProblems = computed(() => {
  return problems.value.filter(p => !ignoredItems.value.has(p.id)).length > 0;
});

const filteredProblems = computed(() => {
  // 首先过滤掉已忽略的项目
  let result = problems.value.filter(p => !ignoredItems.value.has(p.id));
  
  // 根据类型过滤
  if (filterType.value !== 'all') {
    result = result.filter(p => p.type === filterType.value);
  }
  
  // 根据排序选项排序
  result = sortProblems(result, sortOrder.value);
  
  return result;
});

// 格式化时间显示
const formatTime = (timestamp) => {
  if (!timestamp) return '未知';
  
  const date = new Date(timestamp * 1000);
  return date.toLocaleString('zh-CN', { 
    year: 'numeric', 
    month: '2-digit', 
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
};

// 排序问题列表
const sortProblems = (items, order) => {
  return [...items].sort((a, b) => {
    if (order === 'path_asc') return a.path.localeCompare(b.path);
    if (order === 'path_desc') return b.path.localeCompare(a.path);
    if (order === 'type_asc') return a.type.localeCompare(b.type);
    if (order === 'type_desc') return b.type.localeCompare(a.type);
    if (order === 'time_asc') return a.discoveryTime - b.discoveryTime;
    if (order === 'time_desc') return b.discoveryTime - a.discoveryTime;
    return 0;
  });
};

// 处理排序方式变化
const handleSortChange = (value) => {
  sortOrder.value = value;
};

// 开始扫描
const startScan = async () => {
  scanning.value = true;
  scanProgress.value = 0;
  scanStatus.value = '正在初始化扫描...';
  
  try {
    // 请求后端开始扫描
    const response = await fetch(`/api/health/start?type=${scanType.value}`, {
      method: 'POST'
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || '扫描请求失败');
    }
    
    // 轮询扫描状态
    await pollScanStatus();
    
    // 获取扫描结果
    await getHealthProblems();
    
    // 更新最后扫描时间和类型
    lastScanTime.value = Math.floor(Date.now() / 1000);
    lastScanType.value = scanType.value;
    
    message.success('健康度扫描完成');
  } catch (error) {
    console.error('扫描失败:', error);
    message.error('扫描失败: ' + error.message);
  } finally {
    scanning.value = false;
  }
};

// 轮询扫描状态
const pollScanStatus = async () => {
  return new Promise((resolve, reject) => {
    const checkInterval = setInterval(async () => {
      try {
        const response = await fetch('/api/health/status');
        if (!response.ok) {
          clearInterval(checkInterval);
          reject(new Error('获取扫描状态失败'));
          return;
        }
        
        const data = await response.json();
        scanProgress.value = data.progress;
        scanStatus.value = data.status;
        
        if (!data.isScanning) {
          clearInterval(checkInterval);
          resolve();
        }
      } catch (error) {
        clearInterval(checkInterval);
        reject(error);
      }
    }, 1000);
  });
};

// 获取健康问题列表
const getHealthProblems = async () => {
  try {
    const response = await fetch('/api/health/problems');
    if (!response.ok) {
      throw new Error('获取问题列表失败');
    }
    
    const data = await response.json();
    problems.value = data.problems || [];
  } catch (error) {
    console.error('获取问题列表失败:', error);
    message.error('获取问题列表失败: ' + error.message);
  }
};

// 修复单个问题
const repairItem = async (item) => {
  loading.value = true;
  try {
    // 根据问题类型执行不同的修复操作
    let endpoint, requestBody;
    
    if (item.type === 'invalid_strm') {
      endpoint = '/api/health/repair/invalid_strm';
    } else if (item.type === 'missing_strm') {
      endpoint = '/api/health/repair/missing_strm';
    } else {
      throw new Error('未知的问题类型');
    }
    
    requestBody = {
      paths: [item.path],
      type: item.type
    };
    
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(requestBody)
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || '修复请求失败');
    }
    
    const result = await response.json();
    
    // 从问题列表中移除
    problems.value = problems.value.filter(p => p.id !== item.id);
    
    message.success(result.message || '问题已修复');
  } catch (error) {
    console.error('修复失败:', error);
    message.error('修复失败: ' + error.message);
  } finally {
    loading.value = false;
  }
};

// 忽略单个问题
const ignoreItem = (item) => {
  ignoredItems.value.add(item.id);
  message.info('已忽略此问题');
};

// 修复所有问题
const repairAll = async () => {
  if (!hasProblems) return;
  
  loading.value = true;
  try {
    // 按问题类型分组批量处理
    const invalidStrm = filteredProblems.value.filter(p => p.type === 'invalid_strm');
    const missingStrm = filteredProblems.value.filter(p => p.type === 'missing_strm');
    
    let successCount = 0;
    
    if (invalidStrm.length > 0) {
      const response = await fetch('/api/health/repair/invalid_strm', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          paths: invalidStrm.map(p => p.path),
          type: 'invalid_strm'
        })
      });
      
      if (response.ok) {
        const result = await response.json();
        successCount += invalidStrm.length;
        message.success(`成功清理 ${invalidStrm.length} 个无效的STRM文件`);
      }
    }
    
    if (missingStrm.length > 0) {
      const response = await fetch('/api/health/repair/missing_strm', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          paths: missingStrm.map(p => p.path),
          type: 'missing_strm'
        })
      });
      
      if (response.ok) {
        const result = await response.json();
        successCount += missingStrm.length;
        message.success(`成功生成 ${missingStrm.length} 个缺失的STRM文件`);
      }
    }
    
    // 清空问题列表
    if (successCount === filteredProblems.value.length) {
      problems.value = problems.value.filter(p => ignoredItems.value.has(p.id));
      message.success('所有问题已修复');
    } else {
      // 重新获取问题列表
      await getHealthProblems();
      message.warning(`修复了 ${successCount}/${filteredProblems.value.length} 个问题`);
    }
  } catch (error) {
    console.error('批量修复失败:', error);
    message.error('批量修复失败: ' + error.message);
  } finally {
    loading.value = false;
  }
};

onMounted(async () => {
  // 加载当前扫描状态
  try {
    const response = await fetch('/api/health/status');
    if (response.ok) {
      const data = await response.json();
      
      // 如果有上次扫描结果，获取问题列表
      if (data.lastScanTime) {
        lastScanTime.value = data.lastScanTime;
        await getHealthProblems();
      }
      
      // 如果当前正在扫描，显示扫描进度
      if (data.isScanning) {
        scanning.value = true;
        scanProgress.value = data.progress;
        scanStatus.value = data.status;
        
        // 开始轮询扫描状态
        pollScanStatus().then(() => {
          scanning.value = false;
          getHealthProblems();
        }).catch(error => {
          scanning.value = false;
          console.error('轮询扫描状态失败:', error);
        });
      }
    }
  } catch (error) {
    console.error('获取扫描状态失败:', error);
  }
});
</script>

<style scoped>
.strm-health-panel {
  padding: 20px;
}

.action-bar {
  display: flex;
  justify-content: space-between;
  margin-bottom: 20px;
}

.scan-info {
  margin-bottom: 20px;
}

.scan-progress {
  margin: 30px 0;
}

.scan-status {
  text-align: center;
  margin-top: 10px;
  color: rgba(0, 0, 0, 0.65);
}

.empty-state {
  padding: 40px 0;
  text-align: center;
}

.center-button {
  margin-top: 20px;
}

.problem-list {
  margin-top: 20px;
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.problem-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.problem-info {
  flex: 1;
}

.problem-type {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}

.discovery-time {
  margin-left: 10px;
  font-size: 12px;
  color: rgba(0, 0, 0, 0.45);
}

.problem-path {
  font-weight: bold;
  margin-bottom: 8px;
  word-break: break-all;
}

.problem-details {
  color: rgba(0, 0, 0, 0.65);
}

.problem-actions {
  margin-left: 16px;
}

@media (max-width: 768px) {
  .action-bar {
    flex-direction: column;
    gap: 16px;
  }
  
  .problem-item {
    flex-direction: column;
  }
  
  .problem-actions {
    margin-left: 0;
    margin-top: 16px;
    align-self: flex-end;
  }
}
</style> 