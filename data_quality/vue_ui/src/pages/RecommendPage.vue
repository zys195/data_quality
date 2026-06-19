<template>
  <div class="split">
    <section class="band">
      <div class="section-title">
        <div>
          <h2>质量规则智能推荐</h2>
          <p>基于字段名、类型、样例值、字典、业务域和血缘提示自动匹配规则。</p>
        </div>
        <div class="toolbar">
          <button class="primary" @click="generate">生成推荐</button>
          <button class="secondary" @click="confirm">确认推荐入库</button>
          <button class="secondary" @click="refresh">刷新</button>
        </div>
      </div>

      <div class="metrics">
        <MetricCard label="当前表" :value="data.table_name || '-'" :foot="data.table || '待导入'" />
        <MetricCard label="推荐数量" :value="filtered.length" :foot="dimensionName(activeDimension) || '全部维度'" />
        <MetricCard label="可执行入库" :value="data.executable_count || 0" foot="可生成参数配置" />
        <MetricCard label="已确认" :value="data.confirmed_count || 0" foot="进入规则参数页" />
      </div>
      <DimensionTabs v-model="activeDimension" />
      <div class="notice">{{ data.message || '导入数据后可以生成推荐。' }}</div>
    </section>

    <section class="band">
      <div class="section-title">
        <div>
          <h3>推荐结果</h3>
          <p>每页展示 10 条，确认后进入参数配置。</p>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>推荐规则</th>
              <th>字段</th>
              <th>维度</th>
              <th>置信度</th>
              <th>推荐理由</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in paged" :key="item.recommendation_id || `${item.rule_id}-${item.column_name}`">
              <td>
                <div class="code">{{ item.rule_id }}</div>
                <div>{{ item.display_name }}</div>
              </td>
              <td>{{ item.column_name || '-' }}</td>
              <td>{{ dimensionName(item.dimension) }}</td>
              <td><span class="chip green">{{ Math.round((item.confidence || 0) * 100) }}%</span></td>
              <td>{{ item.reason || '-' }}</td>
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
import { dimensionName } from '../labels';
import { getJson, postJson } from '../api';

const data = reactive<any>({ recommendations: [] });
const activeDimension = ref('');
const page = ref(1);

const filtered = computed(() => {
  const rows = data.recommendations || [];
  return activeDimension.value ? rows.filter((item: any) => item.dimension === activeDimension.value) : rows;
});
const paged = computed(() => filtered.value.slice((page.value - 1) * 10, page.value * 10));

async function refresh() {
  const res = await getJson<any>('/api/recommendations');
  Object.assign(data, res);
}

async function generate() {
  page.value = 1;
  const res = await getJson<any>('/api/recommendations?refresh=true');
  Object.assign(data, res);
}

async function confirm() {
  await postJson('/api/recommendations/confirm', { confirmed_by: 'operator' });
  await refresh();
}

onMounted(refresh);
</script>
