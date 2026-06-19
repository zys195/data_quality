# 数据质量规则库与智能推荐文档

本文档集用于说明 `data_quality` 中新增的质量评价规则库和质量规则智能推荐能力，便于方案汇报、开发交接和后续接口对接。

## 文档清单

| 文档 | 说明 |
|---|---|
| [质量评价规则库功能说明](质量评价规则库功能说明.md) | 规则库能力、内置规则、模板字段、接口与落地方式 |
| [质量规则智能推荐功能说明](质量规则智能推荐功能说明.md) | 智能推荐依据、推荐流程、确认入库流程 |
| [质量评价流程实现报告](质量评价流程实现报告.md) | 流程功能实现矩阵、新增规则、测试结果 |
| [质量评价流程API文档](质量评价流程API文档.md) | 参数设定、试跑、任务执行、看板、问题闭环、报告输出 API |
| [测试与演示说明](测试与演示说明.md) | 本地演示页面、测试接口、验证结果 |

## 代码位置

| 模块 | 文件 |
|---|---|
| 规则库核心服务 | `data_quality/rules/rule_library.py` |
| 规则库 API 门面 | `data_quality/api/rule_library_api.py` |
| 智能推荐核心服务 | `data_quality/rules/intelligent_rule_recommender.py` |
| 智能推荐 API 门面 | `data_quality/api/intelligent_rule_recommendation_api.py` |
| 质量评价流程服务 | `data_quality/workflow/quality_assessment_workflow.py` |
| 质量评价流程 API 门面 | `data_quality/api/quality_workflow_api.py` |
| 汇报演示接口 | `data_quality/demo/quality_rule_demo_server.py` |
| 流程冒烟测试 | `data_quality/demo/quality_workflow_smoke_test.py` |

## 当前实现结论

- 规则库已支持导入、新增、修改、删除、复用和脚本预览。
- 内置 95 条规则覆盖规范性、完整性、准确性、一致性、时效性、可访问性六大维度。
- 所有内置规则均提供 SQL、GE、ETL 三种落地脚本模板。
- 智能推荐已支持字段名、类型、样例值、说明、数据字典、业务域、分级分类和值域、血缘关系等多信号综合判断。
- 推荐结果支持人工确认、参数覆盖、阈值调整，并写入规则校验记录。
- 质量评价流程已支持参数设定、试跑、任务执行、六维看板、问题闭环、计分归档和报告输出。
