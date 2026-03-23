<template>
  <a-layout class="shell">
    <a-layout-sider
      v-model:collapsed="collapsed"
      class="shell-sider"
      :width="280"
      :breakpoint="'lg'"
      collapsed-width="88"
    >
      <div class="brand">
        <div class="brand-mark">A</div>
        <div v-if="!collapsed" class="brand-copy">
          <strong>alist-strm</strong>
          <span>Media Control Deck</span>
        </div>
      </div>

      <div v-if="!collapsed" class="brand-panel">
        <span class="brand-panel-label">控制台状态</span>
        <strong>模块隔离加载</strong>
        <p>单页报错不会拖垮其他页面，适合边跑任务边排错。</p>
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
        <section class="hero-strip">
          <div class="hero-copy">
            <p class="page-kicker">Media Automation Console</p>
            <h1 class="page-title">{{ pageMeta.title }}</h1>
            <p class="page-desc">{{ pageMeta.description }}</p>
          </div>

          <div class="hero-badges">
            <div class="hero-badge primary">
              <span>加载模型</span>
              <strong>Panel Isolation</strong>
            </div>
            <div class="hero-badge">
              <span>操作链路</span>
              <strong>Scan · Archive · Refresh</strong>
            </div>
          </div>
        </section>
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
    description: '先看系统脉搏，再决定是修 STRM、跑归档，还是直接处理 Emby 刷新。',
  },
  config: {
    title: '基本配置',
    description: '集中维护 Alist、STRM、Telegram、Emby 和扫描调度的核心参数。',
  },
  archive: {
    title: '网盘归档',
    description: '检查归档规则、目标路径和测试结果，避免移动逻辑判断偏掉。',
  },
  pending: {
    title: '待删除队列',
    description: '核对源路径、迁移状态和删除倒计时，只在确认迁移成功后删源。',
  },
  health: {
    title: 'STRM 健康',
    description: '检测失效 STRM、缺失映射和输出目录里的遗留文件，集中修复。',
  },
  'strm-replace': {
    title: 'STRM 批量替换',
    description: '适合历史链接迁移、路径修正和域名替换，不必手改旧文件。',
  },
  'emby-refresh': {
    title: 'Emby 监控',
    description: '查看最近扫描、刷新记录和日志，确认媒体库联动是不是顺畅。',
  },
  'tmdb-metadata': {
    title: 'TMDB 元数据',
    description: '管理 TMDB 缓存、刮削和媒体补全结果，减少信息缺口。',
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
  --shell-panel: rgba(247, 250, 255, 0.96);
  --shell-border: rgba(107, 128, 164, 0.18);
  --shell-shadow: 0 24px 60px rgba(4, 12, 24, 0.22);
  --shell-ink: #142033;
  --shell-accent: #3f7cff;
}

html,
body,
#app {
  min-height: 100%;
  margin: 0;
  background:
    radial-gradient(circle at top left, rgba(60, 124, 255, 0.24), transparent 20%),
    radial-gradient(circle at top right, rgba(19, 201, 170, 0.12), transparent 18%),
    linear-gradient(180deg, #0b1322 0%, #101a2e 56%, #15223b 100%);
  color: var(--shell-ink);
}

