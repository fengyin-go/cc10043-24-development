<template>
  <section class="page impact-page" data-testid="rule-impact">
    <header class="page-head">
      <div>
        <h2>转换规则影响明细</h2>
        <p class="page-desc">
          以 Schema 版本、来源字段和目标字段定位转换规则，用实际样本区分正在用的规则与尚未生效的候选。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" data-testid="impact-refresh" type="button" @click="reload">刷新列表</button>
      </div>
    </header>

    <form class="analysis-form" @submit.prevent="reload">
      <label>
        Schema 名称
        <input v-model="filters.schema_name" data-testid="filter-schema-name" placeholder="如：订单Schema" />
      </label>
      <label>
        Schema 版本
        <input v-model="filters.schema_version" data-testid="filter-schema-version" placeholder="如：v1" />
      </label>
      <label>
        来源字段
        <input v-model="filters.source_field" data-testid="filter-source-field" placeholder="如：amount_yuan" />
      </label>
      <label>
        目标字段
        <input v-model="filters.target_field" data-testid="filter-target-field" placeholder="如：amount" />
      </label>
      <label>
        绑定状态
        <select v-model="filters.binding" data-testid="filter-binding">
          <option value="">全部</option>
          <option v-for="state in BINDING_STATES" :key="state" :value="state">{{ state }}</option>
        </select>
      </label>
      <label>
        规则/来源关键词
        <input v-model="filters.keyword" data-testid="filter-keyword" placeholder="规则名称或写入来源" />
      </label>
      <button class="btn primary" data-testid="impact-query" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <p class="status-legend">
      共 {{ total }} 条规则版本；
      <span class="badge 生效中">生效中 {{ bindingCount('生效中') }}</span>
      <span class="badge 候选">候选 {{ bindingCount('候选') }}</span>
      <span class="badge 已失效">已失效 {{ bindingCount('已失效') }}</span>
      <span class="badge 已停用">已停用 {{ bindingCount('已停用') }}</span>
    </p>

    <div class="table-wrap">
      <table class="data-table impact-table">
        <thead>
          <tr>
            <th>Schema 版本</th>
            <th>来源字段 → 目标字段</th>
            <th>规则 / 版本</th>
            <th>写入来源</th>
            <th>绑定状态</th>
            <th>实际样本</th>
            <th>竞争来源与采用方</th>
            <th>报表规则引用</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="String(row.rule_id)"
            :data-testid="`impact-row-${row.rule_id}`"
            :class="{ 'stale-row': row.绑定状态 === '已失效' }"
          >
            <td>{{ row.Schema名称 }} {{ row.Schema版本 }}</td>
            <td>
              <div class="field-pair">{{ row.源字段 }} → {{ row.目标字段 }}</div>
              <div class="muted-text">{{ row.转换函数 }}</div>
            </td>
            <td>
              <div>{{ row.规则名称 }}</div>
              <div class="muted-text">
                {{ row.规则键 }} · v{{ row.规则版本 }}（{{ row.版本状态 }}）
              </div>
            </td>
            <td>{{ row.写入来源 || '—' }}</td>
            <td>
              <span class="badge" :class="row.绑定状态">{{ row.绑定状态 }}</span>
              <div v-if="row.失效原因" class="stale-reason" :title="row.失效原因">
                {{ row.失效原因 }}
              </div>
            </td>
            <td>
              <template v-if="row.样本">
                <div class="sample-value">{{ row.样本.样本原始值 }}</div>
                <div class="muted-text">{{ row.样本.采集批次 }} / {{ row.样本.消息ID }}</div>
              </template>
              <span v-else class="muted-text">暂无实际样本</span>
            </td>
            <td>
              <template v-if="row.竞争组.has_competition">
                <div
                  v-for="rival in row.竞争组.competing"
                  :key="rival.rule_id"
                  class="rival-line"
                  :class="{ winner: rival.rule_id === row.竞争组.winner_rule_id }"
                >
                  <span class="rival-source">{{ rival.写入来源 || '未标注来源' }}</span>
                  <span class="muted-text">{{ rival.源字段 }} / {{ rival.status }}</span>
                  <span v-if="rival.rule_id === row.竞争组.winner_rule_id" class="winner-tag">样本采用</span>
                </div>
              </template>
              <span v-else class="muted-text">无竞争</span>
            </td>
            <td>
              <template v-if="row.reference">
                <div>{{ row.reference.引用编号 }}（{{ row.reference.报表名称 }}）</div>
                <div class="muted-text">引用 v{{ row.reference.引用规则版本 }}</div>
                <span class="badge" :class="referenceClass(row.reference.reference_state)">
                  {{ row.reference.reference_state }}
                </span>
              </template>
              <span v-else class="muted-text">未被报表引用</span>
              <div v-if="row.当前绑定" class="binding-now">
                当前绑定：{{ row.当前绑定.规则名称 }} v{{ row.当前绑定.规则版本 }}
              </div>
            </td>
            <td class="row-actions">
              <button
                class="link"
                type="button"
                :data-testid="`rerun-${row.rule_id}`"
                @click="onRerun(row)"
              >
                重跑
              </button>
              <button
                class="link"
                type="button"
                :data-testid="`edit-${row.rule_id}`"
                @click="onEdit(row)"
              >
                编辑
              </button>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td colspan="9" class="empty-state">没有符合条件的转换规则，调整筛选条件后重试</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 编辑规则：生效规则会沉淀新版本，旧版本失效留痕 -->
    <div v-if="editing" class="modal-backdrop" data-testid="edit-modal">
      <form class="modal" @submit.prevent="submitEdit">
        <h3>编辑规则：{{ editing.规则名称 }} v{{ editing.规则版本 }}</h3>
        <p class="muted-text">
          生效规则提交后会生成接棒的新版本，当前版本保留为「已失效」并记录原因，报表旧引用需复核重跑。
        </p>
        <label v-for="field in EDITABLE_FIELDS" :key="field" class="create-field">
          <span>{{ field }}</span>
          <input v-model="editValues[field]" :data-testid="`edit-input-${field}`" />
        </label>
        <p v-if="editError" class="error-text">{{ editError }}</p>
        <div class="page-actions">
          <button class="btn" type="button" @click="editing = null">取消</button>
          <button class="btn primary" data-testid="submit-edit" type="submit" :disabled="saving">
            {{ saving ? '提交中…' : '保存为新版本' }}
          </button>
        </div>
      </form>
    </div>

    <!-- 重跑结果：包含样本值、转换结果和版本失效依据 -->
    <div v-if="rerunResult" class="modal-backdrop" data-testid="rerun-modal">
      <div class="modal">
        <h3>重跑结果：{{ rerunResult.preview.规则名称 }} v{{ rerunResult.preview.规则版本 }}</h3>
        <dl class="result-grid">
          <dt>Schema 版本</dt>
          <dd>{{ rerunResult.preview.Schema名称 }} {{ rerunResult.preview.Schema版本 }}</dd>
          <dt>字段链路</dt>
          <dd>{{ rerunResult.preview.源字段 }} → {{ rerunResult.preview.目标字段 }}</dd>
          <dt>样本原始值</dt>
          <dd>{{ rerunResult.preview.样本原始值 ?? '未提供样本' }}（{{ rerunResult.preview.采集批次 ?? '无批次' }}）</dd>
          <dt>转换函数</dt>
          <dd>{{ rerunResult.preview.转换函数 }}</dd>
          <dt>转换结果</dt>
          <dd class="sample-value">{{ rerunResult.preview.转换结果 }}</dd>
          <dt>引用状态</dt>
          <dd>
            <span
              v-if="rerunResult.reference_state"
              class="badge"
              :class="referenceClass(rerunResult.reference_state)"
            >
              {{ rerunResult.reference_state }}
            </span>
            <span v-else class="muted-text">本次未带报表引用</span>
          </dd>
          <dt>版本失效原因</dt>
          <dd>
            <p v-if="rerunResult.stale_reason" class="stale-reason">{{ rerunResult.stale_reason }}</p>
            <span v-else class="muted-text">版本仍有效</span>
          </dd>
          <dt>当前绑定</dt>
          <dd>
            <template v-if="rerunResult.当前绑定">
              {{ rerunResult.当前绑定.规则名称 }} v{{ rerunResult.当前绑定.规则版本 }}
              （{{ rerunResult.当前绑定.status }}）
            </template>
            <span v-else class="muted-text">无</span>
          </dd>
          <dt>留痕时间</dt>
          <dd>{{ rerunResult.preview.预览时间 }}</dd>
        </dl>
        <div class="page-actions">
          <button class="btn" type="button" @click="rerunResult = null">关闭</button>
          <button class="btn primary" type="button" @click="rerunResult = null; reload()">
            确认并刷新列表
          </button>
        </div>
      </div>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条规则版本记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import {
  editRule,
  fetchRuleImpact,
  rerunRule,
  type ImpactFilters,
} from '@/api/impact'
import type { RuleImpactRow, RerunResult } from '@/data/types'

