<template>
  <section class="page" data-module="gate">
    <header class="page-head">
      <div>
        <h2>闸口通行管理</h2>
        <p class="page-desc">
          维护通行记录，围绕通行编号、车牌号码、关联箱号、进出方向做登记、筛选与状态流转。
          车牌识别失败或关联箱号查不到时，记录会进入待核实台账，人工补录核实后回到正常放行流程。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="exportRows">导出闸口通行清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <section class="panel">
      <h3>闸口识别登记</h3>
      <form class="filter-bar" @submit.prevent="submitRecognition">
        <label class="filter-item">
          <span>车牌号码</span>
          <input v-model="recognitionForm.车牌号码" placeholder="识别失败可留空" />
        </label>
        <label class="filter-item">
          <span>关联箱号</span>
          <input v-model="recognitionForm.关联箱号" placeholder="集装箱档案中的箱号" />
        </label>
        <label class="filter-item">
          <span>进出方向</span>
          <select v-model="recognitionForm.进出方向">
            <option value="进闸">进闸</option>
            <option value="出闸">出闸</option>
          </select>
        </label>
        <label class="filter-item">
          <span>道口编号</span>
          <input v-model="recognitionForm.道口编号" placeholder="如 GATE-01" />
        </label>
        <label class="filter-item">
          <span>值守人员</span>
          <input v-model="recognitionForm.值守人员" placeholder="当班人员" />
        </label>
        <button class="btn primary" type="submit">识别登记</button>
      </form>
      <p v-if="!recognitionResult" class="notice muted">
        暂无车辆过闸识别请求。识别结果会显示在这里：识别成功直接生成待放行记录；
        识别失败会写明原因并生成待核实记录，不会留下空白。
      </p>
      <div v-else class="notice" :class="recognitionResult.recognized ? 'success' : 'warning'">
        <p>{{ recognitionResult.message }}</p>
        <ul v-if="recognitionResult.reasons.length">
          <li v-for="reason in recognitionResult.reasons" :key="reason">{{ reason }}</li>
        </ul>
        <button
          v-if="!recognitionResult.recognized && recognitionResult.entry"
          class="btn"
          type="button"
          @click="startSupplement(recognitionResult.entry)"
        >
          立即人工补录
        </button>
      </div>
    </section>

    <section class="panel">
      <h3>待核实台账（{{ reviewRows.length }}）</h3>
      <p class="page-desc">
        识别失败或关联箱号查不到的通行记录单独归集在这里，换班、重新打开页面后依然保留；
        补录核实通过后自动回到正常放行流程。
      </p>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in reviewColumns" :key="column">{{ column }}</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="row in reviewRows" :key="String(row.id)">
            <tr>
              <td>{{ row['通行编号'] ?? '—' }}</td>
              <td>{{ row['车牌号码'] || '未识别' }}</td>
              <td>{{ row['关联箱号'] || '未识别' }}</td>
              <td>{{ row['识别备注'] || '—' }}</td>
              <td>{{ row['通行时间'] ?? '—' }}</td>
              <td>{{ row['补录次数'] ?? 0 }}</td>
              <td class="row-actions">
                <button class="link" type="button" @click="startSupplement(row)">人工补录</button>
              </td>
            </tr>
            <tr v-if="supplementTarget && supplementTarget.id === row.id">
              <td :colspan="reviewColumns.length + 1">
                <form class="filter-bar supplement-form" @submit.prevent="submitSupplement">
                  <label class="filter-item">
                    <span>车牌号码</span>
                    <input v-model="supplementForm.车牌号码" placeholder="补录车牌号码" />
                  </label>
                  <label class="filter-item">
                    <span>关联箱号</span>
                    <input v-model="supplementForm.关联箱号" placeholder="补录关联箱号" />
                  </label>
                  <label class="filter-item">
                    <span>进出方向</span>
                    <select v-model="supplementForm.进出方向">
                      <option value="">未填写</option>
                      <option value="进闸">进闸</option>
                      <option value="出闸">出闸</option>
                    </select>
                  </label>
                  <label class="filter-item">
                    <span>补录人</span>
                    <input v-model="supplementForm.值守人员" placeholder="补录人员" />
                  </label>
                  <button class="btn primary" type="submit">提交补录</button>
                  <button class="btn ghost" type="button" @click="cancelSupplement">取消</button>
                </form>
              </td>
            </tr>
          </template>
          <tr v-if="!reviewRows.length">
            <td :colspan="reviewColumns.length + 1" class="empty-state">暂无待核实记录</td>
          </tr>
        </tbody>
      </table>
      <p v-if="supplementMessage" class="notice" :class="supplementOk ? 'success' : 'warning'">
        {{ supplementMessage }}
      </p>
    </section>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>关键字</span>
        <input v-model="keyword" placeholder="按通行编号或车牌检索" />
      </label>
      <label class="filter-item">
        <span>状态</span>
        <select v-model="statusFilter">
          <option value="">全部</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td>
            <span class="status-tag" :class="{ review: row.status === '待核实' }">{{ row.status ?? '—' }}</span>
          </td>
          <td class="row-actions">
            <template v-if="row.status !== '待核实'">
              <button
                v-for="action in actions"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
            <button v-else class="link" type="button" @click="startSupplement(row)">待核实，去补录</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无闸口通行数据，可先在上方做识别登记</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条闸口通行记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

