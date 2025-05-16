<template>
  <div class="emby-refresh-panel">
    <a-card class="emby-card" :bordered="false">
      <!-- 添加Emby功能未启用警告 -->
      <a-alert 
        v-if="!embyEnabled" 
        type="warning" 
        banner
        message="Emby刷库功能未启用"
        description="请在基本配置页面启用Emby刷库功能，并确保配置正确的API地址和密钥"
        style="margin-bottom: 16px;"
      />

      <div class="emby-header">
        <div class="emby-title">
          <h2>Emby刷库管理</h2>
        </div>
        <div class="emby-actions">
          <a-space>
            <a-tooltip title="扫描最新添加到Emby的项目">
              <a-button 
                type="primary" 
                @click="scanLatestItems" 
                :loading="scanningLatest"
              >
                扫描最新项目
              </a-button>
            </a-tooltip>
            
            <a-dropdown>
              <template #overlay>
                <a-menu>
                  <a-menu-item key="1" @click="showTagRemoveModal">
                    删除标签
                  </a-menu-item>
                </a-menu>
              </template>
              <a-button>
                更多功能
                <down-outlined />
              </a-button>
            </a-dropdown>
          </a-space>
        </div>
      </div>

      <!-- 标签删除模态框 -->
      <a-modal
        v-model:visible="tagRemoveModalVisible"
        title="删除Emby标签"
        :confirm-loading="removingTag"
        @ok="removeTag"
        okText="删除"
        cancelText="取消"
      >
        <a-form :model="tagRemoveForm" layout="vertical">
          <a-form-item
            label="标签名称"
            name="tagName"
            help="输入要删除的标签名称，将从所有电影和剧集中删除此标签"
            :rules="[{ required: true, message: '请输入标签名称' }]"
          >
            <a-input 
              v-model:value="tagRemoveForm.tagName" 
              placeholder="输入要删除的标签名称"
              allow-clear
            />
          </a-form-item>
          
          <a-alert
            type="warning"
            message="此操作不可逆，将删除所有项目中包含此标签的记录"
            style="margin-bottom: 16px"
          />
        </a-form>
      </a-modal>
      
      <!-- 标签删除结果模态框 -->
      <a-modal
        v-model:visible="tagRemoveResultVisible"
        title="标签删除结果"
        @ok="closeTagRemoveResult"
        okText="确定"
        :footer="tagRemoveResultFooter"
        width="700px"
      >
        <a-result
          :status="tagRemoveResult.success ? 'success' : 'error'"
          :title="tagRemoveResult.message"
          :sub-title="`共处理 ${tagRemoveResult.total} 个项目，成功 ${tagRemoveResult.success_count} 个，失败 ${tagRemoveResult.failed_count} 个`"
        >
          <template #extra v-if="tagRemoveResult.items && tagRemoveResult.items.length > 0">
            <a-divider>处理的项目</a-divider>
            <a-list size="small">
              <a-list-item v-for="item in tagRemoveResult.items" :key="item.id">
                <a-space>
                  <check-circle-outlined v-if="item.success" style="color: #52c41a" />
                  <close-circle-outlined v-else style="color: #f5222d" />
                  <a-tag :color="getEmbyTypeColor(item.type ? item.type.toLowerCase() : 'unknown')">
                    {{ getEmbyTypeLabel(item.type ? item.type.toLowerCase() : 'unknown') }}
                  </a-tag>
                  <span>{{ item.name }}</span>
                </a-space>
              </a-list-item>
            </a-list>
          </template>
        </a-result>
      </a-modal>

      <!-- 扫描结果显示 -->
      <a-card 
        v-if="scanResults.items && scanResults.items.length > 0" 
        title="最近12小时内的新项目" 
        class="emby-card"
      >
        <div class="scan-actions">
          <a-space>
            <a-button 
              type="primary" 
              @click="refreshSelectedItems" 
              :loading="refreshing"
              :disabled="selectedItems.length === 0"
            >
              刷新选中的项目
            </a-button>
            <a-button 
              @click="selectAllItems" 
              :disabled="allSelected"
            >
              全选
            </a-button>
            <a-button 
              @click="deselectAllItems" 
              :disabled="noneSelected"
            >
              取消全选
            </a-button>
          </a-space>
        </div>

        <a-table
          :dataSource="scanResults.items"
          :columns="columns"
          :pagination="{ pageSize: 10 }"
          :row-key="record => record.id"
          :loading="scanningLatest"
          size="middle"
        >
          <!-- 选择框列 -->
          <template #bodyCell="{ column, record }">
            <template v-if="column.dataIndex === 'selected'">
              <a-checkbox 
                v-model:checked="record.selected" 
                @change="updateSelectedCount"
              />
            </template>
            <template v-if="column.dataIndex === 'year'">
              {{ record.year || '-' }}
            </template>
            <template v-if="column.dataIndex === 'created'">
              <div>
                {{ record.created }}
                <a-tag color="blue" style="margin-left: 8px">{{ record.hoursAgo }}小时前</a-tag>
              </div>
            </template>
            <template v-if="column.dataIndex === 'path'">
              <div style="width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" :title="record.path">
                {{ record.path }}
              </div>
              <a-tag v-if="record.is_strm" color="green">STRM</a-tag>
              <a-tag v-else color="orange">普通</a-tag>
            </template>
            <template v-if="column.dataIndex === 'type'">
              <a-tag :color="getEmbyTypeColor(record.type ? record.type.toLowerCase() : 'unknown')">
                {{ getEmbyTypeLabel(record.type ? record.type.toLowerCase() : 'unknown') }}
              </a-tag>
            </template>
          </template>
        </a-table>
      </a-card>

      <!-- 没有扫描结果时显示 -->
      <a-empty 
        v-else-if="scanningLatest === false && scanCompleted" 
        description="没有找到最近12小时内的新项目" 
      />

      <!-- 刷新结果显示 -->
      <a-card 
        v-if="refreshResults.refreshed_items && refreshResults.refreshed_items.length > 0" 
        title="刷新结果" 
        class="emby-card"
      >
        <a-result
          status="success"
          :title="`成功刷新 ${refreshResults.refreshed_count} 个项目`"
          :sub-title="refreshResults.message"
        >
          <template #extra>
            <a-button type="primary" @click="resetRefreshResults">
              确定
            </a-button>
          </template>
        </a-result>

        <a-divider>刷新项目列表</a-divider>
          
        <a-list size="small">
          <a-list-item v-for="item in refreshResults.refreshed_items" :key="item.id">
            <a-space>
              <a-tag :color="getEmbyTypeColor(item.type ? item.type.toLowerCase() : 'unknown')">
                {{ getEmbyTypeLabel(item.type ? item.type.toLowerCase() : 'unknown') }}
              </a-tag>
              <span>{{ item.name }}</span>
            </a-space>
          </a-list-item>
        </a-list>
      </a-card>

      <!-- 最近一次刷新结果卡片 -->
      <a-card title="最近一次刷新信息" class="emby-card" v-if="lastRefreshInfo && !refreshResults.refreshed_items">
        <a-spin :spinning="lastRefreshLoading">
          <div v-if="lastRefreshInfo && lastRefreshInfo.has_refresh">
            <p>刷新时间: {{ lastRefreshInfo.time }}</p>
            <p>刷新项目数: {{ lastRefreshInfo.items.length }} 个</p>
            
            <a-divider>刷新项目列表</a-divider>
            
            <a-list size="small">
              <a-list-item v-for="item in lastRefreshInfo.items" :key="item.id">
                <a-space>
                  <a-tag :color="getEmbyTypeColor(item.type ? item.type.toLowerCase() : 'unknown')">
                    {{ getEmbyTypeLabel(item.type ? item.type.toLowerCase() : 'unknown') }}
                  </a-tag>
                  <span>{{ item.name }}</span>
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
import { ref, computed, onMounted } from 'vue';
import { notification, Modal } from 'ant-design-vue';
import { 
  DownOutlined, 
  CheckCircleOutlined, 
  CloseCircleOutlined 
} from '@ant-design/icons-vue';
import axios from 'axios';