body {
  font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.shell {
  min-height: 100vh;
  background: transparent;
}

.shell-sider.ant-layout-sider {
  background: rgba(8, 16, 30, 0.9);
  border-right: 1px solid rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(18px);
}

.brand {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 24px 22px 16px;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  border-radius: 16px;
  background: linear-gradient(135deg, #6ea8ff 0%, #3365ff 100%);
  color: white;
  font-size: 20px;
  font-weight: 800;
  box-shadow: 0 12px 28px rgba(51, 101, 255, 0.34);
}

.brand-copy {
  display: flex;
  flex-direction: column;
  color: #eff4ff;
}

.brand-copy strong {
  font-size: 18px;
  letter-spacing: 0.02em;
}

.brand-copy span {
  margin-top: 3px;
  color: rgba(223, 232, 250, 0.68);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.brand-panel {
  margin: 0 16px 18px;
  padding: 16px;
  border-radius: 20px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.09), rgba(255, 255, 255, 0.04));
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #edf3ff;
}

.brand-panel-label {
  display: inline-block;
  margin-bottom: 10px;
  color: rgba(223, 232, 250, 0.68);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.brand-panel strong {
  display: block;
  margin-bottom: 8px;
  font-size: 16px;
}

.brand-panel p {
  margin: 0;
  color: rgba(223, 232, 250, 0.76);
  font-size: 13px;
  line-height: 1.5;
}

.nav-menu.ant-menu {
  background: transparent;
  color: rgba(236, 243, 255, 0.84);
  border-inline-end: 0;
  padding: 8px 14px 20px;
}

.nav-menu.ant-menu .ant-menu-item {
  margin-block: 7px;
  height: 48px;
  line-height: 48px;
  border-radius: 15px;
}

.nav-menu.ant-menu .ant-menu-item-selected {
  background: linear-gradient(90deg, rgba(63, 124, 255, 0.3), rgba(63, 124, 255, 0.12));
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
  padding: 28px 30px 10px;
  background: transparent;
}

.hero-strip {
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  gap: 20px;
  padding: 28px 30px;
  border-radius: 30px;
  background:
    radial-gradient(circle at right top, rgba(71, 126, 255, 0.26), transparent 24%),
    linear-gradient(135deg, rgba(10, 19, 35, 0.95), rgba(18, 36, 64, 0.92));
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 24px 60px rgba(4, 10, 24, 0.26);
}

.hero-copy {
  max-width: 760px;
}

.page-kicker {
  margin: 0 0 10px;
  color: rgba(197, 215, 247, 0.72);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.page-title {
  margin: 0;
  color: #f5f8ff;
  font-size: 42px;
  line-height: 1.02;
}

.page-desc {
  max-width: 700px;
  margin: 14px 0 0;
  color: rgba(221, 231, 247, 0.82);
  font-size: 15px;
  line-height: 1.7;
}

.hero-badges {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
  min-width: 260px;
}

.hero-badge {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
  padding: 18px 20px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #eff4ff;
}

.hero-badge.primary {
  background: linear-gradient(135deg, rgba(63, 124, 255, 0.22), rgba(63, 124, 255, 0.08));
}

.hero-badge span {
  color: rgba(208, 222, 250, 0.72);
  font-size: 12px;
}

.hero-badge strong {
  font-size: 18px;
}

.shell-content {
  padding: 14px 30px 30px;
  background: transparent;
}

.shell-content .ant-card {
  border: 1px solid var(--shell-border);
  border-radius: 26px;
  background: var(--shell-panel);
  box-shadow: var(--shell-shadow);
  backdrop-filter: blur(14px);
}

.shell-content .ant-btn-primary {
  background: linear-gradient(135deg, #4f86ff 0%, #3667ff 100%);
  border-color: transparent;
}

.shell-content .ant-btn-primary:hover,
.shell-content .ant-btn-primary:focus {
  background: linear-gradient(135deg, #5d91ff 0%, #4473ff 100%);
  border-color: transparent;
}

.shell-content .ant-radio-button-wrapper-checked:not(.ant-radio-button-wrapper-disabled) {
  background: var(--shell-accent);
  border-color: var(--shell-accent);
}

@media (max-width: 1100px) {
  .hero-strip {
    flex-direction: column;
  }

  .hero-badges {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    min-width: 0;
  }
}

@media (max-width: 992px) {
  .shell-header {
    padding: 24px 20px 8px;
  }

  .shell-content {
    padding: 10px 20px 24px;
  }

  .hero-strip {
    padding: 24px;
  }

  .page-title {
    font-size: 32px;
  }
}

@media (max-width: 680px) {
  .hero-badges {
    grid-template-columns: 1fr;
  }
}
</style>
