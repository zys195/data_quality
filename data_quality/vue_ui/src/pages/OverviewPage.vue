<template>
  <div class="split">
    <section class="band">
      <div class="section-title">
        <div>
          <h2>流程总览</h2>
          <p>从数据导入到溯源报告，按顺序驱动整套质量评价流程。</p>
        </div>
        <div class="toolbar">
          <button class="primary" @click="refresh">刷新总览</button>
          <button class="secondary" @click="go('/import')">去导入数据</button>
          <button class="secondary" @click="go('/rules')">去规则库</button>
        </div>
      </div>

      <div class="metrics">
        <MetricCard label="规则总数" :value="summary.total_rules || 0" foot="JSON Spec 规则库" />
        <MetricCard label="当前数据" :value="current.imported ? '已导入' : '待导入'" foot="支持测试或真实数据" />
        <MetricCard label="当前规则" :value="current.rule_setting_count || 0" foot="已配置参数" />
        <MetricCard label="已确认推荐" :value="current.confirmed_recommendation_count || 0" foot="可直接入库" />
      </div>
    </section>

    <section class="grid-2">
      <div class="panel">
        <div class="section-title">
          <div>
            <h3>流程阶段</h3>
            <p>当前项目按这 9 个阶段执行。</p>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>阶段</th>
                <th>状态</th>
                <th>接口</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in overview.process || []" :key="item.id">
                <td>{{ item.name }}</td>
                <td>{{ item.status }}</td>
                <td class="code">{{ item.api }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="panel">
        <div class="section-title">
          <div>
            <h3>当前数据</h3>
            <p>展示当前导入数据和工作状态。</p>
          </div>
        </div>
        <div v-if="current.imported" class="stack">
          <div><span class="chip green">已导入</span></div>
          <div class="muted">数据源：{{ current.scope?.data_source || '-' }}</div>
          <div class="muted">数据表：{{ current.scope?.table_name || '-' }}</div>
          <div class="muted">业务域：{{ current.scope?.business_domain || '-' }}</div>
          <div class="muted">字段数：{{ (current.columns || []).length }}</div>
        </div>
        <div v-else class="empty">还没有导入数据。先去“数据导入”页面。</div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive } from 'vue';
import { useRouter } from 'vue-router';
import MetricCard from '../components/MetricCard.vue';
import { getJson } from '../api';

const router = useRouter();

const overview = reactive<any>({ process: [] });
const summary = reactive<any>({});
const current = reactive<any>({ imported: false, scope: null, columns: [] });

async function refresh() {
  const data = await getJson<any>('/api/workflow/overview');
  Object.assign(overview, data);
  Object.assign(summary, data.summary || {});
  Object.assign(current, data.current_dataset || {});
}

function go(path: string) {
  router.push(path);
}

onMounted(refresh);
</script>