// 控制状态
const embyEnabled = ref(true); // 默认认为已启用
const scanningLatest = ref(false);
const lastRefreshInfo = ref(null);
const lastRefreshLoading = ref(false);
const scanCompleted = ref(false);
const refreshing = ref(false);

// 扫描结果和选择状态
const scanResults = ref({ items: [] });
const refreshResults = ref({ refreshed_items: [] });
const selectedItems = ref([]);

// 计算属性
const allSelected = computed(() => {
  return scanResults.value.items.length > 0 && 
         scanResults.value.items.every(item => item.selected);
});

const noneSelected = computed(() => {
  return scanResults.value.items.length === 0 || 
         scanResults.value.items.every(item => !item.selected);
});

// 表格列定义
const columns = [
  {
    title: '选择',
    dataIndex: 'selected',
    width: 60
  },
  {
    title: '类型',
    dataIndex: 'type',
    width: 100
  },
  {
    title: '名称',
    dataIndex: 'name'
  },
  {
    title: '年份',
    dataIndex: 'year',
    width: 100
  },
  {
    title: '路径',
    dataIndex: 'path',
    width: 300
  },
  {
    title: '添加时间',
    dataIndex: 'created',
    width: 240
  }
];

// 更新选择计数
const updateSelectedCount = () => {
  selectedItems.value = scanResults.value.items.filter(item => item.selected);
};

// 全选
const selectAllItems = () => {
  scanResults.value.items.forEach(item => {
    item.selected = true;
  });
  updateSelectedCount();
};

// 取消全选
const deselectAllItems = () => {
  scanResults.value.items.forEach(item => {
    item.selected = false;
  });
  updateSelectedCount();
};

// 重置刷新结果
const resetRefreshResults = () => {
  refreshResults.value = { refreshed_items: [] };
};

