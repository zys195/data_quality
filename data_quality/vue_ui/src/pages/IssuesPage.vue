<template>
  <div class="split">
    <section class="band">
      <div class="section-title">
        <div>
          <h2>质量问题分析</h2>
          <p>展示本次评价发现的问题，并支持推进闭环状态。</p>
        </div>
        <button class="primary" @click="load">刷新问题</button>
      </div>
      <DimensionTabs v-model="activeDimension" />
      <div class="metrics">
        <MetricCard label="本次问题" :value="filtered.length" :foot="data.run_id || '-'" />
        <MetricCard label="当前范围" :value="data.issue_scope || 'current'" foot="默认本次执行" />
        <MetricCard label="血缘样例" :value="data.lineage_sample?.available ? '已匹配' : '待导入'" foot="真实血缘" />
        <MetricCard label="每页" value="10" foot="分页展示" />
      </div>
    </section>
    <section class="band">
      <div class="table-wrap">
        <table>
          <thead><tr><th>问题</th><th>规则</th><th>维度</th><th>资源</th><th>状态</th><th>影响行</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="issue in paged" :key="issue.issue_id">
              <td class="code">{{ issue.issue_id }}</td>
              <td class="code">{{ issue.rule_id }}</td>
              <td>{{ dimensionName(issue.dimension) }}</td>
              <td>{{ issue.resource }}</td>
              <td>{{ issueStatusName(issue.status) }}</td>
              <td>{{ issue.affected_rows }}</td>
              <td>
                <div class="toolbar">
                  <button class="secondary" @click="update(issue.issue_id, 'ticketed')">派单</button>
                  <button class="secondary" @click="update(issue.issue_id, 'closed')">关闭</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <Pager v-model:page="page" :total="filtered.length" :page-size="10" />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import MetricCard from '../components/MetricCard.vue';
import DimensionTabs from '../components/DimensionTabs.vue';
import Pager from '../components/Pager.vue';
import { dimensionName, issueStatusName } from '../labels';
import { getJson, postJson, toQuery } from '../api';

const data = reactive<any>({ issues: [] });
const activeDimension = ref('');
const page = ref(1);
const filtered = computed(() => activeDimension.value ? data.issues.filter((item:any) => item.dimension === activeDimension.value) : data.issues);
const paged = computed(() => filtered.value.slice((page.value - 1) * 10, page.value * 10));

async function load() {
  const res = await getJson<any>(`/api/workflow/issues${toQuery({ dimension: activeDimension.value })}`);
  Object.assign(data, res);
}

async function update(issueId: string, status: string) {
  await postJson('/api/workflow/issues/update', { issue_id: issueId, status, assignee: '数据责任人' });
  await load();
}

onMounted(load);
</script>
