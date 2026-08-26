<script setup lang="ts">
// 无口播分镜的 AI 口播文案审校。
// 只列「已识别且确认无口播」和「未识别」的片段 —— 有口播的用真人原声，
// 不需要 AI 文案，全列出来是 55 条噪音。
import { computed, onUnmounted, ref } from 'vue'
import { api } from '../api'
import type { CopyItem, JobEvent } from '../api'

const props = defineProps<{
  source: string
  visionBackend: string
  visionModel: string
  busy: boolean
}>()

const emit = defineEmits<{ busy: [boolean] }>()

const items = ref<CopyItem[]>([])
const loading = ref(false)
const loaded = ref(false)
const error = ref('')
const testing = ref(false)
const testResult = ref('')
const testOk = ref(false)
const generating = ref(false)
const progress = ref<{ done: number; total: number } | null>(null)
// 编辑中的文本，按 path 存。没在这里的表示未改动。
const drafts = ref<Record<string, string>>({})
const saved = ref<Record<string, boolean>>({})
let unsubscribe: (() => void) | null = null

// 只关心没口播的（含状态未知的）
const needCopy = computed(() => items.value.filter((i) => i.asr !== true))
const withCopy = computed(() => needCopy.value.filter((i) => i.copy).length)
const roleName: Record<string, string> = {
  hook: '钩子',
  point: '卖点',
  ending: '结尾',
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const r = await api.copyList(props.source || undefined)
    items.value = r.items
    drafts.value = {}
    saved.value = {}
    loaded.value = true
  } catch (e) {
    error.value = String(e instanceof Error ? e.message : e)
  } finally {
    loading.value = false
  }
}

async function test() {
  testing.value = true
  testResult.value = ''
  try {
    const r = await api.visionTest(props.source || undefined)
    testOk.value = r.ok
    testResult.value = r.ok
      ? `接口正常（模型 ${r.model}${r.with_image ? '，已用真实画面测试' : ''}）：${r.reply}`
      : `失败：${r.error}`
  } catch (e) {
    testOk.value = false
    testResult.value = String(e instanceof Error ? e.message : e)
  } finally {
    testing.value = false
  }
}

async function save(item: CopyItem) {
  const text = drafts.value[item.path] ?? item.copy
  try {
    const r = await api.copySave(item.path, text, props.source || undefined)
    item.copy = r.text
    item.copy_source = r.copy_source
    delete drafts.value[item.path]
    saved.value[item.path] = true
    setTimeout(() => delete saved.value[item.path], 2000)
  } catch (e) {
    error.value = String(e instanceof Error ? e.message : e)
  }
}

async function generate() {
  error.value = ''
  progress.value = null
  try {
    const { id } = await api.copyGenerate(props.source || undefined)
    generating.value = true
    emit('busy', true)
    unsubscribe = api.subscribe(
      id,
      (ev: JobEvent) => {
        if (ev.type === 'error') error.value = ev.error ?? '生成出错'
        if (ev.type === 'item' && ev.total)
          progress.value = { done: ev.index ?? 0, total: ev.total }
      },
      async () => {
        generating.value = false
        unsubscribe = null
        emit('busy', false)
        await load()
      },
    )
  } catch (e) {
    error.value = String(e instanceof Error ? e.message : e)
    generating.value = false
    emit('busy', false)
  }
}

function changed(item: CopyItem) {
  return (
    drafts.value[item.path] !== undefined &&
    drafts.value[item.path] !== item.copy
  )
}

// 卸载时断开 SSE，避免留下悬空连接
onUnmounted(() => unsubscribe?.())
</script>