// 标签删除相关
const tagRemoveModalVisible = ref(false);
const removingTag = ref(false);
const tagRemoveForm = ref({
  tagName: ''
});
const tagRemoveResult = ref({
  success: false,
  message: '',
  total: 0,
  success_count: 0,
  failed_count: 0,
  items: []
});
const tagRemoveResultVisible = ref(false);
const tagRemoveResultFooter = ref([]);

// 显示标签删除模态框
const showTagRemoveModal = () => {
  tagRemoveModalVisible.value = true;
};

// 关闭标签删除结果模态框
const closeTagRemoveResult = () => {
  tagRemoveResultVisible.value = false;
};

// 删除标签
const removeTag = async () => {
  // 验证表单
  if (!tagRemoveForm.value.tagName || !tagRemoveForm.value.tagName.trim()) {
    notification.error({
      message: '输入错误',
      description: '请输入要删除的标签名称'
    });
    return;
  }
  
  removingTag.value = true;
  
  try {
    const response = await axios.post('/api/health/emby/tags/remove', {
      tag_name: tagRemoveForm.value.tagName.trim()
    });
    
    // 保存结果
    tagRemoveResult.value = response.data;
    
    // 关闭输入模态框，显示结果模态框
    tagRemoveModalVisible.value = false;
    tagRemoveResultVisible.value = true;
    
    // 根据结果显示通知
    if (response.data.success) {
      if (response.data.total > 0) {
        notification.success({
          message: '删除标签成功',
          description: `从 ${response.data.success_count}/${response.data.total} 个项目中删除了标签 "${tagRemoveForm.value.tagName}"`,
          duration: 4
        });
      } else {
        notification.info({
          message: '没有找到项目',
          description: `未找到带有标签 "${tagRemoveForm.value.tagName}" 的项目`,
          duration: 4
        });
      }
    } else {
      notification.error({
        message: '删除标签失败',
        description: response.data.message || '请求成功但返回错误'
      });
    }
    
    // 重置表单
    tagRemoveForm.value.tagName = '';
    
  } catch (error) {
    console.error('[Emby标签] 删除标签错误:', error);
    notification.error({
      message: '请求错误',
      description: `删除标签时出错: ${error.message}`
    });
  } finally {
    removingTag.value = false;
  }
};

// 扫描最新添加到Emby的项目
const scanLatestItems = async () => {
  scanningLatest.value = true;
  scanResults.value = { items: [] };
  refreshResults.value = { refreshed_items: [] };
  scanCompleted.value = false;
  
  try {
    const response = await axios.post('/api/health/emby/scan?hours=12');
    
    if (response.data.success) {
      scanResults.value = response.data;
      updateSelectedCount();
      scanCompleted.value = true;
      
      notification.success({
        message: '扫描成功',
        description: `发现 ${scanResults.value.items.length} 个最近添加的项目`,
        duration: 4
      });
    } else {
      notification.error({
        message: '扫描失败',
        description: response.data.message || '请求成功但返回错误'
      });
    }
  } catch (error) {
    console.error('[Emby刷库] 扫描最新项目错误:', error);
    notification.error({
      message: '请求错误',
      description: `扫描Emby最新项目时出错: ${error.message}`
    });
  } finally {
    scanningLatest.value = false;
  }
};

// 刷新选中的项目
const refreshSelectedItems = async () => {
  if (selectedItems.value.length === 0) {
    notification.warning({
      message: '未选择项目',
      description: '请至少选择一个项目进行刷新'
    });
    return;
  }
  
  refreshing.value = true;
  
  try {
    // 获取选中项目的ID列表
    const itemIds = selectedItems.value.map(item => item.id);
    
    const response = await axios.post('/api/health/emby/refresh', {
      item_ids: itemIds
    });
    
    if (response.data.success) {
      refreshResults.value = response.data;
      
      notification.success({
        message: '刷新成功',
        description: `成功刷新 ${refreshResults.value.refreshed_count} 个项目`,
        duration: 4
      });
      
      // 清空扫描结果，避免重复刷新
      scanResults.value = { items: [] };
    } else {
      notification.error({
        message: '刷新失败',
        description: response.data.message || '请求成功但返回错误'
      });
    }
  } catch (error) {
    console.error('[Emby刷库] 刷新项目错误:', error);
    notification.error({
      message: '请求错误',
      description: `刷新Emby项目时出错: ${error.message}`
    });
  } finally {
    refreshing.value = false;
  }
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

// 检查Emby是否启用
const checkEmbyEnabled = async () => {
  try {
    const response = await axios.get('/api/config/emby');
    embyEnabled.value = response.data?.data?.emby_enabled === true;
  } catch (error) {
    console.error('检查Emby启用状态失败:', error);
    embyEnabled.value = false;
  }
};

// 页面加载逻辑
onMounted(() => {
  // 初始化时检查Emby是否启用
  checkEmbyEnabled();
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

.scan-actions {
  margin-bottom: 16px;
}
</style> 