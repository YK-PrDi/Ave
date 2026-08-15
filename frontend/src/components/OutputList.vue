<script setup lang="ts">
import { computed, ref } from 'vue'
import { api, comboIndexOf } from '../api'
import type { ComboItem, OutputFile } from '../api'

const props = defineProps<{
  files: OutputFile[]
  dir: string
  loading: boolean
  combos: ComboItem[]
  outDir: string
}>()

const emit = defineEmits<{ refresh: []; deleted: [string] }>()

// 当前在播的文件名。null = 没开播放器。
const playing = ref<string | null>(null)
const deleting = ref<string | null>(null)
// 播放器报的时长，加载后回填，省掉后端逐个探测 39 次 ffmpeg
const durations = ref<Record<string, number>>({})

const totalMb = computed(() =>
  Math.round(props.files.reduce((s, f) => s + f.size_mb, 0)),
)

// 成品序号 → 组合明细，用来在列表里显示这条是什么组合
const comboBy = computed(() => {
  const m = new Map<number, ComboItem>()
  props.combos.forEach((c) => m.set(c.index, c))
  return m
})

function detail(name: string): ComboItem | undefined {
  const i = comboIndexOf(name)
  return i === null ? undefined : comboBy.value.get(i)
}

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
}

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

    <ul v-else class="list">
      <li v-for="f in props.files" :key="f.name" :class="{ open: playing === f.name }">
        <div class="row">
          <button class="play" :title="playing === f.name ? '收起' : '播放'"
                  @click="toggle(f.name)">
            {{ playing === f.name ? '▊▊' : '▶' }}
          </button>
          <div class="info">
            <span class="name">{{ f.name }}</span>
            <span v-if="detail(f.name)" class="combo">
              {{ detail(f.name)!.hook }}
              <i>+{{ detail(f.name)!.points.length }} 卖点</i>
              {{ detail(f.name)!.ending }}
            </span>
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
          <div v-if="detail(f.name)" class="chain">
            <span class="seg hook">{{ detail(f.name)!.hook }}</span>
            <span v-for="(p, i) in detail(f.name)!.points" :key="i" class="seg">
              <i>{{ i + 1 }}</i>{{ p }}
            </span>
            <span class="seg end">{{ detail(f.name)!.ending }}</span>
          </div>
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