<template>
  <section class="card">
    <div class="head">
      <h2>无口播分镜的 AI 文案</h2>
      <span v-if="loaded" class="muted">
        {{ needCopy.length }} 个无口播片段，{{ withCopy }} 个已有文案
      </span>
      <span class="spacer" />
      <button :disabled="loading || props.busy" @click="load">
        {{ loaded ? '刷新' : '查看' }}
      </button>
      <button :disabled="testing || props.busy" @click="test">
        {{ testing ? '测试中…' : '测试视觉接口' }}
      </button>
      <button
        class="primary"
        :disabled="generating || props.busy || props.visionBackend === 'stub'"
        @click="generate"
      >
        {{ generating ? '生成中…' : '识别并生成全部文案' }}
      </button>
    </div>

    <p v-if="props.visionBackend === 'stub'" class="warn">
      未配置方舟 API Key，无法生成文案。凭证填在
      <code>%LOCALAPPDATA%\Ave\credentials.json</code> 的
      <code>ARK_API_KEY</code>，开通步骤见 docs/资源需求清单.md。
      填好后重启服务即生效。
    </p>
    <p v-else class="muted small">视觉模型：{{ props.visionModel }}</p>

    <p v-if="testResult" class="test" :class="testOk ? 'ok' : 'bad'">
      {{ testResult }}
    </p>
    <p v-if="error" class="warn">{{ error }}</p>
    <p v-if="generating && progress" class="muted small">
      进度 {{ progress.done }}/{{ progress.total }}
      —— 有口播的会跳过，只给无口播的生成
    </p>

    <p v-if="loaded && !needCopy.length" class="muted small">
      所有片段都有真人口播，不需要 AI 文案。
    </p>

    <ul v-if="needCopy.length" class="list">
      <li v-for="i in needCopy" :key="i.path">
        <div class="meta">
          <b>{{ i.label }}</b>
          <span class="tag">{{ roleName[i.role] ?? i.role }}</span>
          <span v-if="i.asr === null" class="tag unknown">未识别</span>
          <span v-else class="tag silent">
            语音占比 {{ Math.round((i.speech_ratio ?? 0) * 100) }}%
          </span>
          <span v-if="i.copy_source === 'edited'" class="tag edited">
            人工改过
          </span>
          <span v-else-if="i.copy_source === 'ai'" class="tag ai">AI 生成</span>
        </div>
        <textarea
          rows="2"
          placeholder="还没有文案。点上面「识别并生成全部文案」，或直接在这里手写。"
          :value="drafts[i.path] ?? i.copy"
          @input="drafts[i.path] = ($event.target as HTMLTextAreaElement).value"
        />
        <div class="row">
          <em class="muted small">
            {{ (drafts[i.path] ?? i.copy).length }} 字
          </em>
          <span class="spacer" />
          <em v-if="saved[i.path]" class="ok small">已保存</em>
          <button :disabled="!changed(i)" @click="save(i)">保存</button>
        </div>
      </li>
    </ul>
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
  line-height: 1.6;
  margin: 8px 0 0;
}
.test {
  font-size: 12px;
  line-height: 1.6;
  margin: 8px 0 0;
  padding: 8px 10px;
  border-radius: 6px;
  word-break: break-all;
}
.test.ok {
  background: #1d3a26;
  color: #8cffb0;
}
.test.bad {
  background: #3a1d1d;
  color: #ff9c9c;
}
.ok {
  color: #8cffb0;
}
.list {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.list li {
  padding: 10px 12px;
  background: #1a2536;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 13px;
  margin-bottom: 6px;
}
.tag {
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 10px;
  background: #223047;
  color: var(--dim);
}
.tag.silent {
  background: #3a331d;
  color: #ffd98c;
}
.tag.unknown {
  background: #2b2b3a;
  color: #b0b0c8;
}
.tag.edited {
  background: #1d3a26;
  color: #8cffb0;
}
.tag.ai {
  background: #1d2a3a;
  color: #8cc8ff;
}
textarea {
  width: 100%;
  box-sizing: border-box;
  resize: vertical;
  font: inherit;
  font-size: 13px;
  line-height: 1.6;
}
.row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}
em {
  font-style: normal;
}
</style>
