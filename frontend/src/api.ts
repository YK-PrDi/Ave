// 后端接口封装。后端跑在本机 8756，开发期由 vite 代理转发。

export interface Health {
  ffmpeg: boolean
  font: boolean
  model: boolean
  tts_backend: string
  tts_ready: boolean
  // 视觉后端状态也从 health 拿 —— copy/list 依赖素材目录，
  // 目录不存在时会 400，不能用它判断凭证配没配
  vision_backend?: string
  vision_model?: string
  vision_models?: string[]
  bgm_count: number
  // BGM 分两层：内置随应用更新，自定义在用户数据目录（各公司自己加）
  bgm: {
    builtin: number
    custom: number
    builtin_dir: string
    custom_dir: string
  }
  source_dir: string
  output_dir: string
  defaults: {
    points: number
    hook_limit: number
    sub_size: number
    speed: number
    bgm_volume: number
  }
}

export interface BgmTrack {
  name: string
  source: 'builtin' | 'custom'
  size_mb: number
}

// 一个片段的口播状态与 AI 文案
export interface CopyItem {
  path: string
  name: string
  role: string
  label: string
  // true 有口播 / false 已识别但无口播 / null 还没识别过（状态未知，不猜）
  asr: boolean | null
  speech_ratio: number | null
  copy: string
  // 'ai' 模型生成 / 'edited' 人工改过（重新生成不覆盖）/ '' 无
  copy_source: string
}

export interface CopyList {
  source: string
  vision_backend: string
  vision_model: string
  vision_models?: string[]
  items: CopyItem[]
}

export interface ScanStats {
  source: string
  hooks: number
  points: number
  endings: number
  groups: { hooks: number; points: number; endings: number }
  unparsed: string[]
  expected: number
}

export interface ComboItem {
  index: number
  hook: string
  points: string[]
  ending: string
}

export interface Preview {
  stats: ScanStats
  total: number
  // 聚类说明，如「33 个卖点组 → 16 个主题（31 组用 ASR 原文…）」
  theme_note: string
  themes: number
  combos: ComboItem[]
}

export interface JobParams {
  source?: string
  points?: number
  hook_limit?: number
  seed?: number
  limit?: number
  out_dir?: string
  bgm_dir?: string
  sub_size?: number
  dedup?: boolean
  // 画面倍速。1.0 = 原速
  speed?: number
  // 给无口播片段用 AI 补口播文案
  ai_copy?: boolean
  // BGM 音量百分比（100 = 原始音量）。0 = 不加 BGM
  bgm_volume?: number
}

// 渲染进度事件。type 决定其余字段是否存在。
export interface JobEvent {
  // prewarm：渲染前的 ASR 预热。全新安装时缓存是空的，这一步要跑两分钟，
  // 没有它界面会静默停在「渲染中」看起来像卡死。
  type: 'start' | 'prewarm' | 'item' | 'done' | 'stopped' | 'error' | 'eof'
  at?: number
  done?: number
  total?: number
  encoder?: string
  backend?: string
  out_dir?: string
  stats?: ScanStats
  index?: number
  ok?: boolean
  file?: string
  size_mb?: number
  seconds?: number
  notes?: string[]
  error?: string
  failed?: { index: number; error: string }[]
  speed?: number
  ai_copy?: boolean
  bgm_volume?: number
  vision_backend?: string
  // 批量生成文案任务用（kind='copy'）
  action?: string
  copy?: string
  made?: number
  skipped?: number
}

// 渲染时落盘的真实构成。后端从 .ave-manifest.json 读出来一并返回。
export interface ComboRecord {
  index: number
  seed: number | null
  hook: string
  points: string[]
  ending: string
  at: number
}

export interface OutputFile {
  name: string
  size_mb: number
  mtime: number
  // 旧成品渲染时还没有清单，为 null
  combo: ComboRecord | null
}

const BASE = '/api'

