<template>
  <div class="grid-2">
    <section class="band">
      <div class="section-title">
        <div>
          <h2>数据导入</h2>
          <p>可以先导入测试数据，后续再切换为真实来源。</p>
        </div>
        <div class="toolbar">
          <button class="secondary" @click="fillExample">填入示例结构</button>
          <button class="primary" @click="importRows">导入 JSON</button>
          <button class="secondary" @click="importCsv">导入 CSV</button>
        </div>
      </div>

      <div class="form">
        <div class="form-grid">
          <div class="field">
            <label>数据源</label>
            <input v-model="form.data_source" placeholder="mysql / oracle / csv" />
          </div>
          <div class="field">
            <label>数据库</label>
            <input v-model="form.database" placeholder="dw" />
          </div>
          <div class="field">
            <label>表名</label>
            <input v-model="form.table_name" placeholder="customer_order" />
          </div>
        </div>
        <div class="form-grid">
          <div class="field">
            <label>业务域</label>
            <input v-model="form.business_domain" placeholder="客户 / 订单" />
          </div>
          <div class="field">
            <label>主题域</label>
            <input v-model="form.subject_domain" placeholder="主数据" />
          </div>
          <div class="field">
            <label>批次号</label>
            <input v-model="form.batch_id" placeholder="batch_20260617" />
          </div>
        </div>
        <div class="field">
          <label>JSON 行数据</label>
          <textarea v-model="rowsText" placeholder='[{"id":"1","mobile_phone":"13800138000000000"}]'></textarea>
        </div>
        <div class="field">
          <label>CSV 文本</label>
          <textarea v-model="csvText" placeholder="id,mobile_phone"></textarea>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="section-title">
        <div>
          <h3>当前结果</h3>
          <p>导入后会自动生成字段画像和预览。</p>
        </div>
      </div>
      <div class="metrics">
        <MetricCard label="导入状态" :value="current.imported ? '已导入' : '未导入'" foot="工作区状态" />
        <MetricCard label="行数" :value="current.row_count || 0" foot="当前预览数据" />
        <MetricCard label="字段数" :value="(current.columns || []).length" foot="自动识别字段" />
        <MetricCard label="规则数" :value="current.rule_setting_count || 0" foot="参数页会使用" />
      </div>

      <div class="stack">
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>字段</th>
                <th>类型</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="col in current.columns || []" :key="col.name">
                <td>{{ col.name }}</td>
                <td>{{ col.data_type || '-' }}</td>
                <td>{{ col.description || '-' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>预览数据</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in current.preview_rows || []" :key="index">
                <td class="code">{{ JSON.stringify(row) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import MetricCard from '../components/MetricCard.vue';
import { getJson, postJson } from '../api';

const form = reactive({
  data_source: 'mysql',
  database: 'dw',
  table_name: 'customer_order',
  business_domain: '客户订单',
  subject_domain: '交易',
  batch_id: 'batch_20260617',
});

const rowsText = ref('');
const csvText = ref('');
const current = reactive<any>({ imported: false, columns: [], preview_rows: [] });

function fillExample() {
  rowsText.value = JSON.stringify([
    { id: '1', mobile_phone: '13800138000000000', amount: '100.00', email: 'ok@example.com' },
    { id: '2', mobile_phone: '12345', amount: '-1', email: 'bad-email' },
    { id: '3', mobile_phone: '13900139000000000', amount: '20.50', email: 'user@example.com' },
  ], null, 2);
}

async function refresh() {
  const data = await getJson<any>('/api/data/current');
  Object.assign(current, data);
}

async function importRows() {
  const payload = {
    ...form,
    rows: JSON.parse(rowsText.value || '[]'),
  };
  await postJson('/api/data/import', payload);
  await refresh();
}

async function importCsv() {
  const payload = { ...form, csv: csvText.value };
  await postJson('/api/data/import', payload);
  await refresh();
}

onMounted(refresh);
</script>
