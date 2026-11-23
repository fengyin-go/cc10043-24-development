/** 纯前端数据层的公共类型：与全栈版后端返回的结构保持一致，换回后端时页面不用改。 */

export type EntryRow = {
  id: number
  status: string
  pending: boolean
  abnormal: boolean
  [field: string]: string | number | boolean
}

export type ModuleMeta = {
  key: string
  name: string
  entity: string
  desc: string
  fields: string[]
  statuses: string[]
  actions: string[]
  actionTargets: Record<string, string>
  metrics: string[]
}

export type PageResult = {
  items: EntryRow[]
  total: number
  page: number
  size: number
}

export type ActionResult = {
  ok: boolean
  message: string
}

export type OverviewResult = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
}

/** 规则影响明细：一行对应一条转换规则版本，按 Schema 版本 + 源/目标字段定位。 */
export type ImpactSample = {
  sample_id: number
  源字段: string
  样本原始值: string
  写入来源: string
  采集批次: string
  消息ID: string
}

export type CompetingRule = {
  rule_id: number
  规则名称: string
  源字段: string
  写入来源: string
  status: string
  规则版本: number
}

export type RuleReference = {
  ref_id: number
  引用编号: string
  报表名称: string
  引用规则版本: number
  reference_state: string
}

export type CurrentBinding = {
  rule_id: number
  规则名称: string
  规则版本: number
  status: string
}

export type RuleImpactRow = EntryRow & {
  rule_id: number
  Schema名称: string
  Schema版本: string
  写入来源: string
  规则键: string
  规则版本: number
  版本状态: string
  失效原因: string | null
  绑定状态: string
  has_sample: boolean
  样本: ImpactSample | null
  竞争组: {
    competing: CompetingRule[]
    winner_rule_id: number | null
    adopted_by_sample: boolean
    has_competition: boolean
  }
  reference: RuleReference | null
  当前绑定: CurrentBinding | null
}

export type ImpactTargetColumn = {
  Schema名称: string
  Schema版本: string
  目标字段: string
  规则数: number
  生效规则数: number
  候选规则数: number
  失效规则数: number
  竞争来源: string[]
  样本采用规则ID: number | null
  reference: RuleReference | null
  当前绑定: CurrentBinding | null
  关联规则: {
    rule_id: number
    规则名称: string
    源字段: string
    写入来源: string
    规则版本: number
    绑定状态: string
  }[]
}

export type PreviewRecord = {
  id: number
  预览时间: string
  rule_id: number
  规则名称: string
  规则版本: number
  版本状态: string
  转换函数: string
  Schema名称: string
  Schema版本: string
  源字段: string
  目标字段: string
  ref_id: number | null
  引用编号: string | null
  reference_state: string | null
  stale_reason: string | null
  sample_id: number | null
  样本原始值: string | null
  采集批次: string | null
  转换结果: string | number | boolean | null
  ok: boolean
  message: string
}

export type RerunResult = {
  ok: boolean
  message: string
  preview: PreviewRecord
  reference_state: string | null
  stale_reason: string | null
  当前绑定: CurrentBinding | null
}

export type ImpactPage<T> = {
  items: T[]
  total: number
  page: number
  size: number
}
