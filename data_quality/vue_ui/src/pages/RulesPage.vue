<template>
  <div class="rules-page">
    <section class="band">
      <div class="section-title">
        <div>
          <h2>质量评价规则库</h2>
          <p>按六个评价维度管理规则，业务人员只需要选择维度、填写检查要求并保存。</p>
        </div>
        <div class="toolbar">
          <button class="secondary" @click="refreshRules">刷新规则库</button>
          <button class="primary" @click="startCreate">新增规则</button>
        </div>
      </div>

      <div class="metrics">
        <MetricCard label="可用规则" :value="rules.length" foot="当前筛选结果" />
        <MetricCard label="所属维度" :value="currentDimensionLabel" foot="六维质量评价" />
        <MetricCard label="每页展示" :value="pageSize" foot="固定分页查看" />
        <MetricCard label="客户视图" value="已开启" foot="隐藏技术明细" />
      </div>

      <div class="dimension-strip">
        <button :class="{ active: !filters.dimension }" @click="chooseDimension('')">
          <strong>全部</strong>
          <span>{{ allRules.length }} 条</span>
        </button>
        <button
          v-for="item in dimensions"
          :key="item.key"
          :class="{ active: filters.dimension === item.key }"
          @click="chooseDimension(item.key)"
        >
          <strong>{{ item.label }}</strong>
          <span>{{ dimensionCounts[item.key] || 0 }} 条</span>
        </button>
      </div>

      <div class="form-grid">
        <div class="field">
          <label>搜索规则</label>
          <input v-model="filters.keyword" placeholder="输入手机号、身份证、金额等关键词" @keyup.enter="refreshRules" />
        </div>
        <div class="field">
          <label>规则类型</label>
          <select v-model="filters.sourceType" @change="page = 1">
            <option value="">全部类型</option>
            <option value="STANDARD">标准规则</option>
            <option value="BUSINESS">业务规则</option>
            <option value="TECHNICAL">技术规则</option>
            <option value="CUSTOM">自定义规则</option>
          </select>
        </div>
        <div class="field">
          <label>每页数量</label>
          <select v-model.number="pageSize" @change="page = 1">
            <option :value="10">10 条</option>
            <option :value="20">20 条</option>
          </select>
        </div>
      </div>

      <div v-if="message.text" class="notice" :class="{ warning: message.type === 'error' }">
        {{ message.text }}
      </div>
    </section>

    <div class="rules-workspace">
      <section class="band rules-list">
        <div class="section-title">
          <div>
            <h3>规则列表</h3>
            <p>一页展示 {{ pageSize }} 条，点击规则可查看业务说明。</p>
          </div>
        </div>

        <div v-if="pagedRules.length" class="rule-card-list">
          <button
            v-for="rule in pagedRules"
            :key="rule.rule_id"
            class="rule-card"
            :class="{ active: selectedRule?.rule_id === rule.rule_id }"
            @click="selectRule(rule)"
          >
            <div class="rule-card-head">
              <span class="chip">{{ rule.dimension_zh || dimensionName(rule.dimension) }}</span>
              <span class="chip gray">{{ sourceTypeName(rule.source_type) }}</span>
            </div>
            <strong>{{ rule.display_name }}</strong>
            <p>{{ rule.core_definition || '用于检查数据是否符合业务质量要求。' }}</p>
            <div class="rule-card-foot">
              <span>{{ levelName(rule.validation_level) }}</span>
              <span>通过率 {{ passRateText(rule) }}</span>
            </div>
          </button>
        </div>
        <div v-else class="empty">当前筛选条件下暂无规则。</div>

        <Pager v-model:page="page" :page-size="pageSize" :total="filteredRules.length" />
      </section>

      <section class="panel rule-detail">
        <template v-if="selectedRule && editorMode !== 'create'">
          <div class="section-title">
            <div>
              <h3>{{ selectedRule.display_name }}</h3>
              <p>{{ selectedRule.dimension_zh || dimensionName(selectedRule.dimension) }} · {{ sourceTypeName(selectedRule.source_type) }}</p>
            </div>
            <div class="toolbar">
              <button class="secondary" @click="reuse(selectedRule)">复用</button>
              <button class="secondary" @click="edit(selectedRule)">编辑</button>
              <button class="secondary" @click="remove(selectedRule)">停用</button>
            </div>
          </div>

          <div class="detail-grid">
            <div>
              <span>适用对象</span>
              <strong>{{ applicabilityText(selectedRule) }}</strong>
            </div>
            <div>
              <span>检查要求</span>
              <strong>{{ requirementText(selectedRule) }}</strong>
            </div>
            <div>
              <span>校验方式</span>
              <strong>{{ levelName(selectedRule.validation_level) }}</strong>
            </div>
            <div>
              <span>责任角色</span>
              <strong>{{ selectedRule.responsible_role || '数据责任人' }}</strong>
            </div>
          </div>

          <div class="business-copy">
            <h4>规则说明</h4>
            <p>{{ selectedRule.core_definition || '该规则用于发现数据质量问题，并在评价实施后生成问题记录。' }}</p>
          </div>
          <div class="business-copy">
            <h4>发现问题后怎么处理</h4>
            <p>{{ selectedRule.remediation_suggestion || '核查源数据，修正后重新执行质量评价。' }}</p>
          </div>

          <details class="tech-details">
            <summary>实施人员查看技术信息</summary>
            <div class="stack">
              <div class="muted small">规则编号：{{ selectedRule.rule_id }}</div>
              <pre class="code">{{ technicalSummary(selectedRule) }}</pre>
            </div>
          </details>
        </template>

        <template v-else>
          <div class="section-title">
            <div>
              <h3>{{ editorMode === 'edit' ? '编辑规则' : '新增规则' }}</h3>
              <p>先选择评价维度，再填写客户能理解的检查要求；执行内容由系统生成。</p>
            </div>
          </div>

          <div class="form">
            <div class="field">
              <label>所属维度</label>
              <div class="dimension-picker">
                <button
                  v-for="item in dimensions"
                  :key="item.key"
                  :class="{ active: form.dimension === item.key }"
                  @click="selectDimension(item.key)"
                >
                  {{ item.label }}
                </button>
              </div>
            </div>

            <div class="form-grid">
              <div class="field">
                <label>规则名称</label>
                <input v-model="form.display_name" placeholder="例如：手机号格式校验" />
              </div>
              <div class="field">
                <label>适用字段</label>
                <input v-model="form.target_field_hint" placeholder="例如：手机号、联系电话" />
              </div>
              <div class="field">
                <label>规则类型</label>
                <select v-model="form.source_type">
                  <option value="CUSTOM">自定义规则</option>
                  <option value="BUSINESS">业务规则</option>
                  <option value="STANDARD">标准规则</option>
                  <option value="TECHNICAL">技术规则</option>
                </select>
              </div>
            </div>

            <div class="form-grid">
              <div class="field">
                <label>校验方式</label>
                <select v-model="form.validation_level">
                  <option value="P1_WARNING">提醒复核</option>
                  <option value="P2_MONITORING">仅监测</option>
                  <option value="P0_BLOCKING">强制拦截</option>
                </select>
              </div>
              <div class="field">
                <label>要求通过率</label>
                <select v-model.number="form.pass_rate">
                  <option :value="1">100%</option>
                  <option :value="0.99">99%</option>
                  <option :value="0.95">95%</option>
                  <option :value="0.9">90%</option>
                </select>
              </div>
              <div class="field">
                <label>责任角色</label>
                <input v-model="form.responsible_role" placeholder="数据责任人" />
              </div>
            </div>

            <div v-if="isPhoneRule" class="friendly-box">
              <div class="section-title compact">
                <div>
                  <h3>手机号检查要求</h3>
                  <p>这里按客户口径配置，系统会自动生成底层校验方式。</p>
                </div>
              </div>
              <div class="form-grid">
                <div class="field">
                  <label>数字个数</label>
                  <input v-model.number="form.phone_digits" type="number" min="1" max="30" />
                </div>
                <div class="field">
                  <label>内容要求</label>
                  <select v-model="form.only_digits">
                    <option :value="true">只能填写数字</option>
                    <option :value="false">允许其他字符</option>
                  </select>
                </div>
                <div class="field">
                  <label>是否必填</label>
                  <select v-model="form.required">
                    <option :value="false">允许为空</option>
                    <option :value="true">必须填写</option>
                  </select>
                </div>
              </div>
            </div>

            <div class="field">
              <label>检查要求</label>
              <textarea v-model="form.core_definition" placeholder="用一句话说明这条规则要检查什么"></textarea>
            </div>
            <div class="field">
              <label>整改建议</label>
              <textarea v-model="form.remediation_suggestion" placeholder="发现问题后，业务人员应该怎么处理"></textarea>
            </div>

            <details class="tech-details">
              <summary>实施人员查看技术信息</summary>
              <div class="stack">
                <div class="form-grid">
                  <div class="field">
                    <label>执行字段占位</label>
                    <input v-model="form.column_placeholder" placeholder="{{ column_name }}" />
                  </div>
                  <div class="field">
                    <label>规则编号</label>
                    <input v-model="form.rule_id" placeholder="不填则自动生成" />
                  </div>
                  <div class="field">
                    <label>问题归类</label>
                    <input v-model="form.problem_category" />
                  </div>
                </div>
                <pre class="code">{{ generatedTechnicalText }}</pre>
              </div>
            </details>

            <div class="toolbar">
              <button class="primary" @click="saveRule">{{ editorMode === 'edit' ? '保存修改' : '保存规则' }}</button>
              <button class="secondary" @click="cancelEditor">取消</button>
            </div>
          </div>
        </template>
      </section>
    </div>

    <section v-if="operationResult" class="panel">
      <div class="section-title">
        <div>
          <h3>当前操作结果</h3>
          <p>{{ operationResult.title }}</p>
        </div>
      </div>
      <div class="business-copy">
        <p>{{ operationResult.message }}</p>
      </div>
      <details v-if="operationResult.technical" class="tech-details">
        <summary>实施人员查看技术结果</summary>
        <pre class="code">{{ operationResult.technical }}</pre>
      </details>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import MetricCard from '../components/MetricCard.vue';
