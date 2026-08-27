<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { api } from '../api'
import type { OutputFile } from '../api'

const props = defineProps<{
  files: OutputFile[]
  dir: string
  loading: boolean
  outDir: string
  // 导出倍速，来自 ParamPanel 那个输入框
  speed: number
}>()

const emit = defineEmits<{ refresh: []; deleted: [string] }>()

// 当前在播的文件名。null = 没开播放器。
const playing = ref<string | null>(null)
const deleting = ref<string | null>(null)
// 播放器报的时长，加载后回填，省掉后端逐个探测 39 次 ffmpeg
const durations = ref<Record<string, number>>({})

// ---- 导出（渲染完之后整条变速）----
const exporting = ref(false)
const exportMsg = ref('')
const exportErr = ref('')
const exportProgress = ref<{ done: number; total: number } | null>(null)
// 预览时是否套上倍速。开着的话 <video> 的 playbackRate 跟着 props.speed 走 ——
// 这样导出前就能先听到变速后的效果，不用等导完再发现不合意。
const previewSpeed = ref(true)
let unsub: (() => void) | null = null

// 成品是自然语速渲的，倍速在导出时才套上。1.0 = 不变速（仍会重编码）
const speedLabel = computed(() =>
  Math.abs(props.speed - 1) < 0.001 ? '原速' : `${props.speed}x`,
)

const totalMb = computed(() =>
  Math.round(props.files.reduce((s, f) => s + f.size_mb, 0)),
)

function toggle(name: string) {
  playing.value = playing.value === name ? null : name
}

function fmtDur(s: number | undefined) {
  if (!s || !isFinite(s)) return ''
  const m = Math.floor(s / 60)
  return `${m}:${String(Math.round(s % 60)).padStart(2, '0')}`
}

function onLoaded(name: string, e: Event) {
  const el = e.target as HTMLVideoElement
  durations.value = { ...durations.value, [name]: el.duration }
  applyRate(el)
}

// 把倍速套到 <video> 上做预览。playbackRate 浏览器会保持音调不变，
// 与后端 atempo 的行为一致，所以预览听到的就是导出后的效果。
function applyRate(el: HTMLVideoElement) {
  el.playbackRate = previewSpeed.value ? props.speed : 1
}

// 倍速或开关变了，正在播的那个立刻跟上
watch([() => props.speed, previewSpeed], () => {
  // 外层 div 才是 .player，video 是它的子元素
  document.querySelectorAll<HTMLVideoElement>('.player video')
    .forEach(applyRate)
})

async function doExport() {
  exporting.value = true
  exportErr.value = ''
  exportMsg.value = ''
  exportProgress.value = null
  try {
    const r = await api.exportOutputs({
      speed: props.speed,
      out_dir: props.outDir || undefined,
    })
    unsub = api.subscribe(
      r.id,
      (ev) => {
        if (ev.type === 'error') exportErr.value = ev.error ?? '导出出错'
        if (ev.type === 'item' && ev.total)
          exportProgress.value = { done: ev.index ?? 0, total: ev.total }
        if (ev.type === 'done')
          exportMsg.value =
            `已导出 ${ev.ok}/${ev.total} 条到 ${ev.out_dir}` +
            (ev.failed ? `（失败 ${ev.failed} 条）` : '')
      },
      () => {
        exporting.value = false
        unsub = null
      },
    )
  } catch (e) {
    exportErr.value = String(e instanceof Error ? e.message : e)
    exporting.value = false
  }
}

onUnmounted(() => unsub?.())

async function remove(name: string) {
  deleting.value = name
  try {
    await api.deleteOutput(name, props.outDir || undefined)
    if (playing.value === name) playing.value = null
    emit('deleted', name)
  } finally {
    deleting.value = null
  }
}
</script>

