<template>
  <div class="app-container">
    <el-container>
      <el-header>
        <h1>Alist STRM 配置</h1>
      </el-header>
      <el-main>
        <el-tabs v-model="activeTab">
          <el-tab-pane label="环境配置" name="config">
            <config-panel />
          </el-tab-pane>
          <el-tab-pane label="STRM生成" name="strm">
            <strm-panel />
          </el-tab-pane>
        </el-tabs>
      </el-main>
    </el-container>
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
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.el-header {
  text-align: center;
  padding: 20px 0;
}

.el-main {
  background-color: #fff;
  border-radius: 4px;
  padding: 20px;
}
</style> 