import Pager from '../components/Pager.vue';
import { getJson, postJson, toQuery } from '../api';
import { dimensionName, dimensions, levelName } from '../labels';
import type { RuleItem } from '../types';

type MessageType = 'success' | 'error';

const filters = reactive({ dimension: '', keyword: '', sourceType: '' });
const allRules = ref<RuleItem[]>([]);
const rules = ref<RuleItem[]>([]);
const selectedRule = ref<RuleItem | null>(null);
const page = ref(1);
const pageSize = ref(10);
const editorMode = ref<'create' | 'edit' | 'view'>('view');
const operationResult = ref<{ title: string; message: string; technical?: string } | null>(null);
const message = reactive<{ text: string; type: MessageType }>({ text: '', type: 'success' });

const form = reactive<any>({
  rule_id: '',
  dimension: 'normativity',
  display_name: '手机号格式校验',
  target_field_hint: '手机号、联系电话',
  source_type: 'CUSTOM',
  problem_category: '格式不规范',
  validation_level: 'P1_WARNING',
  pass_rate: 0.99,
  responsible_role: '数据责任人',
  core_definition: '手机号应为17位数字。',
  remediation_suggestion: '核对手机号来源，修正非数字或位数不正确的数据后重新入库。',
  phone_digits: 17,
  only_digits: true,
  required: false,
  column_placeholder: '{{ column_name }}',
});

