<template>
  <el-dialog v-model="visible" title="任务结果" width="65%">
    <div v-if="result">
      <h4>建议</h4>
      <div class="markdown-content" v-html="renderMarkdown(result.recommendation || '无')"></div>
      <h4 style="margin-top: 16px;">摘要</h4>
      <div class="markdown-content" v-html="renderMarkdown(result.summary || '无')"></div>

      <!-- v1.0.1 HPC 融合分析模块状态 -->
      <div v-if="result.modules_enabled || result.fusion_mode !== undefined || result.performance_summary" class="hpc-section">
        <h4 style="margin-top: 16px;">⚙️ HPC 融合分析引擎</h4>
        <div class="hpc-content">
          <!-- 模块启用状态 -->
          <div v-if="result.modules_enabled" class="modules-status-bar">
            <el-tag
              v-for="(enabled, mod) in result.modules_enabled"
              :key="String(mod)"
              :type="enabled ? 'success' : 'info'"
              size="small"
              effect="plain"
              class="module-tag"
            >
              {{ getModuleLabel(String(mod)) }}
              <el-icon v-if="enabled" style="margin-left: 2px;"><Check /></el-icon>
              <el-icon v-else style="margin-left: 2px;"><Close /></el-icon>
            </el-tag>
          </div>

          <!-- 融合模式 -->
          <div v-if="result.fusion_mode !== undefined" class="fusion-mode-indicator">
            <el-tag :type="result.fusion_mode ? 'warning' : 'info'" effect="dark" size="small">
              🔀 融合模式: {{ result.fusion_mode ? '已启用' : '未启用' }}
            </el-tag>
          </div>

          <!-- 性能摘要 -->
          <div v-if="result.performance_summary" class="performance-summary">
            <el-descriptions :column="3" size="small" border>
              <el-descriptions-item
                v-for="(value, key) in result.performance_summary"
                :key="String(key)"
                :label="getPerfLabel(String(key))"
              >
                {{ formatPerfValue(String(key), value) }}
              </el-descriptions-item>
            </el-descriptions>
          </div>
        </div>
      </div>
    </div>
    <template #footer>
      <el-button @click="emit('close')">关闭</el-button>
      <el-button type="primary" @click="emit('view-report')">查看报告详情</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import { Check, Close } from '@element-plus/icons-vue'

const props = defineProps<{ modelValue: boolean; result: any }>()
const emit = defineEmits(['update:modelValue','close','view-report'])

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v)
})

marked.setOptions({ breaks: true, gfm: true })
const renderMarkdown = (s: string) => { try { return marked.parse(s||'') as string } catch { return s } }

// v1.0.1 HPC 辅助函数
const moduleLabelMap: Record<string, string> = {
  hpc_loop: 'HPC 主循环',
  l_iwm: 'L-IWM 动量预测',
  hsrc_mc: 'HSRC-MC 蒙特卡洛',
  aif_engine: 'AIF 融合引擎',
  diffusion: '扩散模型'
}
const getModuleLabel = (mod: string): string => moduleLabelMap[mod] || mod

const perfLabelMap: Record<string, string> = {
  total_time: '总耗时 (秒)',
  total_tokens: '总 Token 数',
  avg_latency: '平均延迟 (ms)',
  modules_executed: '已执行模块数',
  fusion_rounds: '融合轮次',
  hpc_loop_time: '主循环耗时 (秒)',
  l_iwm_time: 'L-IWM 耗时 (秒)',
  hsrc_mc_time: 'HSRC-MC 耗时 (秒)',
  aif_time: 'AIF 耗时 (秒)',
  diffusion_time: '扩散模型耗时 (秒)'
}
const getPerfLabel = (key: string): string => perfLabelMap[key] || key

const formatPerfValue = (key: string, value: any): string => {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'number') {
    if (key.includes('time') || key.includes('latency')) return value.toFixed(2)
    if (key.includes('tokens')) return value.toLocaleString()
    return value.toString()
  }
  return String(value)
}
</script>

<style scoped>
.hpc-section {
  margin-top: 16px;
}
.hpc-content {
  background: var(--el-fill-color-lighter);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 12px;
}
.modules-status-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.module-tag {
  font-size: 12px;
}
.fusion-mode-indicator {
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
</style>

