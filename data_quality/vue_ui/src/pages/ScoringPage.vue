<template>
  <div class="split">
    <section class="band">
      <div class="section-title">
        <div>
          <h2>计分规则</h2>
          <p>根据六维权重生成总分，并可归档本次计分口径。</p>
        </div>
        <div class="toolbar">
          <button class="primary" @click="archive">归档计分规则</button>
          <button class="secondary" @click="load">刷新</button>
        </div>
      </div>
      <div class="metrics">
        <MetricCard label="总体得分" :value="dashboard.overall_score ?? '-'" :foot="dashboard.quality_level || '-'" />
        <MetricCard label="问题数" :value="dashboard.impact_scope?.issue_count || 0" foot="参与扣分" />
        <MetricCard label="归档状态" :value="archiveData.archive ? '已归档' : '待归档'" foot="计分口径" />
        <MetricCard label="维度数量" :value="dashboard.dimension_scores?.length || 0" foot="六维体系" />
      </div>
    </section>
    <section class="grid-2">
      <div class="panel">
        <div class="section-title"><h3>维度得分</h3></div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>维度</th><th>得分</th><th>通过规则</th><th>总规则</th></tr></thead>
            <tbody>
              <tr v-for="item in dashboard.dimension_scores || []" :key="item.dimension">
                <td>{{ dimensionName(item.dimension) }}</td>
                <td>{{ item.score }}</td>
                <td>{{ item.passed_rules }}</td>
                <td>{{ item.total_rules }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div class="panel">
        <div class="section-title"><h3>归档结果</h3></div>
        <pre class="code">{{ JSON.stringify(archiveData.archive || {}, null, 2) }}</pre>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive } from 'vue';
import MetricCard from '../components/MetricCard.vue';
import { dimensionName } from '../labels';
import { getJson, postJson } from '../api';

const dashboard = reactive<any>({});
const archiveData = reactive<any>({});

async function load() {
  const data = await getJson<any>('/api/workflow/dashboard');
  Object.assign(dashboard, data);
}

async function archive() {
  const data = await postJson<any>('/api/workflow/archive', { archived_by: 'operator', description: 'Vue 页面归档计分口径' });
  Object.assign(archiveData, data);
  Object.assign(dashboard, data.dashboard || {});
}

onMounted(load);
</script>
