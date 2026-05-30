export const CHUNKING_STRATEGY_LABELS: Record<string, string> = {
  fixed: '固定长度切分',
  structural: '按结构切分',
  'table-aware': '表格感知切分',
  'parent-child': '父子分层切分',
  semantic: '语义切分',
  'chat-record': '聊天记录切分',
}

export const RETRIEVAL_STRATEGY_LABELS: Record<string, string> = {
  dense: '稠密检索',
  hybrid: '混合检索',
}

export function getChunkingStrategyLabel(name?: string | null) {
  if (!name) return '固定长度切分'
  return CHUNKING_STRATEGY_LABELS[name] ?? name
}

export function getRetrievalStrategyLabel(name?: string | null) {
  if (!name) return '稠密检索'
  return RETRIEVAL_STRATEGY_LABELS[name] ?? name
}

export function getStatusLabel(status?: string | null) {
  const labels: Record<string, string> = {
    pending: '等待中',
    running: '运行中',
    completed: '已完成',
    failed: '失败',
  }
  return labels[status || ''] ?? status ?? '未知'
}
