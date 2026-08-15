// 后端接口封装。后端跑在本机 8756，开发期由 vite 代理转发。

export interface Health {
  ffmpeg: boolean
  font: boolean
  model: boolean
  tts_backend: string
  tts_ready: boolean
  bgm_count: number
  source_dir: string
  output_dir: string
  defaults: { points: number; hook_limit: number; sub_size: number }
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
}

// 渲染进度事件。type 决定其余字段是否存在。
export interface JobEvent {
  type: 'start' | 'item' | 'done' | 'stopped' | 'error' | 'eof'
  at?: number
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
}

export interface OutputFile {
  name: string
  size_mb: number
  mtime: number
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
  outputs: () => get<{ dir: string; files: OutputFile[] }>('/outputs'),
  openOutput: (outDir?: string) =>
    post<{ ok: boolean }>(
      '/open-output' + (outDir ? `?out_dir=${encodeURIComponent(outDir)}` : ''),
    ),

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
