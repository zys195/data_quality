<template>
  <div class="split">
    <section class="band">
      <div class="section-title">
        <div>
          <h2>六维评价看板</h2>
          <p>按规范性、完整性、准确性、一致性、时效性、可访问性展示结果。</p>
        </div>
        <button class="primary" @click="load">刷新看板</button>
      </div>
      <div class="metrics">
        <MetricCard label="总体得分" :value="dashboard.overall_score ?? '-'" :foot="dashboard.quality_level || '-'" />
        <MetricCard label="问题数量" :value="dashboard.impact_scope?.issue_count || 0" foot="本次执行" />
        <MetricCard label="影响行数" :value="dashboard.impact_scope?.affected_rows || 0" foot="异常数据" />
        <MetricCard label="执行次数" :value="dashboard.execution_trend?.length || 0" foot="历史批次" />
      </div>
    </section>
    <section class="band">
      <div class="grid-3">
        <div v-for="item in dashboard.dimension_scores || []" :key="item.dimension" class="panel">
          <div class="section-title">
            <h3>{{ dimensionName(item.dimension) }}</h3>
            <span class="chip">{{ item.score }}</span>
          </div>
          <div class="muted">通过规则：{{ item.passed_rules || 0 }} / {{ item.total_rules || 0 }}</div>
          <div class="muted">异常行：{{ item.failed_rows || 0 }}</div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive } from 'vue';
import MetricCard from '../components/MetricCard.vue';
import { dimensionName } from '../labels';
import { getJson } from '../api';

const dashboard = reactive<any>({});

async function load() {
  const data = await getJson<any>('/api/workflow/dashboard');
  Object.assign(dashboard, data);
}

onMounted(load);
</script>
