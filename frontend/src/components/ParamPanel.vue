<script setup lang="ts">
import { computed } from 'vue'
import type { ScanStats } from '../api'

const props = defineProps<{
  points: number
  hookLimit: number
  subSize: number
  seed: number | null
  limit: number
  stats: ScanStats | null
}>()

const emit = defineEmits<{
  'update:points': [number]
  'update:hookLimit': [number]
  'update:subSize': [number]
  'update:seed': [number | null]
  'update:limit': [number]
}>()

// 产量随参数实时变，让人调参时能立刻看到影响
const expected = computed(() => {
  if (!props.stats) return null
  const n = props.stats.groups.hooks * props.hookLimit
  return props.limit ? Math.min(n, props.limit) : n
})

// 卖点数超过素材量会直接报错，提前拦
const pointsTooMany = computed(
  () => !!props.stats && props.points > props.stats.groups.points,
)
</script>

<template>
  <section class="card">
    <h2>参数</h2>

    <div class="grid">
      <label>
        <span>每条用几个卖点</span>
        <input
          type="number" min="1" max="20" :value="props.points"
          @input="emit('update:points', +($event.target as HTMLInputElement).value)"
        />
        <em v-if="pointsTooMany" class="bad">
          素材只有 {{ props.stats!.groups.points }} 个卖点
        </em>
      </label>

      <label>
        <span>每个钩子用几次</span>
        <input
          type="number" min="1" max="20" :value="props.hookLimit"
          @input="emit('update:hookLimit', +($event.target as HTMLInputElement).value)"
        />
        <em>决定产量</em>
      </label>

      <label>
        <span>字幕字号</span>
        <input
          type="number" min="8" max="30" :value="props.subSize"
          @input="emit('update:subSize', +($event.target as HTMLInputElement).value)"
        />
        <em>需求要求 10–15</em>
      </label>

      <label>
        <span>随机种子</span>
        <input
          type="number" placeholder="留空则每次不同"
          :value="props.seed ?? ''"
          @input="emit('update:seed',
            ($event.target as HTMLInputElement).value === ''
              ? null : +($event.target as HTMLInputElement).value)"
        />
        <em>填数字可复现同一批组合</em>
      </label>

      <label>
        <span>只跑前几条</span>
        <input
          type="number" min="0" placeholder="0 = 全部" :value="props.limit"
          @input="emit('update:limit', +($event.target as HTMLInputElement).value)"
        />
        <em>先试跑几条用</em>
      </label>

      <div v-if="expected !== null" class="out">
        <span>本次将产出</span>
        <b>{{ expected }} 条</b>
      </div>
    </div>
  </section>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 14px;
  margin-top: 6px;
}
label {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
label > span {
  font-size: 13px;
  color: var(--dim);
}
label em {
  font-size: 11px;
  color: var(--dim);
  font-style: normal;
  opacity: 0.7;
}
label em.bad {
  color: #ff9c9c;
  opacity: 1;
}
.out {
  display: flex;
  flex-direction: column;
  gap: 4px;
  justify-content: center;
  padding: 10px 14px;
  background: #1a2536;
  border: 1px solid #3d5a80;
  border-radius: 8px;
}
.out span {
  font-size: 13px;
  color: var(--dim);
}
.out b {
  font-size: 22px;
}
</style>