const dimensionCounts = computed(() => {
  const counts: Record<string, number> = {};
  allRules.value.forEach((rule) => {
    counts[rule.dimension] = (counts[rule.dimension] || 0) + 1;
  });
  return counts;
});

const filteredRules = computed(() => {
  let data = rules.value;
  if (filters.sourceType) {
    data = data.filter((rule) => rule.source_type === filters.sourceType);
  }
  return data;
});

const totalPages = computed(() => Math.max(1, Math.ceil(filteredRules.value.length / pageSize.value)));
const pagedRules = computed(() => {
  const start = (page.value - 1) * pageSize.value;
  return filteredRules.value.slice(start, start + pageSize.value);
});

const currentDimensionLabel = computed(() => {
  if (!filters.dimension) return '全部';
  return dimensionName(filters.dimension);
});

const isPhoneRule = computed(() => {
  const text = `${form.display_name} ${form.target_field_hint} ${form.core_definition}`.toLowerCase();
  return /phone|mobile|tel|手机号|电话|联系电话/.test(text);
});

const generatedRegex = computed(() => {
  if (isPhoneRule.value && form.only_digits) {
    const digits = Math.max(1, Math.min(30, Number(form.phone_digits) || 17));
    return `^\\d{${digits}}$`;
  }
  return '^.+$';
});

