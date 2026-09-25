<template>
  <section class="page" data-module="gate">
    <header class="page-head">
      <div>
        <h2>闸口通行管理</h2>
        <p class="page-desc">维护通行记录，围绕通行编号、车牌号码、关联箱号、进出方向做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记通行记录</button>
        <button class="btn" type="button" @click="exportRows">导出闸口通行清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <section class="verify-board">
      <header class="verify-head">
        <strong>待核实台账（{{ pendingRows.length }}）</strong>
        <span class="verify-desc">
          车牌识别失败或关联箱号未匹配的通行记录在此单独归集，核实补录前不予放行；换班、重开页面后清单仍在。
        </span>
      </header>
      <table v-if="pendingRows.length" class="data-table">
        <thead>
          <tr>
            <th v-for="column in verifyColumns" :key="column">{{ column }}</th>
            <th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in pendingRows" :key="String(row.id)">
            <td v-for="column in verifyColumns" :key="column">
              <span v-if="column === '车牌号码' && row.recognition_failed" class="plate-failed">（识别失败）</span>
              <template v-else>{{ cell(row, column) }}</template>
            </td>
            <td class="row-actions">
              <button class="link" type="button" @click="openManualEntry(row)">人工补录</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="verify-empty">暂无待核实记录；出现车牌识别失败或箱号未匹配时会自动归集到这里。</p>
    </section>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <span v-if="column === '车牌号码' && row.recognition_failed" class="plate-failed">（识别失败）</span>
            <template v-else>{{ cell(row, column) }}</template>
          </td>
          <td class="row-actions">
            <button
              v-if="row.status === '待核实'"
              class="link"
              type="button"
              @click="openManualEntry(row)"
            >
              人工补录
            </button>
            <button
              v-for="action in row.status === '待核实' ? [] : actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无闸口通行数据，可先登记通行记录</td>
        </tr>
      </tbody>
    </table>

    <div v-if="createVisible" class="modal-mask" @click.self="createVisible = false">
      <div class="modal-panel">
        <h3>登记通行记录</h3>
        <p class="modal-desc">车牌无法辨认时勾选「车牌识别失败」，记录会列入待核实台账，不会丢失。</p>
        <label class="checkbox-item">
          <input v-model="createForm.recognition_failed" type="checkbox" />
          车牌识别失败（车牌无法辨认，先挂起待人工补录）
        </label>
        <label v-if="!createForm.recognition_failed" class="form-item">
          <span>车牌号码 *</span>
          <input v-model="createForm.车牌号码" placeholder="如 沪A12345" />
        </label>
        <label class="form-item">
          <span>关联箱号（查不到会先标为待核实）</span>
          <input v-model="createForm.关联箱号" placeholder="如 集装箱档案样例1" />
        </label>
        <label class="form-item">
          <span>进出方向</span>
          <select v-model="createForm.进出方向">
            <option value="进闸">进闸</option>
            <option value="出闸">出闸</option>
          </select>
        </label>
        <label class="form-item">
          <span>道口编号</span>
          <input v-model="createForm.道口编号" placeholder="如 D01" />
        </label>
        <label class="form-item">
          <span>值守人员</span>
          <input v-model="createForm.值守人员" />
        </label>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="createVisible = false">取消</button>
          <button class="btn primary" type="button" @click="submitCreate">确认登记</button>
        </div>
      </div>
    </div>

    <div v-if="manualVisible" class="modal-mask" @click.self="manualVisible = false">
      <div class="modal-panel">
        <h3>人工补录 · {{ manualTarget?.通行编号 ?? '' }}</h3>
        <p class="modal-desc">{{ manualTarget?.核实说明 || '补全车牌与箱号后，记录转回正常放行流程。' }}</p>
        <label class="form-item">
          <span>车牌号码 *</span>
          <input v-model="manualForm.车牌号码" placeholder="补录识别失败的车牌" />
        </label>
        <label class="form-item">
          <span>关联箱号（留空则沿用原值）</span>
          <input v-model="manualForm.关联箱号" placeholder="如 集装箱档案样例1" />
        </label>
        <label class="form-item">
          <span>值守人员</span>
          <input v-model="manualForm.值守人员" />
        </label>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="manualVisible = false">取消</button>
          <button class="btn primary" type="button" @click="submitManualEntry">完成补录</button>
        </div>
      </div>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条闸口通行记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/gate'
const columns = ["通行编号", "车牌号码", "关联箱号", "进出方向", "通行时间", "道口编号", "值守人员", "通行状态", "核实说明"]
const verifyColumns = ["通行编号", "车牌号码", "关联箱号", "进出方向", "通行时间", "核实说明"]
const actions = ["确认放行", "拦截车辆", "复核通行"]
const filterFields = ["通行编号", "车牌号码", "关联箱号"]
const FILTER_PARAMS: Record<string, string> = { 通行编号: 'keyword', 车牌号码: 'plate', 关联箱号: 'container_no' }

