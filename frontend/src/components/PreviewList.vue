<script setup lang="ts">
import { ref } from 'vue'
import type { ComboItem } from '../api'

const props = defineProps<{
  combos: ComboItem[]
  loading: boolean
}>()

const emit = defineEmits<{ refresh: [] }>()

// 39 条全展开太长，默认只显示前 8 条
const showAll = ref(false)
const PREVIEW_N = 8
</script>

<template>
  <section class="card">
    <div class="head">
      <h2>组合预览</h2>
      <button class="ghost" :disabled="props.loading" @click="emit('refresh')">
        {{ props.loading ? '生成中…' : '重新抽样' }}
      </button>
    </div>

    <p v-if="!props.combos.length" class="empty">
      先扫描素材，再生成组合方案
    </p>

    <template v-else>
      <ol class="list">
        <li
          v-for="c in (showAll ? props.combos : props.combos.slice(0, PREVIEW_N))"
          :key="c.index"
        >
          <div class="top">
            <span class="idx">{{ String(c.index).padStart(2, '0') }}</span>
            <span class="seg hook">{{ c.hook }}</span>
            <span class="arrow">→</span>
            <span class="seg end">{{ c.ending }}</span>
          </div>
          <div class="chain">
            <span v-for="(p, i) in c.points" :key="i" class="seg">
              <i>{{ i + 1 }}</i>{{ p }}
            </span>
          </div>
        </li>
      </ol>

      <button
        v-if="props.combos.length > PREVIEW_N"
        class="ghost wide"
        @click="showAll = !showAll"
      >
        {{ showAll ? '收起' : `展开全部 ${props.combos.length} 条` }}
      </button>
    </template>
  </section>
</template>

<style scoped>
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.list {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 380px;
  overflow-y: auto;
}
.list li {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--line);
}
.top {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.arrow {
  color: var(--dim);
  font-size: 12px;
}
.idx {
  color: var(--dim);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}
.chain {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  padding-left: 22px;
}
.seg i {
  font-style: normal;
  color: var(--dim);
  margin-right: 5px;
  font-size: 10px;
}
.seg {
  font-size: 12px;
  padding: 3px 8px;
  border-radius: 5px;
  background: var(--bg);
  border: 1px solid var(--line);
  color: #cfd6e0;
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
.wide {
  width: 100%;
  margin-top: 10px;
}
</style>
