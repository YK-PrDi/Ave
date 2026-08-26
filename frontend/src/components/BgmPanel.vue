<script setup lang="ts">
// BGM 两层管理。
// 内置层随应用更新替换（我们维护），自定义层在用户数据目录（各公司自己加）。
// 只有自定义层能增删 —— 内置层删了下次更新还会回来。
import { computed, ref } from 'vue'
import { api } from '../api'
import type { BgmTrack } from '../api'

const emit = defineEmits<{ changed: [] }>()

const tracks = ref<BgmTrack[]>([])
const builtinDir = ref('')
const customDir = ref('')
const loading = ref(false)
const adding = ref(false)
const loaded = ref(false)
const error = ref('')
const note = ref('')

const builtin = computed(() => tracks.value.filter((t) => t.source === 'builtin'))
const custom = computed(() => tracks.value.filter((t) => t.source === 'custom'))

async function load() {
  loading.value = true
  error.value = ''
  try {
    const r = await api.bgm()
    tracks.value = r.tracks
    builtinDir.value = r.builtin_dir
    customDir.value = r.custom_dir
    loaded.value = true
  } catch (e) {
    error.value = String(e instanceof Error ? e.message : e)
  } finally {
    loading.value = false
  }
}

async function add() {
  adding.value = true
  error.value = ''
  note.value = ''
  try {
    const r = await api.bgmAdd()
    if (!r.added.length && !r.skipped.length) {
      note.value = '未选择文件'
    } else {
      note.value = `已添加 ${r.added.length} 首`
      if (r.skipped.length)
        note.value += `，跳过 ${r.skipped.map((s) => `${s.name}（${s.why}）`).join('、')}`
      await load()
      emit('changed')
    }
  } catch (e) {
    error.value = String(e instanceof Error ? e.message : e)
  } finally {
    adding.value = false
  }
}

async function remove(t: BgmTrack) {
  if (!confirm(`删除 BGM「${t.name}」？`)) return
  error.value = ''
  note.value = ''
  try {
    await api.bgmDelete(t.name)
    await load()
    emit('changed')
  } catch (e) {
    error.value = String(e instanceof Error ? e.message : e)
  }
}
</script>

<template>
  <section class="card">
    <div class="head">
      <h2>背景音乐</h2>
      <span v-if="loaded" class="muted">
        内置 {{ builtin.length }} 首 · 自定义 {{ custom.length }} 首
      </span>
      <span class="spacer" />
      <button :disabled="loading" @click="load">
        {{ loaded ? '刷新' : '查看' }}
      </button>
      <button class="primary" :disabled="adding" @click="add">
        {{ adding ? '选择中…' : '添加音乐' }}
      </button>
    </div>

    <p v-if="error" class="warn">{{ error }}</p>
    <p v-if="note" class="muted small">{{ note }}</p>

    <template v-if="loaded">
      <div class="layer">
        <div class="layer-head">
          <b>内置</b>
          <em>随应用更新提供，不可删除</em>
        </div>
        <p v-if="!builtin.length" class="muted small">（暂无内置曲库）</p>
        <ul v-else>
          <li v-for="t in builtin" :key="t.name">
            <span class="name">{{ t.name }}</span>
            <span class="muted small">{{ t.size_mb }}MB</span>
          </li>
        </ul>
      </div>

      <div class="layer">
        <div class="layer-head">
          <b>自定义</b>
          <em>你自己加的，更新应用不会动它</em>
        </div>
        <p class="path">{{ customDir }}</p>
        <p v-if="!custom.length" class="muted small">
          （还没加。点「添加音乐」选本机音频文件）
        </p>
        <ul v-else>
          <li v-for="t in custom" :key="t.name">
            <span class="name">{{ t.name }}</span>
            <span class="muted small">{{ t.size_mb }}MB</span>
            <span class="spacer" />
            <button class="del" @click="remove(t)">删除</button>
          </li>
        </ul>
      </div>
    </template>
  </section>
</template>

<style scoped>
.head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.head h2 {
  margin: 0;
}
.spacer {
  flex: 1;
}
.muted {
  color: var(--dim);
  font-size: 13px;
}
.small {
  font-size: 12px;
}
.warn {
  font-size: 12px;
  color: #ffd98c;
  margin: 8px 0 0;
}
.layer {
  margin-top: 14px;
}
.layer-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--line);
}
.layer-head b {
  font-weight: 500;
  font-size: 13px;
}
.layer-head em {
  font-style: normal;
  font-size: 11px;
  color: var(--dim);
}
.path {
  font-size: 11px;
  color: var(--dim);
  margin: 6px 0 0;
  word-break: break-all;
}
ul {
  list-style: none;
  margin: 6px 0 0;
  padding: 0;
}
li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 5px 0;
  font-size: 13px;
}
.name {
  word-break: break-all;
}
.del {
  font-size: 11px;
  padding: 2px 8px;
}
</style>
