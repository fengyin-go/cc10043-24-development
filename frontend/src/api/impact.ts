import { request } from './client'
import type {
  ImpactPage,
  ImpactTargetColumn,
  PreviewRecord,
  RerunResult,
  RuleImpactRow,
} from '@/data/types'

/** 规则影响明细的查询条件：Schema 版本、来源字段、目标字段、绑定状态。 */
export type ImpactFilters = {
  schema_name?: string
  schema_version?: string
  source_field?: string
  target_field?: string
  binding?: string
  keyword?: string
}

async function readJson<T>(response: Response, fallbackMessage: string): Promise<T> {
  if (!response.ok) {
    let detail = fallbackMessage
    try {
      detail = (await response.json()).detail ?? fallbackMessage
    } catch {
      /* 保留兜底文案 */
    }
    throw new Error(detail)
  }
  return (await response.json()) as T
}

function toQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') search.set(key, String(value))
  })
  const query = search.toString()
  return query ? `?${query}` : ''
}

export async function fetchRuleImpact(filters: ImpactFilters): Promise<ImpactPage<RuleImpactRow>> {
  const response = await request(`/api/field_transform/impact${toQuery(filters)}`)
  return readJson(response, '规则影响明细读取失败')
}

export async function editRule(
  ruleId: number,
  values: Record<string, string>,
): Promise<{ ok: boolean; message: string; entry: RuleImpactRow }> {
  const response = await request(`/api/field_transform/rules/${ruleId}/edit`, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  return readJson(response, '规则编辑失败')
}

export async function rerunRule(
  ruleId: number,
  payload: { ref_id?: number; sample_id?: number; sample_value?: string } = {},
): Promise<RerunResult> {
  const response = await request(`/api/field_transform/rules/${ruleId}/rerun`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return readJson(response, '规则重跑失败')
}

export async function fetchPreviews(params: {
  rule_id?: number
  ref_id?: number
}): Promise<ImpactPage<PreviewRecord>> {
  const response = await request(`/api/field_transform/previews${toQuery(params)}`)
  return readJson(response, '预览留痕读取失败')
}

export async function fetchImpactTargets(params: {
  schema_name?: string
  schema_version?: string
  target_field?: string
}): Promise<ImpactPage<ImpactTargetColumn>> {
  const response = await request(`/api/schema_registry/impact${toQuery(params)}`)
  return readJson(response, '影响目标列读取失败')
}

export async function rerunTargetColumn(payload: {
  schema_name: string
  schema_version: string
  target_field: string
  ref_id?: number
}): Promise<RerunResult> {
  const response = await request('/api/schema_registry/rerun-column', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return readJson(response, '目标列重跑失败')
}
