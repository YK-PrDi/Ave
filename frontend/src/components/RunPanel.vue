<script setup lang="ts">
import { computed } from 'vue'
import type { JobEvent } from '../api'

const props = defineProps<{
  running: boolean
  events: JobEvent[]
  outDir: string
  error: string
  picking: boolean
}>()

const emit = defineEmits<{
  start: []
  stop: []
  open: []
  pick: []
  'update:outDir': [string]
}>()

const items = computed(() => props.events.filter((e) => e.type === 'item'))
const startEv = computed(() => props.events.find((e) => e.type === 'start'))
const doneEv = computed(() =>
  props.events.find((e) => e.type === 'done' || e.type === 'stopped'),
)

// ASR 预热。发生在 start **之前** —— 全新安装时缓存空，这一步要跑两分钟，
// 期间没有 start 事件，下面那套进度条全是 0，看着像卡死。
// 所以这段单独显示，只取最后一个（事件是递增的，留最新那条就够）。
const prewarmEvs = computed(() => props.events.filter((e) => e.type === 'prewarm'))
const prewarm = computed(() => prewarmEvs.value[prewarmEvs.value.length - 1])
// 预热完成的判据是 start 已到，不是预热进度跑满 —— 中途出错也要能收尾
const prewarming = computed(() => !!prewarm.value && !startEv.value)
const prewarmPercent = computed(() => {
  const e = prewarm.value
  if (!e?.total) return 0
  return Math.round(((e.done ?? 0) / e.total) * 100)
})
const prewarmFails = computed(() => prewarmEvs.value.filter((e) => e.error).length)

const total = computed(() => startEv.value?.total ?? 0)
const failCount = computed(() => items.value.filter((e) => !e.ok).length)
const percent = computed(() =>
  total.value ? Math.round((items.value.length / total.value) * 100) : 0,
)

// 剩余时间按已完成条目的平均耗时估，比固定值靠谱
const eta = computed(() => {
  const done = items.value.length
  if (!done || !total.value || done >= total.value) return ''
  const avg = items.value.reduce((s, e) => s + (e.seconds ?? 0), 0) / done
  const left = Math.round(avg * (total.value - done))
  if (left < 60) return `约剩 ${left} 秒`
  return `约剩 ${Math.ceil(left / 60)} 分钟`
})

// 提示去重后汇总，避免每条视频重复刷同一句
const notes = computed(() => {
  const s = new Set<string>()
  props.events.forEach((e) => e.notes?.forEach((n) => s.add(n)))
  return [...s]
})
</script>

<template>
  <section class="card">
    <div class="head">
      <h2>渲染</h2>
      <div class="btns">
        <button v-if="!props.running" class="primary" @click="emit('start')">
          开始渲染
        </button>
        <button v-else class="danger" @click="emit('stop')">
          停止（当前条跑完）
        </button>
        <button class="ghost" @click="emit('open')">打开输出目录</button>
      </div>
    </div>

    <div class="row">
      <input
        :value="props.outDir"
        placeholder="输出目录，留空则用桌面 VEDIO抖音"
        @input="emit('update:outDir', ($event.target as HTMLInputElement).value)"
      />
      <button :disabled="props.picking" @click="emit('pick')">
        {{ props.picking ? '选择中…' : '选择文件夹' }}
      </button>
    </div>

    <p v-if="props.error" class="err">{{ props.error }}</p>

    <template v-if="props.events.length">
      <div v-if="prewarming" class="prewarm">
        <div class="bar">
          <div class="fill warm" :style="{ width: prewarmPercent + '%' }" />
        </div>
        <div class="meta">
          <span>识别卖点口播（首次运行需要，之后走缓存）</span>
          <span class="dim">
            {{ prewarm?.done ?? 0 }} / {{ prewarm?.total ?? 0 }}
          </span>
          <span v-if="prewarmFails" class="bad">失败 {{ prewarmFails }}</span>
          <span class="spacer" />
          <span class="dim ell">{{ prewarm?.file }}</span>
        </div>
      </div>

      <div class="bar">
        <div class="fill" :style="{ width: percent + '%' }" />
      </div>

      <div class="meta">
        <span><b>{{ items.length }}</b> / {{ total }} 条</span>
        <span v-if="failCount" class="bad">失败 {{ failCount }}</span>
        <span v-if="eta && props.running" class="dim">{{ eta }}</span>
        <span v-if="doneEv" class="dim">
          用时 {{ doneEv.seconds }} 秒
          <template v-if="doneEv.type === 'stopped'">（已停止）</template>
        </span>
        <span class="spacer" />
        <span v-if="startEv" class="dim">
          {{ startEv.encoder }} ·
          配音 {{ startEv.backend === 'stub' ? '静音占位' : startEv.backend }}
        </span>
      </div>

      <ul class="log">
        <li v-for="e in [...items].reverse()" :key="e.index" :class="{ bad: !e.ok }">
          <span class="n">{{ String(e.index).padStart(2, '0') }}</span>
          <template v-if="e.ok">
            <span class="f">{{ e.file }}</span>
            <span class="dim">{{ e.size_mb }}MB · {{ e.seconds }}s</span>
          </template>
          <span v-else class="msg">{{ e.error }}</span>
        </li>
      </ul>

      <div v-if="notes.length" class="notes">
        <p v-for="n in notes" :key="n">· {{ n }}</p>
      </div>
    </template>

    <p v-else class="empty">目录不存在会自动创建</p>
  </section>
</template>

<style scoped>
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.btns {
  display: flex;
  gap: 8px;
}
.bar {
  height: 6px;
  background: var(--bg);
  border-radius: 3px;
  overflow: hidden;
  margin-top: 14px;
}
.fill {
  height: 100%;
  background: linear-gradient(90deg, #3d7a80, #4a9eff);
  transition: width 0.3s;
}
.fill.warm {
  background: linear-gradient(90deg, #806a3d, #ffd98c);
}
.prewarm {
  padding-bottom: 4px;
}
.ell {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 45%;
}
.meta {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  font-size: 13px;
  margin-top: 10px;
}
.meta .spacer {
  flex: 1;
}
.dim {
  color: var(--dim);
}
.bad {
  color: #ff9c9c;
}
.log {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  max-height: 260px;
  overflow-y: auto;
  font-size: 13px;
}
.log li {
  display: flex;
  gap: 10px;
  padding: 5px 0;
  border-bottom: 1px solid var(--line);
}
.log .n {
  color: var(--dim);
  font-variant-numeric: tabular-nums;
}
.log .f {
  flex: 1;
}
.log .msg {
  color: #ff9c9c;
  flex: 1;
}
.notes {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--line);
}
.notes p {
  margin: 3px 0;
  font-size: 12px;
  color: #ffd98c;
}
.err {
  margin: 12px 0 0;
  padding: 10px;
  background: #3a1d1d;
  border: 1px solid #6b2b2b;
  border-radius: 6px;
  color: #ff9c9c;
  font-size: 13px;
}
.empty {
  color: var(--dim);
  font-size: 13px;
  margin: 12px 0 0;
}
</style>
