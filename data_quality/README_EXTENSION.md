# 数据质量评价扩展模块

基于《GB/T 36344-2018 信息技术 数据质量评价指标》国家标准，扩展 OpenMetadata 数据质量评价功能。

## 功能概览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         数据质量评价扩展框架                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │  维度评估器   │  │  规则推荐器  │  │  参数建议器  │  │ 规则校验器 │  │
│  │              │  │              │  │              │  │            │  │
│  │ • 六维度评分 │  │ • 自动推荐   │  │ • 采样分析   │  │ • 审批流程 │  │
│  │ • 权重计算   │  │ • 智能匹配   │  │ • 参数自动   │  │ • 版本管理 │  │
│  │ • 报告生成   │  │ • 置信度     │  │   设置       │  │ • 使用追踪 │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  └────────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                           REST API 层                              │   │
│  │  • 质量评估 API  • 规则推荐 API  • 血缘分析 API                    │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                           报告生成器                               │   │
│  │  • JSON 报告  • Markdown 报告  • HTML 报告  • 趋势分析报告        │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                         血缘质量分析器                              │   │
│  │  • 问题溯源  • 影响评估  • 传播路径  • 优先级排序                   │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 一、维度评估 (Dimension Evaluator)

### 1.1 六维度体系

| 维度 | 权重 | 说明 |
|------|------|------|
| 规范性 | 20% | 数据符合标准、规则的程度 |
| 完整性 | 20% | 数据无缺失、无遗漏的程度 |
| 准确性 | 15% | 数据反映真实状态的程度 |
| 一致性 | 15% | 数据在不同来源中的一致性 |
| 时效性 | 15% | 数据满足时效需求的程度 |
| 可访问性 | 15% | 数据可被快速获取的程度 |

### 1.2 评分算法

```python
# 总体评分 = Σ(维度评分 × 维度权重)
# 维度评分 = 测试通过率 × 40% + 数据行通过率 × 60%

# 关键规则失败扣分
if 有关键规则失败:
    维度评分 = max(0, 维度评分 - 关键规则失败数 × 10)
```

### 1.3 使用示例

```python
from metadata.data_quality import (
    DimensionEvaluator,
    TestResultSummary,
    QualityDimension,
    RuleSeverity,
)

# 创建评估器
evaluator = DimensionEvaluator()

# 模拟测试结果
test_results = [
    TestResultSummary(
        test_case=None,
        test_definition=None,
        status="Success",
        passed_rows=95,
        failed_rows=5,
        total_rows=100,
        dimension=QualityDimension.COMPLETENESS,
        severity=RuleSeverity.HIGH,
    ),
]

# 执行评估
result = evaluator.evaluate(
    test_results=test_results,
    table_fqn="MySQL.default.db.customers",
    table_row_count=1000000,
)

print(f"总体评分: {result.overall_score:.2f}/100")
print(f"质量等级: {result.quality_level}")
```

---

## 二、规则推荐 (Rule Recommender)

### 2.1 智能推荐逻辑

```
┌─────────────────┐
│   列特征分析     │
├─────────────────┤
│ • 数据类型      │    ┌─────────────────┐
│ • 列名模式      │───►│  规则推荐引擎   │───► 推荐规则列表
│ • 业务分类      │    │                 │
│ • 约束信息      │    │ 置信度计算     │
└─────────────────┘    └─────────────────┘
```

### 2.2 内置规则模板

| 列分类 | 推荐规则 | 严重程度 |
|--------|----------|----------|
| 主键 (id) | 非空、唯一性 | CRITICAL |
| 手机号 | 格式校验 (正则) | HIGH |
| 邮箱 | 格式校验 (正则) | MEDIUM |
| 金额/价格 | 非负、范围校验 | HIGH |
| 年龄 | 范围校验 (0-120) | MEDIUM |
| 状态 | 枚举值校验 | HIGH |
| 时间字段 | 非空、范围校验 | HIGH |

### 2.3 使用示例