const session = useSessionStore()

const rows = ref<Row[]>([])
const pendingRows = ref<Row[]>([])
const total = ref(0)
const stats = ref([
  { label: '进闸车次', value: 0 },
  { label: '出闸车次', value: 0 },
  { label: '拦截车次', value: 0 },
  { label: '待核实', value: 0 },
])
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({})

const createVisible = ref(false)
const createForm = ref({
  车牌号码: '',
  关联箱号: '',
  进出方向: '进闸',
  道口编号: '',
  值守人员: session.operator,
  recognition_failed: false,
})

const manualVisible = ref(false)
const manualTarget = ref<Row | null>(null)
const manualForm = ref({ 车牌号码: '', 关联箱号: '', 值守人员: session.operator })

function cell(row: Row, column: string) {
  if (column === '通行状态') return row.status ?? '—'
  const value = row[column]
  return value === null || value === undefined || value === '' ? '—' : value
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = ''
  createVisible.value = true
}

function openManualEntry(row: Row) {
  errorMessage.value = ''
  manualTarget.value = row
  manualForm.value = {
    车牌号码: row.recognition_failed ? '' : String(row.车牌号码 ?? ''),
    关联箱号: '',
    值守人员: session.operator,
  }
  manualVisible.value = true
}

async function readPayload(response: Response): Promise<Record<string, unknown>> {
  const payload = (await response.json()) as Record<string, unknown>
  if (!response.ok || payload.ok === false) {
    throw new Error(String(payload.message ?? payload.detail ?? '闸口通行操作失败'))
  }
  return payload
}

async function submitCreate() {
  errorMessage.value = ''
  noticeMessage.value = ''
  if (!createForm.value.recognition_failed && !createForm.value.车牌号码.trim()) {
    errorMessage.value = '请填写车牌号码；若车牌无法辨认，请勾选「车牌识别失败」'
    return
  }
  try {
    const response = await request(`${ENDPOINT}/register`, {
      method: 'POST',
      body: JSON.stringify({ values: createForm.value }),
    })
    const payload = await readPayload(response)
    noticeMessage.value = String(payload.message ?? '通行记录已登记')
    createVisible.value = false
    createForm.value = {
      车牌号码: '',
      关联箱号: '',
      进出方向: '进闸',
      道口编号: '',
      值守人员: session.operator,
      recognition_failed: false,
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '通行记录登记失败'
  }
}

async function submitManualEntry() {
  errorMessage.value = ''
  noticeMessage.value = ''
  if (!manualTarget.value) return
  if (!manualForm.value.车牌号码.trim()) {
    errorMessage.value = '人工补录必须填写车牌号码'
    return
  }
  try {
    const response = await request(`${ENDPOINT}/${manualTarget.value.id}/manual-entry`, {
      method: 'POST',
      body: JSON.stringify({ values: manualForm.value }),
    })
    const payload = await readPayload(response)
    noticeMessage.value = String(payload.message ?? '人工补录完成')
    manualVisible.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '人工补录失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await readPayload(response)
    noticeMessage.value = String(payload.message ?? `通行记录已${action}`)
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '闸口通行操作失败'
  }
}

async function reloadPending() {
  const response = await request(`${ENDPOINT}/pending-verification`)
  if (!response.ok) return
  const payload = await response.json()
  pendingRows.value = payload.items ?? []
  stats.value[3].value = pendingRows.value.length
}

async function reloadStats() {
  const response = await request(`${ENDPOINT}?size=200`)
  if (!response.ok) return
  const payload = await response.json()
  const items: Row[] = payload.items ?? []
  stats.value[0].value = items.filter((row) => String(row.进出方向 ?? '').includes('进')).length
  stats.value[1].value = items.filter((row) => String(row.进出方向 ?? '').includes('出')).length
  stats.value[2].value = items.filter((row) => row.status === '已拦截').length
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  for (const field of filterFields) {
    const value = (filters.value[field] ?? '').trim()
    if (value) params.set(FILTER_PARAMS[field], value)
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
  await Promise.all([reloadPending(), reloadStats()])
}

onMounted(reload)
</script>

<style scoped>
.verify-board {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
}
.verify-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.verify-desc { color: var(--muted); font-size: 12px; }
.verify-empty { color: var(--muted); font-size: 13px; margin: 4px 0; }
.plate-failed { color: #b42318; font-weight: 600; }
.notice-text { color: #067647; }
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
}
.modal-panel {
  background: #fff;
  border-radius: 8px;
  padding: 16px 18px;
  width: 420px;
  max-width: calc(100vw - 40px);
}
.modal-panel h3 { margin: 0 0 8px; font-size: 15px; }
.modal-desc { color: var(--muted); font-size: 12px; margin: 0 0 10px; }
.form-item { display: block; margin-bottom: 10px; }
.form-item span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.form-item input,
.form-item select {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
}
.checkbox-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  margin-bottom: 10px;
}
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
</style>