const BINDING_STATES = ['生效中', '候选', '已停用', '已失效']
const EDITABLE_FIELDS = ['规则名称', '源字段', '目标字段', '转换函数', '错误处理']

const rows = ref<RuleImpactRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = reactive<ImpactFilters>({})
const editing = ref<RuleImpactRow | null>(null)
const editValues = reactive<Record<string, string>>({})
const editError = ref('')
const saving = ref(false)
const rerunResult = ref<RerunResult | null>(null)

function bindingCount(state: string): number {
  return rows.value.filter((row) => row.绑定状态 === state).length
}

function referenceClass(state: string): string {
  if (state === '匹配') return '生效中'
  if (state === '版本已失效') return '已失效'
  if (state === '新版本待绑定') return '候选'
  return '已停用'
}

function resetFilters() {
  Object.keys(filters).forEach((key) => {
    filters[key as keyof ImpactFilters] = undefined
  })
  void reload()
}

async function reload() {
  errorMessage.value = ''
  try {
    const page = await fetchRuleImpact({ ...filters })
    rows.value = page.items
    total.value = page.total
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '规则影响明细读取失败'
  }
}

function onEdit(row: RuleImpactRow) {
  editing.value = row
  editError.value = ''
  EDITABLE_FIELDS.forEach((field) => {
    editValues[field] = String(row[field] ?? '')
  })
}

async function submitEdit() {
  if (!editing.value) return
  saving.value = true
  editError.value = ''
  try {
    const result = await editRule(editing.value.rule_id, { ...editValues })
    if (!result.ok) throw new Error(result.message)
    editing.value = null
    await reload()
  } catch (error) {
    editError.value = error instanceof Error ? error.message : '规则编辑失败'
  } finally {
    saving.value = false
  }
}

async function onRerun(row: RuleImpactRow) {
  errorMessage.value = ''
  try {
    rerunResult.value = await rerunRule(row.rule_id, {
      ref_id: row.reference?.ref_id,
      sample_id: row.样本?.sample_id,
    })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '规则重跑失败'
  }
}

onMounted(reload)
</script>
