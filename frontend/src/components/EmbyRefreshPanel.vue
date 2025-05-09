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
          </a-space>
        </div>
      </div>

      <!-- 最近一次刷新结果卡片 -->
      <a-card title="最近一次刷新信息" class="emby-card" v-if="lastRefreshInfo">
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
import { ref, onMounted } from 'vue';
import { notification, Modal } from 'ant-design-vue';
import axios from 'axios';

// 控制状态
const embyEnabled = ref(true); // 默认认为已启用
const scanningLatest = ref(false);
const lastRefreshInfo = ref(null);
const lastRefreshLoading = ref(false);

// 扫描最新添加到Emby的项目
const scanLatestItems = async () => {
  scanningLatest.value = true;
  try {
    const response = await axios.post('/api/health/emby/scan?hours=12');
    console.log('[Emby刷库] 扫描最新项目响应:', response.data);
    
    if (response.data.success) {
      notification.success({
        message: '扫描完成',
        description: response.data.message || '已扫描Emby最新项目'
      });
      
      // 如果有结果，显示详细信息
      if (response.data.added_items && response.data.added_items.length > 0) {
        // 更新最近刷新信息
        lastRefreshInfo.value = {
          time: new Date().toLocaleString(),
          has_refresh: true,
          items: response.data.added_items
        };
        
        Modal.info({
          title: '扫描结果',
          width: 700,
          content: h => {
            return h('div', [
              h('p', `发现 ${response.data.total_found} 个新项目，已刷新 ${response.data.added_items.length} 个项目`),
              h('div', { style: { maxHeight: '400px', overflow: 'auto' } }, [
                h('a-list', { 
                  size: 'small',
                  dataSource: response.data.added_items,
                  renderItem: (item) => {
                    return h('a-list-item', [
                      h('a-space', [
                        h('a-tag', { color: getEmbyTypeColor(item.type ? item.type.toLowerCase() : 'unknown') }, 
                          getEmbyTypeLabel(item.type ? item.type.toLowerCase() : 'unknown')),
                        h('span', item.name),
                        item.year ? h('span', `(${item.year})`) : null
                      ])
                    ]);
                  }
                })
              ])
            ]);
          }
        });
      } else {
        notification.info({
          message: '扫描完成',
          description: '未发现新项目需要刷新'
        });
      }
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
</style> 