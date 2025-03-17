<template>
  <div class="pending-deletion-panel">
    <a-card title="待删除文件列表" :bordered="false">
      <a-spin :spinning="loading">
        <div v-if="pendingItems.length === 0" class="empty-state">
          <a-empty description="暂无待删除文件" />
        </div>
        <div v-else>
          <div class="header-info">
            <a-alert type="info" show-icon>
              <template #message>
                <span>共有 {{ pendingItems.length }} 个待删除项目。文件将在 {{ delayDays }} 天后自动删除。</span>
              </template>
              <template #description>
                <div class="delay-setting">
                  <span>修改延迟天数: </span>
                  <a-input-number
                    v-model:value="newDelayDays"
                    :min="1"
                    :max="365"
                    style="width: 100px; margin: 0 8px;"
                  />
                  <a-button type="primary" size="small" @click="updateDelayDays" :loading="updating">
                    保存
                  </a-button>
                </div>
              </template>
            </a-alert>
          </div>

          <div class="list-header">
            <a-space>
              <a-popconfirm
                title="确定要立即删除所有待删除项目吗？此操作无法撤销，所有文件和目录将被立即删除。"
                @confirm="deleteAllNow"
              >
                <a-button type="primary" danger>
                  立即删除所有
                </a-button>
              </a-popconfirm>
              <a-popconfirm
                title="确定要清空所有待删除项目吗？此操作将取消所有文件的删除计划。"
                @confirm="clearAllItems"
              >
                <a-button type="primary" danger>
                  清空待删除列表
                </a-button>
              </a-popconfirm>
            </a-space>
          </div>

          <a-list
            class="pending-list"
            :data-source="pendingItems"
            :grid="{ gutter: 16, column: 1 }"
          >
            <template #renderItem="{ item }">
              <a-list-item>
                <a-card>
                  <div class="item-content">
                    <div class="item-info">
                      <div class="item-path">{{ item.path }}</div>
                      <div class="item-details">
                        <a-tag color="blue">预计删除: {{ item.delete_time }}</a-tag>
                        <a-tag :color="getDaysColor(item.days_left)">
                          剩余: {{ item.days_left }} 天
                        </a-tag>
                      </div>
                    </div>
                    <div class="item-actions">
                      <a-popconfirm
                        title="确定要立即删除这个文件吗？此操作无法撤销。"
                        @confirm="deleteNow(item)"
                      >
                        <a-button type="primary" danger style="margin-right: 8px;">立即删除</a-button>
                      </a-popconfirm>
                      <a-popconfirm
                        title="确定要取消删除这个文件吗?"
                        @confirm="removeItem(item)"
                      >
                        <a-button type="primary">取消删除</a-button>
                      </a-popconfirm>
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
import { ref, onMounted } from 'vue';
import { message } from 'ant-design-vue';

const pendingItems = ref([]);
const loading = ref(true);
const delayDays = ref(7);
const newDelayDays = ref(7);
const updating = ref(false);

onMounted(() => {
  loadPendingItems();
  loadDelayDays();
});

// 加载待删除项目列表
const loadPendingItems = async () => {
  loading.value = true;
  try {
    const response = await fetch('/api/archive/pending-deletions');
    const data = await response.json();
    
    if (data.success) {
      console.log('加载待删除项目成功:', data.data);
      // 处理API返回的数据，添加格式化的日期和剩余天数
      pendingItems.value = data.data.map(item => {
        const deleteTimestamp = item.delete_time * 1000; // 转为毫秒
        const deleteDate = new Date(deleteTimestamp);
        const now = new Date();
        
        // 计算剩余天数
        const msPerDay = 24 * 60 * 60 * 1000;
        const daysLeft = Math.ceil((deleteTimestamp - now.getTime()) / msPerDay);
        
        return {
          ...item,
          delete_time: formatDate(deleteDate),
          days_left: daysLeft,
          timestamp: deleteTimestamp
        };
      });
    } else {
      console.error('加载待删除项目失败:', data.message);
      message.error(data.message || '加载失败');
    }
  } catch (error) {
    console.error('加载待删除项目异常:', error);
    message.error('加载失败: ' + error.message);
  } finally {
    loading.value = false;
  }
};