interface RecognitionResult {
  recognized: boolean
  message: string
  reasons: string[]
  entry: Row | null
}

const ENDPOINT = '/api/gate'
const columns = ["通行编号", "车牌号码", "关联箱号", "进出方向", "通行时间", "道口编号", "值守人员", "通行状态"]
const reviewColumns = ["通行编号", "车牌号码", "关联箱号", "识别备注", "通行时间", "补录次数"]
const actions = ["确认放行", "拦截车辆", "复核通行"]
const statuses = ["待放行", "已放行", "已拦截", "已复核", "待核实"]

const rows = ref<Row[]>([])
const reviewRows = ref<Row[]>([])
const total = ref(0)
const stats = ref([
  { label: '通行记录总数', value: 0 },
  { label: '待核实记录', value: 0 },
  { label: '已放行记录', value: 0 },
])
const errorMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')

const recognitionForm = ref({ 车牌号码: '', 关联箱号: '', 进出方向: '进闸', 道口编号: '', 值守人员: '' })
const recognitionResult = ref<RecognitionResult | null>(null)

const supplementTarget = ref<Row | null>(null)
const supplementForm = ref({ 车牌号码: '', 关联箱号: '', 进出方向: '', 值守人员: '' })
const supplementMessage = ref('')
const supplementOk = ref(true)

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function submitRecognition() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/recognition`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...recognitionForm.value } }),
    })
    if (!response.ok) {
      throw new Error('识别登记未生效，请稍后重试')
    }
    const payload = await response.json()
    recognitionResult.value = {
      recognized: Boolean(payload.recognized),
      message: payload.message ?? '',
      reasons: payload.reasons ?? [],
      entry: payload.entry ?? null,
    }
    await refreshAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '识别登记失败'
  }
}

function startSupplement(row: Row) {
  supplementTarget.value = row
  supplementForm.value = {
    车牌号码: String(row['车牌号码'] ?? ''),
    关联箱号: String(row['关联箱号'] ?? ''),
    进出方向: String(row['进出方向'] ?? ''),
    值守人员: '',
  }
  supplementMessage.value = ''
}

function cancelSupplement() {
  supplementTarget.value = null
  supplementMessage.value = ''
}

async function submitSupplement() {
  if (!supplementTarget.value) {
    return
  }
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${supplementTarget.value.id}/supplement`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...supplementForm.value } }),
    })
    if (!response.ok) {
      throw new Error('人工补录未生效，请稍后重试')
    }
    const payload = await response.json()
    supplementOk.value = Boolean(payload.recognized)
    supplementMessage.value = payload.message ?? ''
    if (payload.recognized) {
      supplementTarget.value = null
    }
    await refreshAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '人工补录失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '闸口通行动作未生效，请稍后重试')
    }
    await refreshAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '闸口通行操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  if (keyword.value) {
    params.set('keyword', keyword.value)
  }
  if (statusFilter.value) {
    params.set('status', statusFilter.value)
  }
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error('通行记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '闸口通行列表读取失败'
  }
}

async function loadReview() {
  try {
    const response = await request(`${ENDPOINT}/pending-review`)
    if (!response.ok) {
      throw new Error('待核实台账读取失败')
    }
    const payload = await response.json()
    reviewRows.value = payload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '待核实台账读取失败'
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) {
      throw new Error('闸口统计读取失败')
    }
    const payload = await response.json()
    stats.value = [
      { label: '通行记录总数', value: payload.total ?? 0 },
      { label: '待核实记录', value: payload.pending_review ?? 0 },
      { label: '已放行记录', value: payload.by_status?.['已放行'] ?? 0 },
    ]
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '闸口统计读取失败'
  }
}

async function refreshAll() {
  await Promise.all([reload(), loadReview(), loadStats()])
}

onMounted(refreshAll)
</script>
