import { createSystemConfig, fetchSystemConfigs, updateSystemConfig } from './api'
import type { FieldKey, FieldOption, FieldOptionsConfig, SystemConfigItem } from './types'

export const FIELD_OPTIONS_CONFIG_KEY = 'metadata.field_options'

export const FIELD_LABELS: Record<FieldKey, string> = {
  source_module: '知识库',
  source_type: '文档类型',
}

export const FIELD_ORDER: FieldKey[] = ['source_module', 'source_type']

export const DEFAULT_FIELD_OPTIONS_CONFIG: FieldOptionsConfig = {
  fields: {
    source_module: [
      { value: 'oa', label: 'OA', enabled: true, sort_order: 10 },
      { value: 'hr', label: 'HR', enabled: true, sort_order: 20 },
      { value: 'crm', label: 'CRM', enabled: true, sort_order: 30 },
      { value: 'general', label: '通用', enabled: true, sort_order: 40 },
    ],
    source_type: [
      { value: 'rule_doc', label: '制度规范', enabled: true, sort_order: 10 },
      { value: 'faq', label: 'FAQ问答', enabled: true, sort_order: 20 },
      { value: 'manual', label: '操作手册', enabled: true, sort_order: 30 },
      { value: 'policy', label: '政策文件', enabled: true, sort_order: 40 },
      { value: 'notice', label: '通知公告', enabled: true, sort_order: 50 },
      { value: 'other', label: '其他文档', enabled: true, sort_order: 60 },
    ],
  },
}

function isFieldKey(value: string): value is FieldKey {
  return FIELD_ORDER.includes(value as FieldKey)
}

function cloneConfig(config: FieldOptionsConfig): FieldOptionsConfig {
  return {
    fields: Object.fromEntries(
      FIELD_ORDER.map((fieldKey) => [
        fieldKey,
        config.fields[fieldKey].map((option) => ({ ...option })),
      ]),
    ) as Record<FieldKey, FieldOption[]>,
  }
}

function normalizeOption(raw: unknown, fallbackOrder: number): FieldOption | null {
  if (!raw || typeof raw !== 'object') return null
  const item = raw as Record<string, unknown>
  const value = typeof item.value === 'string' ? item.value.trim() : ''
  if (!value) return null
  const label = typeof item.label === 'string' && item.label.trim() ? item.label.trim() : value
  const enabled = typeof item.enabled === 'boolean' ? item.enabled : true
  const sortOrder = typeof item.sort_order === 'number' && Number.isFinite(item.sort_order)
    ? item.sort_order
    : fallbackOrder
  return { value, label, enabled, sort_order: sortOrder }
}

function sortOptions(options: FieldOption[]) {
  return [...options].sort((a, b) => a.sort_order - b.sort_order || a.label.localeCompare(b.label, 'zh-CN'))
}

export function normalizeFieldOptionsConfig(raw: unknown): FieldOptionsConfig {
  const next = cloneConfig(DEFAULT_FIELD_OPTIONS_CONFIG)
  if (!raw || typeof raw !== 'object') return next
  const fields = (raw as { fields?: unknown }).fields
  if (!fields || typeof fields !== 'object') return next

  Object.entries(fields as Record<string, unknown>).forEach(([key, value]) => {
    if (!isFieldKey(key) || !Array.isArray(value)) return
    const seen = new Set<string>()
    const normalized = value
      .map((option, index) => normalizeOption(option, (index + 1) * 10))
      .filter((option): option is FieldOption => Boolean(option))
      .filter((option) => {
        if (seen.has(option.value)) return false
        seen.add(option.value)
        return true
      })
    next.fields[key] = sortOptions(normalized.length > 0 ? normalized : next.fields[key])
  })

  return next
}

export function getFieldOptions(config: FieldOptionsConfig, fieldKey: FieldKey, currentValue?: string | null) {
  const value = currentValue?.trim()
  const enabledOptions = sortOptions(config.fields[fieldKey].filter((option) => option.enabled))
  if (!value || enabledOptions.some((option) => option.value === value)) return enabledOptions
  const knownOption = config.fields[fieldKey].find((option) => option.value === value)
  return [
    ...enabledOptions,
    {
      value,
      label: `${knownOption?.label ?? value}（历史值）`,
      enabled: false,
      sort_order: Number.MAX_SAFE_INTEGER,
    },
  ]
}

export function getFieldLabel(config: FieldOptionsConfig, fieldKey: FieldKey, value?: string | null) {
  if (!value) return ''
  return config.fields[fieldKey].find((option) => option.value === value)?.label ?? value
}

export function firstEnabledValue(config: FieldOptionsConfig, fieldKey: FieldKey, fallback = '') {
  return getFieldOptions(config, fieldKey)[0]?.value ?? fallback
}

export async function loadFieldOptionsSystemConfig(): Promise<{
  item: SystemConfigItem
  config: FieldOptionsConfig
}> {
  const response = await fetchSystemConfigs({ keyword: FIELD_OPTIONS_CONFIG_KEY })
  const existing = response.items.find((item) => item.config_key === FIELD_OPTIONS_CONFIG_KEY)
  if (existing) {
    return { item: existing, config: normalizeFieldOptionsConfig(existing.config_value) }
  }

  try {
    const created = await createSystemConfig({
      config_key: FIELD_OPTIONS_CONFIG_KEY,
      config_value: DEFAULT_FIELD_OPTIONS_CONFIG as unknown as Record<string, unknown>,
      description: '文档元数据字段选项配置',
    })
    return { item: created, config: normalizeFieldOptionsConfig(created.config_value) }
  } catch {
    // 并发创建可能冲突，等待后重试
    await new Promise((resolve) => setTimeout(resolve, 300))
    const retry = await fetchSystemConfigs({ keyword: FIELD_OPTIONS_CONFIG_KEY })
    const retried = retry.items.find((item) => item.config_key === FIELD_OPTIONS_CONFIG_KEY)
    if (retried) return { item: retried, config: normalizeFieldOptionsConfig(retried.config_value) }
    // 再试一次创建
    const created = await createSystemConfig({
      config_key: FIELD_OPTIONS_CONFIG_KEY,
      config_value: DEFAULT_FIELD_OPTIONS_CONFIG as unknown as Record<string, unknown>,
      description: '文档元数据字段选项配置',
    })
    return { item: created, config: normalizeFieldOptionsConfig(created.config_value) }
  }
}

export async function saveFieldOptionsSystemConfig(configId: number | null, config: FieldOptionsConfig) {
  const normalized = normalizeFieldOptionsConfig(config)
  if (configId) {
    return updateSystemConfig(configId, {
      config_value: normalized as unknown as Record<string, unknown>,
      description: '文档元数据字段选项配置',
    })
  }
  return createSystemConfig({
    config_key: FIELD_OPTIONS_CONFIG_KEY,
    config_value: normalized as unknown as Record<string, unknown>,
    description: '文档元数据字段选项配置',
  })
}
