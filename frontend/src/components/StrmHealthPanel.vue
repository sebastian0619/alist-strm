<template>
  <div class="strm-health-panel">
    <a-card title="STRM健康度检测" :bordered="false">
      <a-spin :spinning="loading">
        <div class="action-bar">
          <a-space>
            <a-button type="primary" @click="startScan" :loading="scanning" :disabled="scanning">
              开始扫描
            </a-button>
            <a-button @click="repairAll" :disabled="!hasProblems || scanning" type="primary" danger>
              修复所有问题
            </a-button>
          </a-space>
          
          <a-radio-group v-model:value="filterType" button-style="solid" :disabled="scanning">
            <a-radio-button value="all">全部</a-radio-button>
            <a-radio-button value="missing_strm">STRM文件缺失</a-radio-button>
            <a-radio-button value="missing_source">网盘文件缺失</a-radio-button>
          </a-radio-group>
        </div>

        <div v-if="lastScanTime" class="scan-info">
          <a-alert type="info">
            <template #message>
              <div>上次扫描: {{ lastScanTime }}</div>
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
          <a-result status="success" title="所有STRM文件状态良好">
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
                        <a-tag :color="item.type === 'missing_strm' ? 'orange' : 'red'">
                          {{ item.type === 'missing_strm' ? 'STRM文件缺失' : '网盘文件缺失' }}
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
                          {{ item.type === 'missing_strm' ? '重新生成' : '清理STRM' }}
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

// 状态变量
const loading = ref(false);
const scanning = ref(false);
const problems = ref([]);
const filterType = ref('all');
const sortOrder = ref('time_desc');
const lastScanTime = ref('');
const scanProgress = ref(0);
const scanStatus = ref('');
const ignoredItems = ref(new Set());

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
  const date = new Date(timestamp);
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
    // 启动扫描
    await scanStrmHealth();
    
    // 更新最后扫描时间
    lastScanTime.value = new Date().toLocaleString('zh-CN');
    message.success('健康度扫描完成');
  } catch (error) {
    console.error('扫描失败:', error);
    message.error('扫描失败: ' + error.message);
  } finally {
    scanning.value = false;
  }
};

// 扫描STRM文件健康状态
const scanStrmHealth = async () => {
  // 这里会是实际的API调用，现在使用模拟数据
  return new Promise((resolve) => {
    // 模拟进度更新
    let progress = 0;
    const interval = setInterval(() => {
      progress += 5;
      scanProgress.value = Math.min(progress, 99);
      
      if (progress <= 30) {
        scanStatus.value = '正在扫描STRM文件...';
      } else if (progress <= 60) {
        scanStatus.value = '正在检查网盘文件...';
      } else if (progress <= 90) {
        scanStatus.value = '正在分析问题...';
      } else {
        scanStatus.value = '正在完成扫描...';
      }
      
      if (progress >= 100) {
        clearInterval(interval);
        
        // 模拟问题数据
        problems.value = [
          {
            id: '1',
            type: 'missing_strm',
            path: 'data/动漫/完结动漫/没能成为魔法师的女孩子的故事 (2024)/Season 1 (2024)/没能成为魔法师的女孩子的故事 - S01E01 - 第 1 集 -  我想成为魔法师！.mkv',
            details: 'STRM文件已被删除，但网盘中仍存在对应文件',
            discoveryTime: Date.now() - 3600000
          },
          {
            id: '2',
            type: 'missing_strm',
            path: 'data/动漫/完结动漫/没能成为魔法师的女孩子的故事 (2024)/Season 1 (2024)/没能成为魔法师的女孩子的故事 - S01E02 - 第 2 集 -  我说不定也能成为魔法师？.mkv',
            details: 'STRM文件已被删除，但网盘中仍存在对应文件',
            discoveryTime: Date.now() - 7200000
          },
          {
            id: '3',
            type: 'missing_source',
            path: 'data/电影/流浪地球3 (2024)/流浪地球3.strm',
            details: '网盘中找不到对应的源文件，STRM文件可能已失效',
            discoveryTime: Date.now() - 86400000
          }
        ];
        
        scanProgress.value = 100;
        resolve();
      }
    }, 300);
  });
};

// 修复单个问题
const repairItem = async (item) => {
  loading.value = true;
  try {
    // 根据问题类型执行不同的修复操作
    if (item.type === 'missing_strm') {
      await regenerateStrmFile(item.path);
      message.success('STRM文件已重新生成');
    } else if (item.type === 'missing_source') {
      await cleanupStrmFile(item.path);
      message.success('已清理无效的STRM文件');
    }
    
    // 从问题列表中移除
    problems.value = problems.value.filter(p => p.id !== item.id);
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
    const missingStrm = filteredProblems.value.filter(p => p.type === 'missing_strm');
    const missingSource = filteredProblems.value.filter(p => p.type === 'missing_source');
    
    if (missingStrm.length > 0) {
      await regenerateStrmFiles(missingStrm.map(p => p.path));
    }
    
    if (missingSource.length > 0) {
      await cleanupStrmFiles(missingSource.map(p => p.path));
    }
    
    // 清空问题列表
    problems.value = [];
    message.success('所有问题已修复');
  } catch (error) {
    console.error('批量修复失败:', error);
    message.error('批量修复失败: ' + error.message);
  } finally {
    loading.value = false;
  }
};

// 模拟API调用的函数
const regenerateStrmFile = async (path) => {
  console.log('重新生成STRM文件:', path);
  return new Promise(resolve => setTimeout(resolve, 500));
};

const cleanupStrmFile = async (path) => {
  console.log('清理无效STRM文件:', path);
  return new Promise(resolve => setTimeout(resolve, 500));
};

const regenerateStrmFiles = async (paths) => {
  console.log('批量重新生成STRM文件:', paths);
  return new Promise(resolve => setTimeout(resolve, 1000));
};

const cleanupStrmFiles = async (paths) => {
  console.log('批量清理无效STRM文件:', paths);
  return new Promise(resolve => setTimeout(resolve, 1000));
};

onMounted(() => {
  // 可以在这里添加初始化逻辑，比如检查是否有保存的扫描结果等
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