<template>
  <section class="card">
    <div class="head">
      <h2>成品</h2>
      <div class="right">
        <span v-if="props.files.length" class="dim">
          {{ props.files.length }} 条 · {{ totalMb }}MB
        </span>
        <button class="ghost" :disabled="props.loading" @click="emit('refresh')">
          {{ props.loading ? '读取中…' : '刷新' }}
        </button>
      </div>
    </div>

    <p v-if="!props.files.length" class="empty">
      还没有成品。渲染完成后在这里播放预览。
    </p>

    <!-- 成品是自然语速渲的，倍速在导出时整条套上（用户 2026-08-26 定）。
         改倍速不用重渲：一条 1.4 秒，39 条约 1 分钟。 -->
    <div v-if="props.files.length" class="export">
      <label class="chk">
        <input type="checkbox" v-model="previewSpeed" />
        <span>预览时按 <b>{{ speedLabel }}</b> 播放</span>
      </label>
      <span class="spacer" />
      <span class="dim small">
        导出到 <code>导出_{{ props.speed }}x/</code>，不覆盖原片
      </span>
      <button class="primary" :disabled="exporting" @click="doExport">
        {{ exporting ? '导出中…' : `按 ${speedLabel} 导出全部` }}
      </button>
    </div>
    <p v-if="exportProgress && exporting" class="dim small">
      进度 {{ exportProgress.done }}/{{ exportProgress.total }}
    </p>
    <p v-if="exportMsg" class="ok small">{{ exportMsg }}</p>
    <p v-if="exportErr" class="bad small">{{ exportErr }}</p>

    <ul v-else class="list">
      <li v-for="f in props.files" :key="f.name" :class="{ open: playing === f.name }">
        <div class="row">
          <button class="play" :title="playing === f.name ? '收起' : '播放'"
                  @click="toggle(f.name)">
            {{ playing === f.name ? '▊▊' : '▶' }}
          </button>
          <div class="info">
            <span class="name">{{ f.name }}</span>
            <span v-if="f.combo" class="combo">
              {{ f.combo.hook }}
              <i>+{{ f.combo.points.length }} 卖点</i>
              {{ f.combo.ending }}
            </span>
            <span v-else class="combo na">组合信息不可用（渲染时未记录）</span>
          </div>
          <span class="dim size">
            <template v-if="durations[f.name]">{{ fmtDur(durations[f.name]) }} · </template>
            {{ f.size_mb }}MB
          </span>
          <button class="del" :disabled="deleting === f.name"
                  title="删除这条成品" @click="remove(f.name)">
            {{ deleting === f.name ? '…' : '删除' }}
          </button>
        </div>

        <div v-if="playing === f.name" class="player">
          <!-- 竖版 720x1280，限高避免撑爆页面 -->
          <video
            :src="api.videoUrl(f.name, props.outDir || undefined)"
            controls
            autoplay
            preload="metadata"
            @loadedmetadata="onLoaded(f.name, $event)"
          />
          <div v-if="f.combo" class="chain">
            <span class="seg hook">{{ f.combo.hook }}</span>
            <span v-for="(p, i) in f.combo.points" :key="i" class="seg">
              <i>{{ i + 1 }}</i>{{ p }}
            </span>
            <span class="seg end">{{ f.combo.ending }}</span>
            <span class="meta dim">
              #{{ f.combo.index }}
              <template v-if="f.combo.seed !== null"> · seed {{ f.combo.seed }}</template>
            </span>
          </div>
          <p v-else class="chain na">
            这条渲染时还没有组合清单，无法确定真实构成。重渲后可见。
          </p>
        </div>
      </li>
    </ul>

    <p v-if="props.files.length" class="path dim">{{ props.dir }}</p>
  </section>
</template>

<style scoped>
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.right {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}
.list {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  max-height: 460px;
  overflow-y: auto;
}
.list li {
  border-bottom: 1px solid var(--line);
}
.list li.open {
  background: #171b21;
}
.row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 0;
}
.play {
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  padding: 0;
  font-size: 11px;
  border-radius: 15px;
}
.info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.name {
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}
.combo {
  font-size: 11px;
  color: var(--dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.combo i {
  font-style: normal;
  color: #6f7b8a;
  margin: 0 4px;
}
.na {
  color: #6f7b8a;
  font-style: italic;
}
.meta {
  font-size: 11px;
  align-self: center;
  font-variant-numeric: tabular-nums;
}
.size {
  font-size: 12px;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}
.del {
  flex-shrink: 0;
  font-size: 12px;
  padding: 5px 9px;
}
.del:hover:not(:disabled) {
  border-color: #6b2b2b;
  color: #ff9c9c;
}
.player {
  padding: 4px 0 14px 40px;
  display: flex;
  gap: 14px;
  align-items: flex-start;
  flex-wrap: wrap;
}
video {
  max-height: 420px;
  max-width: 240px;
  border-radius: 8px;
  background: #000;
  border: 1px solid var(--line);
}
.chain {
  flex: 1;
  min-width: 180px;
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  align-content: flex-start;
}
.seg {
  font-size: 12px;
  padding: 3px 8px;
  border-radius: 5px;
  background: var(--bg);
  border: 1px solid var(--line);
  color: #cfd6e0;
}
.seg i {
  font-style: normal;
  color: var(--dim);
  margin-right: 5px;
  font-size: 10px;
}
.seg.hook {
  border-color: #3d5a80;
  background: #1a2536;
}
.seg.end {
  border-color: #5a3d80;
  background: #251a36;
}
/* 导出条 */
.export {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin: 12px 0 4px;
  padding: 10px 12px;
  background: #1a2536;
  border: 1px solid #3d5a80;
  border-radius: 8px;
}
.export .chk {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  cursor: pointer;
}
.export .chk input {
  width: 15px;
  height: 15px;
  cursor: pointer;
}
.export .spacer {
  flex: 1;
}
.small {
  font-size: 12px;
}
.ok {
  color: #8cffb0;
  margin: 6px 0 0;
}
.bad {
  color: #ff9c9c;
  margin: 6px 0 0;
}
code {
  background: #223047;
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 11px;
}

.empty {
  color: var(--dim);
  font-size: 13px;
  margin: 12px 0 0;
}
.dim {
  color: var(--dim);
}
.path {
  font-size: 11px;
  margin: 10px 0 0;
  word-break: break-all;
}
</style>