// 加载延迟删除天数
const loadDelayDays = async () => {
  try {
    const response = await fetch('/api/archive/deletion-delay');
    const data = await response.json();
    
    if (data.success) {
      delayDays.value = data.data.days;
      newDelayDays.value = data.data.days;
    }
  } catch (error) {
    console.error('加载延迟天数失败:', error);
  }
};

// 更新延迟删除天数
const updateDelayDays = async () => {
  if (!newDelayDays.value || newDelayDays.value < 1) {
    message.error('请输入有效的天数（≥1）');
    return;
  }
  
  updating.value = true;
  try {
    const response = await fetch('/api/archive/deletion-delay', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ days: newDelayDays.value })
    });
    
    const data = await response.json();
    
    if (data.success) {
      delayDays.value = newDelayDays.value;
      message.success('延迟删除天数已更新');
    } else {
      message.error(data.message || '更新失败');
    }
  } catch (error) {
    message.error('更新失败: ' + error.message);
  } finally {
    updating.value = false;
  }
};

// 格式化日期为易读格式
const formatDate = (date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  
  return `${year}-${month}-${day} ${hours}:${minutes}`;
};

// 从删除列表中移除项目
const removeItem = async (item) => {
  loading.value = true;
  try {
    const response = await fetch('/api/archive/clear-pending-deletion', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        path: item.path,
        delete_time: Math.floor(item.timestamp / 1000) // 转回秒级时间戳
      })
    });
    
    const data = await response.json();
    
    if (data.success) {
      pendingItems.value = pendingItems.value.filter(i => i.path !== item.path);
      message.success('已从待删除列表中移除');
    } else {
      message.error(data.message || '操作失败');
    }
  } catch (error) {
    message.error('操作失败: ' + error.message);
  } finally {
    loading.value = false;
  }
};

// 根据剩余天数获取标签颜色
const getDaysColor = (days) => {
  if (days < 1) return 'red';
  if (days < 3) return 'orange';
  return 'green';
};

// 清空所有待删除项目
const clearAllItems = async () => {
  loading.value = true;
  try {
    const response = await fetch('/api/archive/clear-all-pending-deletions', {
      method: 'POST'
    });
    
    const data = await response.json();
    
    if (data.success) {
      pendingItems.value = [];
      message.success('已清空所有待删除项目');
    } else {
      message.error(data.message || '操作失败');
    }
  } catch (error) {
    message.error('操作失败: ' + error.message);
  } finally {
    loading.value = false;
  }
};

// 立即删除文件
const deleteNow = async (item) => {
  loading.value = true;
  try {
    const response = await fetch('/api/archive/delete-now', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        path: item.path,
        delete_time: Math.floor(item.timestamp / 1000) // 转回秒级时间戳
      })
    });
    
    const data = await response.json();
    
    if (data.success) {
      pendingItems.value = pendingItems.value.filter(i => i.path !== item.path);
      message.success('文件已成功删除');
    } else {
      message.error(data.message || '删除失败');
    }
  } catch (error) {
    message.error('删除失败: ' + error.message);
  } finally {
    loading.value = false;
  }
};

// 立即删除所有待删除文件
const deleteAllNow = async () => {
  loading.value = true;
  try {
    const response = await fetch('/api/archive/delete-all-now', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      }
    });
    
    const data = await response.json();
    
    if (data.success) {
      pendingItems.value = [];
      message.success(data.message || '所有文件已成功删除');
    } else {
      message.error(data.message || '删除失败');
    }
  } catch (error) {
    message.error('删除失败: ' + error.message);
  } finally {
    loading.value = false;
  }
};
</script>

<style scoped>
.pending-deletion-panel {
  padding: 20px;
}

.header-info {
  margin-bottom: 20px;
}

.delay-setting {
  display: flex;
  align-items: center;
  margin-top: 8px;
}

.empty-state {
  padding: 40px 0;
  text-align: center;
}

.pending-list {
  margin-top: 20px;
}

.item-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.item-path {
  font-weight: bold;
  margin-bottom: 8px;
  word-break: break-all;
}

.item-details {
  display: flex;
  gap: 8px;
}

@media (max-width: 768px) {
  .item-content {
    flex-direction: column;
    align-items: flex-start;
  }
  
  .item-actions {
    margin-top: 16px;
    align-self: flex-end;
  }
}

.list-header {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 16px;
}
</style> 