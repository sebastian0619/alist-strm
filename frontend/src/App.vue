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
        <a-tab-pane key="strm" tab="STRM管理">
          <strm-panel />
        </a-tab-pane>
        <a-tab-pane key="archive" tab="归档管理">
          <archive-panel />
        </a-tab-pane>
      </a-tabs>
    </a-layout-content>
  </a-layout>
</template>

<script setup>
import { ref } from 'vue'
import ConfigPanel from './components/ConfigPanel.vue'
import StrmPanel from './components/StrmPanel.vue'
import ArchivePanel from './components/ArchivePanel.vue'

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