```python
from metadata.data_quality import RuleRecommender

recommender = RuleRecommender()

# 获取表结构
table = metadata.get_by_name(Table, fqn="MySQL.default.db.customers")

# 自动推荐规则
recommendations = recommender.recommend_for_table(table)

# 按维度筛选
normativity_rules = recommender.filter_by_dimension(
    recommendations, QualityDimension.NORMATIVITY
)

# 按严重程度筛选
critical_rules = recommender.filter_by_severity(
    recommendations, min_severity=RuleSeverity.CRITICAL
)

# 按置信度筛选
high_confidence = recommender.filter_by_confidence(
    recommendations, min_confidence=0.8
)
```

---

## 三、参数自动建议 (Parameter Suggester)

### 3.1 采样分析流程

```
采样数据 ──► 统计分析 ──► 模式检测 ──► 参数建议
              │              │
              ▼              ▼
         • 空值率       • 正则模式
         • 唯一值       • 格式类型
         • 数值范围      • 值域分布
         • 长度分布
```

### 3.2 自动参数类型

| 规则类型 | 可建议参数 |
|----------|-----------|
| columnValuesToBeBetween | minValue, maxValue |
| columnValueMinToBeBetween | minValue |
| columnValueMaxToBeBetween | maxValue |
| columnValuesToBeInSet | columnValues (频繁值) |
| columnValuesToMatchRegex | regex (检测到的模式) |
| columnValueLengthsToBeBetween | minLength, maxLength |

### 3.3 使用示例

```python
from metadata.data_quality import ParameterSuggester

suggester = ParameterSuggester()

# 获取采样数据
samples = fetch_samples_from_database("phone", limit=1000)

# 分析采样数据
analysis = suggester.analyze_sample_data("phone", samples)

print(f"样本数: {analysis.sample_size}")
print(f"空值率: {analysis.null_ratio:.2%}")
print(f"唯一值: {analysis.unique_count}")
print(f"检测模式: {analysis.detected_patterns}")

# 为规则建议参数
params = suggester.suggest_parameters(analysis, "columnValuesToMatchRegex")

for param in params:
    print(f"{param.parameter_name}: {param.suggested_value}")
    print(f"置信度: {param.confidence:.0%}")
    print(f"理由: {param.rationale}")
```

---

## 四、规则校验 (Rule Validator)

### 4.1 校验工作流

```
┌─────────────┐    推荐生成     ┌─────────────┐    校验审批     ┌─────────────┐
│  规则推荐   │ ──────────────► │  待校验队列  │ ──────────────► │  已批准规则  │
│             │                │              │                │             │
│ • 置信度    │                │ • 自动排序   │                │ • 版本管理   │
│ • 智能匹配  │                │ • 超期提醒   │                │ • 使用追踪   │
└─────────────┘                └─────────────┘                └─────────────┘
```

### 4.2 校验状态

| 状态 | 说明 |
|------|------|
| PENDING | 待校验 |
| APPROVED | 已批准 |
| REJECTED | 已拒绝 |
| MODIFIED | 已修改 |
| DEPRECATED | 已废弃 |

### 4.3 校验优先级

| 优先级 | 说明 |
|--------|------|
| LOW | 低优先级 |
| NORMAL | 普通优先级 |
| HIGH | 高优先级 |
| URGENT | 紧急优先级 |

### 4.4 使用示例

```python
from metadata.data_quality import (
    RuleValidator,
    ValidationStatus,
    ValidationPriority,
)

validator = RuleValidator()

# 创建校验记录
record = validator.create_validation_record(
    rule_id="rule_001",
    table_fqn="MySQL.default.db.customers",
    column_name="email",
    confidence_score=0.95,
    recommended_by="RuleRecommender",
)

# 批准规则
validator.approve_rule(
    validation_id=record.validation_id,
    approved_by="admin",
    comments="Email validation is critical for user communication",
)

# 批量批准
validator.batch_approve(
    validation_ids=["val_001", "val_002", "val_003"],
    approved_by="admin",
)

# 查询待校验列表
pending = validator.get_pending_validations(
    priority_min=ValidationPriority.NORMAL,
    limit=50,
)

# 获取校验统计
summary = validator.get_validation_summary()
print(f"待校验: {summary.pending_count}")
print(f"已批准: {summary.approved_count}")
print(f"已拒绝: {summary.rejected_count}")
```