async function post<T>(path: string, body: unknown = {}): Promise<T> {
  const r = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText)
  return r.json()
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(BASE + path)
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText)
  return r.json()
}

export const api = {
  health: () => get<Health>('/health'),
  scan: (source?: string) => post<ScanStats>('/scan', { source }),

  // 弹系统目录选择框。浏览器拿不到真实路径，必须走后端。
  pickDir: (title: string, initial?: string) =>
    post<{ path: string | null }>('/pick-dir', { title, initial }),

  preview: (p: JobParams) => post<Preview>('/preview', p),
  createJob: (p: JobParams) => post<{ id: string }>('/jobs', p),
  stopJob: (id: string) => post<{ ok: boolean }>(`/jobs/${id}/stop`),
  outputs: (outDir?: string) =>
    get<{ dir: string; files: OutputFile[] }>(
      '/outputs' + (outDir ? `?out_dir=${encodeURIComponent(outDir)}` : ''),
    ),

  // <video src> 直接指这个地址，后端支持 Range 所以能拖进度条
  videoUrl: (name: string, outDir?: string) =>
    `${BASE}/video?name=${encodeURIComponent(name)}` +
    (outDir ? `&out_dir=${encodeURIComponent(outDir)}` : ''),

  deleteOutput: (name: string, outDir?: string) =>
    post<{ ok: boolean }>(
      `/outputs/delete?name=${encodeURIComponent(name)}` +
        (outDir ? `&out_dir=${encodeURIComponent(outDir)}` : ''),
    ),
  openOutput: (outDir?: string) =>
    post<{ ok: boolean }>(
      '/open-output' + (outDir ? `?out_dir=${encodeURIComponent(outDir)}` : ''),
    ),

  // ---- BGM 两层管理 ----
  bgm: () =>
    get<{ builtin_dir: string; custom_dir: string; tracks: BgmTrack[] }>('/bgm'),
  // 弹系统文件框选音频（浏览器拿不到真实路径，必须走后端）
  bgmAdd: () =>
    post<{ added: string[]; skipped: { name: string; why: string }[] }>(
      '/bgm/add',
    ),
  bgmDelete: (name: string) =>
    post<{ ok: boolean }>(`/bgm/delete?name=${encodeURIComponent(name)}`),

  // ---- AI 口播文案 ----
  copyList: (source?: string) => post<CopyList>('/copy/list', { source }),
  copySave: (path: string, text: string, source?: string) =>
    post<{ ok: boolean; text: string; copy_source: string }>('/copy/save', {
      path,
      text,
      source,
    }),
  copyGenerate: (source?: string) =>
    post<{ id: string }>('/copy/generate', { source }),

  // ---- 导出（渲染完之后整条变速，不覆盖原片）----
  // 用户 2026-08-26 定：整个视频出来之后再过一遍前端的倍速，然后导出
  exportOutputs: (p: {
    speed: number
    names?: string[]
    out_dir?: string
    sub_dir?: string
  }) => post<{ id: string; out_dir: string; total: number }>('/export', p),
  visionTest: (source?: string) =>
    post<{
      ok: boolean
      backend: string
      model?: string
      models?: string[]
      note?: string
      reply?: string
      error?: string
      with_image?: boolean
    }>('/vision/test', { source }),

  // SSE 订阅渲染进度。返回取消函数。
  subscribe(id: string, onEvent: (e: JobEvent) => void, onEnd: () => void) {
    const es = new EventSource(`${BASE}/jobs/${id}/events`)
    es.onmessage = (m) => {
      const ev: JobEvent = JSON.parse(m.data)
      if (ev.type === 'eof') {
        es.close()
        onEnd()
        return
      }
      onEvent(ev)
    }
    // 出错也要收尾，否则界面会一直停在"渲染中"
    es.onerror = () => {
      es.close()
      onEnd()
    }
    return () => es.close()
  },
}