const generatedSql = computed(() => {
  const emptyCondition = `${form.column_placeholder} IS NULL OR TRIM(${form.column_placeholder}) = ''`;
  const formatCondition = `${form.column_placeholder} IS NOT NULL AND ${form.column_placeholder} NOT REGEXP '{{ regex }}'`;
  if (form.required) {
    return `SELECT * FROM {{ table_name }} WHERE ${emptyCondition} OR (${formatCondition})`;
  }
  return `SELECT * FROM {{ table_name }} WHERE ${formatCondition}`;
});

const generatedTechnicalText = computed(() => JSON.stringify({
  parameters: {
    regex: generatedRegex.value,
    phone_digit_count: isPhoneRule.value ? String(form.phone_digits || 17) : undefined,
    only_digits: isPhoneRule.value ? form.only_digits : undefined,
    required: form.required,
  },
  threshold: {
    pass_rate: form.pass_rate,
  },
  sql_template: generatedSql.value,
}, null, 2));

watch([filteredRules, pageSize], () => {
  if (page.value > totalPages.value) page.value = 1;
});

function showMessage(text: string, type: MessageType = 'success') {
  message.text = text;
  message.type = type;
}

async function refreshRules(feedback = '规则库已刷新') {
  const query = toQuery({
    dimension: filters.dimension,
    keyword: filters.keyword,
  });
  const [visibleData, allData] = await Promise.all([
    getJson<any>(`/api/rules${query}`),
    getJson<any>('/api/rules'),
  ]);
  rules.value = visibleData.rules || [];
  allRules.value = allData.rules || [];
  page.value = Math.min(page.value, totalPages.value);
  if (!selectedRule.value || !rules.value.some((rule) => rule.rule_id === selectedRule.value?.rule_id)) {
    selectedRule.value = pagedRules.value[0] || null;
  }
  editorMode.value = selectedRule.value ? 'view' : 'create';
  showMessage(feedback);
}

function chooseDimension(dimension: string) {
  filters.dimension = dimension;
  page.value = 1;
  refreshRules(`${dimension ? dimensionName(dimension) : '全部'}规则已加载`);
}

function selectRule(rule: RuleItem) {
  selectedRule.value = rule;
  editorMode.value = 'view';
  operationResult.value = null;
}

function selectDimension(dimension: string) {
  form.dimension = dimension;
  if (editorMode.value === 'create') {
    Object.assign(form, presets[dimension] || presets.normativity);
  }
}

function startCreate() {
  editorMode.value = 'create';
  operationResult.value = null;
  resetForm();
}

function edit(rule: RuleItem) {
  editorMode.value = 'edit';
  selectedRule.value = rule;
  const regex = rule.parameters?.regex || '';
  const digits = regex.match(/\\d\{(\d+)\}/)?.[1];
  Object.assign(form, {
    rule_id: rule.rule_id,
    dimension: rule.dimension,
    display_name: rule.display_name,
    target_field_hint: applicabilityText(rule),
    source_type: rule.source_type || 'CUSTOM',
    problem_category: rule.problem_category || '自定义问题',
    validation_level: rule.validation_level || 'P1_WARNING',
    pass_rate: rule.threshold?.pass_rate ?? 0.99,
    responsible_role: rule.responsible_role || '数据责任人',
    core_definition: rule.core_definition || '',
    remediation_suggestion: rule.remediation_suggestion || '',
    phone_digits: digits ? Number(digits) : 17,
    only_digits: Boolean(regex.includes('\\d')),
    required: Boolean(rule.parameters?.required),
    column_placeholder: '{{ column_name }}',
  });
}

function cancelEditor() {
  editorMode.value = selectedRule.value ? 'view' : 'create';
  if (!selectedRule.value) resetForm();
}

function resetForm() {
  Object.assign(form, {
    rule_id: '',
    dimension: filters.dimension || 'normativity',
    display_name: '',
    target_field_hint: '',
    source_type: 'CUSTOM',
    problem_category: '自定义问题',
    validation_level: 'P1_WARNING',
    pass_rate: 0.99,
    responsible_role: '数据责任人',
    core_definition: '',
    remediation_suggestion: '',
    phone_digits: 17,
    only_digits: true,
    required: false,
    column_placeholder: '{{ column_name }}',
  });
  selectDimension(form.dimension);
}