---

## 五、血缘质量分析 (Lineage Analyzer)

### 5.1 功能架构

```
┌─────────────────────────────────────────────────────────┐
│                  血缘质量分析器                           │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   上游追溯              问题诊断              下游影响    │
│   ─────────            ────────             ─────────  │
│   • 溯源根因           • 传播路径             • 影响评估  │
│   • 源头评分           • 置信度               • 阻断点   │
│   • 阻断建议           • 修复建议             • 优先级    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 5.2 使用示例

```python
from metadata.data_quality import QualityLineageAnalyzer, QualityIssue
from datetime import datetime

# 创建分析器
analyzer = QualityLineageAnalyzer(metadata_client)

# 定义质量问题
issues = [
    QualityIssue(
        entity_fqn="warehouse.orders_agg",
        column_name="total_amount",
        rule_name="columnValueMinToBeBetween",
        rule_dimension="accuracy",
        severity="HIGH",
        failure_rate=0.05,
        affected_rows=500,
        detected_at=datetime.now(),
    ),
]

# 生成血缘质量报告
report = analyzer.generate_lineage_quality_report(
    entity_fqn="warehouse.orders_agg",
    quality_issues=issues,
)

# 报告结构
# {
#     "entity": "warehouse.orders_agg",
#     "summary": {...},
#     "upstream": {"quality_score": 85.0, "problem_nodes": [...]},
#     "downstream": {"impact_prediction": {...}},
#     "root_cause_analysis": {
#         "root_causes": [...],
#         "propagation_paths": [...]
#     },
#     "recommendations": [...]
# }

# 获取修复优先级
entities = ["table_a", "table_b", "table_c"]
priority_order = analyzer.get_quality_priority_order(entities, issue_map)
```

---

## 六、REST API 接口

### 6.1 质量评估 API (QualityAssessmentAPI)

质量评估 API 提供表级别的数据质量评估功能。

#### 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/quality/assess` | 执行质量评估 |
| GET | `/quality/result/{table_fqn}` | 获取评估结果 |
| GET | `/quality/history/{table_fqn}` | 获取评估历史 |
| GET | `/quality/trend/{table_fqn}` | 获取趋势分析 |
| GET | `/quality/critical/{table_fqn}` | 获取关键失败 |
| GET | `/quality/ranking` | 获取表排名 |

#### 请求示例

```python
from metadata.data_quality import (
    QualityAssessmentAPI,
    QualityAssessmentRequest,
)

api = QualityAssessmentAPI(metadata_client)

# 执行质量评估
request = QualityAssessmentRequest(
    table_fqn="MySQL.default.db.customers",
    include_dimensions=True,
    include_recommendations=True,
    lookback_days=30,
)

response = api.assess_quality(request)

# 获取维度评分
for dim in response.dimension_scores:
    print(f"{dim.dimension}: {dim.score:.2f}")

# 获取趋势分析
trend = api.get_trend(
    table_fqn="MySQL.default.db.customers",
    dimension=QualityDimension.COMPLETENESS,
    days=30,
)

print(f"趋势: {trend.direction} ({trend.change_rate:.2%})")
```

### 6.2 规则推荐 API (RuleRecommendationAPI)

规则推荐 API 提供规则推荐、校验和审批功能。

#### 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/rules/recommend` | 执行规则推荐 |
| POST | `/rules/batch-recommend` | 批量推荐 |
| POST | `/rules/validate` | 校验推荐结果 |
| POST | `/rules/approve` | 批准规则 |
| POST | `/rules/reject` | 拒绝规则 |
| GET | `/rules/pending` | 获取待校验列表 |
| GET | `/rules/summary` | 获取校验汇总 |

#### 请求示例

