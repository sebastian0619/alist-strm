<template>
  <div class="tmdb-metadata-panel">
    <a-card class="tmdb-card" :bordered="false">
      <div class="tmdb-header">
        <div class="tmdb-title">
          <h2>TMDB元数据浏览器</h2>
        </div>
        <div class="tmdb-actions">
          <a-space>
            <a-input-search
              v-model:value="searchTerm"
              placeholder="搜索电影、剧集或合集"
              style="width: 300px"
              @search="handleSearch"
            />
            <a-button type="primary" @click="handleSearch">
              搜索
            </a-button>
            <a-button @click="reloadMetadata">
              刷新
            </a-button>
          </a-space>
        </div>
      </div>

      <a-row :gutter="16">
        <!-- 左侧分类区域 -->
        <a-col :span="6">
          <a-card title="分类" class="category-card">
            <a-menu 
              v-model:selectedKeys="selectedCategory" 
              style="height: 100%"
              @select="handleCategorySelect"
            >
              <a-menu-item key="tmdb-tv">
                剧集 ({{ stats['tmdb-tv'] || 0 }})
              </a-menu-item>
              <a-menu-item key="tmdb-movies2">
                电影 ({{ stats['tmdb-movies2'] || 0 }})
              </a-menu-item>
              <a-menu-item key="tmdb-collections">
                合集 ({{ stats['tmdb-collections'] || 0 }})
              </a-menu-item>
            </a-menu>
          </a-card>
        </a-col>

        <!-- 右侧内容区域 -->
        <a-col :span="18">
          <a-card title="元数据列表" class="content-card">
            <a-spin :spinning="loading">
              <a-table
                :columns="columns"
                :data-source="filteredItems"
                :row-key="record => record.id"
                :pagination="{ pageSize: 10 }"
                @row-click="handleRowClick"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'action'">
                    <a-button type="link" @click.stop="openTmdbUrl(record)">
                      TMDB
                    </a-button>
                    <a-button type="link" @click.stop="deleteItem(record)" danger>
                      删除
                    </a-button>
                  </template>
                </template>
              </a-table>
            </a-spin>
          </a-card>
        </a-col>
      </a-row>

      <!-- 详情弹窗 -->
      <a-modal
        v-model:visible="detailVisible"
        :title="currentItem ? `${currentItem.name} (${currentItem.year || '未知年份'})` : '详情'"
        :width="800"
        @cancel="detailVisible = false"
      >
        <a-spin :spinning="detailLoading">
          <div v-if="itemDetail">
            <div class="detail-section">
              <h3>基本信息</h3>
              <p><strong>ID:</strong> {{ itemDetail.id }}</p>
              <p><strong>类型:</strong> {{ getTypeLabel(currentCategory) }}</p>
              <p v-if="itemDetail.release_date || itemDetail.first_air_date">
                <strong>发布日期:</strong> {{ formatDate(itemDetail.release_date || itemDetail.first_air_date) }}
              </p>
              <p v-if="itemDetail.vote_average">
                <strong>评分:</strong> {{ itemDetail.vote_average }} ({{ itemDetail.vote_count }} 票)
              </p>
            </div>

            <div class="detail-section">
              <h3>简介</h3>
              <p>{{ itemDetail.overview || '暂无简介' }}</p>
            </div>

            <div class="detail-section" v-if="currentCategory === 'tmdb-tv' && seasons.length > 0">
              <h3>季列表</h3>
              <a-collapse>
                <a-collapse-panel 
                  v-for="season in seasons" 
                  :key="season.season_number" 
                  :header="`第${season.season_number}季: ${season.name}`"
                >
                  <a-list 
                    v-if="episodes[season.season_number]"
                    size="small"
                    :data-source="episodes[season.season_number]"
                  >
                    <template #renderItem="{ item }">
                      <a-list-item>
                        <strong>第{{ item.episode_number }}集:</strong> {{ item.name }}
                        <div>{{ item.overview?.substring(0, 100) }}{{ item.overview?.length > 100 ? '...' : '' }}</div>
                      </a-list-item>
                    </template>
                  </a-list>
                  <div v-else-if="!episodeLoading[season.season_number]">
                    <a-button size="small" @click="loadEpisodes(season.season_number)">
                      加载集列表
                    </a-button>
                  </div>
                  <a-spin v-else size="small" />
                </a-collapse-panel>
              </a-collapse>
            </div>
          </div>
          <a-empty v-else description="暂无详情" />
        </a-spin>
      </a-modal>
    </a-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue';
import axios from 'axios';
import { message, Modal } from 'ant-design-vue';

// 状态变量
const searchTerm = ref('');
const loading = ref(false);
const detailVisible = ref(false);
const detailLoading = ref(false);
const stats = ref({});
const items = ref([]);
const currentCategory = ref('tmdb-tv');
const selectedCategory = ref(['tmdb-tv']);
const currentItem = ref(null);
const itemDetail = ref(null);
const seasons = ref([]);
const episodes = reactive({});
const episodeLoading = reactive({});

// 表格列定义
const columns = [
  {
    title: '名称',
    dataIndex: 'name',
    key: 'name',
  },
  {
    title: 'TMDB ID',
    dataIndex: 'id',
    key: 'id',
  },
  {
    title: '年份',
    dataIndex: 'year',
    key: 'year',
  },
  {
    title: '操作',
    key: 'action',
  },
];

// 过滤后的项目
const filteredItems = computed(() => {
  return items.value;
});

// 格式化日期
const formatDate = (dateStr) => {
  if (!dateStr) return '';
  try {
    const date = new Date(dateStr);
    return date.toLocaleDateString();
  } catch (e) {
    return dateStr;
  }
};

