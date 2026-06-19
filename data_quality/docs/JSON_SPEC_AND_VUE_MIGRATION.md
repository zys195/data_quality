# 质量评价模块 JSON Spec 与 Vue 迁移说明

## 1. 本次调整

本次将质量评价规则库从“代码内置/可选文件存储”调整为“JSON Spec 优先存储”，并新增 Vue 前端工程，便于后续接入 Java/OM 类项目。

## 2. 规则库存储

规则 Spec 文件：

```text
data_quality/specs/quality_rule_library.spec.json
```

Spec 顶层结构：

```json
{
  "$schema": "https://om.local/specs/data-quality-rule-library.schema.json",
  "kind": "DataQualityRuleLibrarySpec",
  "apiVersion": "om.dataQuality/v1.0.0",
  "version": "1.0.0",
  "metadata": {},
  "dimensions": {},
  "rules": [],
  "reuse_counts": {}
}
```

Python 后端 `RuleLibrary()` 默认优先读取该 JSON Spec。若文件不存在，则使用 Python 内置规则模板作为兜底，并可导出生成 Spec。

## 3. Metadata 说明

`metadata` 中补充了：

| 字段 | 说明 |
|---|---|
| `storage.type` | 固定为 `JSON_SPEC` |
| `storage.default_path` | 默认规则 Spec 路径 |
| `compatible_backends` | Python、Java OM、OpenMetadata style API |
| `field_metadata` | 规则字段含义说明 |
| `om_alignment` | 与 OM Test Definition/TestCase 对齐说明 |

## 4. 新增/调整接口

| 接口 | 说明 |
|---|---|
| `GET /api/rules/spec` | 返回完整 JSON Spec |
| `GET /api/rules/metadata` | 返回规则库元数据、维度说明和统计 |
| `GET /api/rules` | 已补充 `scripts`、`parameters`、`threshold` 等前端需要字段 |

## 5. Vue 前端

Vue 工程位置：

```text
data_quality/vue_ui
```

常用命令：

```bash
npm install
npm run build
npm run dev
```

构建产物：

```text
data_quality/vue_ui/dist
```

Python 后端会自动托管 `dist`，因此构建后访问：

```text
http://127.0.0.1:8765/
```

即可打开 Vue 页面。

## 6. Java/OM 接入建议

推荐 Java 项目直接读取：

```text
data_quality/specs/quality_rule_library.spec.json
```

然后按以下对象拆分：

| Java 对象 | JSON Spec 来源 |
|---|---|
| `QualityRuleSpec` | `rules[]` |
| `QualityDimensionSpec` | `dimensions` |
| `RuleLibraryMetadata` | `metadata` |
| `RuleScriptTemplate` | `rules[].scripts` |
| `RuleThreshold` | `rules[].threshold` |

REST 路径建议对齐为：

```text
/om/data-quality/rules
/om/data-quality/rules/spec
/om/data-quality/recommendations
/om/data-quality/workflow/*
```

Vue 前端通过环境变量切换后端：

```text
VITE_API_BASE_URL=http://java-backend-host
```

或通过 Vite proxy 转发 `/api`。
