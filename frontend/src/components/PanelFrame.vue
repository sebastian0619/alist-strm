<template>
  <div class="panel-frame">
    <a-alert
      v-if="errorMessage"
      type="error"
      show-icon
      class="panel-error"
      message="当前页面加载失败"
      :description="errorMessage"
    >
      <template #action>
        <a-button size="small" danger @click="retryPanel">重试</a-button>
      </template>
    </a-alert>

    <Suspense v-else>
      <template #default>
        <component
          :is="panelComponent"
          :key="renderKey"
          @navigate="$emit('navigate', $event)"
        />
      </template>
      <template #fallback>
        <div class="panel-loading">
          <a-spin size="large" />
          <span>页面加载中...</span>
        </div>
      </template>
    </Suspense>
  </div>
</template>

<script setup>
import { onErrorCaptured, ref, watch } from 'vue'

const props = defineProps({
  panelComponent: {
    type: [Object, Function, String],
    required: true,
  },
  panelKey: {
    type: String,
    required: true,
  },
})

defineEmits(['navigate'])

const errorMessage = ref('')
const renderKey = ref(0)

watch(
  () => props.panelKey,
  () => {
    errorMessage.value = ''
    renderKey.value += 1
  },
)

const retryPanel = () => {
  errorMessage.value = ''
  renderKey.value += 1
}

onErrorCaptured((error) => {
  errorMessage.value = error instanceof Error ? error.message : String(error)
  return false
})
</script>

<style scoped>
.panel-frame {
  min-height: 320px;
}

.panel-error {
  margin-bottom: 20px;
  border-radius: 18px;
}

.panel-loading {
  min-height: 320px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 14px;
  color: #665747;
}
</style>