async function saveRule() {
  if (!form.display_name.trim()) {
    showMessage('请先填写规则名称。', 'error');
    return;
  }
  if (!form.core_definition.trim()) {
    showMessage('请先填写检查要求。', 'error');
    return;
  }

  const payload = buildPayload();
  try {
    let data: any;
    if (editorMode.value === 'edit' && form.rule_id) {
      data = await postJson('/api/rules/update', { rule_id: form.rule_id, updates: payload });
    } else {
      data = await postJson('/api/rules/create', payload);
    }
    operationResult.value = {
      title: data.message || '规则已保存',
      message: `${payload.display_name} 已保存到规则库，后续可用于智能推荐、参数配置和评价实施。`,
      technical: JSON.stringify(data.rule || payload, null, 2),
    };
    await refreshRules(data.message || '规则已保存');
    const saved = rules.value.find((rule) => rule.rule_id === (data.rule?.rule_id || payload.rule_id));
    if (saved) selectedRule.value = saved;
    editorMode.value = 'view';
  } catch (error) {
    showMessage(error instanceof Error ? error.message : String(error), 'error');
  }
}

async function remove(rule: RuleItem) {
  if (!window.confirm(`确认停用规则“${rule.display_name}”？停用后前端默认不再展示。`)) return;
  try {
    const data = await postJson<any>('/api/rules/delete', { rule_id: rule.rule_id });
    operationResult.value = {
      title: data.message || '规则已停用',
      message: `规则“${rule.display_name}”已停用，如需恢复可由实施人员在规则 Spec 中处理。`,
    };
    selectedRule.value = null;
    await refreshRules(data.message || '规则已停用');
  } catch (error) {
    showMessage(error instanceof Error ? error.message : String(error), 'error');
  }
}

async function reuse(rule: RuleItem) {
  try {
    const data = await postJson<any>('/api/rules/reuse', {
      rule_id: rule.rule_id,
      table_name: 'customer_order',
      column_name: isPhoneBusinessRule(rule) ? 'mobile_phone' : 'target_column',
      engine: 'SQL',
    });
    operationResult.value = {
      title: '规则复用配置已生成',
      message: `规则“${rule.display_name}”已生成复用配置，可进入参数设定和评价实施环节继续使用。`,
      technical: JSON.stringify(data.plan || data, null, 2),
    };
    showMessage('规则复用配置已生成');
  } catch (error) {
    showMessage(error instanceof Error ? error.message : String(error), 'error');
  }
}

function buildPayload() {
  const regex = generatedRegex.value;
  const parameters: Record<string, any> = {
    regex,
    required: form.required,
  };
  if (isPhoneRule.value) {
    parameters.phone_digit_count = String(form.phone_digits || 17);
    parameters.only_digits = form.only_digits;
  }
  return {
    rule_id: form.rule_id || undefined,
    dimension: form.dimension,
    display_name: form.display_name.trim(),
    source_type: form.source_type,
    problem_category: form.problem_category || '自定义问题',
    core_definition: form.core_definition.trim(),
    responsible_role: form.responsible_role || '数据责任人',
    remediation_suggestion: form.remediation_suggestion || '核查源数据，修正后重新执行质量评价。',
    validation_level: form.validation_level,
    severity: severityFromLevel(form.validation_level),
    threshold: {
      operator: '==',
      expected_value: 0,
      pass_rate: Number(form.pass_rate) || 0.99,
      unit: 'failed_rows',
      description: `要求通过率不低于 ${Math.round((Number(form.pass_rate) || 0.99) * 100)}%。`,
    },
    parameters,
    sql: generatedSql.value,
    scripts: {
      SQL: { expression: generatedSql.value, language: 'SQL', description: '系统自动生成的执行模板' },
      GE: {
        expression: 'ge_df.expect_column_values_to_match_regex(column="{{ column_name }}", regex=r"{{ regex }}", mostly={{ pass_rate }})',
        language: 'Python/Great Expectations',
        description: '系统自动生成的执行模板',
      },
      ETL: {
        expression: '{"action":"regex_check","column":"{{ column_name }}","regex":"{{ regex }}","on_fail":"issue_table"}',
        language: 'JSON DSL',
        description: '系统自动生成的执行模板',
      },
    },
    tags: [dimensionName(form.dimension), form.target_field_hint || form.display_name].filter(Boolean),
  };
}

