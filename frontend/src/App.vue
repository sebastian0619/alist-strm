<template>
  <a-layout>
    <a-layout-header class="header">
      <div class="logo">Alist STRM</div>
    </a-layout-header>
    <a-layout-content>
      <a-tabs v-model:activeKey="activeKey">
        <a-tab-pane key="config" tab="基本配置">
          <config-panel />
        </a-tab-pane>
        <a-tab-pane key="archive" tab="网盘归档">
          <archive-panel />
        </a-tab-pane>
        <a-tab-pane key="pending" tab="待删除文件">
          <pending-deletion-panel />
        </a-tab-pane>
        <a-tab-pane key="health" tab="STRM健康检测">
          <strm-health-panel />
        </a-tab-pane>
        <a-tab-pane key="strm-replace" tab="STRM批量替换">
          <strm-replace-panel />
        </a-tab-pane>
        <a-tab-pane key="emby-refresh" tab="Emby刷库队列">
          <emby-refresh-panel />
        </a-tab-pane>
        <a-tab-pane key="tmdb-metadata" tab="TMDB元数据">
          <tmdb-metadata-panel />
        </a-tab-pane>
      </a-tabs>
    </a-layout-content>
  </a-layout>
</template>

<script setup>
import { defineAsyncComponent, ref } from 'vue'

const ConfigPanel = defineAsyncComponent(() => import('./components/ConfigPanel.vue'))
const ArchivePanel = defineAsyncComponent(() => import('./components/ArchivePanel.vue'))
const PendingDeletionPanel = defineAsyncComponent(() => import('./components/PendingDeletionPanel.vue'))
const StrmHealthPanel = defineAsyncComponent(() => import('./components/StrmHealthPanel.vue'))
const StrmReplacePanel = defineAsyncComponent(() => import('./components/StrmReplacePanel.vue'))
const EmbyRefreshPanel = defineAsyncComponent(() => import('./components/EmbyRefreshPanel.vue'))
const TmdbMetadataPanel = defineAsyncComponent(() => import('./components/TmdbMetadataPanel.vue'))

const activeKey = ref('config')
</script>

<style>
#app {
  height: 100vh;
}

.header {
  display: flex;
  align-items: center;
  padding: 0 24px;
  background: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.logo {
  font-size: 18px;
  font-weight: bold;
  color: #1890ff;
}

.ant-layout-content {
  padding: 0;
  background: #fff;
}

.ant-tabs {
  height: 100%;
}
</style> 
