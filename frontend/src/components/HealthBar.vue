<script setup lang="ts">
import type { Health } from '../api'

const props = defineProps<{ health: Health | null }>()

// 只列出真正会阻塞出片的项，避免满屏绿勾噪音
function issues(h: Health) {
  const out: { text: string; level: 'error' | 'warn' }[] = []
  if (!h.ffmpeg) out.push({ text: '找不到 ffmpeg，无法渲染', level: 'error' })
  if (!h.model) out.push({ text: '缺语音识别模型，无法生成字幕', level: 'error' })
  if (!h.font) out.push({ text: '找不到字体文件，字幕无法渲染', level: 'error' })
  if (!h.tts_ready) out.push({ text: '火山引擎凭证不全，配音会失败', level: 'error' })
  if (h.tts_backend === 'stub')
    out.push({ text: '配音为静音占位（等火山引擎凭证）', level: 'warn' })
  // ⚠️ `bgm_count` 只数本地两层，**不含云端**。云端启用时本地 0 首是
  // 正常状态（曲子抽中才下载），这时报「未放入 BGM」是假警告 ——
  // 实测清掉内置层后必然触发，而云端 312 首好着呢。
  if (h.bgm_count === 0 && !h.bgm.cloud)
    out.push({ text: '未放入 BGM，成品无背景音乐', level: 'warn' })
  return out
}
</script>

<template>
  <div v-if="props.health" class="health">
    <template v-if="issues(props.health).length">
      <span
        v-for="i in issues(props.health)"
        :key="i.text"
        class="pill"
        :class="i.level"
      >{{ i.text }}</span>
    </template>
    <span v-else class="pill ok">环境就绪</span>
    <span class="spacer" />
    <span class="muted">
      BGM {{ props.health.bgm_count }} 首（内置
      {{ props.health.bgm.builtin }} · 自定义 {{ props.health.bgm.custom }}<template
        v-if="props.health.bgm.cloud"
      >
        · 云端曲库已启用</template
      >）
    </span>
  </div>
</template>

<style scoped>
.health {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  padding: 10px 14px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
}
.pill {
  font-size: 13px;
  padding: 3px 10px;
  border-radius: 20px;
  border: 1px solid transparent;
}
.pill.error {
  background: #3a1d1d;
  color: #ff9c9c;
  border-color: #6b2b2b;
}
.pill.warn {
  background: #3a331d;
  color: #ffd98c;
  border-color: #6b5c2b;
}
.pill.ok {
  background: #1d3a26;
  color: #8cffb0;
  border-color: #2b6b3f;
}
.spacer {
  flex: 1;
}
.muted {
  color: var(--dim);
  font-size: 13px;
}
</style>
