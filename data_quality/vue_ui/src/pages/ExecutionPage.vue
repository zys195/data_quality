<template>
  <div class="split">
    <section class="band">
      <div class="section-title">
        <div>
          <h2>质量评价实施</h2>
          <p>确认检查范围、执行方式和执行人后运行评价。</p>
        </div>
        <div class="toolbar">
          <button class="primary" @click="execute">开始执行</button>
          <button class="secondary" @click="load">刷新结果</button>
        </div>
      </div>
      <div class="metrics">
        <MetricCard label="数据表" :value="scope.table_name || '-'" :foot="scope.table_fqn || '-'" />
        <MetricCard label="字段数" :value="scope.fields?.length || 0" foot="检查对象" />
        <MetricCard label="调度方式" :value="options.schedule" foot="默认手动执行" />
        <MetricCard label="执行人" :value="options.created_by" foot="用于记录责任" />
      </div>
      <div class="form-grid">
        <div class="field">
          <label>什么时候执行</label>
          <select v-model="options.schedule"><option value="manual">手动执行</option><option value="dependency">依赖触发</option><option value="cron">定时执行</option></select>
        </div>
        <div class="field">
          <label>检查哪些数据</label>
          <select v-model="options.scan_mode"><option value="full">全部导入数据</option><option value="incremental">增量数据</option></select>
        </div>
        <div class="field">
          <label>执行人</label>
          <input v-model="options.created_by" />
        </div>
      </div>
    </section>

    <section class="band" v-if="run">
      <div class="section-title">
        <div>
          <h3>本次执行结果</h3>
          <p>和问题分析页保持同一批次口径。</p>
        </div>
      </div>
      <div class="metrics">
        <MetricCard label="执行状态" :value="runStatusName(run.status)" :foot="run.blocked ? '存在强校验问题' : '可继续查看看板'" />
        <MetricCard label="检查规则" :value="run.total_rules" foot="本次启用规则" />
        <MetricCard label="发现问题" :value="run.issue_ids?.length || 0" foot="本次问题数" />
        <MetricCard label="异常数据" :value="run.exception_rows" foot="需复核行数" />
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>规则</th><th>维度</th><th>结果</th><th>异常行</th><th>通过率</th></tr></thead>
          <tbody>
            <tr v-for="item in run.rule_results || []" :key="item.setting_id">
              <td class="code">{{ item.rule_id }}</td>
              <td>{{ dimensionName(item.dimension) }}</td>
              <td>{{ item.failed_rows > 0 ? '发现问题' : '通过' }}</td>
              <td>{{ item.failed_rows }}</td>
              <td>{{ Math.round((item.pass_rate || 0) * 1000) / 10 }}%</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
    <section v-else class="band">
      <div class="empty">还没有执行结果。点击“开始执行”。</div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import MetricCard from '../components/MetricCard.vue';
import { dimensionName, runStatusName } from '../labels';
import { getJson, postJson } from '../api';

const scope = reactive<any>({ fields: [] });
const options = reactive({ schedule: 'manual', scan_mode: 'full', created_by: 'operator', parallelism: 2 });
const run = ref<any>(null);

async function load() {
  const [current, data] = await Promise.all([
    getJson<any>('/api/data/current'),
    getJson<any>('/api/workflow/execute'),
  ]);
  Object.assign(scope, current.scope || {});
  run.value = data.run || null;
}

async function execute() {
  const data = await postJson<any>('/api/workflow/execute', options);
  run.value = data.run;
  const current = await getJson<any>('/api/data/current');
  Object.assign(scope, current.scope || {});
}

onMounted(async () => {
  const current = await getJson<any>('/api/data/current');
  Object.assign(scope, current.scope || {});
});
</script>
