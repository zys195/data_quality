<template>
  <div class="split">
    <section class="band">
      <div class="section-title">
        <div>
          <h2>规则参数设定</h2>
          <p>业务人员只调整能看懂的要求，技术脚本默认隐藏。</p>
        </div>
        <div class="toolbar">
          <button class="primary" @click="generate">生成参数配置</button>
          <button class="secondary" @click="saveAll">保存全部配置</button>
          <button class="secondary" @click="trial">试跑验证</button>
        </div>
      </div>
      <DimensionTabs v-model="activeDimension" />
      <div class="metrics">
        <MetricCard label="配置数量" :value="filtered.length" foot="当前维度" />
        <MetricCard label="启用规则" :value="settings.filter((item:any) => item.enabled !== false).length" foot="参与评价" />
        <MetricCard label="试跑问题" :value="trialResults.reduce((sum:number, item:any) => sum + (item.failure_count || 0), 0)" foot="样例异常" />
        <MetricCard label="字段数" :value="scope.fields?.length || 0" :foot="scope.table_name || '-'" />
      </div>
    </section>

    <section class="grid-2">
      <div class="band">
        <div class="section-title">
          <div>
            <h3>参数配置列表</h3>
            <p>每页展示 10 条，点击编辑后在右侧调整。</p>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>规则</th>
                <th>字段</th>
                <th>维度</th>
                <th>校验级别</th>
                <th>通过率</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in paged" :key="item.setting_id">
                <td class="code">{{ item.rule_id }}</td>
                <td>{{ item.target_column || '-' }}</td>
                <td>{{ dimensionName(item.dimension) }}</td>
                <td>{{ levelName(item.validation_level) }}</td>
                <td>{{ Math.round((item.threshold?.pass_rate ?? 1) * 1000) / 10 }}%</td>
                <td><button class="secondary" @click="edit(item)">编辑</button></td>
              </tr>
            </tbody>
          </table>
        </div>
        <Pager v-model:page="page" :total="filtered.length" :page-size="10" />
      </div>

      <div class="panel">
        <div class="section-title">
          <div>
            <h3>人工调整区</h3>
            <p>把技术参数翻译成业务可理解的配置。</p>
          </div>
        </div>
        <div v-if="!selected" class="empty">点击左侧“编辑”后调整参数。</div>
        <div v-else class="form">
          <div class="form-grid">
            <div class="field">
              <label>是否启用</label>
              <select v-model="editor.enabled"><option :value="true">启用</option><option :value="false">停用</option></select>
            </div>
            <div class="field">
              <label>绑定字段</label>
              <select v-model="editor.target_column">
                <option v-for="field in scope.fields || []" :key="field" :value="field">{{ field }}</option>
              </select>
            </div>
            <div class="field">
              <label>校验级别</label>
              <select v-model="editor.validation_level"><option>P0_BLOCKING</option><option>P1_WARNING</option><option>P2_MONITORING</option></select>
            </div>
          </div>
          <div class="form-grid">
            <div class="field">
              <label>必须填写</label>
              <select v-model="editor.required"><option :value="true">必须填写</option><option :value="false">允许为空</option></select>
            </div>
            <div class="field">
              <label>手机号数字个数</label>
              <input v-model.number="editor.phone_length" type="number" min="1" />
            </div>
            <div class="field">
              <label>要求通过率（%）</label>
              <input v-model.number="editor.pass_percent" type="number" min="0" max="100" step="0.1" />
            </div>
          </div>
          <div class="field">
            <label>责任角色</label>
            <input v-model="editor.responsible_role" />
          </div>
          <div class="field">
            <label>业务备注</label>
            <textarea v-model="editor.condition"></textarea>
          </div>
          <details class="panel" style="padding:12px">
            <summary>技术参数与执行脚本（实施人员查看）</summary>
            <pre class="code">{{ selectedPreview }}</pre>
          </details>
          <div class="toolbar">
            <button class="primary" @click="saveOne">保存当前配置</button>
          </div>
        </div>
      </div>
    </section>

    <section class="band" v-if="trialResults.length">
      <div class="section-title">
        <div>
          <h3>试跑结果</h3>
          <p>仅基于当前导入样例数据。</p>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>规则</th><th>维度</th><th>结果</th><th>异常行</th><th>通过率</th></tr></thead>
          <tbody>
            <tr v-for="item in trialResults" :key="item.setting_id">
              <td class="code">{{ item.rule_id }}</td>
              <td>{{ dimensionName(item.dimension) }}</td>
              <td>{{ item.passed ? '通过' : '发现问题' }}</td>
              <td>{{ item.failure_count }}</td>
              <td>{{ Math.round((item.pass_rate || 0) * 1000) / 10 }}%</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import MetricCard from '../components/MetricCard.vue';
import DimensionTabs from '../components/DimensionTabs.vue';
import Pager from '../components/Pager.vue';
import { dimensionName, levelName } from '../labels';
import { getJson, postJson } from '../api';

const scope = reactive<any>({ fields: [] });
const settings = ref<any[]>([]);
const previews = ref<any[]>([]);
const trialResults = ref<any[]>([]);
const activeDimension = ref('');
const page = ref(1);
const selected = ref<any>(null);
const editor = reactive<any>({});

const filtered = computed(() => activeDimension.value ? settings.value.filter((item) => item.dimension === activeDimension.value) : settings.value);
const paged = computed(() => filtered.value.slice((page.value - 1) * 10, page.value * 10));
const selectedPreview = computed(() => {
  if (!selected.value) return '';
  const index = settings.value.findIndex((item) => item.setting_id === selected.value.setting_id);
  return JSON.stringify(previews.value[index] || {}, null, 2);
});

async function generate() {
  const data = await getJson<any>('/api/workflow/configure');
  Object.assign(scope, data.scope || {});
  settings.value = data.settings || [];
  previews.value = data.script_previews || [];
}

function edit(item: any) {
  selected.value = item;
  Object.assign(editor, {
    setting_id: item.setting_id,
    enabled: item.enabled !== false,
    target_column: item.target_column,
    validation_level: item.validation_level,
    required: item.parameter_overrides?.required ?? true,
    phone_length: item.parameter_overrides?.phone_digit_count ?? item.parameter_overrides?.phone_length ?? 17,
    pass_percent: Math.round((item.threshold?.pass_rate ?? 1) * 1000) / 10,
    responsible_role: item.responsible_role || '数据责任人',
    condition: item.condition || '',
  });
}

function payloadFromEditor(item = editor) {
  return {
    setting_id: item.setting_id,
    enabled: item.enabled,
    target_column: item.target_column,
    validation_level: item.validation_level,
    responsible_role: item.responsible_role,
    condition: item.condition,
    threshold: { pass_rate: Number(item.pass_percent || 100) / 100 },
    parameter_overrides: {
      required: item.required,
      phone_length: item.phone_length,
      phone_digit_count: String(item.phone_length || 17),
      regex: `^\\d{${Number(item.phone_length || 17)}}$`,
    },
  };
}

async function saveOne() {
  if (!selected.value) return;
  await postJson('/api/workflow/settings/update', { settings: [payloadFromEditor()] });
  await generate();
}

async function saveAll() {
  if (selected.value) {
    await saveOne();
  }
}

async function trial() {
  const data = await getJson<any>('/api/workflow/trial');
  trialResults.value = data.trial_results || [];
}

onMounted(generate);
</script>