// 获取类型标签
const getTypeLabel = (type) => {
  const labels = {
    'tmdb-tv': '剧集',
    'tmdb-movies2': '电影',
    'tmdb-collections': '合集'
  };
  return labels[type] || type;
};

// 加载元数据统计信息
const loadStats = async () => {
  try {
    const response = await axios.get('/api/tmdb/stats');
    if (response.data && response.data.success) {
      stats.value = response.data.data;
    } else {
      console.error('加载统计信息失败:', response.data);
    }
  } catch (error) {
    console.error('加载统计信息错误:', error);
  }
};

// 加载指定类型的元数据
const loadItems = async (category) => {
  loading.value = true;
  try {
    const response = await axios.get(`/api/tmdb/items?type=${category}&search=${encodeURIComponent(searchTerm.value)}`);
    if (response.data && response.data.success) {
      items.value = response.data.data || [];
    } else {
      console.error('加载元数据列表失败:', response.data);
      items.value = [];
    }
  } catch (error) {
    console.error('加载元数据列表错误:', error);
    items.value = [];
  } finally {
    loading.value = false;
  }
};

// 加载项目详情
const loadItemDetail = async (item) => {
  detailLoading.value = true;
  try {
    const response = await axios.get(`/api/tmdb/detail?type=${currentCategory.value}&id=${item.id}`);
    if (response.data && response.data.success) {
      itemDetail.value = response.data.data;
      
      // 如果是剧集，加载季列表
      if (currentCategory.value === 'tmdb-tv') {
        await loadSeasons(item.id);
      }
    } else {
      itemDetail.value = null;
      console.error('加载详情失败:', response.data);
    }
  } catch (error) {
    itemDetail.value = null;
    console.error('加载详情错误:', error);
  } finally {
    detailLoading.value = false;
  }
};

// 加载季列表
const loadSeasons = async (itemId) => {
  try {
    const response = await axios.get(`/api/tmdb/seasons?id=${itemId}`);
    if (response.data && response.data.success) {
      seasons.value = response.data.data || [];
    } else {
      seasons.value = [];
      console.error('加载季列表失败:', response.data);
    }
  } catch (error) {
    seasons.value = [];
    console.error('加载季列表错误:', error);
  }
};

// 加载集列表
const loadEpisodes = async (seasonNumber) => {
  if (episodes[seasonNumber]) return;
  
  episodeLoading[seasonNumber] = true;
  try {
    const response = await axios.get(
      `/api/tmdb/episodes?id=${currentItem.value.id}&season=${seasonNumber}`
    );
    if (response.data && response.data.success) {
      episodes[seasonNumber] = response.data.data || [];
    } else {
      episodes[seasonNumber] = [];
      console.error('加载集列表失败:', response.data);
    }
  } catch (error) {
    episodes[seasonNumber] = [];
    console.error('加载集列表错误:', error);
  } finally {
    episodeLoading[seasonNumber] = false;
  }
};

// 处理搜索
const handleSearch = () => {
  loadItems(currentCategory.value);
};

// 处理分类选择
const handleCategorySelect = ({ key }) => {
  currentCategory.value = key;
  loadItems(key);
};

// 处理行点击
const handleRowClick = (record) => {
  currentItem.value = record;
  detailVisible.value = true;
  loadItemDetail(record);
};

// 打开TMDB网站
const openTmdbUrl = (record) => {
  let url;
  const id = record.id;
  
  if (currentCategory.value === 'tmdb-tv') {
    url = `https://www.themoviedb.org/tv/${id}`;
  } else if (currentCategory.value === 'tmdb-movies2') {
    url = `https://www.themoviedb.org/movie/${id}`;
  } else if (currentCategory.value === 'tmdb-collections') {
    url = `https://www.themoviedb.org/collection/${id}`;
  }
  
  if (url) {
    window.open(url, '_blank');
  }
};

// 删除项目
const deleteItem = (record) => {
  Modal.confirm({
    title: '确认删除',
    content: `确定要删除 "${record.name}" 吗？`,
    okText: '确认',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      try {
        const response = await axios.delete(`/api/tmdb/item?type=${currentCategory.value}&id=${record.id}`);
        if (response.data && response.data.success) {
          message.success('删除成功');
          // 重新加载数据
          loadItems(currentCategory.value);
          loadStats();
        } else {
          message.error('删除失败: ' + (response.data?.message || '未知错误'));
        }
      } catch (error) {
        message.error('删除出错: ' + (error.message || '未知错误'));
      }
    }
  });
};

// 重新加载所有元数据
const reloadMetadata = async () => {
  loading.value = true;
  try {
    const response = await axios.post('/api/tmdb/reload');
    if (response.data && response.data.success) {
      message.success('元数据已重新加载');
      await loadStats();
      await loadItems(currentCategory.value);
    } else {
      message.error('重新加载失败: ' + (response.data?.message || '未知错误'));
    }
  } catch (error) {
    message.error('重新加载出错: ' + (error.message || '未知错误'));
  } finally {
    loading.value = false;
  }
};

// 组件挂载时执行
onMounted(async () => {
  await loadStats();
  await loadItems(currentCategory.value);
});
</script>

<style scoped>
.tmdb-metadata-panel {
  padding: 20px;
}

.tmdb-card {
  margin-bottom: 24px;
}

.tmdb-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.tmdb-title {
  display: flex;
  flex-direction: column;
}

.category-card, .content-card {
  margin-bottom: 16px;
  height: calc(100vh - 250px);
  overflow: auto;
}

.detail-section {
  margin-bottom: 20px;
}
</style> 