```python
from metadata.data_quality import (
    RuleRecommendationAPI,
    RuleRecommendationRequest,
)

api = RuleRecommendationAPI(metadata_client)

# 推荐规则
request = RuleRecommendationRequest(
    table_fqn="MySQL.default.db.customers",
    min_confidence=0.7,
    max_rules=20,
)

response = api.recommend(request)

# 批量推荐
batch_response = api.batch_recommend([
    "MySQL.default.db.customers",
    "MySQL.default.db.orders",
    "MySQL.default.db.products",
])

# 批准推荐规则
api.approve_rules(
    validation_ids=response.validation_ids,
    approved_by="admin",
)

# 获取校验汇总
summary = api.get_validation_summary()
print(f"待处理: {summary.pending}")
print(f"已批准: {summary.approved}")
print(f"已拒绝: {summary.rejected}")
```

### 6.3 血缘分析 API (LineageAnalysisAPI)

血缘分析 API 提供血缘图构建和影响分析功能。

#### 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/lineage/graph/{table_fqn}` | 获取血缘图 |
| POST | `/lineage/trace` | 追溯质量问题 |
| POST | `/lineage/impact` | 影响分析 |
| POST | `/lineage/root-cause` | 根因分析 |
| GET | `/lineage/summary/{table_fqn}` | 质量汇总 |

#### 请求示例

```python
from metadata.data_quality import (
    LineageAnalysisAPI,
    LineageDirection,
)

api = LineageAnalysisAPI(metadata_client)

# 获取血缘图
graph = api.get_lineage_graph(
    table_fqn="warehouse.orders_agg",
    direction=LineageDirection.BOTH,
    depth=5,
)

print(f"上游节点: {len(graph.upstream_nodes)}")
print(f"下游节点: {len(graph.downstream_nodes)}")

# 追溯质量问题传播
impacted = api.trace_quality_issue(
    table_fqn="source.raw_orders",
    column_name="total_amount",
    rule_name="columnValueMinToBeBetween",
)

for table in impacted.impacted_tables:
    print(f"受影响表: {table.table_fqn}")
    print(f"影响路径: {table.impact_path}")

# 根因分析
root_cause = api.analyze_root_causes(
    table_fqn="warehouse.orders_agg",
    quality_issue=issue,
)

for cause in root_cause.root_causes:
    print(f"根因: {cause.entity_fqn}")
    print(f"置信度: {cause.confidence}")
    print(f"建议: {cause.remediation}")
```

---

## 七、报告生成 (Report Generator)

### 7.1 支持格式

| 格式 | 说明 |
|------|------|
| JSON | 机器可读的完整报告 |
| Markdown | 可读的文档格式 |
| HTML | 带样式的可视化报告 |
| Trend | 趋势分析报告 |

### 7.2 使用示例

```python
from metadata.data_quality import QualityReportGenerator

generator = QualityReportGenerator()

# 生成综合报告
report = generator.generate_json_report(
    table_fqn="MySQL.default.db.customers",
    test_results=test_results,
    dimension_scores=dimension_scores,
    recommendations=recommendations,
    include_lineage=True,
    include_recommendations=True,
)

# 生成 Markdown 报告
markdown = generator.generate_markdown_report(
    table_fqn="MySQL.default.db.customers",
    assessment=assessment,
    report_title="数据质量评估报告",
    include_charts=True,
)

# 保存报告
generator.save_report(
    report=markdown,
    file_path="./reports/quality_report.md",
    format="markdown",
)

# 生成趋势分析报告
trend_report = generator.generate_trend_report(
    table_fqn="MySQL.default.db.customers",
    days=30,
    dimensions=[QualityDimension.COMPLETENESS, QualityDimension.ACCURACY],
)
```

### 7.3 报告结构

```json
{
  "report_metadata": {
    "table_fqn": "MySQL.default.db.customers",
    "generated_at": "2025-04-11T10:30:00Z",
    "report_type": "quality_assessment"
  },
  "overall_score": 85.5,
  "quality_level": "GOOD",
  "dimension_scores": [
    {"dimension": "completeness", "score": 92.0, "trend": "stable"},
    {"dimension": "accuracy", "score": 88.0, "trend": "improving"}
  ],
  "test_results": {
    "total": 50,
    "passed": 45,
    "failed": 5,
    "pass_rate": "90.0%"
  },
  "recommendations": [...]
}
```

---

## 八、完整工作流示例

