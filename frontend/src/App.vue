<template>
  <a-layout class="shell">
    <a-layout-sider
      v-model:collapsed="collapsed"
      class="shell-sider"
      :width="260"
      :breakpoint="'lg'"
      collapsed-width="80"
    >
      <div class="brand">
        <div class="brand-mark">AS</div>
        <div v-if="!collapsed" class="brand-copy">
          <strong>alist-strm</strong>
          <span>Media Ops Console</span>
        </div>
      </div>

      <a-menu v-model:selectedKeys="selectedKeys" mode="inline" class="nav-menu">
        <a-menu-item key="dashboard" @click="activeKey = 'dashboard'">
          <template #icon><DashboardOutlined /></template>
          总览
        </a-menu-item>
        <a-menu-item key="config" @click="activeKey = 'config'">
          <template #icon><SettingOutlined /></template>
          基本配置
        </a-menu-item>
        <a-menu-item key="archive" @click="activeKey = 'archive'">
          <template #icon><InboxOutlined /></template>
          网盘归档
        </a-menu-item>
        <a-menu-item key="pending" @click="activeKey = 'pending'">
          <template #icon><DeleteOutlined /></template>
          待删除队列
        </a-menu-item>
        <a-menu-item key="health" @click="activeKey = 'health'">
          <template #icon><SafetyCertificateOutlined /></template>
          STRM 健康
        </a-menu-item>
        <a-menu-item key="strm-replace" @click="activeKey = 'strm-replace'">
          <template #icon><SwapOutlined /></template>
          STRM 替换
        </a-menu-item>
        <a-menu-item key="emby-refresh" @click="activeKey = 'emby-refresh'">
          <template #icon><RadarChartOutlined /></template>
          Emby 监控
        </a-menu-item>
        <a-menu-item key="tmdb-metadata" @click="activeKey = 'tmdb-metadata'">
          <template #icon><DatabaseOutlined /></template>
          TMDB 元数据
        </a-menu-item>
      </a-menu>
    </a-layout-sider>

    <a-layout class="shell-main">
      <a-layout-header class="shell-header">
        <div>
          <div class="page-kicker">媒体自动化控制台</div>
          <h1 class="page-title">{{ pageMeta.title }}</h1>
          <p class="page-desc">{{ pageMeta.description }}</p>
        </div>
        <div class="header-status">
          <span class="status-dot" />
          <div class="status-copy">
            <strong>Console Ready</strong>
            <span>模块独立加载，单页故障不影响其他页面</span>
          </div>
        </div>
      </a-layout-header>

      <a-layout-content class="shell-content">
        <panel-frame
          :panel-component="currentPanelComponent"
          :panel-key="activeKey"
          @navigate="handleNavigate"
        />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script setup>
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import {
  DashboardOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  InboxOutlined,
  RadarChartOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  SwapOutlined,
} from '@ant-design/icons-vue'
import PanelFrame from './components/PanelFrame.vue'

const createAsyncPanel = (loader) =>
  defineAsyncComponent({
    loader,
    delay: 120,
    timeout: 15000,
    suspensible: true,
    onError(error, retry, fail, attempts) {
      if (attempts <= 2) {
        retry()
        return
      }
      fail(error)
    },
  })

const DashboardPanel = createAsyncPanel(() => import('./components/DashboardPanel.vue'))
const ConfigPanel = createAsyncPanel(() => import('./components/ConfigPanel.vue'))
const ArchivePanel = createAsyncPanel(() => import('./components/ArchivePanel.vue'))
const PendingDeletionPanel = createAsyncPanel(() => import('./components/PendingDeletionPanel.vue'))
const StrmHealthPanel = createAsyncPanel(() => import('./components/StrmHealthPanel.vue'))
const StrmReplacePanel = createAsyncPanel(() => import('./components/StrmReplacePanel.vue'))
const EmbyRefreshPanel = createAsyncPanel(() => import('./components/EmbyRefreshPanel.vue'))
const TmdbMetadataPanel = createAsyncPanel(() => import('./components/TmdbMetadataPanel.vue'))

const activeKey = ref('dashboard')
const selectedKeys = ref(['dashboard'])
const collapsed = ref(false)

const panelMap = {
  dashboard: DashboardPanel,
  config: ConfigPanel,
  archive: ArchivePanel,
  pending: PendingDeletionPanel,
  health: StrmHealthPanel,
  'strm-replace': StrmReplacePanel,
  'emby-refresh': EmbyRefreshPanel,
  'tmdb-metadata': TmdbMetadataPanel,
}

