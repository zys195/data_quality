# 质量评价流程 API 文档

## 1. 概览

流程 API 门面位于 `data_quality/api/quality_workflow_api.py`，服务类为 `QualityWorkflowAPI`。当前实现是后端服务层接口，可直接被 FastAPI、Flask 或现有路由层包装成 REST 接口。

核心服务类：`QualityAssessmentWorkflow`

核心 API 门面：`QualityWorkflowAPI`

## 2. 推荐 REST 路径

| REST 路径 | 服务方法 | 说明 |
|---|---|---|
| `POST /qualityWorkflow/parameters/configure` | `configure_rule_parameters()` | 配置规则参数 |
| `POST /qualityWorkflow/rules/preview` | `preview_rule_script()` | 预览 SQL/GE/ETL 脚本 |
| `POST /qualityWorkflow/rules/trial-run` | `trial_run()` | 样例数据试跑 |
| `POST /qualityWorkflow/tasks` | `create_task()` | 创建质量评价任务 |
| `POST /qualityWorkflow/tasks/execute` | `execute_task()` | 执行质量评价任务 |
| `GET /qualityWorkflow/dashboard` | `get_dashboard()` | 查询六维质量看板 |
| `GET /qualityWorkflow/issues` | `query_issues()` | 查询质量问题 |
| `GET /qualityWorkflow/issues/{issue_id}/lineage` | `analyze_issue_lineage()` | 查询问题血缘影响 |
| `POST /qualityWorkflow/issues/status` | `update_issue_status()` | 推进问题闭环状态 |
| `POST /qualityWorkflow/scoring/archive` | `archive_scoring_rules()` | 归档计分规则 |
| `GET /qualityWorkflow/report` | `generate_report()` | 生成 Markdown/JSON 报告 |

## 3. 通用数据范围

`DataScopeRequest`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `data_source` | string | 是 | 数据源名称 |
| `database` | string | 否 | 数据库 |
| `schema` | string | 否 | Schema |
| `table_fqn` | string | 否 | 表全限定名 |
| `table_name` | string | 否 | 表名 |
| `fields` | array | 否 | 字段列表 |
| `subject_domain` | string | 否 | 主题域 |
| `business_domain` | string | 否 | 业务域 |
| `batch_id` | string | 否 | 批次号 |
| `partition` | string | 否 | 时间分区 |
| `row_count` | integer | 否 | 行数 |
| `data_classification` | string | 否 | 数据分类分级 |

## 4. 配置规则参数

```http
POST /qualityWorkflow/parameters/configure
```

请求模型：`ConfigureRuleParameterRequest`

```json
{
  "rule_id": "N-F02",
  "scope": {
    "data_source": "mysql",
    "database": "dw",
    "schema": "public",
    "table_fqn": "mysql.dw.public.customer_order",
    "table_name": "customer_order",
    "business_domain": "客户订单",
    "batch_id": "batch_20260531"
  },
  "target_column": "mobile_phone",
  "threshold": {
    "operator": "==",
    "expected_value": 0,
    "pass_rate": 0.999,
    "unit": "failed_rows"
  },
  "weight": 1.0,
  "schedule": "manual",
  "scan_mode": "full",
  "validation_level": "P1_WARNING",
  "execution_engine": "SQL",
  "parameter_overrides": {}
}
```

主要返回：

| 字段 | 说明 |
|---|---|
| `setting_id` | 规则参数配置 ID |
| `rule_id` | 规则编号 |
| `dimension` | 评价维度 |
| `threshold` | 阈值配置 |
| `validation_level` | P0/P1/P2 强弱校验 |
| `execution_engine` | SQL/GE/ETL |

## 5. 预览规则脚本

```http
POST /qualityWorkflow/rules/preview
```

请求模型：`PreviewWorkflowRuleRequest`

```json
{
  "setting_or_rule_id": "setting-20260531190952-0001",
  "engine": "SQL",
  "target_object": {
    "table_name": "customer_order",
    "column_name": "mobile_phone"
  },
  "parameter_overrides": {}
}
```

返回字段：

| 字段 | 说明 |
|---|---|
| `rule_id` | 规则编号 |
| `engine` | 执行引擎 |
| `expression` | 原始脚本模板 |
| `rendered_expression` | 渲染后的脚本 |
| `parameters` | 实际参数 |
| `unresolved_placeholders` | 未解析占位符 |

## 6. 样例试跑

```http
POST /qualityWorkflow/rules/trial-run
```

请求模型：`TrialRunRequest`

```json
{
  "setting_id": "setting-20260531190952-0001",
  "sample_rows": [
    {"id": "1", "mobile_phone": "13800138000"},
    {"id": "2", "mobile_phone": "12345"}
  ],
  "max_invalid_samples": 10
}
```

