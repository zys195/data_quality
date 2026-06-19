<template>
  <div class="split">
    <section class="band">
      <div class="section-title">
        <div>
          <h2>质量问题溯源</h2>
          <p>该部分需要后续导入真实血缘数据后才能给出最终结论。</p>
        </div>
        <div class="toolbar">
          <button class="primary" @click="load">刷新</button>
          <button class="secondary" @click="importReal">导入真实血缘</button>
        </div>
      </div>
      <div class="metrics">
        <MetricCard label="问题数量" :value="data.total || 0" foot="当前问题范围" />
        <MetricCard label="血缘记录" :value="data.lineage_record_count || 0" foot="真实导入后生效" />
        <MetricCard label="选中问题" :value="data.selected_issue_id || '-'" foot="默认当前问题" />
        <MetricCard label="是否可用" :value="data.lineage?.available ? '可用' : '待导入'" foot="真实血缘优先" />
      </div>
    </section>
    <section class="grid-2">
      <div class="panel">
        <div class="section-title"><h3>问题列表</h3></div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>问题</th><th>规则</th><th>维度</th><th>资源</th></tr></thead>
            <tbody>
              <tr v-for="issue in paged" :key="issue.issue_id">
                <td class="code">{{ issue.issue_id }}</td>
                <td class="code">{{ issue.rule_id }}</td>
                <td>{{ dimensionName(issue.dimension) }}</td>
                <td>{{ issue.resource }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <Pager v-model:page="page" :total="data.issues?.length || 0" :page-size="10" />
      </div>
      <div class="panel">
        <div class="section-title"><h3>溯源结果</h3></div>
        <div v-if="data.lineage?.available" class="stack">
          <div class="muted">上游：{{ (data.lineage.upstream_trace || []).join(' / ') || '-' }}</div>
          <div class="muted">下游：{{ (data.lineage.downstream_impacts || []).join(' / ') || '-' }}</div>
          <div class="muted">建议：{{ (data.lineage.recommendations || []).join(' / ') || '-' }}</div>
        </div>
        <div v-else class="empty">
          {{ data.lineage?.message || '请导入真实血缘数据后查看最终溯源结果。' }}
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import MetricCard from '../components/MetricCard.vue';
import Pager from '../components/Pager.vue';
import { dimensionName } from '../labels';
import { getJson, postJson } from '../api';

const data = reactive<any>({ issues: [], lineage: {} });
const page = ref(1);
const paged = computed(() => (data.issues || []).slice((page.value - 1) * 10, page.value * 10));

async function load() {
  const res = await getJson<any>('/api/workflow/lineage');
  Object.assign(data, res);
}

async function importReal() {
  await postJson('/api/lineage/import', {
    lineage_records: [
      {
        target_table: 'customer_order',
        target_column: 'mobile_phone',
        source_system: 'crm',
        source_table: 'crm_customer',
        source_column: 'phone',
        etl_task: 'sync_customer',
        downstream_objects: ['dashboard.customer', 'report.customer_quality'],
        owner: '数据责任人',
      },
    ],
  });
  await load();
}

onMounted(load);
</script>
