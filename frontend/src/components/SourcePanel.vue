<script setup lang="ts">
import type { ScanStats } from '../api'

const props = defineProps<{
  source: string
  stats: ScanStats | null
  scanning: boolean
  picking: boolean
}>()

const emit = defineEmits<{
  'update:source': [string]
  scan: []
  pick: []
}>()
</script>

<template>
  <section class="card">
    <h2>素材</h2>

    <div class="row">
      <input
        :value="props.source"
        class="path"
        placeholder="分镜素材根目录，例如 D:\Download\分镜"
        @input="emit('update:source', ($event.target as HTMLInputElement).value)"
        @keyup.enter="emit('scan')"
      />
      <button :disabled="props.picking" @click="emit('pick')">
        {{ props.picking ? '选择中…' : '选择文件夹' }}
      </button>
      <!-- 扫描是必做的第一步，给 primary —— 原来它是普通样式，
           反而「添加音乐」是 primary，第一次用的人会先点错那个。 -->
      <button class="primary" :disabled="props.scanning" @click="emit('scan')">
        {{ props.scanning ? '扫描中…' : '扫描' }}
      </button>
    </div>

    <div v-if="props.stats" class="stats">
      <div class="tiles">
        <div class="tile">
          <b>{{ props.stats.groups.hooks }}</b>
          <span>钩子</span>
          <em v-if="props.stats.hooks !== props.stats.groups.hooks">
            {{ props.stats.hooks }} 个文件
          </em>
        </div>
        <div class="tile">
          <b>{{ props.stats.groups.points }}</b>
          <span>卖点</span>
          <em v-if="props.stats.points !== props.stats.groups.points">
            {{ props.stats.points }} 个文件
          </em>
        </div>
        <div class="tile">
          <b>{{ props.stats.groups.endings }}</b>
          <span>结尾促单</span>
          <em v-if="props.stats.endings !== props.stats.groups.endings">
            {{ props.stats.endings }} 个文件
          </em>
        </div>
        <div class="tile accent">
          <b>{{ props.stats.expected }}</b>
          <span>预计产出</span>
          <em>钩子数 × 使用次数</em>
        </div>
      </div>

      <p v-if="props.stats.unparsed.length" class="warn">
        {{ props.stats.unparsed.length }} 个文件命名不符规范、已跳过：
        {{ props.stats.unparsed.slice(0, 4).join('、') }}
        <template v-if="props.stats.unparsed.length > 4">等</template>
      </p>
    </div>
  </section>
</template>

<style scoped>
.tiles {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-top: 14px;
}
.tile {
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.tile.accent {
  border-color: #3d5a80;
  background: #1a2536;
}
.tile b {
  font-size: 26px;
  line-height: 1.1;
}
.tile span {
  font-size: 13px;
  color: var(--dim);
}
.tile em {
  font-size: 11px;
  color: var(--dim);
  font-style: normal;
  opacity: 0.7;
}
.path {
  flex: 1;
}
.warn {
  margin: 12px 0 0;
  font-size: 13px;
  color: #ffd98c;
}
</style>