function sourceTypeName(value?: string) {
  const map: Record<string, string> = {
    STANDARD: '标准规则',
    BUSINESS: '业务规则',
    TECHNICAL: '技术规则',
    CUSTOM: '自定义规则',
  };
  return map[value || ''] || value || '规则';
}

function severityFromLevel(value: string) {
  if (value === 'P0_BLOCKING') return 'CRITICAL';
  if (value === 'P2_MONITORING') return 'LOW';
  return 'MEDIUM';
}

function passRateText(rule: RuleItem) {
  const rate = Number(rule.threshold?.pass_rate ?? 1);
  return `${Math.round(rate * 100)}%`;
}

function applicabilityText(rule: RuleItem) {
  const patterns = rule.applicability?.column_name_patterns || [];
  if (!patterns.length) return '按规则选择字段';
  return patterns.map((item: string) => item.replace(/\*/g, '')).join('、');
}

function requirementText(rule: RuleItem) {
  if (isPhoneBusinessRule(rule)) {
    const digits = String(rule.parameters?.phone_digit_count || '').trim() || regexDigits(rule.parameters?.regex) || '17';
    return `${digits}位数字`;
  }
  const regex = String(rule.parameters?.regex || '');
  if (/\\d\{(\d+)\}/.test(regex)) return `${regexDigits(regex)}位数字`;
  if (rule.threshold?.description) return rule.threshold.description;
  return rule.problem_category || '按规则要求检查';
}

function regexDigits(regex?: string) {
  const match = String(regex || '').match(/\\d\{(\d+)\}/);
  return match?.[1] || '';
}

function isPhoneBusinessRule(rule: RuleItem) {
  const text = `${rule.display_name} ${rule.core_definition} ${(rule.tags || []).join(' ')}`.toLowerCase();
  return /phone|mobile|tel|手机号|电话|联系电话/.test(text);
}

function technicalSummary(rule: RuleItem) {
  return JSON.stringify({
    parameters: rule.parameters || {},
    threshold: rule.threshold || {},
    scripts: rule.scripts || {},
  }, null, 2);
}

const presets: Record<string, Partial<typeof form>> = {
  normativity: {
    display_name: '手机号格式校验',
    target_field_hint: '手机号、联系电话',
    problem_category: '格式不规范',
    core_definition: '手机号应为17位数字。',
    remediation_suggestion: '核对手机号来源，修正非数字或位数不正确的数据后重新入库。',
    phone_digits: 17,
    only_digits: true,
  },
  completeness: {
    display_name: '必填字段完整性校验',
    target_field_hint: '客户名称、证件号、订单号',
    problem_category: '字段不完整',
    core_definition: '关键字段应填写完整，不应为空。',
    remediation_suggestion: '补录缺失信息后重新提交数据。',
  },
  accuracy: {
    display_name: '金额合理性校验',
    target_field_hint: '金额、数量、工时',
    problem_category: '取值不合理',
    core_definition: '金额、数量等数值应在业务允许范围内。',
    remediation_suggestion: '核对业务来源，修正明显异常的数值。',
  },
  consistency: {
    display_name: '主从表一致性校验',
    target_field_hint: '客户编号、订单编号',
    problem_category: '数据不一致',
    core_definition: '同一业务对象在相关表或系统中应保持一致。',
    remediation_suggestion: '核对同步链路和映射关系，修正不一致数据。',
  },
  timeliness: {
    display_name: '数据更新及时性校验',
    target_field_hint: '更新时间、入库时间',
    problem_category: '更新不及时',
    core_definition: '数据应在约定时间内完成更新。',
    remediation_suggestion: '检查同步任务和调度链路，必要时补跑数据。',
  },
  accessibility: {
    display_name: '数据访问可用性校验',
    target_field_hint: '数据表、接口、权限',
    problem_category: '访问不可用',
    core_definition: '授权用户应能正常访问对应数据对象。',
    remediation_suggestion: '检查权限、连接和服务状态，恢复后重新验证。',
  },
};

onMounted(async () => {
  await refreshRules('规则库已加载');
});
</script>