返回字段：

| 字段 | 说明 |
|---|---|
| `passed` | 是否通过试跑 |
| `total_rows` | 样例总行数 |
| `failure_count` | 失败行数 |
| `pass_rate` | 通过率 |
| `invalid_samples` | 异常样例 |
| `script_preview` | 脚本预览 |

## 7. 创建任务

```http
POST /qualityWorkflow/tasks
```

请求模型：`CreateQualityTaskRequest`

```json
{
  "task_name": "客户订单质量评价任务",
  "scope": {
    "data_source": "mysql",
    "table_fqn": "mysql.dw.public.customer_order",
    "table_name": "customer_order",
    "business_domain": "客户订单"
  },
  "rule_setting_ids": [
    "setting-20260531190952-0001",
    "setting-20260531190952-0002"
  ],
  "schedule": "manual",
  "scan_mode": "full",
  "parallelism": 2,
  "created_by": "admin"
}
```

## 8. 执行任务

```http
POST /qualityWorkflow/tasks/execute
```

请求模型：`ExecuteQualityTaskRequest`

```json
{
  "task_id": "task-20260531190952-0005",
  "batch_id": "batch_20260531",
  "sample_rows": [
    {"id": "1", "mobile_phone": "13800138000", "amount": "10.00"},
    {"id": "1", "mobile_phone": "12345", "amount": "10.123"}
  ]
}
```

返回字段：

| 字段 | 说明 |
|---|---|
| `run_id` | 执行批次 ID |
| `status` | `success`、`warning`、`blocked`、`failed` |
| `total_rules` | 规则总数 |
| `passed_rules` | 通过规则数 |
| `failed_rules` | 失败规则数 |
| `exception_rows` | 异常行数 |
| `blocked` | 是否阻断下游 |
| `blocked_reason` | 阻断原因 |
| `notifications` | 告警通知 |
| `issue_ids` | 自动生成的问题 ID |

## 9. 查询看板

```http
GET /qualityWorkflow/dashboard
```

请求模型：`DashboardQueryRequest`

```json
{
  "run_ids": ["run-20260531190952-0010"]
}
```

返回内容包括：

- 总体得分和质量等级。
- 六维评分。
- 规则通过率。
- 问题类型分布。
- 影响行数和下游对象。
- 执行趋势。
- 健康等级分布。

## 10. 查询质量问题

```http
GET /qualityWorkflow/issues
```

请求模型：`IssueQueryRequest`

| 字段 | 说明 |
|---|---|
| `batch_id` | 批次筛选 |
| `resource` | 资源筛选 |
| `status` | 问题状态 |
| `data_source` | 数据源 |
| `business_domain` | 业务域 |
| `dimension` | 评价维度 |
| `include_archived` | 是否包含已归档问题 |

## 11. 问题血缘分析

```http
GET /qualityWorkflow/issues/{issue_id}/lineage
```

返回内容包括：

- 问题资源。
- 根因说明。
- 上游溯源对象。
- 下游影响对象。
- 整改建议。

## 12. 更新问题状态

```http
POST /qualityWorkflow/issues/status
```

请求模型：`IssueStatusUpdateRequest`

```json
{
  "issue_id": "issue-20260531190952-0006",
  "status": "ticketed",
  "assignee": "数据责任人",
  "remediation": "修正手机号并重新执行检核",
  "review_notes": ""
}
```

支持状态：

| 状态 | 说明 |
|---|---|
| `discovered` | 已发现 |
| `alerted` | 已告警 |
| `ticketed` | 已生成工单 |
| `remediating` | 整改中 |
| `reviewing` | 复核中 |
| `closed` | 已关闭 |
| `archived` | 已归档 |

## 13. 计分规则归档

```http
POST /qualityWorkflow/scoring/archive
```

请求模型：`ScoringArchiveRequest`

```json
{
  "weights": {
    "normativity": 0.2,
    "completeness": 0.2,
    "accuracy": 0.15,
    "consistency": 0.15,
    "timeliness": 0.15,
    "accessibility": 0.15
  },
  "archived_by": "admin",
  "description": "2026版质量评价计分规则"
}
```

## 14. 生成报告

```http
GET /qualityWorkflow/report
```

请求模型：`WorkflowReportRequest`

| 字段 | 说明 |
|---|---|
| `run_id` | 指定执行批次，不传则生成全部批次报告 |
| `output_format` | `markdown` 或 `json` |

返回：

- `markdown`：返回 Markdown 文本。
- `json`：返回包含看板、执行批次、问题、计分归档的结构化对象。
