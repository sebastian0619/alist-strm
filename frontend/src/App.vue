<template>
  <div class="app-container">
    <a-layout>
      <a-layout-header class="header">
        <h1>Alist STRM 配置</h1>
      </a-layout-header>
      <a-layout-content class="main-content">
        <a-tabs v-model:activeKey="activeTab">
          <a-tab-pane key="config" tab="环境配置">
            <config-panel />
          </a-tab-pane>
          <a-tab-pane key="strm" tab="STRM生成">
            <strm-panel />
          </a-tab-pane>
        </a-tabs>
      </a-layout-content>
    </a-layout>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import ConfigPanel from './components/ConfigPanel.vue'
import StrmPanel from './components/StrmPanel.vue'

const activeTab = ref('config')
</script>

<style>
.app-container {
  min-height: 100vh;
  background-color: #f0f2f5;
}

.header {
  background: #fff;
  padding: 0;
  text-align: center;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.header h1 {
  margin: 0;
  line-height: 64px;
  color: #1890ff;
}

.main-content {
  padding: 24px;
  min-height: calc(100vh - 64px);
}

:deep(.ant-tabs) {
  background: #fff;
  padding: 24px;
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}
</style> 