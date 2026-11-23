<template>
  <section class="page impact-page" data-testid="schema-impact">
    <header class="page-head">
      <div>
        <h2>Schema 影响目标列</h2>
        <p class="page-desc">
          从影响清单选中实际关联的目标列，发布前拿报表中的规则引用重跑这一列，核对样本转换结果与版本依据。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" data-testid="schema-impact-refresh" type="button" @click="reload">刷新清单</button>
      </div>
    </header>

    <form class="analysis-form" @submit.prevent="reload">
      <label>
        Schema 名称
        <input v-model="filters.schema_name" data-testid="schema-filter-name" placeholder="如：订单Schema" />
      </label>
      <label>
        Schema 版本
        <input v-model="filters.schema_version" data-testid="schema-filter-version" placeholder="如：v1" />
      </label>
      <label>
        目标字段
        <input v-model="filters.target_field" data-testid="schema-filter-target" placeholder="如：amount" />
      </label>
      <button class="btn primary" data-testid="schema-impact-query" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div class="table-wrap">
      <table class="data-table impact-table">
        <thead>
          <tr>
            <th>Schema 版本</th>
            <th>目标字段</th>
            <th>规则构成</th>
            <th>竞争来源</th>
            <th>样本采用</th>
            <th>报表规则引用</th>
            <th>发布前预检</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="column in rows"
            :key="`${column.Schema名称}-${column.Schema版本}-${column.目标字段}`"
            :data-testid="`column-${column.Schema名称}-${column.目标字段}`"
          >
            <td>{{ column.Schema名称 }} {{ column.Schema版本 }}</td>
            <td class="sample-value">{{ column.目标字段 }}</td>
            <td>
              <div>共 {{ column.规则数 }} 条规则</div>
              <div class="muted-text">
                生效 {{ column.生效规则数 }} · 候选 {{ column.候选规则数 }} · 失效 {{ column.失效规则数 }}
              </div>
              <ul class="rule-mini-list">
                <li v-for="rule in column.关联规则" :key="rule.rule_id">
                  <span class="badge" :class="rule.绑定状态">{{ rule.绑定状态 }}</span>
                  {{ rule.规则名称 }} v{{ rule.规则版本 }}
                  <span class="muted-text">（{{ rule.写入来源 || '未标注来源' }} / {{ rule.源字段 }}）</span>
                </li>
              </ul>
            </td>
            <td>
              <span v-if="column.竞争来源.length" class="rival-source">
                {{ column.竞争来源.join('、') }}
              </span>
              <span v-else class="muted-text">无竞争</span>
            </td>
            <td>
              <span v-if="column.样本采用规则ID" class="winner-tag">
                样本采用规则 #{{ column.样本采用规则ID }}
              </span>
              <span v-else class="muted-text">暂无样本</span>
            </td>
            <td>
              <template v-if="column.reference">
                <div>{{ column.reference.引用编号 }}</div>
                <div class="muted-text">
                  {{ column.reference.报表名称 }} · 引用 v{{ column.reference.引用规则版本 }}
                </div>
                <span class="badge" :class="referenceClass(column.reference.reference_state)">
                  {{ column.reference.reference_state }}
                </span>
              </template>
              <span v-else class="muted-text">无报表引用，预检将改用生效规则</span>
            </td>
            <td>
              <button
                class="btn primary"
                type="button"
                :data-testid="`rerun-column-${column.目标字段}`"
                :disabled="runningKey === columnKey(column)"
                @click="onRerunColumn(column)"
              >
                {{ runningKey === columnKey(column) ? '重跑中…' : '按引用重跑此列' }}
              </button>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td colspan="7" class="empty-state">没有关联转换规则的目标列</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="rerunResult" class="modal-backdrop" data-testid="column-rerun-modal">
      <div class="modal">
        <h3>
          发布前预检：{{ rerunResult.preview.Schema名称 }} {{ rerunResult.preview.Schema版本 }}
          的 {{ rerunResult.preview.目标字段 }}
        </h3>
        <dl class="result-grid">
          <dt>执行规则</dt>
          <dd>{{ rerunResult.preview.规则名称 }} v{{ rerunResult.preview.规则版本 }}</dd>
          <dt>样本原始值</dt>
          <dd>{{ rerunResult.preview.样本原始值 ?? '未提供样本' }}（{{ rerunResult.preview.采集批次 ?? '无批次' }}）</dd>
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
            <span v-else class="muted-text">该列没有报表引用</span>
          </dd>
          <dt>版本失效原因</dt>
          <dd>
            <p v-if="rerunResult.stale_reason" class="stale-reason">{{ rerunResult.stale_reason }}</p>
            <span v-else class="muted-text">版本仍有效，可发布</span>
          </dd>
          <dt>当前绑定</dt>
          <dd>
            <template v-if="rerunResult.当前绑定">
              {{ rerunResult.当前绑定.规则名称 }} v{{ rerunResult.当前绑定.规则版本 }}
              （{{ rerunResult.当前绑定.status }}）
            </template>
            <span v-else class="muted-text">无</span>
          </dd>
        </dl>
        <div class="page-actions">
          <button class="btn" type="button" @click="rerunResult = null">关闭</button>
          <button class="btn primary" type="button" @click="rerunResult = null; reload()">
            确认并刷新清单
          </button>
        </div>
      </div>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 个受影响目标列</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { fetchImpactTargets, rerunTargetColumn } from '@/api/impact'
import type { ImpactTargetColumn, RerunResult } from '@/data/types'

const rows = ref<ImpactTargetColumn[]>([])
const total = ref(0)
const errorMessage = ref('')
const runningKey = ref('')
const rerunResult = ref<RerunResult | null>(null)
const filters = reactive<{ schema_name?: string; schema_version?: string; target_field?: string }>({})

function columnKey(column: ImpactTargetColumn): string {
  return `${column.Schema名称}/${column.Schema版本}/${column.目标字段}`
}

function referenceClass(state: string): string {
  if (state === '匹配') return '生效中'
  if (state === '版本已失效') return '已失效'
  if (state === '新版本待绑定') return '候选'
  return '已停用'
}

function resetFilters() {
  filters.schema_name = undefined
  filters.schema_version = undefined
  filters.target_field = undefined
  void reload()
}

async function reload() {
  errorMessage.value = ''
  try {
    const page = await fetchImpactTargets({ ...filters })
    rows.value = page.items
    total.value = page.total
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '影响目标列读取失败'
  }
}

async function onRerunColumn(column: ImpactTargetColumn) {
  errorMessage.value = ''
  runningKey.value = columnKey(column)
  try {
    rerunResult.value = await rerunTargetColumn({
      schema_name: column.Schema名称,
      schema_version: column.Schema版本,
      target_field: column.目标字段,
      ref_id: column.reference?.ref_id,
    })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '目标列重跑失败'
  } finally {
    runningKey.value = ''
  }
}

onMounted(reload)
</script>
