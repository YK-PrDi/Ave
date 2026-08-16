<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { api } from './api'
import type { ComboItem, Health, JobEvent, OutputFile, ScanStats } from './api'
import HealthBar from './components/HealthBar.vue'
import SourcePanel from './components/SourcePanel.vue'
import ParamPanel from './components/ParamPanel.vue'
import PreviewList from './components/PreviewList.vue'
import RunPanel from './components/RunPanel.vue'
import OutputList from './components/OutputList.vue'

const health = ref<Health | null>(null)
const source = ref('')
const stats = ref<ScanStats | null>(null)
const scanning = ref(false)

const points = ref(5)
const hookLimit = ref(3)
const subSize = ref(12)
const seed = ref<number | null>(null)
const limit = ref(0)
// 默认开：实测关掉后 30.8/39 条会出现同主题重复
const dedup = ref(true)

const combos = ref<ComboItem[]>([])
const themeNote = ref('')
const previewing = ref(false)

const running = ref(false)
const events = ref<JobEvent[]>([])
const error = ref('')
const jobId = ref('')
const outDir = ref('')
const picking = ref(false)
let unsubscribe: (() => void) | null = null

const outputs = ref<OutputFile[]>([])
const outputsDir = ref('')
const loadingOutputs = ref(false)

async function loadOutputs() {
  loadingOutputs.value = true
  try {
    const r = await api.outputs(outDir.value || undefined)
    outputs.value = r.files
    outputsDir.value = r.dir
  } catch (e) {
    error.value = String(e instanceof Error ? e.message : e)
  } finally {
    loadingOutputs.value = false
  }
}

function params() {
  return {
    source: source.value || undefined,
    points: points.value,
    hook_limit: hookLimit.value,
    sub_size: subSize.value,
    seed: seed.value ?? undefined,
    limit: limit.value || 0,
    out_dir: outDir.value || undefined,
    dedup: dedup.value,
  }
}

async function pick(target: 'source' | 'out') {
  picking.value = true
  error.value = ''
  try {
    const title = target === 'source' ? '选择分镜素材文件夹' : '选择输出文件夹'
    const initial = target === 'source' ? source.value : outDir.value
    const { path } = await api.pickDir(title, initial || undefined)
    if (!path) return                       // 用户取消
    if (target === 'source') {
      source.value = path
      await doScan()
    } else {
      outDir.value = path
      await loadOutputs()
    }
  } catch (e) {
    error.value = String(e instanceof Error ? e.message : e)
  } finally {
    picking.value = false
  }
}

onMounted(async () => {
  try {
    const h = await api.health()
    health.value = h
    source.value = h.source_dir
    outDir.value = h.output_dir
    points.value = h.defaults.points
    hookLimit.value = h.defaults.hook_limit
    subSize.value = h.defaults.sub_size
    await doScan()
    await loadOutputs()
  } catch (e) {
    error.value = `连不上后端服务，请先运行 python -m ave.server（${e}）`
  }
})

async function doScan() {
  scanning.value = true
  error.value = ''
  try {
    stats.value = await api.scan(source.value || undefined)
    await doPreview()
  } catch (e) {
    error.value = String(e instanceof Error ? e.message : e)
    stats.value = null
    combos.value = []
  } finally {
    scanning.value = false
  }
}

async function doPreview() {
  previewing.value = true
  try {
    const p = await api.preview(params())
    combos.value = p.combos
    stats.value = p.stats
    themeNote.value = p.theme_note
  } catch (e) {
    error.value = String(e instanceof Error ? e.message : e)
    combos.value = []
  } finally {
    previewing.value = false
  }
}

async function start() {
  error.value = ''
  events.value = []
  try {
    const { id } = await api.createJob(params())
    jobId.value = id
    running.value = true
    unsubscribe = api.subscribe(
      id,
      (ev) => {
        if (ev.type === 'error') error.value = ev.error ?? '渲染出错'
        events.value = [...events.value, ev]
        // 每渲完一条就刷成品列表，边跑边能点开看质量。
        // 只是一次本地 listdir，代价可忽略。
        if (ev.type === 'item' && ev.ok) loadOutputs()
      },
      async () => {
        running.value = false
        unsubscribe = null
        // 跑完刷新环境状态（BGM 可能中途放进去了）
        health.value = await api.health().catch(() => health.value)
        await loadOutputs()
      },
    )
  } catch (e) {
    error.value = String(e instanceof Error ? e.message : e)
  }
}

async function stop() {
  if (!jobId.value) return
  try {
    await api.stopJob(jobId.value)
  } catch (e) {
    error.value = String(e instanceof Error ? e.message : e)
  }
}

async function open() {
  await api.openOutput(outDir.value || undefined).catch((e) => {
    error.value = String(e instanceof Error ? e.message : e)
  })
}

// 卸载时断开 SSE，避免留下悬空连接
onUnmounted(() => unsubscribe?.())
</script>

<template>
  <div class="app">
    <header>
      <h1>分镜自动化混剪</h1>
      <span class="sub">按排列组合把分镜混剪成竖版短视频</span>
    </header>

    <HealthBar :health="health" />

    <SourcePanel
      v-model:source="source"
      :stats="stats"
      :scanning="scanning"
      :picking="picking"
      @scan="doScan"
      @pick="pick('source')"
    />

    <ParamPanel
      v-model:points="points"
      v-model:hook-limit="hookLimit"
      v-model:sub-size="subSize"
      v-model:seed="seed"
      v-model:limit="limit"
      v-model:dedup="dedup"
      :theme-note="themeNote"
      :stats="stats"
    />

    <PreviewList
      :combos="combos"
      :loading="previewing"
      @refresh="doPreview"
    />

    <RunPanel
      v-model:out-dir="outDir"
      :running="running"
      :events="events"
      :error="error"
      :picking="picking"
      @start="start"
      @stop="stop"
      @open="open"
      @pick="pick('out')"
    />

    <OutputList
      :files="outputs"
      :dir="outputsDir"
      :loading="loadingOutputs"
      :out-dir="outDir"
      @refresh="loadOutputs"
      @deleted="loadOutputs"
    />
  </div>
</template>

<style scoped>
.app {
  max-width: 900px;
  margin: 0 auto;
  padding: 28px 20px 60px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}
h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
}
.sub {
  color: var(--dim);
  font-size: 13px;
}
</style>