```python
from metadata.sdk.data_quality import TestRunner
from metadata.data_quality import (
    DimensionEvaluator,
    RuleRecommender,
    ParameterSuggester,
    RuleValidator,
    QualityLineageAnalyzer,
    QualityAssessmentAPI,
    RuleRecommendationAPI,
    QualityReportGenerator,
)

# 1. 初始化组件
metadata = OpenMetadata(ometa_connection)
evaluator = DimensionEvaluator()
recommender = RuleRecommender()
suggester = ParameterSuggester()
validator = RuleValidator()
lineage_analyzer = QualityLineageAnalyzer(metadata)
assessment_api = QualityAssessmentAPI(metadata)
recommendation_api = RuleRecommendationAPI(metadata)
report_generator = QualityReportGenerator()

# 2. 获取表实体
table = metadata.get_by_name(Table, fqn="MySQL.default.db.customers")

# 3. 推荐规则
recommendations = recommender.recommend_for_table(table)

# 4. 自动设置参数
for rec in recommendations:
    samples = fetch_samples(table, rec.column_name, 1000)
    analysis = suggester.analyze_sample_data(rec.column_name, samples)
    params = suggester.suggest_parameters(analysis, rec.test_definition_name)
    for p in params:
        rec.parameters[p.parameter_name] = p.suggested_value

# 5. 创建校验记录
for rec in recommendations:
    validator.create_validation_record(
        rule_id=rec.rule_id,
        table_fqn=table.fqn,
        column_name=rec.column_name,
        confidence_score=rec.confidence,
        recommended_by="RuleRecommender",
    )

# 6. 批准规则 (通过 API)
recommendation_api.approve_rules(
    validation_ids=[v.validation_id for v in pending_validations],
    approved_by="admin",
)

# 7. 执行测试
runner = TestRunner.for_table("MySQL.default.db.customers")
for rec in recommendations:
    runner.add_test(create_test(rec))

test_results = runner.run()

# 8. 维度评估
assessment = evaluator.evaluate(test_results, table.fqn, row_count)

# 9. 质量评估 (通过 API)
assessment_response = assessment_api.assess_quality(
    QualityAssessmentRequest(
        table_fqn=table.fqn,
        include_dimensions=True,
    )
)

# 10. 血缘分析
issues = convert_to_issues(test_results)
lineage_report = lineage_analyzer.generate_lineage_quality_report(
    table.fqn, issues
)

# 11. 生成综合报告
report = report_generator.generate_markdown_report(
    table_fqn=table.fqn,
    assessment=assessment,
    report_title="数据质量评估报告",
    include_lineage=True,
)

# 12. 保存报告
report_generator.save_report(
    report=report,
    file_path=f"./reports/{table.name}_quality_report.md",
)
```

---

## 九、文件结构

```
metadata/data_quality/
├── dimension/                    # 维度评估模块
│   ├── models.py               # 维度定义和权重
│   └── evaluator.py            # 评估器实现
│
├── rules/                       # 规则推荐模块
│   ├── rule_recommender.py     # 规则推荐引擎
│   ├── parameter_suggester.py   # 参数自动建议
│   └── rule_validator.py       # [NEW] 规则校验器
│
├── lineage/                     # 血缘分析模块
│   └── quality_lineage_analyzer.py  # 血缘质量分析
│
├── api/                         # [NEW] REST API 模块
│   ├── quality_assessment_api.py    # 质量评估 API
│   ├── rule_recommendation_api.py   # 规则推荐 API
│   └── lineage_analysis_api.py      # 血缘分析 API
│
├── reports/                     # [NEW] 报告生成模块
│   └── quality_report.py        # 报告生成器
│
├── specs/                       # 配置规范
│   ├── data_quality_rules.yml  # 规则库定义
│   └── test_suite_examples.yml # 配置示例
│
└── __init__.py                 # 模块导出
```

---

## 十、依赖说明

扩展模块依赖以下包：
- `openmetadata-ingestion`: 核心框架
- `re`: 正则表达式匹配
- `statistics`: 统计分析
- `collections`: 数据结构

所有功能设计为与现有 OpenMetadata 工作流兼容，可无缝集成。