const pageMetaMap = {
  dashboard: {
    title: '运行总览',
    description: '聚合扫描、归档、待删除和 Emby 刷新状态，先看系统，再处理问题。',
  },
  config: {
    title: '基本配置',
    description: '维护扫描、Alist、Telegram、Emby 和路径映射的核心参数。',
  },
  archive: {
    title: '网盘归档',
    description: '配置归档规则，查看测试结果，并确认最终 archive 目标路径。',
  },
  pending: {
    title: '待删除队列',
    description: '检查源路径、归档目标和删除倒计时，只在确认迁移后再删源。',
  },
  health: {
    title: 'STRM 健康',
    description: '检测无效 STRM 和缺失映射，集中修复异常文件。',
  },
  'strm-replace': {
    title: 'STRM 批量替换',
    description: '批量调整历史 STRM 内容，适合路径迁移和域名替换。',
  },
  'emby-refresh': {
    title: 'Emby 监控',
    description: '查看最近扫描、最近刷新、日志和候选项目，统一处理 Emby 刷新。',
  },
  'tmdb-metadata': {
    title: 'TMDB 元数据',
    description: '管理 TMDB 元数据缓存与媒体补全能力。',
  },
}

const currentPanelComponent = computed(() => panelMap[activeKey.value] || DashboardPanel)
const pageMeta = computed(() => pageMetaMap[activeKey.value] || pageMetaMap.dashboard)

watch(activeKey, (value) => {
  selectedKeys.value = [value]
})

const handleNavigate = (key) => {
  if (panelMap[key]) {
    activeKey.value = key
  }
}
</script>

<style>
:root {
  --shell-bg: #f3efe7;
  --panel-bg: rgba(255, 252, 246, 0.86);
  --panel-border: rgba(52, 43, 33, 0.08);
  --panel-shadow: 0 20px 50px rgba(67, 54, 39, 0.08);
  --ink-1: #241d15;
  --ink-2: #605244;
  --ink-3: #8d7d6d;
  --accent: #b4542f;
  --accent-soft: rgba(180, 84, 47, 0.12);
  --olive: #5f6b3f;
}

html,
body,
#app {
  min-height: 100%;
  margin: 0;
  background:
    radial-gradient(circle at top left, rgba(180, 84, 47, 0.12), transparent 28%),
    radial-gradient(circle at top right, rgba(95, 107, 63, 0.11), transparent 24%),
    linear-gradient(180deg, #f7f2ea 0%, #efe7da 100%);
  color: var(--ink-1);
}

.shell {
  min-height: 100vh;
  background: transparent;
}

.shell-sider.ant-layout-sider {
  background: rgba(36, 29, 21, 0.96);
  box-shadow: inset -1px 0 0 rgba(255, 255, 255, 0.06);
}

.brand {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 22px 20px 18px;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 14px;
  background: linear-gradient(135deg, #c35f35 0%, #8a3e22 100%);
  color: #fff8f1;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.brand-copy {
  display: flex;
  flex-direction: column;
  color: #f6eee3;
}

.brand-copy span {
  color: rgba(246, 238, 227, 0.66);
  font-size: 12px;
}

.nav-menu.ant-menu {
  background: transparent;
  color: rgba(246, 238, 227, 0.8);
  border-inline-end: 0;
  padding: 8px 12px 20px;
}

.nav-menu.ant-menu .ant-menu-item {
  margin-block: 6px;
  height: 46px;
  line-height: 46px;
  border-radius: 14px;
}

.nav-menu.ant-menu .ant-menu-item-selected {
  background: linear-gradient(90deg, rgba(180, 84, 47, 0.22), rgba(180, 84, 47, 0.08));
  color: #fff;
}

.nav-menu.ant-menu .ant-menu-item:hover {
  color: #fff;
}

.shell-main {
  background: transparent;
}

.shell-header {
  height: auto;
  padding: 28px 32px 10px;
  background: transparent;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
}

.page-kicker {
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.page-title {
  margin: 6px 0 6px;
  color: var(--ink-1);
  font-size: 34px;
  line-height: 1.05;
}

.page-desc {
  max-width: 760px;
  margin: 0;
  color: var(--ink-2);
  font-size: 15px;
}

.header-status {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 12px 14px;
  border-radius: 18px;
  background: rgba(255, 252, 246, 0.66);
  border: 1px solid rgba(52, 43, 33, 0.08);
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: linear-gradient(180deg, #6e8b44 0%, #547031 100%);
  box-shadow: 0 0 0 6px rgba(95, 107, 63, 0.1);
}

.status-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.status-copy strong {
  color: var(--ink-1);
  font-size: 13px;
}

.status-copy span {
  color: var(--ink-2);
  font-size: 12px;
}

.shell-content {
  padding: 10px 32px 32px;
  background: transparent;
}

.shell-content .ant-card {
  border: 1px solid var(--panel-border);
  border-radius: 24px;
  background: var(--panel-bg);
  box-shadow: var(--panel-shadow);
  backdrop-filter: blur(8px);
}

@media (max-width: 992px) {
  .shell-header {
    padding: 24px 20px 8px;
    flex-direction: column;
  }

  .shell-content {
    padding: 8px 20px 24px;
  }

  .page-title {
    font-size: 28px;
  }

  .header-status {
    width: 100%;
  }
}
</style>
