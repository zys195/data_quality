"""
质量规则库与智能推荐项目运行接口。

运行方式：
    python data_quality/demo/quality_rule_demo_server.py --port 8765

该脚本提供可直接导入数据并运行质量评价的轻量服务入口。它用最小依赖桩加载
data_quality 中的规则库、智能推荐和评价流程模块，不要求安装完整 OpenMetadata /
pydantic 环境。
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
import re
import sys
import types
from datetime import datetime
from enum import Enum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[2]
DATA_QUALITY = ROOT / "data_quality"
VUE_DIST = DATA_QUALITY / "vue_ui" / "dist"


def install_runtime_stubs() -> None:
    """Install minimal modules required by the standalone demo."""
    if "pydantic" not in sys.modules:
        pydantic = types.ModuleType("pydantic")

        class BaseModel:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

            def model_dump(self):
                return dict(self.__dict__)

        def Field(default=None, **kwargs):
            if "default_factory" in kwargs:
                return kwargs["default_factory"]()
            return None if default is Ellipsis else default

        pydantic.BaseModel = BaseModel
        pydantic.Field = Field
        sys.modules["pydantic"] = pydantic

    metadata = types.ModuleType("metadata")
    dq = types.ModuleType("metadata.data_quality")
    dim_pkg = types.ModuleType("metadata.data_quality.dimension")
    evaluator = types.ModuleType("metadata.data_quality.dimension.evaluator")
    models = types.ModuleType("metadata.data_quality.dimension.models")
    rules_pkg = types.ModuleType("metadata.data_quality.rules")
    workflow_pkg = types.ModuleType("metadata.data_quality.workflow")
    api_pkg = types.ModuleType("metadata.data_quality.api")

    class RuleSeverity(str, Enum):
        CRITICAL = "CRITICAL"
        HIGH = "HIGH"
        MEDIUM = "MEDIUM"
        LOW = "LOW"

    class QualityDimension(str, Enum):
        NORMATIVITY = "normativity"
        COMPLETENESS = "completeness"
        ACCURACY = "accuracy"
        CONSISTENCY = "consistency"
        TIMELINESS = "timeliness"
        ACCESSIBILITY = "accessibility"

    class QualityRuleCategory(str, Enum):
        FORMAT_CHECK = "format_check"
        ENUM_CHECK = "enum_check"
        REGEX_CHECK = "regex_check"
        NULL_CHECK = "null_check"
        FILL_RATE_CHECK = "fill_rate_check"
        REFERENCE_CHECK = "reference_check"
        RANGE_CHECK = "range_check"
        PRECISION_CHECK = "precision_check"
        DUPLICATE_CHECK = "duplicate_check"
        DIRTY_DATA_CHECK = "dirty_data_check"
        CROSS_TABLE_CHECK = "cross_table_check"
        CROSS_SYSTEM_CHECK = "cross_system_check"
        CALCULATION_CHECK = "calculation_check"
        UPDATE_LATENCY_CHECK = "update_latency_check"
        TIME_SEQUENCE_CHECK = "time_sequence_check"
        HISTORY_VALIDITY_CHECK = "history_validity_check"
        ACCESSIBLE_CHECK = "accessible_check"
        PERFORMANCE_CHECK = "performance_check"
        UNIQUENESS_CHECK = "uniqueness_check"

    evaluator.RuleSeverity = RuleSeverity
    models.QualityDimension = QualityDimension
    models.QualityRuleCategory = QualityRuleCategory
    models.get_dimension_by_test_definition = lambda _name: QualityDimension.NORMATIVITY

    sys.modules.update(
        {
            "metadata": metadata,
            "metadata.data_quality": dq,
            "metadata.data_quality.dimension": dim_pkg,
            "metadata.data_quality.dimension.evaluator": evaluator,
            "metadata.data_quality.dimension.models": models,
            "metadata.data_quality.rules": rules_pkg,
            "metadata.data_quality.workflow": workflow_pkg,
            "metadata.data_quality.api": api_pkg,
        }
    )

    sys.modules["metadata.generated"] = types.ModuleType("metadata.generated")
    sys.modules["metadata.generated.schema"] = types.ModuleType("metadata.generated.schema")
    sys.modules["metadata.generated.schema.entity"] = types.ModuleType(
        "metadata.generated.schema.entity"
    )
    sys.modules["metadata.generated.schema.entity.data"] = types.ModuleType(
        "metadata.generated.schema.entity.data"
    )
    table_mod = types.ModuleType("metadata.generated.schema.entity.data.table")

    class Column:
        pass

    class Table:
        pass

    table_mod.Column = Column
    table_mod.Table = Table
    sys.modules["metadata.generated.schema.entity.data.table"] = table_mod


def load_module(name: str, relative_path: str):
    path = DATA_QUALITY / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module: {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_demo_modules() -> Dict[str, Any]:
    install_runtime_stubs()
    modules = {}
    modules["rule_recommender"] = load_module(
        "metadata.data_quality.rules.rule_recommender",
        "rules/rule_recommender.py",
    )
    modules["rule_library"] = load_module(
        "metadata.data_quality.rules.rule_library",
        "rules/rule_library.py",
    )
    modules["workflow"] = load_module(
        "metadata.data_quality.workflow.quality_assessment_workflow",
        "workflow/quality_assessment_workflow.py",
    )
    modules["workflow_api"] = load_module(
        "metadata.data_quality.api.quality_workflow_api",
        "api/quality_workflow_api.py",
    )
    modules["rule_validator"] = load_module(
        "metadata.data_quality.rules.rule_validator",
        "rules/rule_validator.py",
    )
    modules["parameter_suggester"] = load_module(
        "metadata.data_quality.rules.parameter_suggester",
        "rules/parameter_suggester.py",
    )
    modules["intelligent"] = load_module(
        "metadata.data_quality.rules.intelligent_rule_recommender",
        "rules/intelligent_rule_recommender.py",
    )
    modules["api"] = load_module(
        "metadata.data_quality.api.intelligent_rule_recommendation_api",
        "api/intelligent_rule_recommendation_api.py",
    )
    return modules


MODULES = load_demo_modules()
RULE_LIBRARY = MODULES["rule_library"].RuleLibrary(load_builtin=True)
RECOMMENDER = MODULES["intelligent"].IntelligentRuleRecommender(RULE_LIBRARY)
WORKFLOW_MOD = MODULES["workflow"]
WORKFLOW_SERVICE = WORKFLOW_MOD.QualityAssessmentWorkflow(RULE_LIBRARY)
WORKFLOW_STATE: Dict[str, Any] = {
    "imported": False,
    "table_metadata": None,
    "recommendations": [],
    "recommendation_request_id": "",
    "confirmed_recommendations": [],
    "columns": [],
    "preview_rows": [],
    "configured": False,
    "scope": None,
    "settings": [],
    "task": None,
    "run": None,
    "task_options": {},
    "lineage_records": [],
    "sample_rows": [],
    "imported_at": "",
}


def reset_workflow_state() -> None:
    """Reset in-memory workflow runtime data."""
    global WORKFLOW_SERVICE
    WORKFLOW_SERVICE = WORKFLOW_MOD.QualityAssessmentWorkflow(RULE_LIBRARY)
    WORKFLOW_STATE.update(
        {
            "imported": False,
            "table_metadata": None,
            "recommendations": [],
            "recommendation_request_id": "",
            "confirmed_recommendations": [],
            "columns": [],
            "preview_rows": [],
            "configured": False,
            "scope": None,
            "settings": [],
            "task": None,
            "run": None,
            "task_options": {},
            "lineage_records": [],
            "sample_rows": [],
            "imported_at": "",
        }
    )


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _safe_float(value: Any) -> Optional[float]:
    if _is_empty(value):
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _get_first(mapping: Dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return default


def _semantic_text(name: str, description: str = "") -> str:
    return f"{name} {description}".lower()


def _detect_semantics(name: str, description: str = "") -> set:
    text = _semantic_text(name, description)
    patterns = {
        "phone": [r"phone", r"mobile", r"tel", r"手机号", r"电话", r"联系方式"],
        "id_card": [r"id[_-]?card", r"identity", r"cert", r"身份证", r"证件号"],
        "email": [r"email", r"mail", r"邮箱"],
        "amount": [r"amount", r"price", r"cost", r"fee", r"money", r"金额", r"价格", r"费用"],
        "quantity": [r"qty", r"quantity", r"count", r"num", r"hours?", r"数量", r"库存", r"工时"],
        "enum": [r"status", r"type", r"level", r"grade", r"flag", r"状态", r"类型", r"等级"],
        "date": [r"date", r"time", r"dt$", r"日期", r"时间"],
        "ip": [r"\bip\b", r"ipv4", r"ip地址"],
        "mac": [r"\bmac\b", r"物理地址"],
        "imei": [r"imei", r"设备号"],
        "plate": [r"plate", r"vehicle", r"car_no", r"车牌"],
        "url": [r"url", r"link", r"网址", r"链接"],
        "code": [r"code", r"编码", r"行政区划", r"sku", r"no$"],
        "id": [r"(^|[_-])id$", r"key$", r"uuid", r"主键", r"唯一键"],
        "text": [r"name", r"desc", r"address", r"名称", r"描述", r"地址"],
    }
    result = set()
    for semantic, regexes in patterns.items():
        if any(re.search(regex, text, re.IGNORECASE) for regex in regexes):
            result.add(semantic)
    if "id_card" in result:
        result.discard("id")
    return result


def _sample_patterns(values: Sequence[Any]) -> set:
    patterns = set()
    non_empty = [str(value).strip() for value in values if not _is_empty(value)]
    if not non_empty:
        return patterns
    if any(re.match(r"^1[3-9]\d{9}$", value) for value in non_empty):
        patterns.add("phone")
    if any(re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", value) for value in non_empty):
        patterns.add("email")
    if any(re.match(r"^[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[0-9Xx]$", value) for value in non_empty):
        patterns.add("id_card")
    if any(re.match(r"^((25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(25[0-5]|2[0-4]\d|[01]?\d\d?)$", value) for value in non_empty):
        patterns.add("ip")
    if any(re.match(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$", value) for value in non_empty):
        patterns.add("mac")
    if any(re.match(r"^\d{15}$", value) for value in non_empty):
        patterns.add("imei")
    if any(re.match(r"^https?://", value, re.IGNORECASE) for value in non_empty):
        patterns.add("url")
    return patterns


def _parse_csv_rows(csv_text: str) -> List[Dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(csv_text.strip("\ufeff\r\n")))
    if not reader.fieldnames:
        raise ValueError("CSV缺少表头")
    return [dict(row) for row in reader]


def _coerce_rows(rows: Any) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        raise ValueError("rows必须是对象数组")
    normalized: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"第{idx + 1}行不是JSON对象")
        normalized.append(
            {
                str(key).strip(): value
                for key, value in row.items()
                if str(key).strip()
            }
        )
    return normalized


def _column_names_from_payload(payload: Dict[str, Any], rows: Sequence[Dict[str, Any]]) -> List[str]:
    names: List[str] = []
    for item in payload.get("columns", []) or []:
        if isinstance(item, dict):
            name = _get_first(item, "name", "column_name", "field", default="")
        else:
            name = str(item)
        if name and name not in names:
            names.append(str(name))

    for row in rows:
        for name in row:
            if name not in names:
                names.append(name)
    return names


def _column_metadata_map(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for item in payload.get("columns", []) or []:
        if not isinstance(item, dict):
            continue
        name = _get_first(item, "name", "column_name", "field", default="")
        if name:
            result[str(name)] = item
    return result


def _infer_type(values: Sequence[Any]) -> Tuple[str, Optional[float], Optional[float]]:
    non_empty = [value for value in values if not _is_empty(value)]
    if not non_empty:
        return "varchar", None, None

    numbers = [_safe_float(value) for value in non_empty]
    if all(number is not None for number in numbers):
        numeric_values = [float(number) for number in numbers if number is not None]
        if all(float(number).is_integer() for number in numeric_values):
            return "int", min(numeric_values), max(numeric_values)
        return "decimal", min(numeric_values), max(numeric_values)

    date_pattern = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}([ T]\d{1,2}:\d{1,2}(:\d{1,2})?)?$")
    if all(date_pattern.match(str(value).strip()) for value in non_empty):
        return "datetime" if any(":" in str(value) for value in non_empty) else "date", None, None

    return "varchar", None, None


def _unique_ratio(values: Sequence[Any]) -> Optional[float]:
    non_empty = [str(value) for value in values if not _is_empty(value)]
    if not non_empty:
        return None
    return round(len(set(non_empty)) / len(non_empty), 4)


def _null_ratio(values: Sequence[Any], total_rows: int) -> Optional[float]:
    if total_rows <= 0:
        return None
    nulls = sum(1 for value in values if _is_empty(value))
    return round(nulls / total_rows, 4)


def _enum_values(values: Sequence[Any], semantics: set, meta: Dict[str, Any]) -> List[Any]:
    explicit = _get_first(meta, "enum_values", "allowed_values", default=[])
    if isinstance(explicit, str):
        return [item.strip().strip("'\"") for item in explicit.split(",") if item.strip()]
    if isinstance(explicit, list):
        return explicit

    non_empty = [value for value in values if not _is_empty(value)]
    unique_values = list(dict.fromkeys(non_empty))
    if "enum" in semantics and 1 < len(unique_values) <= 30:
        return unique_values
    if non_empty and 1 < len(unique_values) <= 20 and len(unique_values) / max(len(non_empty), 1) <= 0.4:
        return unique_values
    return []


def _build_lineage_hint(meta: Dict[str, Any]):
    intelligent = MODULES["intelligent"]
    lineage = meta.get("lineage") if isinstance(meta.get("lineage"), dict) else {}
    related_table = _get_first(meta, "related_table", "referenced_table", default="")
    related_column = _get_first(meta, "related_column", "referenced_column", default="")
    source_system = _get_first(meta, "source_system", default="")
    target_systems = meta.get("target_systems", [])
    if isinstance(target_systems, str):
        target_systems = [item.strip() for item in target_systems.split(",") if item.strip()]
    if not any([lineage, related_table, related_column, source_system, target_systems]):
        return None
    return intelligent.FieldLineageHint(
        upstream_fields=list(lineage.get("upstream_fields", [])),
        downstream_fields=list(lineage.get("downstream_fields", [])),
        source_system=str(lineage.get("source_system", source_system) or ""),
        target_systems=list(lineage.get("target_systems", target_systems) or []),
        related_table=str(lineage.get("related_table", related_table) or ""),
        related_column=str(lineage.get("related_column", related_column) or ""),
        transform_expression=str(lineage.get("transform_expression", "") or ""),
        relationship_type=str(lineage.get("relationship_type", "") or ""),
    )


def _build_dictionary(meta: Dict[str, Any], enum_values: List[Any]):
    intelligent = MODULES["intelligent"]
    dictionary = meta.get("dictionary") if isinstance(meta.get("dictionary"), dict) else {}
    allowed_values = dictionary.get("allowed_values", enum_values)
    return intelligent.DataDictionaryEntry(
        name=str(dictionary.get("name", meta.get("name", "")) or ""),
        display_name=str(dictionary.get("display_name", meta.get("display_name", "")) or ""),
        description=str(dictionary.get("description", meta.get("description", "")) or ""),
        allowed_values=list(allowed_values or []),
        value_descriptions=dict(dictionary.get("value_descriptions", {}) or {}),
        code_table=str(dictionary.get("code_table", meta.get("code_table", "")) or ""),
        regex=str(dictionary.get("regex", meta.get("regex", "")) or ""),
        min_value=_safe_float(dictionary.get("min_value", meta.get("min_value"))),
        max_value=_safe_float(dictionary.get("max_value", meta.get("max_value"))),
        min_length=int(dictionary.get("min_length", meta.get("min_length", 0)) or 0) or None,
        max_length=int(dictionary.get("max_length", meta.get("max_length", 0)) or 0) or None,
        required=bool(dictionary.get("required", meta.get("required", False))),
        unique=bool(dictionary.get("unique", meta.get("unique", False))),
    ) if dictionary or enum_values else None


def _build_table_metadata(
    payload: Dict[str, Any],
    rows: Sequence[Dict[str, Any]],
    fields: Sequence[str],
) -> Any:
    intelligent = MODULES["intelligent"]
    table_name = str(_get_first(payload, "table_name", "table", default="imported_table"))
    data_source = str(_get_first(payload, "data_source", "source", default="uploaded"))
    database = str(_get_first(payload, "database", "db", default=""))
    schema = str(_get_first(payload, "schema", default=""))
    table_fqn = str(
        _get_first(
            payload,
            "table_fqn",
            "fqn",
            default=".".join(part for part in [data_source, database, schema, table_name] if part),
        )
    )
    meta_by_name = _column_metadata_map(payload)
    total_rows = len(rows)
    columns = []

    for field in fields:
        values = [row.get(field) for row in rows]
        meta = meta_by_name.get(field, {})
        description = str(_get_first(meta, "description", "comment", "display_name", default=""))
        semantics = _detect_semantics(field, description)
        inferred_type, min_value, max_value = _infer_type(values)
        data_type = str(_get_first(meta, "data_type", "type", default=inferred_type))
        non_empty = [value for value in values if not _is_empty(value)]
        sample_values = list(non_empty[:20])
        semantics.update(_sample_patterns(sample_values))
        unique_ratio = _unique_ratio(values)
        null_ratio = _null_ratio(values, total_rows)
        max_length = max([len(str(value)) for value in non_empty], default=0) or None
        enum_values = _enum_values(values, semantics, meta)
        dictionary = _build_dictionary(meta, enum_values)
        lower_name = field.lower()
        is_primary_key = bool(
            meta.get("is_primary_key")
            or meta.get("primary_key")
            or lower_name in {"id", "uuid", f"{table_name.lower()}_id"}
            or ("主键" in description)
        )
        is_unique = bool(
            meta.get("is_unique")
            or meta.get("unique")
            or (unique_ratio is not None and unique_ratio >= 0.98 and bool(semantics & {"id", "phone", "email", "id_card"}))
        )
        is_foreign_key = bool(
            meta.get("is_foreign_key")
            or meta.get("foreign_key")
            or (lower_name.endswith("_id") and not is_primary_key)
        )
        nullable = bool(meta.get("nullable", True))
        if is_primary_key:
            nullable = False
        columns.append(
            intelligent.FieldMetadata(
                name=field,
                data_type=data_type,
                length=int(meta.get("length", max_length or 0) or 0) or None,
                nullable=nullable,
                is_primary_key=is_primary_key,
                is_foreign_key=is_foreign_key,
                is_unique=is_unique,
                description=description,
                comment=str(meta.get("comment", "")),
                business_domain=str(_get_first(meta, "business_domain", default=payload.get("business_domain", ""))),
                data_classification=str(_get_first(meta, "data_classification", default=payload.get("data_classification", ""))),
                security_level=str(meta.get("security_level", "")),
                tags=list(meta.get("tags", []) or []),
                sample_values=sample_values,
                enum_values=enum_values,
                min_value=_safe_float(meta.get("min_value")) if "min_value" in meta else min_value,
                max_value=_safe_float(meta.get("max_value")) if "max_value" in meta else max_value,
                null_ratio=null_ratio,
                unique_ratio=unique_ratio,
                dictionary=dictionary,
                lineage=_build_lineage_hint(meta),
                related_columns=dict(meta.get("related_columns", {}) or {}),
            )
        )

    return intelligent.TableMetadata(
        table_fqn=table_fqn,
        table_name=table_name,
        columns=columns,
        business_domain=str(payload.get("business_domain", "")),
        data_classification=str(payload.get("data_classification", "")),
        row_count=total_rows,
        tags=list(payload.get("tags", []) or []),
    )


def _build_scope(payload: Dict[str, Any], fields: Sequence[str], row_count: int) -> Any:
    table_name = str(_get_first(payload, "table_name", "table", default="imported_table"))
    data_source = str(_get_first(payload, "data_source", "source", default="uploaded"))
    database = str(_get_first(payload, "database", "db", default=""))
    schema = str(_get_first(payload, "schema", default=""))
    table_fqn = str(
        _get_first(
            payload,
            "table_fqn",
            "fqn",
            default=".".join(part for part in [data_source, database, schema, table_name] if part),
        )
    )
    return WORKFLOW_MOD.DataScope(
        data_source=data_source,
        database=database,
        schema=schema,
        table_fqn=table_fqn,
        table_name=table_name,
        fields=list(fields),
        subject_domain=str(payload.get("subject_domain", "")),
        business_domain=str(payload.get("business_domain", "")),
        batch_id=str(payload.get("batch_id") or f"batch_{datetime.now().strftime('%Y%m%d%H%M%S')}"),
        partition=str(payload.get("partition", "")),
        row_count=row_count,
        data_classification=str(payload.get("data_classification", "")),
    )


def parse_import_payload(payload: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str], Any, Any]:
    if not isinstance(payload, dict):
        raise ValueError("请求体必须是JSON对象")

    if payload.get("csv"):
        rows = _parse_csv_rows(str(payload["csv"]))
    elif "rows" in payload:
        rows = _coerce_rows(payload["rows"])
    else:
        raise ValueError("请提供rows数组或csv文本")

    fields = _column_names_from_payload(payload, rows)
    if not fields:
        raise ValueError("未识别到字段，请在columns或数据表头中提供字段名")
    normalized_rows = [{field: row.get(field) for field in fields} for row in rows]
    scope = _build_scope(payload, fields, len(normalized_rows))
    table_metadata = _build_table_metadata(payload, normalized_rows, fields)
    return normalized_rows, fields, scope, table_metadata


def _column_summaries(table_metadata: Any) -> List[Dict[str, Any]]:
    if not table_metadata:
        return []
    summaries = []
    for column in table_metadata.columns:
        summaries.append(
            {
                "name": column.name,
                "data_type": column.data_type,
                "length": column.length,
                "nullable": column.nullable,
                "is_primary_key": column.is_primary_key,
                "is_foreign_key": column.is_foreign_key,
                "is_unique": column.is_unique,
                "null_ratio": column.null_ratio,
                "unique_ratio": column.unique_ratio,
                "sample_values": list(column.sample_values[:5]),
                "enum_values": list(column.enum_values[:20]),
                "description": column.description,
            }
        )
    return summaries


def api_data_current() -> Dict[str, Any]:
    scope = WORKFLOW_STATE.get("scope")
    table_metadata = WORKFLOW_STATE.get("table_metadata")
    return {
        "imported": bool(WORKFLOW_STATE.get("imported")),
        "message": "已导入数据，可以运行质量评价流程" if WORKFLOW_STATE.get("imported") else "请先导入待评价数据",
        "imported_at": WORKFLOW_STATE.get("imported_at", ""),
        "scope": scope.to_dict() if scope else None,
        "row_count": len(WORKFLOW_STATE.get("sample_rows", [])),
        "columns": _column_summaries(table_metadata),
        "preview_rows": WORKFLOW_STATE.get("sample_rows", []),
        "configured": bool(WORKFLOW_STATE.get("configured")),
        "rule_setting_count": len(WORKFLOW_STATE.get("settings", [])),
        "confirmed_recommendation_count": len(WORKFLOW_STATE.get("confirmed_recommendations", [])),
    }


def api_data_import(payload: Dict[str, Any]) -> Dict[str, Any]:
    global WORKFLOW_SERVICE
    rows, fields, scope, table_metadata = parse_import_payload(payload)
    WORKFLOW_SERVICE = WORKFLOW_MOD.QualityAssessmentWorkflow(RULE_LIBRARY)
    WORKFLOW_STATE.update(
        {
            "imported": True,
            "table_metadata": table_metadata,
            "recommendations": [],
            "recommendation_request_id": "",
            "confirmed_recommendations": [],
            "columns": list(fields),
            "preview_rows": rows[:10],
            "configured": False,
            "scope": scope,
            "settings": [],
            "task": None,
            "run": None,
            "task_options": {},
            "lineage_records": [],
            "sample_rows": rows,
            "imported_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    current = api_data_current()
    return {
        "status": "imported",
        "message": "数据导入完成，已生成评价范围和字段画像",
        **current,
    }


EXECUTABLE_RECOMMENDATION_RULES = {
    "AUTO-EMAIL-FORMAT": "N-F08",
    "AUTO-UNIQUE": "C-F04",
    "AUTO-NUMERIC-PRECISION": "A-N03",
    "AUTO-DATE-FORMAT": "A-T02",
}


def _executable_rule_id(rec: Any) -> str:
    candidate = getattr(rec, "library_rule_id", None) or getattr(rec, "rule_id", "")
    rule = RULE_LIBRARY.get_rule(candidate) if candidate else None
    if rule and rule.enabled:
        return candidate
    mapped = EXECUTABLE_RECOMMENDATION_RULES.get(getattr(rec, "rule_id", ""))
    mapped_rule = RULE_LIBRARY.get_rule(mapped) if mapped else None
    return mapped if mapped_rule and mapped_rule.enabled else ""


def _recommend_current_table(refresh: bool = False) -> Tuple[str, List[Any]]:
    table_metadata = WORKFLOW_STATE.get("table_metadata")
    if not table_metadata:
        return "", []
    if WORKFLOW_STATE.get("recommendations") and not refresh:
        return WORKFLOW_STATE.get("recommendation_request_id", ""), WORKFLOW_STATE["recommendations"]
    recommendations = RECOMMENDER.recommend_table(table_metadata, min_confidence=0.6)
    request_id = f"rec_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    WORKFLOW_STATE["recommendations"] = recommendations
    WORKFLOW_STATE["recommendation_request_id"] = request_id
    return request_id, recommendations


def api_recommendations_confirm(payload: Dict[str, Any]) -> Dict[str, Any]:
    request_id, recommendations = _recommend_current_table(refresh=False)
    cached = {rec.recommendation_id: rec for rec in recommendations}
    raw_confirmations = payload.get("confirmations") if isinstance(payload, dict) else None
    if not raw_confirmations:
        raw_confirmations = [
            {"recommendation_id": rec.recommendation_id}
            for rec in recommendations
            if _executable_rule_id(rec)
        ][:10]

    confirmed = []
    skipped = []
    for item in raw_confirmations:
        if isinstance(item, str):
            item = {"recommendation_id": item}
        if not isinstance(item, dict) or item.get("enabled", True) is False:
            continue
        rec = cached.get(str(item.get("recommendation_id", "")))
        if not rec:
            skipped.append({"recommendation_id": item.get("recommendation_id"), "reason": "推荐结果不存在"})
            continue
        rule_id = str(item.get("rule_id") or _executable_rule_id(rec))
        if not rule_id:
            skipped.append({"recommendation_id": rec.recommendation_id, "reason": "该推荐暂未映射到可执行规则模板"})
            continue
        parameters = dict(getattr(rec, "parameters", {}) or {})
        parameters.update(item.get("parameter_overrides", {}) or {})
        confirmed.append(
            {
                "recommendation_id": rec.recommendation_id,
                "source_rule_id": rec.rule_id,
                "rule_id": rule_id,
                "display_name": rec.display_name,
                "column_name": rec.column_name or "",
                "parameters": parameters,
                "threshold_override": item.get("threshold_override") or {},
                "validation_level": item.get("validation_level") or rec.validation_level.value,
                "confirmed_by": payload.get("confirmed_by", "operator") if isinstance(payload, dict) else "operator",
                "confirmed_at": datetime.now().isoformat(timespec="seconds"),
            }
        )

    WORKFLOW_STATE["confirmed_recommendations"] = confirmed
    WORKFLOW_STATE["configured"] = False
    WORKFLOW_STATE["settings"] = []
    WORKFLOW_STATE["task"] = None
    WORKFLOW_STATE["run"] = None
    return {
        "status": "stored",
        "request_id": request_id,
        "stored_count": len(confirmed),
        "skipped_count": len(skipped),
        "confirmed_recommendations": confirmed,
        "skipped": skipped,
        "message": "推荐规则已确认入库，可进入参数设定和评价执行",
    }


def _quoted_allowed_values(values: Sequence[Any]) -> str:
    clean = [str(value).replace("'", "''") for value in values if not _is_empty(value)]
    return ", ".join(f"'{value}'" for value in dict.fromkeys(clean))


def _add_rule_config(
    configs: List[Dict[str, Any]],
    rule_id: str,
    column_name: str,
    validation_level: str = "",
    parameter_overrides: Optional[Dict[str, Any]] = None,
    threshold: Optional[Dict[str, Any]] = None,
    source: str = "metadata",
) -> None:
    rule = RULE_LIBRARY.get_rule(rule_id)
    if not column_name or not rule or not rule.enabled:
        return
    key = (rule_id, column_name)
    if any((item["rule_id"], item["column_name"]) == key for item in configs):
        return
    configs.append(
        {
            "rule_id": rule_id,
            "column_name": column_name,
            "validation_level": validation_level,
            "parameter_overrides": parameter_overrides or {},
            "threshold": threshold,
            "source": source,
        }
    )


def _default_rule_configs() -> List[Dict[str, Any]]:
    table_metadata = WORKFLOW_STATE.get("table_metadata")
    if not table_metadata:
        return []

    configs: List[Dict[str, Any]] = []
    for column in table_metadata.columns:
        semantics = _detect_semantics(column.name, column.description)
        semantics.update(_sample_patterns(column.sample_values))
        if column.is_primary_key or "id" in semantics:
            _add_rule_config(configs, "C-F04", column.name, "P0_BLOCKING")
            _add_rule_config(configs, "C-F01", column.name, "P0_BLOCKING")
        if "phone" in semantics:
            _add_rule_config(configs, "N-F02", column.name, "P1_WARNING")
            _add_rule_config(configs, "C-F01", column.name, "P1_WARNING")
        if "id_card" in semantics:
            _add_rule_config(configs, "N-F01", column.name, "P1_WARNING")
            _add_rule_config(configs, "C-F04", column.name, "P1_WARNING")
        if "email" in semantics:
            _add_rule_config(configs, "N-F08", column.name, "P1_WARNING")
        if "amount" in semantics or "quantity" in semantics or column.data_type.lower() in {"int", "decimal", "numeric", "float", "double"}:
            max_value = column.max_value if column.max_value is not None else 999999999
            _add_rule_config(
                configs,
                "A-N02",
                column.name,
                "P1_WARNING",
                {"min_value": "0", "max_value": str(max_value)},
            )
            if "amount" in semantics:
                _add_rule_config(configs, "A-N03", column.name, "P1_WARNING", {"decimal_scale": "2"})
        if "enum" in semantics or column.enum_values:
            allowed = _quoted_allowed_values(column.enum_values)
            if allowed:
                _add_rule_config(configs, "N-V01", column.name, "P1_WARNING", {"allowed_values": allowed})
        if "ip" in semantics:
            _add_rule_config(configs, "N-F06", column.name, "P1_WARNING")
        if "mac" in semantics:
            _add_rule_config(configs, "N-F05", column.name, "P1_WARNING")
        if "imei" in semantics:
            _add_rule_config(configs, "N-F04", column.name, "P1_WARNING")
        if "plate" in semantics:
            _add_rule_config(configs, "N-F03", column.name, "P1_WARNING")
        if "url" in semantics:
            _add_rule_config(configs, "N-F07", column.name, "P1_WARNING")
        if "code" in semantics:
            _add_rule_config(configs, "N-C01", column.name, "P1_WARNING")
        if "text" in semantics and column.data_type.lower() in {"varchar", "char", "text", "string"}:
            _add_rule_config(configs, "C-F03", column.name, "P1_WARNING")

    if not configs and table_metadata.columns:
        first = table_metadata.columns[0]
        _add_rule_config(configs, "C-F01", first.name, "P1_WARNING")
    return configs[:10]


def _rule_configs_from_confirmed() -> List[Dict[str, Any]]:
    configs: List[Dict[str, Any]] = []
    for item in WORKFLOW_STATE.get("confirmed_recommendations", [])[:10]:
        _add_rule_config(
            configs,
            item["rule_id"],
            item["column_name"],
            item.get("validation_level", ""),
            item.get("parameters", {}),
            item.get("threshold_override") or None,
            source="confirmed_recommendation",
        )
    return configs


def demo_table():
    intelligent = MODULES["intelligent"]
    return intelligent.TableMetadata(
        table_fqn="mysql.default.customer_order",
        table_name="customer_order",
        business_domain="客户与订单",
        columns=[
            intelligent.FieldMetadata(
                name="user_id",
                data_type="varchar",
                is_primary_key=True,
                nullable=False,
                unique_ratio=1.0,
                description="用户主键",
            ),
            intelligent.FieldMetadata(
                name="mobile_phone",
                data_type="varchar",
                description="客户手机号",
                sample_values=["13800138000000000", "13900139000000000", "13700137000000000"],
                null_ratio=0.0,
            ),
            intelligent.FieldMetadata(
                name="id_card",
                data_type="varchar",
                description="身份证号码",
                sample_values=["110101199001011234", "110101198812123456"],
            ),
            intelligent.FieldMetadata(
                name="birthday",
                data_type="date",
                description="出生日期",
            ),
            intelligent.FieldMetadata(
                name="gender",
                data_type="varchar",
                description="性别",
                enum_values=["男", "女"],
            ),
            intelligent.FieldMetadata(
                name="order_amount",
                data_type="decimal",
                description="订单金额",
                min_value=0,
                max_value=999999,
            ),
            intelligent.FieldMetadata(
                name="order_status",
                data_type="varchar",
                description="订单状态",
                dictionary=intelligent.DataDictionaryEntry(
                    allowed_values=["待支付", "已支付", "已取消"],
                    required=True,
                ),
            ),
            intelligent.FieldMetadata(
                name="dept_id",
                data_type="varchar",
                is_foreign_key=True,
                description="部门外键",
                lineage=intelligent.FieldLineageHint(
                    related_table="dim_dept",
                    related_column="dept_id",
                ),
            ),
            intelligent.FieldMetadata(
                name="crm_customer_name",
                data_type="varchar",
                description="CRM客户名称",
                lineage=intelligent.FieldLineageHint(
                    source_system="crm",
                    target_systems=["dw.customer_order"],
                    relationship_type="sync",
                ),
            ),
        ],
    )


def api_summary() -> Dict[str, Any]:
    summary = RULE_LIBRARY.get_summary().to_dict()
    return {
        "title": "质量规则库概览",
        "summary": summary,
        "links": [
            "/api/rules",
            "/api/recommendations",
            "/api/preview?rule_id=N-F02&table=customer_order&column=mobile_phone",
            "/api/report",
        ],
    }


def api_rules(query: Optional[Dict[str, List[str]]] = None) -> Dict[str, Any]:
    keyword = ""
    dimension = ""
    if query:
        keyword = query.get("keyword", query.get("q", [""]))[0]
        dimension = query.get("dimension", [""])[0]
    rules = RULE_LIBRARY.list_rules(
        include_disabled=False,
        keyword=keyword or None,
        dimension=dimension or None,
    )
    return {
        "total": len(rules),
        "keyword": keyword,
        "dimension": dimension,
        "rules": [
            {
                "rule_id": rule.rule_id,
                "name": rule.display_name,
                "display_name": rule.display_name,
                "dimension": rule.dimension.value,
                "dimension_zh": rule.dimension_zh,
                "problem_category": rule.problem_category,
                "severity": rule.severity.value,
                "validation_level": rule.validation_level.value,
                "engines": [engine.value for engine in rule.scripts],
                "scripts": {
                    engine.value: script.to_dict() for engine, script in rule.scripts.items()
                },
                "parameters": dict(rule.parameters),
                "threshold": rule.threshold.to_dict(),
                "core_definition": rule.core_definition,
                "source_type": rule.source_type.value,
                "responsible_role": rule.responsible_role,
                "remediation_suggestion": rule.remediation_suggestion,
                "issue_strategy": rule.issue_strategy,
                "status": rule.status.value,
                "tags": list(rule.tags),
            }
            for rule in rules
        ],
    }


def api_rules_spec() -> Dict[str, Any]:
    return RULE_LIBRARY.export_rules(include_disabled=True)


def api_rules_metadata() -> Dict[str, Any]:
    return {
        "metadata": RULE_LIBRARY.get_metadata(),
        "dimensions": MODULES["rule_library"].build_dimension_metadata(),
        "summary": RULE_LIBRARY.get_summary().to_dict(),
    }


def _invalidate_rule_runtime(reset_recommendations: bool = False) -> None:
    """Clear generated workflow state after rule library changes."""
    updates = {
        "configured": False,
        "settings": [],
        "task": None,
        "run": None,
        "task_options": {},
    }
    if reset_recommendations:
        updates.update(
            {
                "recommendations": [],
                "recommendation_request_id": "",
                "confirmed_recommendations": [],
            }
        )
    WORKFLOW_STATE.update(updates)


def api_rule_create(payload: Dict[str, Any]) -> Dict[str, Any]:
    rule_id = str(payload.get("rule_id") or f"CUSTOM-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    display_name = str(payload.get("display_name") or payload.get("name") or "自定义质量规则")
    dimension = str(payload.get("dimension") or "normativity")
    sql = str(
        payload.get("sql")
        or "SELECT * FROM {{ table_name }} WHERE {{ column_name }} IS NULL"
    )
    rule = RULE_LIBRARY.create_rule(
        {
            "rule_id": rule_id,
            "name": rule_id.lower().replace("-", "_"),
            "display_name": display_name,
            "dimension": dimension,
            "source_type": str(payload.get("source_type") or "CUSTOM"),
            "problem_category": str(payload.get("problem_category") or "自定义问题"),
            "core_definition": str(payload.get("core_definition") or "由页面新增的自定义质量评价规则。"),
            "applicability": {"entity_type": "COLUMN"},
            "scripts": {
                "SQL": {
                    "expression": sql,
                    "language": "SQL",
                    "description": "返回不符合规则的数据行。",
                },
                "GE": {
                    "expression": "ge_df.expect_query_to_return_no_rows(query=\"{{ sql }}\")",
                    "language": "Python/Great Expectations",
                    "description": "新增规则的GE执行占位模板。",
                },
                "ETL": {
                    "expression": '{"action":"custom_rule","sql":"{{ sql }}","on_fail":"issue_table"}',
                    "language": "JSON DSL",
                    "description": "新增规则的ETL执行占位模板。",
                },
            },
            "parameters": payload.get("parameters") or {},
            "threshold": payload.get("threshold") or {"pass_rate": 1.0},
            "validation_level": str(payload.get("validation_level") or "P1_WARNING"),
            "severity": str(payload.get("severity") or "MEDIUM"),
            "responsible_role": str(payload.get("responsible_role") or "数据责任人"),
            "remediation_suggestion": str(payload.get("remediation_suggestion") or "核查源数据、修正规则参数并重新执行检核。"),
            "issue_strategy": str(payload.get("issue_strategy") or "不符合规则的数据进入问题库，并生成整改工单。"),
            "tags": list(payload.get("tags") or ["自定义规则"]),
        },
        overwrite=False,
    )
    _invalidate_rule_runtime()
    return {"status": "created", "rule": rule.to_dict(), "message": "规则已新增"}


def api_rule_import(payload: Dict[str, Any]) -> Dict[str, Any]:
    rules_payload: Any = payload
    if "rule_id" in payload and "rules" not in payload:
        rules_payload = [payload]
    overwrite = bool(payload.get("overwrite", False)) if isinstance(payload, dict) else False
    result = RULE_LIBRARY.import_rules(rules_payload, overwrite=overwrite, persist=True)
    _invalidate_rule_runtime(reset_recommendations=True)
    summary = RULE_LIBRARY.get_summary().to_dict()
    return {
        "status": "imported",
        "message": "规则导入完成",
        "result": result.to_dict(),
        "summary": summary,
    }


def api_rule_update(payload: Dict[str, Any]) -> Dict[str, Any]:
    rule_id = str(payload.get("rule_id") or "").strip()
    if not rule_id:
        raise ValueError("rule_id不能为空")

    updates = payload.get("updates")
    if not isinstance(updates, dict):
        updates = {
            key: value
            for key, value in payload.items()
            if key
            not in {
                "rule_id",
                "id",
            }
            and value not in (None, "")
        }
    if not updates:
        raise ValueError("updates不能为空")

    rule = RULE_LIBRARY.update_rule(rule_id, updates)
    _invalidate_rule_runtime(reset_recommendations=True)
    return {"status": "updated", "rule": rule.to_dict(), "message": "规则已修改"}


def api_rule_delete(payload: Dict[str, Any]) -> Dict[str, Any]:
    rule_id = str(payload.get("rule_id") or "")
    if not rule_id:
        raise ValueError("rule_id不能为空")
    deleted = RULE_LIBRARY.delete_rule(rule_id, soft_delete=True)
    if not deleted:
        raise ValueError(f"规则不存在: {rule_id}")
    _invalidate_rule_runtime(reset_recommendations=True)
    return {"status": "deleted", "rule_id": rule_id, "message": "规则已删除"}


def api_rule_reuse(payload: Dict[str, Any]) -> Dict[str, Any]:
    rule_id = str(payload.get("rule_id") or "").strip()
    if not rule_id:
        raise ValueError("rule_id不能为空")

    target = {
        "table_name": str(payload.get("table_name") or payload.get("table") or "").strip(),
        "column_name": str(payload.get("column_name") or payload.get("column") or "").strip(),
    }
    if not target["table_name"]:
        scope = WORKFLOW_STATE.get("scope")
        if scope:
            target["table_name"] = scope.table_name
    if not target["column_name"]:
        scope = WORKFLOW_STATE.get("scope")
        if scope and scope.fields:
            target["column_name"] = scope.fields[0]

    plan = RULE_LIBRARY.reuse_rule(
        rule_id,
        target,
        engine=str(payload.get("engine") or "SQL"),
        parameter_overrides=payload.get("parameter_overrides") or {},
        test_case_name=payload.get("test_case_name") or None,
    )
    return {"status": "reused", "message": "规则复用配置已生成", "plan": plan.to_dict()}


def api_recommendations(query: Optional[Dict[str, List[str]]] = None) -> Dict[str, Any]:
    table_metadata = WORKFLOW_STATE.get("table_metadata")
    if not table_metadata:
        return {
            "request_id": "",
            "imported": False,
            "table": "",
            "table_name": "",
            "row_count": 0,
            "total_columns": 0,
            "total": 0,
            "executable_count": 0,
            "confirmed_count": 0,
            "message": "请先在数据导入页面导入实际数据后再生成智能推荐",
            "recommendations": [],
        }
    refresh_requested = _query_bool(query, "refresh", False)
    refresh = refresh_requested or not WORKFLOW_STATE.get("recommendations")
    request_id, recommendations = _recommend_current_table(refresh=refresh)
    executable_count = sum(1 for rec in recommendations if _executable_rule_id(rec))
    return {
        "request_id": request_id,
        "imported": bool(WORKFLOW_STATE.get("imported")),
        "table": table_metadata.table_fqn,
        "table_name": table_metadata.table_name,
        "row_count": getattr(table_metadata, "row_count", 0),
        "total_columns": len(table_metadata.columns),
        "total": len(recommendations),
        "executable_count": executable_count,
        "confirmed_count": len(WORKFLOW_STATE.get("confirmed_recommendations", [])),
        "refreshed": refresh,
        "message": "已基于当前导入数据生成推荐" if WORKFLOW_STATE.get("imported") else "当前展示内置示例画像，请在数据导入页导入实际数据后运行",
        "recommendations": [rec.to_dict() for rec in recommendations],
    }


def api_preview(query: Dict[str, List[str]]) -> Dict[str, Any]:
    rule_id = query.get("rule_id", ["N-F02"])[0]
    table = query.get("table", ["customer_order"])[0]
    column = query.get("column", ["mobile_phone"])[0]
    preview = RULE_LIBRARY.preview_script(
        rule_id,
        "SQL",
        {"table_name": table, "column_name": column},
    )
    return preview.to_dict()


def ensure_workflow_configured() -> None:
    if WORKFLOW_STATE["configured"]:
        return
    if not WORKFLOW_STATE.get("scope"):
        raise ValueError("请先在数据导入页面导入待评价数据")

    scope = WORKFLOW_STATE["scope"]
    rule_configs = _rule_configs_from_confirmed() or _default_rule_configs()
    if not rule_configs:
        raise ValueError("未能为当前数据集匹配可执行规则，请补充字段元数据或手工确认推荐规则")

    settings = []
    for config in rule_configs:
        settings.append(
            WORKFLOW_SERVICE.configure_rule_parameters(
                config["rule_id"],
                scope,
                target_column=config["column_name"],
                validation_level=config.get("validation_level") or None,
                threshold=config.get("threshold"),
                parameter_overrides=config.get("parameter_overrides") or {},
            )
        )
    WORKFLOW_STATE.update(
        {
            "configured": True,
            "scope": scope,
            "settings": settings,
        }
    )


def api_workflow_overview() -> Dict[str, Any]:
    summary = RULE_LIBRARY.get_summary().to_dict()
    current = api_data_current()
    return {
        "title": "质量评价工作台",
        "process": [
            {"id": 0, "name": "数据导入", "status": "已导入" if current["imported"] else "待导入", "api": "/api/data/import"},
            {"id": 1, "name": "质量评价规则库", "status": "可运行", "api": "/api/rules"},
            {"id": 2, "name": "质量规则智能推荐", "status": "可运行" if current["imported"] else "待导入", "api": "/api/recommendations"},
            {"id": 3, "name": "规则参数设定", "status": "可运行" if current["imported"] else "待导入", "api": "/api/workflow/configure"},
            {"id": 4, "name": "质量评价实施", "status": "可运行" if current["imported"] else "待导入", "api": "/api/workflow/execute"},
            {"id": 5, "name": "六个维度的展示", "status": "可运行" if current["imported"] else "待导入", "api": "/api/workflow/dashboard"},
            {"id": 6, "name": "质量问题分析", "status": "可运行" if current["imported"] else "待导入", "api": "/api/workflow/issues"},
            {"id": 7, "name": "计分规则", "status": "可运行" if current["imported"] else "待导入", "api": "/api/workflow/archive"},
            {"id": 8, "name": "质量问题溯源", "status": "可运行" if current["imported"] else "待导入", "api": "/api/workflow/lineage"},
        ],
        "current_dataset": current,
        "summary": {
            "total_rules": summary["total_rules"],
            "active_rules": summary["active_rules"],
            "dimensions": summary["by_dimension"],
            "engines": summary["by_engine"],
        },
    }


def api_workflow_configure() -> Dict[str, Any]:
    ensure_workflow_configured()
    previews = [
        WORKFLOW_SERVICE.preview_rule_script(setting.setting_id).to_dict()
        for setting in WORKFLOW_STATE["settings"]
    ]
    return {
        "message": "已完成规则参数设定",
        "scope": WORKFLOW_STATE["scope"].to_dict(),
        "settings": [setting.to_dict() for setting in WORKFLOW_STATE["settings"]],
        "script_previews": previews,
    }


def _normalize_parameter_overrides(raw: Any) -> Dict[str, Any]:
    if raw in (None, ""):
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"参数JSON解析失败: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError("参数配置必须是JSON对象")
        return value
    raise ValueError("参数配置必须是JSON对象")


def _normalize_setting_updates(item: Dict[str, Any]) -> Dict[str, Any]:
    updates: Dict[str, Any] = {}
    for key in (
        "target_table",
        "target_column",
        "validation_level",
        "execution_engine",
        "condition",
        "responsible_role",
        "enabled",
        "weight",
    ):
        if key in item:
            updates[key] = item[key]

    if "parameter_overrides" in item:
        updates["parameter_overrides"] = _normalize_parameter_overrides(
            item.get("parameter_overrides")
        )

    threshold_keys = {
        "operator",
        "expected_value",
        "pass_rate",
        "unit",
        "description",
    }
    threshold = item.get("threshold") if isinstance(item.get("threshold"), dict) else {}
    threshold = dict(threshold or {})
    for key in threshold_keys:
        form_key = f"threshold_{key}"
        if form_key in item:
            threshold[key] = item[form_key]
    if threshold:
        if "pass_rate" in threshold:
            try:
                threshold["pass_rate"] = float(threshold["pass_rate"])
            except (TypeError, ValueError):
                raise ValueError("通过率阈值必须是数字")
        updates["threshold"] = threshold
    return updates


def api_workflow_settings_update(payload: Dict[str, Any]) -> Dict[str, Any]:
    ensure_workflow_configured()
    raw_settings = payload.get("settings", [])
    if isinstance(raw_settings, dict):
        raw_settings = [raw_settings]
    if not isinstance(raw_settings, list):
        raise ValueError("settings必须是数组")

    by_id = {setting.setting_id: setting for setting in WORKFLOW_STATE["settings"]}
    updated_settings = []
    errors = []
    for index, item in enumerate(raw_settings):
        if not isinstance(item, dict):
            errors.append(f"第{index + 1}项不是对象")
            continue
        setting_id = str(item.get("setting_id") or "").strip()
        if setting_id not in by_id:
            errors.append(f"规则参数不存在: {setting_id or index + 1}")
            continue
        try:
            updated = WORKFLOW_SERVICE.update_rule_parameter_setting(
                setting_id,
                _normalize_setting_updates(item),
            )
            updated_settings.append(updated)
        except Exception as exc:  # noqa: BLE001 - 批量保存需要逐条反馈
            errors.append(f"{setting_id}: {exc}")

    if errors:
        raise ValueError("; ".join(errors))

    WORKFLOW_STATE["settings"] = WORKFLOW_SERVICE.get_settings()
    WORKFLOW_STATE["task"] = None
    WORKFLOW_STATE["run"] = None
    previews = [
        WORKFLOW_SERVICE.preview_rule_script(setting.setting_id).to_dict()
        for setting in WORKFLOW_STATE["settings"]
    ]
    return {
        "status": "updated",
        "message": "参数配置已保存，请重新试跑验证后执行评价任务",
        "updated_count": len(updated_settings),
        "settings": [setting.to_dict() for setting in WORKFLOW_STATE["settings"]],
        "script_previews": previews,
    }


def api_workflow_trial() -> Dict[str, Any]:
    ensure_workflow_configured()
    settings_by_id = {setting.setting_id: setting for setting in WORKFLOW_STATE["settings"]}
    results = []
    for setting in WORKFLOW_STATE["settings"]:
        if not setting.enabled:
            continue
        result = WORKFLOW_SERVICE.trial_run(
            setting.setting_id,
            sample_rows=WORKFLOW_STATE["sample_rows"],
        ).to_dict()
        setting_data = settings_by_id[setting.setting_id].to_dict()
        result["dimension"] = setting_data.get("dimension", "")
        result["dimension_zh"] = setting_data.get("dimension_zh", "")
        results.append(result)
    return {
        "message": "已完成导入数据试跑验证",
        "sample_rows": WORKFLOW_STATE["sample_rows"],
        "trial_results": results,
    }


def _workflow_task_options(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = payload or WORKFLOW_STATE.get("task_options") or {}
    schedule = str(payload.get("schedule") or payload.get("schedule_type") or "manual")
    scan_mode = str(payload.get("scan_mode") or "full")
    dependency = str(payload.get("dependency") or "")
    try:
        parallelism = int(payload.get("parallelism") or 2)
    except (TypeError, ValueError):
        parallelism = 2
    return {
        "schedule": schedule if schedule in {"manual", "cron", "dependency"} else "manual",
        "scan_mode": scan_mode if scan_mode in {"full", "incremental"} else "full",
        "dependency": dependency,
        "parallelism": max(1, min(parallelism, 16)),
        "created_by": str(payload.get("created_by") or "operator"),
    }


def api_workflow_execute(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ensure_workflow_configured()
    if not payload and WORKFLOW_STATE.get("run") and WORKFLOW_STATE.get("task"):
        return {
            "message": "已读取最近一次质量评价任务执行结果",
            "task": WORKFLOW_STATE["task"].to_dict(),
            "run": WORKFLOW_STATE["run"].to_dict(),
        }
    if payload:
        WORKFLOW_STATE["task_options"] = _workflow_task_options(payload)
        WORKFLOW_STATE["task"] = None
        WORKFLOW_STATE["run"] = None
    options = _workflow_task_options()
    if not WORKFLOW_STATE["task"]:
        task = WORKFLOW_SERVICE.create_task(
            task_name=f"{WORKFLOW_STATE['scope'].table_name or '导入数据'}质量评价任务",
            scope=WORKFLOW_STATE["scope"],
            rule_setting_ids=[
                setting.setting_id for setting in WORKFLOW_STATE["settings"]
            ],
            schedule=options["schedule"],
            scan_mode=options["scan_mode"],
            dependency=options["dependency"],
            parallelism=options["parallelism"],
            created_by=options["created_by"],
        )
        WORKFLOW_STATE["task"] = task
    run = WORKFLOW_SERVICE.execute_task(
        WORKFLOW_STATE["task"].task_id,
        sample_rows=WORKFLOW_STATE["sample_rows"],
        batch_id=WORKFLOW_STATE["scope"].batch_id,
    )
    WORKFLOW_STATE["run"] = run
    return {
        "message": "已完成质量评价任务执行",
        "task": WORKFLOW_STATE["task"].to_dict(),
        "run": run.to_dict(),
    }


def ensure_workflow_executed() -> None:
    ensure_workflow_configured()
    if not WORKFLOW_STATE["run"]:
        api_workflow_execute()


def api_workflow_dashboard() -> Dict[str, Any]:
    ensure_workflow_executed()
    run = WORKFLOW_STATE["run"]
    return WORKFLOW_SERVICE.build_dashboard(run_ids=[run.run_id]).to_dict()


def _first_query_value(query: Optional[Dict[str, List[str]]], key: str, default: str = "") -> str:
    if not query:
        return default
    values = query.get(key)
    if not values:
        return default
    return str(values[0]).strip()


def _query_bool(query: Optional[Dict[str, List[str]]], key: str, default: bool = False) -> bool:
    value = _first_query_value(query, key, "")
    if value == "":
        return default
    return value.lower() in {"1", "true", "yes", "on", "是"}


def _normalize_lineage_records(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_records = payload.get("lineage_records", payload.get("records", payload.get("lineage", [])))
    if isinstance(raw_records, dict):
        raw_records = [raw_records]
    if not isinstance(raw_records, list):
        raise ValueError("lineage_records必须是数组")

    records: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_records, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"第{index}条血缘记录必须是对象")
        target_table = str(item.get("target_table") or item.get("table_name") or item.get("resource") or "").strip()
        target_column = str(item.get("target_column") or item.get("column_name") or "").strip()
        if not target_table:
            raise ValueError(f"第{index}条血缘记录缺少target_table")
        record = {
            "lineage_id": str(item.get("lineage_id") or item.get("id") or f"lineage_{index}"),
            "target_table": target_table,
            "target_column": target_column,
            "source_system": str(item.get("source_system") or item.get("source") or "").strip(),
            "source_table": str(item.get("source_table") or item.get("upstream_table") or "").strip(),
            "source_column": str(item.get("source_column") or item.get("upstream_column") or "").strip(),
            "etl_task": str(item.get("etl_task") or item.get("process") or item.get("job_name") or "").strip(),
            "transform_rule": str(item.get("transform_rule") or item.get("mapping_rule") or "").strip(),
            "downstream_objects": list(item.get("downstream_objects") or item.get("downstream") or []),
            "owner": str(item.get("owner") or item.get("responsible_role") or "数据责任人").strip(),
            "updated_at": str(item.get("updated_at") or datetime.now().isoformat(timespec="seconds")),
        }
        records.append(record)
    return records


def api_lineage_import(payload: Dict[str, Any]) -> Dict[str, Any]:
    records = _normalize_lineage_records(payload)
    WORKFLOW_STATE["lineage_records"] = records
    return {
        "status": "imported",
        "message": "真实血缘数据已导入，质量问题溯源将基于该血缘数据展示",
        "total": len(records),
        "lineage_records": records,
    }


def api_lineage_current() -> Dict[str, Any]:
    records = WORKFLOW_STATE.get("lineage_records", [])
    return {
        "imported": bool(records),
        "total": len(records),
        "lineage_records": records,
    }


def _matches_lineage_record(issue: Any, record: Dict[str, Any]) -> bool:
    issue_resource = str(getattr(issue, "resource", "") or "")
    issue_table = issue_resource.split(".")[-1] if issue_resource else ""
    target_table = str(record.get("target_table") or "")
    target_column = str(record.get("target_column") or "")
    issue_column = str(getattr(issue, "column_name", "") or "")
    table_match = target_table in {issue_resource, issue_table} or issue_resource.endswith(target_table)
    column_match = not target_column or not issue_column or target_column == issue_column
    return table_match and column_match


def _lineage_from_real_records(issue: Any) -> Dict[str, Any]:
    records = [
        record
        for record in WORKFLOW_STATE.get("lineage_records", [])
        if _matches_lineage_record(issue, record)
    ]
    if not records:
        return {
            "available": False,
            "source": "real_lineage_required",
            "message": "未导入匹配当前问题的真实血缘数据，暂不展示模拟溯源结果。",
            "issue_id": getattr(issue, "issue_id", ""),
            "resource": getattr(issue, "resource", ""),
            "column_name": getattr(issue, "column_name", ""),
            "records": [],
            "upstream_trace": [],
            "downstream_impacts": [],
            "recommendations": ["请通过 /api/lineage/import 导入真实字段级血缘数据后再查看溯源。"],
        }
    upstream = []
    downstream = []
    for record in records:
        source = ".".join(
            part for part in [record.get("source_system"), record.get("source_table"), record.get("source_column")] if part
        )
        if source:
            upstream.append(source)
        downstream.extend(str(item) for item in record.get("downstream_objects", []) if item)
    return {
        "available": True,
        "source": "real_lineage",
        "issue_id": getattr(issue, "issue_id", ""),
        "resource": getattr(issue, "resource", ""),
        "column_name": getattr(issue, "column_name", ""),
        "matched_count": len(records),
        "records": records,
        "upstream_trace": list(dict.fromkeys(upstream)),
        "downstream_impacts": list(dict.fromkeys(downstream)),
        "root_cause": "基于真实血缘记录定位上游来源和加工链路，请结合异常样例核查源表、字段映射或ETL任务。",
        "recommendations": [
            "优先核查匹配血缘记录中的源表、源字段和ETL任务。",
            "对下游对象标记质量风险，整改并复核后解除影响提示。",
        ],
    }


def api_workflow_issues(query: Optional[Dict[str, List[str]]] = None) -> Dict[str, Any]:
    ensure_workflow_executed()
    run = WORKFLOW_STATE["run"]
    filters = {
        "batch_id": _first_query_value(query, "batch_id"),
        "resource": _first_query_value(query, "resource"),
        "status": _first_query_value(query, "status") or None,
        "data_source": _first_query_value(query, "data_source"),
        "business_domain": _first_query_value(query, "business_domain"),
        "dimension": _first_query_value(query, "dimension") or None,
        "include_archived": _query_bool(query, "include_archived", True),
    }
    issues = WORKFLOW_SERVICE.query_issues(**filters)
    if _first_query_value(query, "issue_scope", "current") != "all":
        current_issue_ids = set(run.issue_ids)
        issues = [issue for issue in issues if issue.issue_id in current_issue_ids]
    first_lineage = _lineage_from_real_records(issues[0]) if issues else {}
    return {
        "total": len(issues),
        "filters": filters,
        "issue_scope": _first_query_value(query, "issue_scope", "current"),
        "run_id": run.run_id,
        "current_run_issue_count": len(run.issue_ids),
        "issues": [issue.to_dict() for issue in issues],
        "lineage_sample": first_lineage,
    }


def api_workflow_issue_update(payload: Dict[str, Any]) -> Dict[str, Any]:
    ensure_workflow_executed()
    issue_id = str(payload.get("issue_id") or "").strip()
    if not issue_id:
        raise ValueError("issue_id不能为空")
    status = str(payload.get("status") or "ticketed")
    issue = WORKFLOW_SERVICE.update_issue_status(
        issue_id=issue_id,
        status=status,
        assignee=str(payload.get("assignee") or ""),
        remediation=str(payload.get("remediation") or ""),
        review_notes=str(payload.get("review_notes") or ""),
    )
    return {
        "status": "updated",
        "message": "质量问题工单状态已更新",
        "issue": issue.to_dict(),
        "lineage": _lineage_from_real_records(issue),
    }


def _normalize_scoring_thresholds(raw: Any) -> Optional[Dict[str, Tuple[float, float]]]:
    if not isinstance(raw, dict) or not raw:
        return None
    normalized: Dict[str, Tuple[float, float]] = {}
    for name, bounds in raw.items():
        if isinstance(bounds, dict):
            low = bounds.get("min", bounds.get("from", 0))
            high = bounds.get("max", bounds.get("to", 100))
        elif isinstance(bounds, (list, tuple)) and len(bounds) >= 2:
            low, high = bounds[0], bounds[1]
        else:
            continue
        normalized[str(name)] = (float(low), float(high))
    return normalized or None


def api_workflow_archive(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ensure_workflow_executed()
    payload = payload or {}
    archive = WORKFLOW_SERVICE.archive_scoring_rules(
        weights=payload.get("weights") or None,
        grade_thresholds=_normalize_scoring_thresholds(payload.get("grade_thresholds")),
        archived_by=str(payload.get("archived_by") or "operator"),
        description=str(payload.get("description") or "项目运行计分规则归档"),
    )
    dashboard = api_workflow_dashboard()
    return {"status": "archived", "archive": archive.to_dict(), "dashboard": dashboard}


def api_workflow_lineage(query: Optional[Dict[str, List[str]]] = None) -> Dict[str, Any]:
    ensure_workflow_executed()
    run = WORKFLOW_STATE["run"]
    issue_id = _first_query_value(query, "issue_id")
    issues = WORKFLOW_SERVICE.query_issues(include_archived=True)
    if _first_query_value(query, "issue_scope", "current") != "all":
        current_issue_ids = set(run.issue_ids)
        issues = [issue for issue in issues if issue.issue_id in current_issue_ids]
    if not issue_id and issues:
        issue_id = issues[0].issue_id
    if not issue_id:
        return {
            "total": 0,
            "selected_issue_id": "",
            "issues": [],
            "lineage": {},
            "message": "当前执行结果未产生质量问题",
        }
    issue = next((item for item in issues if item.issue_id == issue_id), None)
    if not issue:
        raise ValueError(f"质量问题不存在: {issue_id}")
    lineage = _lineage_from_real_records(issue)
    return {
        "total": len(issues),
        "selected_issue_id": issue_id,
        "issues": [issue.to_dict() for issue in issues],
        "lineage_imported": bool(WORKFLOW_STATE.get("lineage_records")),
        "lineage_record_count": len(WORKFLOW_STATE.get("lineage_records", [])),
        "lineage": lineage,
    }


def api_workflow_report() -> Dict[str, Any]:
    ensure_workflow_executed()
    run = WORKFLOW_STATE["run"]
    report_md = WORKFLOW_SERVICE.generate_workflow_report(run_id=run.run_id)
    report_json = WORKFLOW_SERVICE.generate_workflow_report(
        run_id=run.run_id,
        output_format="json",
    )
    return {
        "markdown": report_md,
        "json": report_json,
    }


def api_report() -> Dict[str, Any]:
    summary = RULE_LIBRARY.get_summary().to_dict()
    recommendations = WORKFLOW_STATE.get("recommendations") or []
    dimension_summary: Dict[str, int] = {}
    for rec in recommendations:
        dimension_summary[rec.dimension.value] = dimension_summary.get(rec.dimension.value, 0) + 1
    return {
        "report_name": "质量规则智能推荐运行报告",
        "run_result": "READY",
        "rule_library": {
            "total_rules": summary["total_rules"],
            "active_rules": summary["active_rules"],
            "by_dimension": summary["by_dimension"],
            "by_engine": summary["by_engine"],
        },
        "recommendation": {
            "current_table": WORKFLOW_STATE["scope"].table_fqn if WORKFLOW_STATE.get("scope") else "",
            "total_recommendations": len(recommendations),
            "by_dimension": dimension_summary,
            "covered_cases": [
                "手机号格式/非空/唯一性",
                "身份证格式/出生日期一致性/性别一致性",
                "金额非负和值域",
                "枚举值域",
                "外键关联完整性",
                "跨系统一致性",
            ],
        },
    }


def api_run_test() -> Dict[str, Any]:
    """Run service health checks on demand for the report page."""
    checks: List[Dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = "") -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
        if not passed:
            raise AssertionError(f"{name}: {detail}")

    started_at = __import__("datetime").datetime.now()
    try:
        summary = RULE_LIBRARY.get_summary().to_dict()
        check("规则库内置规则数量", summary["total_rules"] >= 95, summary["total_rules"])
        whitepaper_extended_rule_ids = set()
        for prefix in ["N", "C", "A", "CS", "T", "AC"]:
            whitepaper_extended_rule_ids.update(
                f"{prefix}-W{i:02d}" for i in range(1, 11)
            )
        check(
            "白皮书扩展规则覆盖",
            whitepaper_extended_rule_ids.issubset(
                {rule.rule_id for rule in RULE_LIBRARY.list_rules()}
            ),
            sorted(whitepaper_extended_rule_ids),
        )
        check(
            "六维评价规则覆盖",
            set(summary["by_dimension"])
            == {
                "normativity",
                "completeness",
                "accuracy",
                "consistency",
                "timeliness",
                "accessibility",
            },
            summary["by_dimension"],
        )
        check(
            "SQL/GE/ETL执行方式覆盖",
            all(summary["by_engine"].get(engine, 0) > 0 for engine in ["SQL", "GE", "ETL"]),
            summary["by_engine"],
        )

        preview = RULE_LIBRARY.preview_script(
            "N-F02",
            "SQL",
            {"table_name": "customer_order", "column_name": "mobile_phone"},
        ).to_dict()
        check(
            "手机号规则脚本预览",
            "mobile_phone" in preview["rendered_expression"]
            and "REGEXP" in preview["rendered_expression"],
            preview["rendered_expression"],
        )
        check(
            "手机号规则放宽为17位数字",
            "\\d{17}" in preview["expression"] or "\\d{17}" in preview["rendered_expression"],
            preview["rendered_expression"],
        )

        recommendations = RECOMMENDER.recommend_table(demo_table(), min_confidence=0.6)
        rule_ids = {rec.rule_id for rec in recommendations}
        expected_rules = {
            "N-F02",
            "N-F01",
            "AUTO-IDCARD-BIRTHDAY-CONSISTENCY",
            "A-N02",
            "N-V01",
            "C-L01",
            "CS-S01",
        }
        check("智能推荐关键规则命中", expected_rules.issubset(rule_ids), sorted(rule_ids))
        check("智能推荐结果数量", len(recommendations) >= 10, len(recommendations))
        check(
            "推荐结果包含脚本预览",
            any(rec.script_preview for rec in recommendations),
            "至少一条推荐含SQL预览",
        )

        ended_at = __import__("datetime").datetime.now()
        return {
            "test_result": "PASS",
            "started_at": started_at.isoformat(timespec="seconds"),
            "ended_at": ended_at.isoformat(timespec="seconds"),
            "duration_ms": int((ended_at - started_at).total_seconds() * 1000),
            "total_checks": len(checks),
            "passed_checks": sum(1 for item in checks if item["passed"]),
            "failed_checks": sum(1 for item in checks if not item["passed"]),
            "checks": checks,
        }
    except Exception as exc:
        ended_at = __import__("datetime").datetime.now()
        return {
            "test_result": "FAIL",
            "started_at": started_at.isoformat(timespec="seconds"),
            "ended_at": ended_at.isoformat(timespec="seconds"),
            "duration_ms": int((ended_at - started_at).total_seconds() * 1000),
            "total_checks": len(checks),
            "passed_checks": sum(1 for item in checks if item["passed"]),
            "failed_checks": sum(1 for item in checks if not item["passed"]),
            "checks": checks,
            "error": str(exc),
        }


def page_html(page: str = "rules") -> str:
    template = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>质量评价工作台</title>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Arial, 'Microsoft YaHei', sans-serif; background: #f5f7fa; color: #1f2937; }
    header { background: #fff; border-bottom: 1px solid #d9dee8; padding: 16px 24px; position: sticky; top: 0; z-index: 5; }
    h1 { font-size: 23px; margin: 0 0 6px; letter-spacing: 0; }
    h2 { font-size: 18px; margin: 0 0 10px; letter-spacing: 0; }
    h3 { font-size: 15px; margin: 0 0 10px; letter-spacing: 0; }
    .sub { color: #667085; font-size: 14px; }
    .app { display: grid; grid-template-columns: 248px minmax(0, 1fr); gap: 16px; padding: 16px 24px 28px; }
    nav { background: #fff; border: 1px solid #d9dee8; border-radius: 8px; padding: 10px; height: fit-content; position: sticky; top: 86px; }
    .nav-title { color: #667085; font-size: 12px; margin: 2px 8px 8px; }
    .nav-link { display: grid; grid-template-columns: 26px 1fr; align-items: center; gap: 9px; color: #1f2937; text-decoration: none; padding: 10px 8px; border-radius: 6px; margin-bottom: 2px; min-height: 46px; }
    .nav-link:hover { background: #f2f5f9; }
    .nav-link.active { background: #e0ecff; color: #1d4ed8; font-weight: 700; }
    .nav-no { width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; background: #eef2f7; color: #475467; font-size: 12px; font-weight: 700; }
    .nav-link.active .nav-no { background: #1d4ed8; color: #fff; }
    main { min-width: 0; display: grid; gap: 14px; }
    .page-head { background: #fff; border: 1px solid #d9dee8; border-radius: 8px; padding: 16px; }
    section { background: #fff; border: 1px solid #d9dee8; border-radius: 8px; padding: 16px; }
    .toolbar { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
    button { border: 1px solid #1d4ed8; background: #1d4ed8; color: white; border-radius: 6px; padding: 8px 12px; cursor: pointer; font-size: 13px; min-height: 36px; }
    button.secondary { background: #ffffff; color: #1d4ed8; }
    button.warning { border-color: #b45309; background: #b45309; }
    button.danger { border-color: #dc2626; background: #dc2626; }
    button.tiny { min-height: 30px; padding: 5px 8px; font-size: 12px; }
    button:disabled { opacity: .55; cursor: wait; }
    .stats { display: grid; grid-template-columns: repeat(4, minmax(130px, 1fr)); gap: 10px; }
    .metric { border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; background: #fbfcfe; min-height: 82px; }
    .metric-label { color: #667085; font-size: 12px; }
    .metric-value { font-size: 26px; font-weight: 800; margin-top: 8px; color: #111827; }
    .metric-foot { color: #667085; font-size: 12px; margin-top: 4px; }
    .two-col { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(320px, .85fr); gap: 14px; }
    .three-col { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
    .panel { border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; background: #ffffff; }
    .business-note { border: 1px solid #bfdbfe; background: #eff6ff; color: #1e3a8a; border-radius: 8px; padding: 10px 12px; font-size: 13px; line-height: 1.55; margin-bottom: 12px; }
    .business-params { border: 1px solid #e5e7eb; background: #fbfcfe; border-radius: 8px; padding: 12px; margin-top: 12px; }
    .business-params h4 { font-size: 14px; margin: 0 0 10px; color: #111827; letter-spacing: 0; }
    .help-text { color: #667085; font-size: 12px; line-height: 1.45; margin-top: 5px; }
    .business-textarea { min-height: 88px; font-family: Arial, 'Microsoft YaHei', sans-serif; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { padding: 9px 10px; border-bottom: 1px solid #e5e7eb; text-align: left; vertical-align: top; }
    th { color: #475467; background: #f8fafc; font-weight: 700; }
    .badge { display: inline-flex; align-items: center; border-radius: 999px; padding: 2px 8px; font-size: 12px; font-weight: 700; background: #e0f2fe; color: #075985; }
    .badge.green { background: #dcfce7; color: #166534; }
    .badge.red { background: #fee2e2; color: #991b1b; }
    .badge.amber { background: #fef3c7; color: #92400e; }
    .badge.gray { background: #eef2f7; color: #344054; }
    .dimension-control { display: grid; gap: 10px; margin-top: 12px; }
    .dimension-title { color: #344054; font-size: 13px; font-weight: 700; }
    .dimension-tabs { display: flex; flex-wrap: wrap; gap: 8px; }
    .dim-tab { border: 1px solid #cbd5e1; background: #ffffff; color: #344054; min-height: 34px; padding: 7px 10px; }
    .dim-tab:hover { border-color: #1d4ed8; color: #1d4ed8; background: #f8fbff; }
    .dim-tab.active { border-color: #1d4ed8; background: #1d4ed8; color: #ffffff; }
    .dimension-summary { display: grid; grid-template-columns: repeat(6, minmax(110px, 1fr)); gap: 8px; }
    .dim-card { border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px; background: #fbfcfe; }
    .dim-card.active { border-color: #1d4ed8; background: #eff6ff; }
    .dim-card-label { color: #475467; font-size: 12px; font-weight: 700; }
    .dim-card-value { color: #111827; font-size: 22px; font-weight: 800; margin-top: 4px; }
    .dim-card-foot { color: #667085; font-size: 12px; margin-top: 2px; }
    .rule-create-grid { display: grid; grid-template-columns: minmax(0, .8fr) minmax(0, 1.2fr); gap: 14px; align-items: start; }
    .dim-choice-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
    .dim-choice { text-align: left; border: 1px solid #cbd5e1; background: #ffffff; color: #344054; border-radius: 8px; padding: 10px; min-height: 74px; }
    .dim-choice strong { display: block; color: #111827; font-size: 15px; margin-bottom: 4px; }
    .dim-choice span { display: block; color: #667085; font-size: 12px; line-height: 1.35; }
    .dim-choice.active { border-color: #1d4ed8; background: #eff6ff; color: #1d4ed8; }
    .dim-choice.active strong { color: #1d4ed8; }
    .form-section-title { color: #344054; font-size: 14px; font-weight: 800; margin: 0 0 10px; }
    .compact-textarea { min-height: 118px; }
    details.tech-detail { border: 1px dashed #cbd5e1; border-radius: 8px; padding: 10px 12px; background: #f8fafc; margin-top: 12px; }
    details.tech-detail summary { cursor: pointer; color: #1d4ed8; font-weight: 700; font-size: 13px; }
    details.tech-detail pre { margin-top: 10px; min-height: 120px; }
    .progress { height: 10px; background: #eef2f7; border-radius: 999px; overflow: hidden; min-width: 120px; }
    .bar { height: 100%; background: #16a34a; width: 0%; }
    .bar.warn { background: #d97706; }
    .bar.bad { background: #dc2626; }
    pre { background: #111827; color: #d1fae5; padding: 14px; border-radius: 8px; overflow: auto; min-height: 220px; margin: 0; font-size: 12px; }
    .json-view { min-height: 420px; }
    .status { display: none; margin-top: 12px; padding: 10px 12px; border-radius: 8px; background: #ecfdf5; border: 1px solid #a7f3d0; color: #166534; font-size: 13px; }
    .status.fail { background: #fef2f2; border-color: #fecaca; color: #991b1b; }
    .muted { color: #667085; font-size: 13px; }
    label { display: block; font-size: 13px; font-weight: 700; color: #344054; margin: 0 0 6px; }
    textarea, input, select { width: 100%; border: 1px solid #cbd5e1; border-radius: 6px; padding: 9px 10px; font: 13px Arial, 'Microsoft YaHei', sans-serif; background: #fff; color: #1f2937; }
    textarea { min-height: 260px; resize: vertical; font-family: Consolas, Monaco, monospace; line-height: 1.45; }
    textarea.flash, input.flash { border-color: #1d4ed8; box-shadow: 0 0 0 3px rgba(37, 99, 235, .16); }
    .form-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
    .field { min-width: 0; }
    .search-row { display: grid; grid-template-columns: minmax(220px, 1fr) auto auto; gap: 8px; align-items: end; }
    .row-actions { display: flex; flex-wrap: wrap; gap: 6px; }
    .pager { display: flex; align-items: center; justify-content: flex-end; gap: 8px; margin-top: 12px; color: #667085; font-size: 13px; }
    .pager button { min-height: 30px; padding: 5px 9px; }
    .pager button:disabled { background: #eef2f7; border-color: #d9dee8; color: #98a2b3; cursor: default; }
    .chart-grid { display: grid; grid-template-columns: minmax(260px, .9fr) minmax(360px, 1.1fr); gap: 14px; align-items: stretch; }
    .chart-box { border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; background: #fbfcfe; min-height: 280px; }
    canvas { display: block; width: 100%; max-width: 100%; height: 240px; }
    .list { display: grid; gap: 8px; }
    .list-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; border-bottom: 1px solid #eef1f5; padding: 8px 0; }
    .mono { font-family: Consolas, Monaco, monospace; }
    .empty { color: #667085; padding: 18px; border: 1px dashed #cbd5e1; border-radius: 8px; background: #f8fafc; }
    @media (max-width: 980px) {
      .app { grid-template-columns: 1fr; padding: 12px; }
      nav { position: static; }
      .stats, .two-col, .three-col, .chart-grid, .search-row, .dimension-summary, .rule-create-grid, .dim-choice-grid { grid-template-columns: 1fr; }
      header { padding: 14px 16px; }
    }
  </style>
</head>
<body>
  <header>
    <h1>质量评价工作台</h1>
    <div id="status" class="status"></div>
  </header>

  <div class="app">
    <nav>
      <div class="nav-title">功能页面</div>
      <a class="nav-link" data-page="import" href="/import"><span class="nav-no">0</span><span>数据导入</span></a>
      <a class="nav-link" data-page="rules" href="/rules"><span class="nav-no">1</span><span>质量评价规则库</span></a>
      <a class="nav-link" data-page="recommend" href="/recommend"><span class="nav-no">2</span><span>质量规则智能推荐</span></a>
      <a class="nav-link" data-page="parameters" href="/parameters"><span class="nav-no">3</span><span>规则参数设定</span></a>
      <a class="nav-link" data-page="execution" href="/execution"><span class="nav-no">4</span><span>质量评价实施</span></a>
      <a class="nav-link" data-page="dashboard" href="/dashboard"><span class="nav-no">5</span><span>六个维度的展示</span></a>
      <a class="nav-link" data-page="issues" href="/issues"><span class="nav-no">6</span><span>质量问题分析</span></a>
      <a class="nav-link" data-page="scoring" href="/scoring"><span class="nav-no">7</span><span>计分规则</span></a>
      <a class="nav-link" data-page="lineage" href="/lineage"><span class="nav-no">8</span><span>质量问题溯源</span></a>
    </nav>

    <main>
      <div class="page-head">
        <h2 id="pageTitle"></h2>
        <div class="muted" id="pageDesc"></div>
        <div class="toolbar" id="pageActions"></div>
      </div>
      <div id="content"></div>
      <pre id="output" class="json-view" style="display:none"></pre>
    </main>
  </div>

  <script>
    const currentPage = "__PAGE__";
    const pages = {
      import: { title: '0 数据导入', desc: '导入待评价表数据，系统自动生成评价范围、字段画像和数据预览。' },
      rules: { title: '1 质量评价规则库', desc: '统一管理标准规则、业务规则、技术规则和自定义规则。' },
      recommend: { title: '2 质量规则智能推荐', desc: '根据元数据、样例值、字典、业务域和血缘自动推荐适用规则。' },
      parameters: { title: '3 规则参数设定', desc: '把规则模板配置到具体表字段，并调整阈值、级别、执行方式。' },
      execution: { title: '4 质量评价实施', desc: '执行质量评价任务，记录通过、失败、异常行、阻断和告警。' },
      dashboard: { title: '5 六个维度的展示', desc: '按规范性、完整性、准确性、一致性、时效性、可访问性展示质量结果。' },
      issues: { title: '6 质量问题分析', desc: '分析失败规则形成的问题、责任人、整改建议和下游影响。' },
      scoring: { title: '7 计分规则', desc: '维护六维质量得分权重、等级阈值和归档记录，支撑最终质量等级判定。' },
      lineage: { title: '8 质量问题溯源', desc: '按问题记录查看上游来源、下游影响、根因提示和整改建议。' }
    };

    const dimName = {
      normativity: '规范性',
      completeness: '完整性',
      accuracy: '准确性',
      consistency: '一致性',
      timeliness: '时效性',
      accessibility: '可访问性'
    };

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, function(ch) {
        return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]);
      });
    }

    function escapeJs(value) {
      return String(value ?? '').replace(/[^0-9A-Za-z_.:-]/g, '_');
    }

    function badge(text, type) {
      return `<span class="badge ${type || 'gray'}">${escapeHtml(text)}</span>`;
    }

    const PAGE_SIZE = 10;
    const pageState = {};
    const issueFilters = {};
    const dimOrder = Object.keys(dimName);
    const dimensionFilters = {
      rules: '',
      recommendations: '',
      parameters: '',
      trial: '',
      execution: ''
    };

    function normalizeDimension(value) {
      const text = String(value ?? '').trim();
      if (!text) return '';
      const index = Number(text);
      if (Number.isInteger(index) && index >= 1 && index <= dimOrder.length) {
        return dimOrder[index - 1];
      }
      const lower = text.toLowerCase();
      const byKey = dimOrder.find(key => key.toLowerCase() === lower);
      if (byKey) return byKey;
      const byName = dimOrder.find(key => dimName[key] === text);
      return byName || '';
    }

    function getDimensionKey(item) {
      if (!item) return '';
      if (item.dimension && dimName[item.dimension]) return item.dimension;
      const zh = item.dimension_zh || item.dimensionName || item.dimension_label || '';
      const byName = dimOrder.find(key => dimName[key] === zh);
      return byName || item.dimension || '';
    }

    function dimensionLabel(item) {
      const key = getDimensionKey(item);
      return dimName[key] || item?.dimension_zh || item?.dimension || '-';
    }

    function filterByDimension(rows, dimension) {
      const list = Array.isArray(rows) ? rows : [];
      return dimension ? list.filter(item => getDimensionKey(item) === dimension) : list;
    }

    function dimensionCounts(rows) {
      const counts = Object.fromEntries(dimOrder.map(key => [key, 0]));
      (Array.isArray(rows) ? rows : []).forEach(item => {
        const key = getDimensionKey(item);
        if (Object.prototype.hasOwnProperty.call(counts, key)) {
          counts[key] += 1;
        }
      });
      return counts;
    }

    function dimensionSummaryHtml(rows, unit = '条') {
      const counts = dimensionCounts(rows);
      const total = Object.values(counts).reduce((sum, value) => sum + value, 0);
      return `
        <div class="dimension-summary">
          ${dimOrder.map(key => {
            const active = counts[key] > 0 ? 'active' : '';
            const ratio = total ? Math.round(counts[key] * 100 / total) : 0;
            return `<div class="dim-card ${active}">
              <div class="dim-card-label">${dimName[key]}</div>
              <div class="dim-card-value">${counts[key]}</div>
              <div class="dim-card-foot">${ratio}% · ${unit}</div>
            </div>`;
          }).join('')}
        </div>`;
    }

    function dimensionTabsHtml(scope, rows, loaderName, title = '按六维分类') {
      const active = scope === 'issues' ? (issueFilters.dimension || '') : (dimensionFilters[scope] || '');
      const counts = dimensionCounts(rows);
      const total = (Array.isArray(rows) ? rows : []).length;
      const tab = (key, label, count) => `
        <button class="dim-tab ${active === key ? 'active' : ''}" onclick="setDimensionFilter('${scope}', '${key}', '${loaderName}')">
          ${escapeHtml(label)} ${count}
        </button>`;
      return `
        <div class="dimension-control">
          <div class="dimension-title">${escapeHtml(title)}</div>
          <div class="dimension-tabs">
            ${tab('', '全部', total)}
            ${dimOrder.map(key => tab(key, dimName[key], counts[key])).join('')}
          </div>
        </div>`;
    }

    function setDimensionFilter(scope, dimension, loaderName) {
      if (scope === 'issues') {
        issueFilters.dimension = dimension;
        pageState.issues = 1;
      } else {
        dimensionFilters[scope] = dimension;
        pageState[scope] = 1;
      }
      const loader = globalThis[loaderName] || window[loaderName];
      if (typeof loader === 'function') {
        const feedback = `已切换到${dimension ? dimName[dimension] : '全部维度'}`;
        if (loaderName === 'loadRecommendations') {
          loader(false, feedback);
        } else {
          loader(feedback);
        }
      }
    }

    function dimensionPromptText(title) {
      return `${title}\\n${dimOrder.map((key, index) => `${index + 1}. ${dimName[key]} (${key})`).join('\\n')}`;
    }

    function safeDomId(value) {
      return String(value ?? '').replace(/[^0-9A-Za-z_-]/g, '_');
    }

    function validationLevelLabel(level) {
      const labels = {
        P0_BLOCKING: '强校验（不通过需阻断或立即处理）',
        P1_WARNING: '告警校验（生成质量问题）',
        P2_MONITORING: '监控校验（仅统计观察）'
      };
      return labels[level] || level || '-';
    }

    function validationLevelBadge(level) {
      const color = level === 'P0_BLOCKING' ? 'red' : (level === 'P2_MONITORING' ? 'gray' : 'amber');
      return badge(validationLevelLabel(level), color);
    }

    function validationLevelOptions(selected) {
      return ['P1_WARNING', 'P0_BLOCKING', 'P2_MONITORING']
        .map(level => `<option value="${level}" ${selected === level ? 'selected' : ''}>${validationLevelLabel(level)}</option>`)
        .join('');
    }

    function boolFromValue(value, fallback = false) {
      if (value === undefined || value === null || value === '') return fallback;
      if (typeof value === 'boolean') return value;
      const text = String(value).trim().toLowerCase();
      if (['true', '1', 'yes', 'y', '是', '必须', '必填'].includes(text)) return true;
      if (['false', '0', 'no', 'n', '否', '允许', '非必填'].includes(text)) return false;
      return fallback;
    }

    function numberFromInput(id, fallback = 0) {
      const el = document.getElementById(id);
      if (!el || el.value === '') return Number(fallback);
      const parsed = Number(el.value);
      return Number.isFinite(parsed) ? parsed : Number(fallback);
    }

    function textFromInput(id, fallback = '') {
      const el = document.getElementById(id);
      return el ? String(el.value ?? '').trim() : String(fallback ?? '');
    }

    function percentFromRate(rate) {
      const value = Number(rate ?? 1);
      return Math.round((Number.isFinite(value) ? value : 1) * 10000) / 100;
    }

    function rateFromPercentInput(id, fallbackRate = 1) {
      const percent = numberFromInput(id, percentFromRate(fallbackRate));
      return Math.max(0, Math.min(100, percent)) / 100;
    }

    function parseBusinessList(value) {
      if (Array.isArray(value)) {
        return value.map(item => String(item ?? '').trim()).filter(Boolean);
      }
      const text = String(value ?? '').trim();
      if (!text || text.startsWith('${')) return [];
      return text
        .split(/[\\n,，、]+/)
        .map(item => item.trim().replace(/^['"]|['"]$/g, ''))
        .filter(item => item && !item.startsWith('${'));
    }

    function sqlLiteralList(values) {
      return parseBusinessList(values)
        .map(item => `'${String(item).replace(/'/g, "''")}'`)
        .join(',');
    }

    function domainPatternList(value) {
      return parseBusinessList(value)
        .map(item => item.replace(/[^A-Za-z0-9.-]/g, '').split('.').filter(Boolean).join('[.]'))
        .filter(Boolean);
    }

    function parameterEditorKind(setting) {
      const ruleId = String(setting?.rule_id || '');
      const params = setting?.parameter_overrides || {};
      const text = `${ruleId} ${setting?.target_column || ''}`.toLowerCase();
      if (['C-F01', 'C-F02', 'C-F03'].includes(ruleId) || /required|not_null|null|blank|空值/.test(ruleId.toLowerCase())) return 'required';
      if (ruleId === 'C-F04') return 'unique';
      if (ruleId === 'N-F02') return 'phone';
      if (ruleId === 'N-F01') return 'id_card';
      if (ruleId === 'N-F08') return 'email';
      if (ruleId === 'N-V01' || params.allowed_values !== undefined) return 'enum';
      if (ruleId === 'A-N03' || params.decimal_scale !== undefined) return 'decimal';
      if (ruleId === 'A-L01' || params.min_length !== undefined || params.max_length !== undefined) return 'length';
      if (['A-N02', 'A-W01', 'A-W02', 'A-W03', 'A-W04'].includes(ruleId) || params.min_value !== undefined || params.max_value !== undefined) return 'range';
      if (/phone|mobile|tel|手机号|电话|联系电话/.test(text)) return 'phone';
      if (/id_card|identity|cert|身份证|证件号/.test(text)) return 'id_card';
      if (/email|mail|邮箱|电子邮件/.test(text)) return 'email';
      if (/status|type|flag|level|状态|类型|等级/.test(text)) return 'enum';
      if (/unique|唯一|主键/.test(text)) return 'unique';
      if (params.regex !== undefined) return 'format';
      return 'generic';
    }

    function parameterEditorTitle(kind, setting) {
      const titles = {
        phone: '手机号规则要求',
        id_card: '身份证号规则要求',
        email: '邮箱规则要求',
        enum: '枚举取值要求',
        decimal: '金额/数值精度要求',
        length: '字段长度要求',
        range: '数值范围要求',
        required: '必填完整性要求',
        unique: '唯一性要求',
        format: '字段格式要求',
        generic: '规则业务要求'
      };
      return titles[kind] || `规则 ${setting.rule_id}`;
    }

    function businessParameterSummary(setting) {
      const params = setting?.parameter_overrides || {};
      const kind = parameterEditorKind(setting);
      if (kind === 'phone') {
        return `手机号 ${params.phone_digit_count || params.phone_length || 11} 位，${params.phone_prefix || '1'} 开头，第二位 ${params.phone_second_range || '3-9'}`;
      }
      if (kind === 'id_card') {
        return `身份证号 ${params.id_card_length || 18} 位${boolFromValue(params.allow_x_checksum, true) ? '，末位可为X' : ''}`;
      }
      if (kind === 'email') {
        const domains = parseBusinessList(params.email_domains || []);
        return domains.length ? `邮箱格式，限制 ${domains.join('、')}` : '邮箱格式校验';
      }
      if (kind === 'enum') {
        const values = parseBusinessList(params.allowed_value_list || params.allowed_values);
        return values.length ? `允许 ${values.length} 个取值` : '枚举取值待填写';
      }
      if (kind === 'range') {
        const min = params.min_value ?? '不限';
        const max = params.max_value ?? '不限';
        return `允许范围：${min} 至 ${max}`;
      }
      if (kind === 'decimal') {
        return `最多 ${params.decimal_scale ?? 2} 位小数`;
      }
      if (kind === 'length') {
        return `长度 ${params.min_length ?? 1} 至 ${params.max_length ?? 128}`;
      }
      if (kind === 'required') {
        return '不能为空或空白字符';
      }
      if (kind === 'unique') {
        return '字段值不允许重复';
      }
      return parameterEditorTitle(kind, setting);
    }

    function executionStatusLabel(status, blocked) {
      if (blocked) return '已完成，存在阻断问题';
      const labels = {
        success: '已完成，全部通过',
        warning: '已完成，有问题需处理',
        blocked: '已完成，存在阻断问题',
        failed: '执行失败'
      };
      return labels[status] || '已完成';
    }

    function executionStatusFoot(status, blocked) {
      if (blocked) return '请先处理强校验问题，再继续使用数据';
      if (status === 'success') return '数据质量检查通过';
      if (status === 'failed') return '请重新执行或联系管理员';
      return '建议进入质量问题分析处理异常';
    }

    function taskScheduleLabel(value) {
      const labels = {
        manual: '立即执行',
        dependency: '上游完成后执行',
        daily: '每天自动执行',
        weekly: '每周自动执行',
        monthly: '每月自动执行',
        cron: '按周期执行'
      };
      return labels[value] || '立即执行';
    }

    function scanModeLabel(value) {
      const labels = {
        full: '检查全部数据',
        incremental: '只检查新增或变更数据'
      };
      return labels[value] || '检查全部数据';
    }

    function ruleRunStatusBadge(status) {
      const labels = {
        passed: '通过',
        failed: '未通过',
        warning: '需关注',
        skipped: '未执行'
      };
      const label = labels[status] || status || '-';
      const color = status === 'passed' ? 'green' : (status === 'skipped' ? 'gray' : 'red');
      return badge(label, color);
    }

    function ruleRunSuggestion(item) {
      if (!item || Number(item.failed_rows || 0) <= 0) return '无需处理，可继续使用。';
      const dim = dimensionLabel(item);
      return `${dim}发现异常，进入“质量问题分析”查看样例、责任人和整改建议。`;
    }

    function ruleFriendlyName(setting) {
      const names = {
        'N-F01': '身份证号码格式校验',
        'N-F02': '手机号格式校验',
        'N-F03': '车牌号格式校验',
        'N-F04': 'IMEI格式校验',
        'N-F05': 'MAC地址格式校验',
        'N-F06': 'IP地址格式校验',
        'N-F08': '邮箱格式校验',
        'N-V01': '枚举取值校验',
        'C-F01': '必填字段空值校验',
        'C-F03': '空白字符串校验',
        'C-F04': '唯一性校验',
        'A-N02': '取值范围校验',
        'A-N03': '金额精度校验',
        'A-L01': '长度校验'
      };
      return names[setting?.rule_id] || setting?.rule_id || '规则配置';
    }

    function requiredSelectHtml(id, params, defaultRequired = false, label = '是否必须填写') {
      const required = boolFromValue(params.required, defaultRequired);
      return `
        <div class="field">
          <label>${label}</label>
          <select id="param_${id}_required">
            <option value="true" ${required ? 'selected' : ''}>必须填写，空值算问题</option>
            <option value="false" ${required ? '' : 'selected'}>允许为空，只校验已填写的数据</option>
          </select>
        </div>`;
    }

    function businessParameterHtml(setting, id) {
      const params = setting.parameter_overrides || {};
      const kind = parameterEditorKind(setting);
      if (kind === 'phone') {
        const digits = params.phone_digit_count || params.phone_length || 11;
        const prefix = params.phone_prefix || '1';
        const secondRange = params.phone_second_range || '3-9';
        return `
          <div class="business-params">
            <h4>手机号规则要求</h4>
            <div class="form-grid">
              <div class="field"><label>手机号数字个数</label><input id="param_${id}_phone_digits" type="number" min="5" max="20" step="1" value="${escapeHtml(digits)}"><div class="help-text">大陆手机号通常为 11 位。</div></div>
              <div class="field"><label>号码开头数字</label><input id="param_${id}_phone_prefix" inputmode="numeric" value="${escapeHtml(prefix)}"><div class="help-text">例如大陆手机号以 1 开头。</div></div>
              <div class="field"><label>第二位允许范围</label><select id="param_${id}_phone_second_range">
                ${['3-9', '0-9', '4-9', '5-9'].map(item => `<option value="${item}" ${secondRange === item ? 'selected' : ''}>${item}</option>`).join('')}
              </select><div class="help-text">默认 3-9，可覆盖常见号段。</div></div>
            </div>
            <div class="form-grid" style="margin-top:12px">
              ${requiredSelectHtml(id, params, false, '手机号是否必须填写')}
              <div class="field"><label>输入内容要求</label><input value="只能填写数字，不能带空格、横线或括号" disabled></div>
              <div class="field"><label>问题处理方式</label><input value="格式不符合时进入质量问题清单" disabled></div>
            </div>
          </div>`;
      }
      if (kind === 'id_card') {
        const length = params.id_card_length || 18;
        const allowX = boolFromValue(params.allow_x_checksum, true);
        return `
          <div class="business-params">
            <h4>身份证号规则要求</h4>
            <div class="form-grid">
              <div class="field"><label>身份证号位数</label><select id="param_${id}_id_card_length">
                <option value="18" ${String(length) === '18' ? 'selected' : ''}>18 位</option>
                <option value="15" ${String(length) === '15' ? 'selected' : ''}>15 位</option>
              </select></div>
              <div class="field"><label>最后一位是否允许 X</label><select id="param_${id}_id_card_allow_x">
                <option value="true" ${allowX ? 'selected' : ''}>允许 X 或 x</option>
                <option value="false" ${allowX ? '' : 'selected'}>只允许数字</option>
              </select></div>
              ${requiredSelectHtml(id, params, false, '身份证号是否必须填写')}
            </div>
          </div>`;
      }
      if (kind === 'email') {
        const domains = (params.email_domains || []).length ? params.email_domains : '';
        return `
          <div class="business-params">
            <h4>邮箱规则要求</h4>
            <div class="form-grid">
              ${requiredSelectHtml(id, params, false, '邮箱是否必须填写')}
              <div class="field"><label>域名限制（可选）</label><input id="param_${id}_email_domains" placeholder="例如 company.com，可留空" value="${escapeHtml(Array.isArray(domains) ? domains.join(',') : domains)}"><div class="help-text">留空表示只检查邮箱格式。</div></div>
              <div class="field"><label>格式要求</label><input value="必须包含 @ 和合法域名后缀" disabled></div>
            </div>
          </div>`;
      }
      if (kind === 'enum') {
        const values = params.allowed_value_list || parseBusinessList(params.allowed_values).join('\\n');
        return `
          <div class="business-params">
            <h4>枚举取值要求</h4>
            <div style="margin-bottom:12px">
              <label>允许出现的取值</label>
              <textarea id="param_${id}_allowed_values" class="business-textarea" placeholder="每行一个值，例如：&#10;待支付&#10;已支付&#10;已取消">${escapeHtml(Array.isArray(values) ? values.join('\\n') : values)}</textarea>
              <div class="help-text">用户只需要填写中文或业务编码，系统保存时自动转换成可执行校验参数。</div>
            </div>
            <div class="form-grid">
              ${requiredSelectHtml(id, params, false, '该字段是否必须填写')}
              <div class="field"><label>取值大小写</label><input value="按填写值精确匹配" disabled></div>
              <div class="field"><label>问题处理方式</label><input value="不在允许值内时进入质量问题清单" disabled></div>
            </div>
          </div>`;
      }
      if (kind === 'range') {
        return `
          <div class="business-params">
            <h4>数值范围要求</h4>
            <div class="form-grid">
              <div class="field"><label>最小允许值</label><input id="param_${id}_min_value" type="number" step="0.01" value="${escapeHtml(params.min_value ?? '')}" placeholder="可留空"></div>
              <div class="field"><label>最大允许值</label><input id="param_${id}_max_value" type="number" step="0.01" value="${escapeHtml(params.max_value ?? '')}" placeholder="可留空"></div>
              ${requiredSelectHtml(id, params, false, '该字段是否必须填写')}
            </div>
          </div>`;
      }
      if (kind === 'decimal') {
        return `
          <div class="business-params">
            <h4>金额/数值精度要求</h4>
            <div class="form-grid">
              <div class="field"><label>最多允许小数位数</label><input id="param_${id}_decimal_scale" type="number" min="0" max="8" step="1" value="${escapeHtml(params.decimal_scale ?? 2)}"></div>
              ${requiredSelectHtml(id, params, false, '该字段是否必须填写')}
              <div class="field"><label>问题处理方式</label><input value="超过小数位数时进入质量问题清单" disabled></div>
            </div>
          </div>`;
      }
      if (kind === 'length') {
        return `
          <div class="business-params">
            <h4>字段长度要求</h4>
            <div class="form-grid">
              <div class="field"><label>最短长度</label><input id="param_${id}_min_length" type="number" min="0" step="1" value="${escapeHtml(params.min_length ?? 1)}"></div>
              <div class="field"><label>最长长度</label><input id="param_${id}_max_length" type="number" min="1" step="1" value="${escapeHtml(params.max_length ?? 128)}"></div>
              ${requiredSelectHtml(id, params, false, '该字段是否必须填写')}
            </div>
          </div>`;
      }
      if (kind === 'required') {
        return `
          <div class="business-params">
            <h4>必填完整性要求</h4>
            <div class="form-grid">
              <div class="field"><label>空值处理</label><input value="不能为空，也不能只填写空格" disabled></div>
              <div class="field"><label>整改要求</label><input value="补齐字段值或回溯源系统" disabled></div>
              <div class="field"><label>检查状态</label><input value="由上方“是否启用”控制" disabled></div>
            </div>
          </div>`;
      }
      if (kind === 'unique') {
        return `
          <div class="business-params">
            <h4>唯一性要求</h4>
            <div class="form-grid">
              <div class="field"><label>重复值处理</label><input value="同一字段值不允许重复" disabled></div>
              <div class="field"><label>适用场景</label><input value="主键、业务编号、证件号等唯一标识" disabled></div>
              <div class="field"><label>检查状态</label><input value="由上方“是否启用”控制" disabled></div>
            </div>
          </div>`;
      }
      return `
        <div class="business-params">
          <h4>${escapeHtml(parameterEditorTitle(kind, setting))}</h4>
          <div class="form-grid">
            ${requiredSelectHtml(id, params, false, '该字段是否必须填写')}
            <div class="field"><label>规则说明</label><input value="系统已按规则库模板生成执行参数" disabled></div>
            <div class="field"><label>检查状态</label><input value="由上方“是否启用”控制" disabled></div>
          </div>
        </div>`;
    }

    function buildPhoneRegex(digits, prefix, secondRange) {
      const cleanPrefix = String(prefix || '1').replace(/[^0-9]/g, '') || '1';
      const length = Math.round(Math.max(cleanPrefix.length + 1, Math.min(20, Number(digits) || 11)));
      const range = String(secondRange || '3-9').replace(/[^0-9-]/g, '') || '3-9';
      const remaining = Math.max(0, length - cleanPrefix.length - 1);
      return '^' + cleanPrefix + '[' + range + '][0-9]{' + remaining + '}$';
    }

    function businessOverridesFromForm(kind, setting, id, baseOverrides) {
      const overrides = { ...(baseOverrides || {}) };
      const requiredEl = document.getElementById(`param_${id}_required`);
      if (requiredEl) overrides.required = requiredEl.value === 'true';
      if (kind === 'phone') {
        const digits = Math.round(Math.max(5, Math.min(20, numberFromInput(`param_${id}_phone_digits`, overrides.phone_digit_count || 11))));
        const prefix = textFromInput(`param_${id}_phone_prefix`, overrides.phone_prefix || '1').replace(/[^0-9]/g, '') || '1';
        const secondRange = textFromInput(`param_${id}_phone_second_range`, overrides.phone_second_range || '3-9').replace(/[^0-9-]/g, '') || '3-9';
        overrides.phone_digit_count = String(digits);
        overrides.phone_prefix = prefix;
        overrides.phone_second_range = secondRange;
        overrides.regex = buildPhoneRegex(digits, prefix, secondRange);
      } else if (kind === 'id_card') {
        const length = textFromInput(`param_${id}_id_card_length`, overrides.id_card_length || 18);
        const allowX = textFromInput(`param_${id}_id_card_allow_x`, 'true') === 'true';
        overrides.id_card_length = length;
        overrides.allow_x_checksum = allowX;
        overrides.regex = length === '15'
          ? '^[1-9][0-9]{5}[0-9]{2}(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])[0-9]{3}$'
          : '^[1-9][0-9]{5}(18|19|20)[0-9]{2}(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])[0-9]{3}' + (allowX ? '[0-9Xx]' : '[0-9]') + '$';
      } else if (kind === 'email') {
        const domains = parseBusinessList(textFromInput(`param_${id}_email_domains`, ''));
        overrides.email_domains = domains;
        const patterns = domainPatternList(domains);
        overrides.regex = patterns.length
          ? '^[A-Za-z0-9._%+-]+@(' + patterns.join('|') + ')$'
          : '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}$';
      } else if (kind === 'enum') {
        const values = parseBusinessList(textFromInput(`param_${id}_allowed_values`, ''));
        overrides.allowed_value_list = values;
        overrides.allowed_values = sqlLiteralList(values);
      } else if (kind === 'range') {
        const minValue = textFromInput(`param_${id}_min_value`, '');
        const maxValue = textFromInput(`param_${id}_max_value`, '');
        if (minValue === '') delete overrides.min_value; else overrides.min_value = minValue;
        if (maxValue === '') delete overrides.max_value; else overrides.max_value = maxValue;
      } else if (kind === 'decimal') {
        overrides.decimal_scale = String(Math.round(Math.max(0, Math.min(8, numberFromInput(`param_${id}_decimal_scale`, overrides.decimal_scale || 2)))));
      } else if (kind === 'length') {
        overrides.min_length = String(Math.round(Math.max(0, numberFromInput(`param_${id}_min_length`, overrides.min_length || 1))));
        overrides.max_length = String(Math.round(Math.max(1, numberFromInput(`param_${id}_max_length`, overrides.max_length || 128))));
      }
      return overrides;
    }

    function promptDimension(title, defaultValue = 'normativity', allowEmpty = false) {
      const raw = prompt(dimensionPromptText(title), defaultValue);
      if (raw === null) return null;
      if (allowEmpty && !String(raw).trim()) return '';
      const dimension = normalizeDimension(raw);
      if (!dimension) {
        alert('维度输入无效，请输入 1-6、中文维度名称或英文编码。');
        return null;
      }
      return dimension;
    }

    const ruleCreateTemplates = {
      normativity: {
        hint: '字段格式、编码、命名、长度等是否符合标准。',
        displayName: '自定义字段格式规范校验',
        category: '格式不规范',
        core: '检查字段值是否满足指定格式、编码或命名规范。',
        sql: `SELECT * FROM {{ table_name }}
WHERE {{ column_name }} IS NULL
   OR TRIM(CAST({{ column_name }} AS CHAR)) = ''`,
        remediation: '按标准格式修正字段值，必要时回溯采集或映射规则。'
      },
      completeness: {
        hint: '字段、记录、关联对象是否完整。',
        displayName: '自定义字段完整性校验',
        category: '字段不完整',
        core: '检查关键字段不能为空，保障评价对象的基础完整性。',
        sql: `SELECT * FROM {{ table_name }}
WHERE {{ column_name }} IS NULL
   OR TRIM(CAST({{ column_name }} AS CHAR)) = ''`,
        remediation: '补齐缺失字段，修复源系统采集、同步或补录流程。'
      },
      accuracy: {
        hint: '值域、数值、日期、业务逻辑是否准确。',
        displayName: '自定义取值准确性校验',
        category: '取值不准确',
        core: '检查字段值是否落在允许范围内，识别异常值和错误值。',
        sql: `SELECT * FROM {{ table_name }}
WHERE {{ column_name }} IS NULL
   OR {{ column_name }} < {{ min_value }}
   OR {{ column_name }} > {{ max_value }}`,
        remediation: '核对业务口径和源数据取值，修正异常值后重新评价。'
      },
      consistency: {
        hint: '跨字段、跨表、跨系统数据是否一致。',
        displayName: '自定义关联一致性校验',
        category: '关联不一致',
        core: '检查当前字段是否能在关联主数据或业务表中找到匹配记录。',
        sql: `SELECT t.*
FROM {{ table_name }} t
LEFT JOIN {{ related_table }} r
  ON t.{{ column_name }} = r.{{ related_column }}
WHERE r.{{ related_column }} IS NULL`,
        remediation: '核查主外键映射、同步链路和跨系统口径，统一后重跑评价。'
      },
      timeliness: {
        hint: '数据新鲜度、更新时间、响应时效是否达标。',
        displayName: '自定义数据时效性校验',
        category: '数据不及时',
        core: '检查更新时间是否超过允许延迟窗口，识别过期数据。',
        sql: `SELECT * FROM {{ table_name }}
WHERE {{ column_name }} IS NULL
   OR {{ column_name }} < CURRENT_DATE - INTERVAL '{{ max_delay_days }} DAY'`,
        remediation: '检查调度任务、接口同步和增量链路，补跑或修复延迟数据。'
      },
      accessibility: {
        hint: '权限、可用性、服务响应和访问链路是否满足要求。',
        displayName: '自定义可访问性校验',
        category: '访问不可用',
        core: '检查数据访问状态、权限标识或服务响应是否满足使用要求。',
        sql: `SELECT * FROM {{ table_name }}
WHERE {{ column_name }} IS NULL
   OR {{ column_name }} NOT IN ('enabled', 'active', 'available')`,
        remediation: '核查授权配置、服务状态和资源发布链路，恢复可访问状态。'
      }
    };

    function renderRuleCreatePanel(selectedDimension) {
      const selected = normalizeDimension(selectedDimension) || 'normativity';
      const template = ruleCreateTemplates[selected];
      return `
        <section id="ruleCreatePanel" style="display:none">
          <h2>新增质量评价规则</h2>
          <div class="muted" style="margin-bottom:12px">业务用户只需要选择维度并填写规则含义；系统会自动生成落地脚本，技术人员需要时再查看。</div>
          <div class="rule-create-grid">
            <div>
              <div class="form-section-title">1. 选择规则所属维度</div>
              <div class="dim-choice-grid">
                ${dimOrder.map(key => `
                  <button class="dim-choice ${key === selected ? 'active' : ''}" id="ruleCreateDim_${key}" onclick="selectRuleCreateDimension('${key}')">
                    <strong>${dimName[key]}</strong>
                    <span>${escapeHtml(ruleCreateTemplates[key].hint)}</span>
                  </button>
                `).join('')}
              </div>
            </div>
            <div>
              <div class="form-section-title">2. 填写规则内容</div>
              <input id="ruleCreateDimension" type="hidden" value="${selected}">
              <div class="form-grid">
                <div class="field"><label>规则编号</label><input id="ruleCreateId" placeholder="留空自动生成"></div>
                <div class="field"><label>规则名称</label><input id="ruleCreateName" value="${escapeHtml(template.displayName)}"></div>
                <div class="field"><label>校验级别</label><select id="ruleCreateLevel">
                  ${validationLevelOptions('P1_WARNING')}
                </select></div>
              </div>
              <div class="form-grid" style="margin-top:12px">
                <div class="field"><label>问题归类</label><input id="ruleCreateCategory" value="${escapeHtml(template.category)}"></div>
                <div class="field"><label>严重程度</label><select id="ruleCreateSeverity">
                  <option value="MEDIUM">MEDIUM</option>
                  <option value="HIGH">HIGH</option>
                  <option value="LOW">LOW</option>
                  <option value="CRITICAL">CRITICAL</option>
                </select></div>
                <div class="field"><label>责任角色</label><input id="ruleCreateRole" value="数据责任人"></div>
              </div>
              <div style="margin-top:12px">
                <label>核心定义</label>
                <textarea id="ruleCreateCore" class="compact-textarea">${escapeHtml(template.core)}</textarea>
              </div>
              <details class="tech-detail">
                <summary>查看系统自动生成的技术脚本</summary>
                <pre id="ruleCreateSql">${escapeHtml(template.sql)}</pre>
                <div class="muted" style="margin-top:6px">该脚本由系统根据维度模板生成，业务用户不需要填写或修改。</div>
              </details>
              <div style="margin-top:12px">
                <label>整改建议</label>
                <textarea id="ruleCreateRemediation" class="compact-textarea">${escapeHtml(template.remediation)}</textarea>
              </div>
              <div class="toolbar">
                <button onclick="createRuleFromForm()">保存规则</button>
                <button class="secondary" onclick="resetRuleCreateTemplate()">重置当前维度模板</button>
                <button class="secondary" onclick="cancelRuleCreatePanel()">取消</button>
              </div>
            </div>
          </div>
        </section>`;
    }

    function showRuleCreatePanel() {
      const panel = document.getElementById('ruleCreatePanel');
      if (!panel) return;
      panel.style.display = 'block';
      selectRuleCreateDimension(dimensionFilters.rules || 'normativity', false);
      panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
      setStatusMessage('请选择六个质量评价维度之一，然后填写规则内容并保存。');
    }

    function cancelRuleCreatePanel() {
      const panel = document.getElementById('ruleCreatePanel');
      if (panel) panel.style.display = 'none';
      setStatusMessage('已取消新增规则');
    }

    function selectRuleCreateDimension(dimension, overwrite = true) {
      const selected = normalizeDimension(dimension) || 'normativity';
      const template = ruleCreateTemplates[selected];
      const hidden = document.getElementById('ruleCreateDimension');
      if (hidden) hidden.value = selected;
      dimOrder.forEach(key => {
        const btn = document.getElementById('ruleCreateDim_' + key);
        if (btn) btn.classList.toggle('active', key === selected);
      });
      if (!overwrite) return;
      const fields = {
        ruleCreateName: template.displayName,
        ruleCreateCategory: template.category,
        ruleCreateCore: template.core,
        ruleCreateRemediation: template.remediation
      };
      Object.entries(fields).forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el) {
          if (el.tagName === 'PRE') el.textContent = value;
          else el.value = value;
        }
      });
      const script = document.getElementById('ruleCreateSql');
      if (script) script.textContent = template.sql;
    }

    function resetRuleCreateTemplate() {
      const dimension = document.getElementById('ruleCreateDimension')?.value || 'normativity';
      selectRuleCreateDimension(dimension, true);
      setStatusMessage(`已重置为${dimName[dimension]}规则模板`);
    }

    async function createRuleFromForm() {
      const dimension = normalizeDimension(document.getElementById('ruleCreateDimension')?.value || '');
      const displayName = document.getElementById('ruleCreateName')?.value.trim() || '';
      if (!dimension) {
        setStatusMessage('请先选择规则所属维度。', true);
        return;
      }
      if (!displayName) {
        setStatusMessage('请填写规则名称。', true);
        return;
      }
      const sql = ruleCreateTemplates[dimension].sql;
      const payload = {
        rule_id: document.getElementById('ruleCreateId')?.value.trim() || '',
        display_name: displayName,
        dimension,
        problem_category: document.getElementById('ruleCreateCategory')?.value.trim() || ruleCreateTemplates[dimension].category,
        core_definition: document.getElementById('ruleCreateCore')?.value.trim() || ruleCreateTemplates[dimension].core,
        sql,
        validation_level: document.getElementById('ruleCreateLevel')?.value || 'P1_WARNING',
        severity: document.getElementById('ruleCreateSeverity')?.value || 'MEDIUM',
        responsible_role: document.getElementById('ruleCreateRole')?.value.trim() || '数据责任人',
        remediation_suggestion: document.getElementById('ruleCreateRemediation')?.value.trim() || ruleCreateTemplates[dimension].remediation,
        tags: ['页面新增', dimName[dimension]]
      };
      const data = await postJson('/api/rules/create', payload);
      dimensionFilters.rules = dimension;
      pageState.rules = 1;
      await loadRules(`${data.message}：已归入${dimName[dimension]}`);
    }

    function pagedData(key, rows) {
      const list = Array.isArray(rows) ? rows : [];
      const total = list.length;
      const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
      const current = Math.min(Math.max(Number(pageState[key] || 1), 1), totalPages);
      pageState[key] = current;
      const start = (current - 1) * PAGE_SIZE;
      return {
        items: list.slice(start, start + PAGE_SIZE),
        start,
        page: current,
        total,
        totalPages
      };
    }

    function paginationHtml(key, page, loaderName) {
      const from = page.total === 0 ? 0 : page.start + 1;
      const to = Math.min(page.start + PAGE_SIZE, page.total);
      return `
        <div class="pager">
          <span>每页 ${PAGE_SIZE} 条，${from}-${to} / ${page.total}</span>
          <button class="secondary" ${page.page <= 1 ? 'disabled' : ''} onclick="setPage('${key}', ${page.page - 1}, '${loaderName}')">上一页</button>
          <span>${page.page} / ${page.totalPages}</span>
          <button class="secondary" ${page.page >= page.totalPages ? 'disabled' : ''} onclick="setPage('${key}', ${page.page + 1}, '${loaderName}')">下一页</button>
        </div>`;
    }

    function setPage(key, page, loaderName) {
      pageState[key] = page;
      const loader = globalThis[loaderName] || window[loaderName];
      if (typeof loader === 'function') {
        loader();
      }
    }

    function setStatusMessage(message, failed) {
      const status = document.getElementById('status');
      status.style.display = 'block';
      status.className = failed ? 'status fail' : 'status';
      status.textContent = message;
    }

    const chartColors = ['#2563eb', '#16a34a', '#f59e0b', '#dc2626', '#7c3aed', '#0891b2'];

    function drawPieChart(canvasId, items) {
      const canvas = document.getElementById(canvasId);
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      const width = canvas.clientWidth || 420;
      const height = 240;
      canvas.width = width;
      canvas.height = height;
      ctx.clearRect(0, 0, width, height);
      const total = items.reduce((sum, item) => sum + Math.max(Number(item.score || 0), 0), 0) || 1;
      const radius = Math.min(width * .28, height * .38);
      const cx = Math.round(width * .32);
      const cy = Math.round(height * .48);
      let start = -Math.PI / 2;
      items.forEach((item, index) => {
        const value = Math.max(Number(item.score || 0), 0);
        const angle = (value / total) * Math.PI * 2;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, radius, start, start + angle);
        ctx.closePath();
        ctx.fillStyle = chartColors[index % chartColors.length];
        ctx.fill();
        start += angle;
      });
      ctx.font = '12px Arial';
      items.forEach((item, index) => {
        const y = 26 + index * 28;
        ctx.fillStyle = chartColors[index % chartColors.length];
        ctx.fillRect(width * .62, y - 10, 12, 12);
        ctx.fillStyle = '#344054';
        ctx.fillText(`${item.label} ${Math.round(item.score || 0)}`, width * .62 + 18, y);
      });
    }

    function drawBarChart(canvasId, items) {
      const canvas = document.getElementById(canvasId);
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      const width = canvas.clientWidth || 520;
      const height = 260;
      canvas.width = width;
      canvas.height = height;
      ctx.clearRect(0, 0, width, height);
      const left = 78;
      const top = 22;
      const rowHeight = Math.max(26, Math.floor((height - 42) / Math.max(items.length, 1)));
      ctx.font = '12px Arial';
      items.forEach((item, index) => {
        const y = top + index * rowHeight;
        const score = Math.max(0, Math.min(100, Number(item.score || 0)));
        const barWidth = Math.max(2, (width - left - 48) * score / 100);
        ctx.fillStyle = '#475467';
        ctx.fillText(item.label, 8, y + 15);
        ctx.fillStyle = '#e5e7eb';
        ctx.fillRect(left, y, width - left - 48, 16);
        ctx.fillStyle = chartColors[index % chartColors.length];
        ctx.fillRect(left, y, barWidth, 16);
        ctx.fillStyle = '#111827';
        ctx.fillText(`${score.toFixed(1)}`, left + barWidth + 6, y + 13);
      });
    }

    function setOutput(data, visible = false) {
      const output = document.getElementById('output');
      output.textContent =
        typeof data === 'string' ? data : JSON.stringify(data, null, 2);
      output.style.display = visible ? 'block' : 'none';
    }

    async function loadJson(path, visible = false) {
      const res = await fetch(path);
      const data = await res.json();
      setOutput(data, visible);
      if (!res.ok) throw new Error(data.error || res.statusText);
      return data;
    }

    async function showJson(path) {
      try {
        const data = await loadJson(path, true);
        setStatusMessage('接口数据已显示在页面底部');
        document.getElementById('output').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        return data;
      } catch (err) {
        setOutput(String(err), true);
        setStatusMessage('接口调用失败：' + err, true);
        return null;
      }
    }

    async function postJson(path, payload, visible = false) {
      const res = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      setOutput(data, visible);
      if (!res.ok) throw new Error(data.error || res.statusText);
      return data;
    }

    window.addEventListener('unhandledrejection', event => {
      const message = event.reason && event.reason.message ? event.reason.message : String(event.reason);
      setStatusMessage('操作失败：' + message, true);
      setOutput(message, true);
    });

    window.addEventListener('error', event => {
      const message = event.message || '页面脚本执行失败';
      setStatusMessage('页面脚本异常：' + message, true);
      setOutput(message, true);
    });

    function setActions(actions) {
      document.getElementById('pageActions').innerHTML = actions.map(item =>
        `<button class="${item.secondary ? 'secondary' : ''}" onclick="${item.fn}">${item.text}</button>`
      ).join('');
    }

    function setContent(html) {
      document.getElementById('content').innerHTML = html;
    }

    async function ensureImportedPage() {
      const data = await loadJson('/api/data/current');
      if (data.imported) return true;
      setActions([{ text: '去导入数据', fn: "location.href='/import'" }, { text: '刷新当前页', fn: 'refreshPage()', secondary: true }]);
      setContent(`<section><div class="empty">请先导入待评价数据。导入后即可运行当前功能页面。</div></section>`);
      return false;
    }

    function activateNav() {
      document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.toggle('active', link.dataset.page === currentPage);
      });
      document.getElementById('pageTitle').textContent = pages[currentPage].title;
      document.getElementById('pageDesc').textContent = pages[currentPage].desc;
    }

    async function runHealthCheck() {
      const btn = document.getElementById('healthBtn');
      const status = document.getElementById('status');
      btn.disabled = true;
      btn.textContent = '检查中...';
      status.style.display = 'block';
      status.className = 'status';
      status.textContent = '正在执行规则库与智能推荐健康检查...';
      document.getElementById('output').textContent = 'Running...';
      try {
        const res = await fetch('/api/run-test');
        const data = await res.json();
        const pass = data.test_result === 'PASS';
        status.className = pass ? 'status' : 'status fail';
        status.textContent = pass
          ? `健康检查通过：${data.passed_checks}/${data.total_checks} 项，耗时 ${data.duration_ms} ms`
          : `健康检查失败：${data.failed_checks} 项失败，耗时 ${data.duration_ms} ms`;
        document.getElementById('output').textContent = JSON.stringify(data, null, 2);
      } catch (err) {
        status.className = 'status fail';
        status.textContent = '健康检查接口调用失败：' + err;
        document.getElementById('output').textContent = String(err);
      } finally {
        btn.disabled = false;
        btn.textContent = '健康检查';
      }
    }

    async function resetRuntime() {
      const data = await loadJson('/api/workflow/reset');
      const status = document.getElementById('status');
      status.style.display = 'block';
      status.className = 'status';
      status.textContent = data.message || '运行数据已重置';
      await renderCurrentPage();
    }

    async function loadOverview() {
      const data = await loadJson('/api/workflow/overview');
      const s = data.summary;
      const ds = data.current_dataset || {};
      const processPage = pagedData('overviewProcess', data.process || []);
      setActions([{ text: '刷新总览', fn: 'loadOverview()' }, { text: '去导入数据', fn: "location.href='/import'", secondary: true }, { text: '查看总览JSON', fn: "showJson('/api/workflow/overview')", secondary: true }]);
      setContent(`
        <section>
          <div class="stats">
            <div class="metric"><div class="metric-label">规则总数</div><div class="metric-value">${s.total_rules}</div><div class="metric-foot">内置规则95条，导入规则会临时增加</div></div>
            <div class="metric"><div class="metric-label">启用规则</div><div class="metric-value">${s.active_rules}</div><div class="metric-foot">当前全部启用</div></div>
            <div class="metric"><div class="metric-label">导入行数</div><div class="metric-value">${ds.row_count || 0}</div><div class="metric-foot">${ds.imported ? '当前数据集' : '待导入'}</div></div>
            <div class="metric"><div class="metric-label">字段数量</div><div class="metric-value">${(ds.columns || []).length}</div><div class="metric-foot">字段画像</div></div>
          </div>
        </section>
        <section>
          <h2>当前数据集</h2>
          ${ds.imported ? `
            <div class="stats">
              <div class="metric"><div class="metric-label">数据表</div><div class="metric-value" style="font-size:18px">${escapeHtml(ds.scope.table_name)}</div><div class="metric-foot">${escapeHtml(ds.scope.table_fqn)}</div></div>
              <div class="metric"><div class="metric-label">业务域</div><div class="metric-value" style="font-size:18px">${escapeHtml(ds.scope.business_domain || '-')}</div><div class="metric-foot">${escapeHtml(ds.scope.data_classification || '-')}</div></div>
              <div class="metric"><div class="metric-label">规则配置</div><div class="metric-value">${ds.rule_setting_count}</div><div class="metric-foot">${ds.configured ? '已生成参数' : '未配置'}</div></div>
              <div class="metric"><div class="metric-label">确认推荐</div><div class="metric-value">${ds.confirmed_recommendation_count}</div><div class="metric-foot">可入库执行</div></div>
            </div>` : `<div class="empty">还没有导入数据。请进入“数据导入”页面，粘贴JSON rows或CSV后开始运行评价流程。</div>`}
        </section>
        <section>
          <h2>功能页面关系</h2>
          <div class="three-col">${processPage.items.map(item => `
            <div class="panel">
              <h3>${item.id} ${escapeHtml(item.name)}</h3>
              <div>${badge(item.status, item.status === '已完成' ? 'green' : 'amber')}</div>
              <div class="muted mono" style="margin-top:10px">${escapeHtml(item.api)}</div>
            </div>`).join('')}</div>
          ${paginationHtml('overviewProcess', processPage, 'loadOverview')}
        </section>
        <section>
          <h2>白皮书功能对照</h2>
          <table>
            <thead><tr><th>白皮书能力</th><th>当前实现页面</th><th>状态</th><th>说明</th></tr></thead>
            <tbody>
              <tr><td>规则模板、规则查询与统计</td><td>质量评价规则库</td><td>${badge('已实现', 'green')}</td><td>六维分类、CRUD、导入、复用、脚本预览。</td></tr>
              <tr><td>自动化规则推荐与人工确认</td><td>质量规则智能推荐</td><td>${badge('已实现', 'green')}</td><td>基于字段名、类型、样例值、字典、业务域、分类分级、血缘推荐。</td></tr>
              <tr><td>检核任务可视化配置</td><td>规则参数设定</td><td>${badge('已实现', 'green')}</td><td>绑定表字段、阈值、级别、执行方式和脚本预览。</td></tr>
              <tr><td>单目标/批量检核调度</td><td>质量评价实施</td><td>${badge('已实现', 'green')}</td><td>支持手动、周期、依赖触发，全量/增量和并行度配置。</td></tr>
              <tr><td>检核记录、异常明细</td><td>质量评价实施</td><td>${badge('已实现', 'green')}</td><td>展示规则数、异常数、规则执行脚本、通过率。</td></tr>
              <tr><td>质量分析和六维评分</td><td>六个维度的展示、计分规则</td><td>${badge('已实现', 'green')}</td><td>输出六维得分、总体得分、质量等级和计分归档。</td></tr>
              <tr><td>质量问题工单闭环</td><td>质量问题分析</td><td>${badge('已实现', 'green')}</td><td>支持发现、告警、建单、整改、复核、关闭、归档。</td></tr>
              <tr><td>字段级血缘问题溯源</td><td>质量问题溯源</td><td>${badge('已实现', 'green')}</td><td>展示上游来源、下游影响、根因提示和整改建议。</td></tr>
              <tr><td>质量报告生成</td><td>质量问题分析/流程报告</td><td>${badge('已实现', 'green')}</td><td>生成 Markdown/JSON 报告，页面可查看接口结果。</td></tr>
            </tbody>
          </table>
        </section>`);
    }

    const defaultImportPayload = {
      data_source: 'mysql',
      database: 'dw',
      schema: 'public',
      table_name: 'customer_order',
      business_domain: '客户订单',
      data_classification: '内部数据',
      columns: [
        { name: 'id', data_type: 'varchar', description: '订单主键', is_primary_key: true, nullable: false },
        { name: 'mobile_phone', data_type: 'varchar', description: '客户手机号' },
        { name: 'amount', data_type: 'decimal', description: '订单金额', min_value: 0, max_value: 999999 },
        { name: 'email', data_type: 'varchar', description: '客户邮箱' },
        { name: 'order_status', data_type: 'varchar', description: '订单状态', enum_values: ['待支付', '已支付', '已取消'] }
      ],
      rows: [
        { id: '1', mobile_phone: '13800138000000000', amount: '10.00', email: 'ok@example.com', order_status: '已支付' },
        { id: '1', mobile_phone: '12345', amount: '10.123', email: 'bad-email', order_status: '未知' },
        { id: '3', mobile_phone: '13900139000000000', amount: '20.10', email: 'user@example.com', order_status: '待支付' }
      ]
    };

    function renderCurrentDataset(data) {
      const columns = data.columns || [];
      const previewRows = data.preview_rows || [];
      const columnsPage = pagedData('importColumns', columns);
      const rowsPage = pagedData('importRows', previewRows);
      return `
        <section>
          <h2>当前导入状态</h2>
          <div class="stats">
            <div class="metric"><div class="metric-label">状态</div><div class="metric-value" style="font-size:20px">${data.imported ? '已导入' : '待导入'}</div><div class="metric-foot">${escapeHtml(data.imported_at || '-')}</div></div>
            <div class="metric"><div class="metric-label">数据表</div><div class="metric-value" style="font-size:18px">${escapeHtml(data.scope ? data.scope.table_name : '-')}</div><div class="metric-foot">${escapeHtml(data.scope ? data.scope.table_fqn : '-')}</div></div>
            <div class="metric"><div class="metric-label">行数</div><div class="metric-value">${data.row_count || 0}</div><div class="metric-foot">导入数据</div></div>
            <div class="metric"><div class="metric-label">字段数</div><div class="metric-value">${columns.length}</div><div class="metric-foot">字段画像</div></div>
          </div>
        </section>
        <section class="two-col">
          <div>
            <h2>字段画像</h2>
            ${columns.length ? `<table>
              <thead><tr><th>字段</th><th>类型</th><th>空值率</th><th>唯一率</th><th>样例</th></tr></thead>
              <tbody>${columnsPage.items.map(col => `
                <tr>
                  <td class="mono">${escapeHtml(col.name)}</td>
                  <td>${escapeHtml(col.data_type || '-')}</td>
                  <td>${col.null_ratio ?? '-'}</td>
                  <td>${col.unique_ratio ?? '-'}</td>
                  <td>${escapeHtml((col.sample_values || []).join(', '))}</td>
                </tr>`).join('')}</tbody>
            </table>${paginationHtml('importColumns', columnsPage, 'loadImportPage')}` : `<div class="empty">导入后自动显示字段画像。</div>`}
          </div>
          <div>
            <h2>数据预览</h2>
            <pre>${escapeHtml(JSON.stringify(rowsPage.items, null, 2))}</pre>
            ${paginationHtml('importRows', rowsPage, 'loadImportPage')}
          </div>
        </section>`;
    }

    async function loadImportPage() {
      const data = await loadJson('/api/data/current');
      setActions([
        { text: '导入JSON数据', fn: 'importJsonData()' },
        { text: '导入CSV数据', fn: 'importCsvData()', secondary: true },
        { text: '填入示例结构', fn: 'fillImportExample()', secondary: true },
        { text: '查看当前数据', fn: "showJson('/api/data/current')", secondary: true }
      ]);
      setContent(`
        <section class="two-col">
          <div>
            <h2>JSON导入</h2>
            <div class="form-grid">
              <div class="field"><label>数据源</label><input id="importSource" value="mysql"></div>
              <div class="field"><label>数据库</label><input id="importDatabase" value="dw"></div>
              <div class="field"><label>Schema</label><input id="importSchema" value="public"></div>
            </div>
            <div class="form-grid" style="margin-top:12px">
              <div class="field"><label>表名</label><input id="importTable" value="customer_order"></div>
              <div class="field"><label>业务域</label><input id="importDomain" value="客户订单"></div>
              <div class="field"><label>分级分类</label><input id="importClass" value="内部数据"></div>
            </div>
            <div style="margin-top:12px">
              <label>JSON数据</label>
              <textarea id="importJson"></textarea>
            </div>
          </div>
          <div>
            <h2>CSV导入</h2>
            <label>CSV文本</label>
            <textarea id="importCsv">id,mobile_phone,amount,email,order_status
1,13800138000000000,10.00,ok@example.com,已支付
1,12345,10.123,bad-email,未知
3,13900139000000000,20.10,user@example.com,待支付</textarea>
          </div>
        </section>
        ${renderCurrentDataset(data)}`);
      if (!document.getElementById('importJson').value) {
        fillImportExample(false);
      }
    }

    function baseImportMeta() {
      return {
        data_source: document.getElementById('importSource')?.value || 'uploaded',
        database: document.getElementById('importDatabase')?.value || '',
        schema: document.getElementById('importSchema')?.value || '',
        table_name: document.getElementById('importTable')?.value || 'imported_table',
        business_domain: document.getElementById('importDomain')?.value || '',
        data_classification: document.getElementById('importClass')?.value || ''
      };
    }

    function fillImportExample(updateOutput = true) {
      const target = document.getElementById('importJson');
      if (target) {
        target.value = JSON.stringify(defaultImportPayload, null, 2);
        target.classList.add('flash');
        target.focus();
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        setTimeout(() => target.classList.remove('flash'), 1100);
      }
      if (updateOutput) {
        setOutput(defaultImportPayload, true);
        setStatusMessage('示例结构已填入JSON数据框，可以点击“导入JSON数据”继续。');
      }
    }

    async function importJsonData() {
      const raw = document.getElementById('importJson').value.trim();
      let payload = raw ? JSON.parse(raw) : defaultImportPayload;
      payload = { ...baseImportMeta(), ...payload };
      const data = await postJson('/api/data/import', payload);
      const status = document.getElementById('status');
      status.style.display = 'block';
      status.className = 'status';
      status.textContent = `导入完成：${data.row_count} 行，${data.columns.length} 个字段`;
      await loadImportPage();
    }

    async function importCsvData() {
      const payload = {
        ...baseImportMeta(),
        csv: document.getElementById('importCsv').value
      };
      const data = await postJson('/api/data/import', payload);
      const status = document.getElementById('status');
      status.style.display = 'block';
      status.className = 'status';
      status.textContent = `CSV导入完成：${data.row_count} 行，${data.columns.length} 个字段`;
      await loadImportPage();
    }

    async function loadRules(feedback = '') {
      const keyword = document.getElementById('ruleSearch')?.value || '';
      const data = await loadJson('/api/rules' + (keyword ? `?keyword=${encodeURIComponent(keyword)}` : ''));
      const overview = await fetch('/api/workflow/overview').then(res => res.json());
      const allRules = data.rules || [];
      const activeDimension = dimensionFilters.rules || '';
      const visibleRules = filterByDimension(allRules, activeDimension);
      const rulesPage = pagedData('rules', visibleRules);
      const coveredDimensions = Object.values(dimensionCounts(allRules)).filter(count => count > 0).length;
      setActions([
        { text: '新增规则', fn: 'addRule()' },
        { text: '导入规则', fn: 'importRules()', secondary: true },
        { text: '刷新规则库', fn: 'refreshRules()', secondary: true }
      ]);
      setContent(`
        <section>
          <div class="search-row">
            <div class="field">
              <label>搜索规则</label>
              <input id="ruleSearch" value="${escapeHtml(keyword)}" placeholder="编号、名称、维度、标签">
            </div>
            <button onclick="searchRules()">搜索</button>
            <button class="secondary" onclick="clearRuleSearch()">清空</button>
          </div>
          ${dimensionTabsHtml('rules', allRules, 'loadRules', '规则维度分类')}
        </section>
        ${renderRuleCreatePanel(activeDimension || 'normativity')}
        <section>
          <div class="stats">
            <div class="metric"><div class="metric-label">当前规则</div><div class="metric-value">${visibleRules.length}</div><div class="metric-foot">${activeDimension ? dimName[activeDimension] : (keyword ? '搜索结果' : '启用规则')}</div></div>
            <div class="metric"><div class="metric-label">覆盖维度</div><div class="metric-value">${coveredDimensions}</div><div class="metric-foot">六维评价</div></div>
            <div class="metric"><div class="metric-label">SQL规则</div><div class="metric-value">${overview.summary.engines.SQL}</div><div class="metric-foot">全部覆盖</div></div>
            <div class="metric"><div class="metric-label">GE/ETL</div><div class="metric-value">${overview.summary.engines.GE}/${overview.summary.engines.ETL}</div><div class="metric-foot">全部覆盖</div></div>
          </div>
        </section>
        <section>
          <h2>六维规则统计</h2>
          ${dimensionSummaryHtml(allRules, '条规则')}
        </section>
        <section>
          <h2>规则列表（${visibleRules.length}）</h2>
        <table>
          <thead><tr><th>编号</th><th>规则名称</th><th>维度</th><th>级别</th><th>引擎</th><th>操作</th></tr></thead>
          <tbody>${rulesPage.items.length ? rulesPage.items.map(rule => `
            <tr>
              <td class="mono">${escapeHtml(rule.rule_id)}</td>
              <td>${escapeHtml(rule.name)}</td>
              <td>${escapeHtml(dimensionLabel(rule))}</td>
              <td>${validationLevelBadge(rule.validation_level)}</td>
              <td>${rule.engines.map(e => badge(e, 'gray')).join(' ')}</td>
              <td>
                <div class="row-actions">
                  <button class="tiny secondary" onclick="previewRule('${escapeJs(rule.rule_id)}')">技术预览</button>
                  <button class="tiny secondary" onclick="updateRule('${escapeJs(rule.rule_id)}')">修改</button>
                  <button class="tiny secondary" onclick="reuseRule('${escapeJs(rule.rule_id)}')">复用</button>
                  <button class="tiny danger" onclick="deleteRule('${escapeJs(rule.rule_id)}')">删除</button>
                </div>
              </td>
            </tr>`).join('') : `<tr><td colspan="6" class="muted">当前维度暂无规则，可切换到“全部”或新增该维度规则。</td></tr>`}</tbody>
        </table>
        ${paginationHtml('rules', rulesPage, 'loadRules')}
        </section>
        <section id="rulePreviewPanel" style="display:none">
          <h2>技术脚本预览</h2>
          <pre id="rulePreviewText"></pre>
        </section>
        <section id="ruleReusePanel" style="display:none">
          <h2>规则复用结果</h2>
          <pre id="ruleReuseText"></pre>
        </section>`);
      if (feedback) {
        setStatusMessage(`${feedback}：当前显示 ${visibleRules.length} 条规则${activeDimension ? `，维度“${dimName[activeDimension]}”` : ''}${keyword ? `，关键词“${keyword}”` : ''}`);
      }
    }

    async function refreshRules() {
      await loadRules('规则库已刷新');
    }

    async function searchRules() {
      pageState.rules = 1;
      await loadRules('搜索完成');
    }

    async function clearRuleSearch() {
      const input = document.getElementById('ruleSearch');
      if (input) input.value = '';
      pageState.rules = 1;
      await loadRules('搜索条件已清空');
    }

    async function addRule() {
      showRuleCreatePanel();
    }

    function defaultRuleImportPayload() {
      return {
        overwrite: false,
        rules: [
          {
            rule_id: 'CUSTOM-DEMO-IMPORT-01',
            name: 'custom_demo_import_01',
            display_name: '导入示例非空校验',
            dimension: 'completeness',
            source_type: 'CUSTOM',
            problem_category: '空值校验',
            core_definition: '检查指定字段不能为空，用于验证规则导入能力。',
            applicability: { entity_type: 'COLUMN' },
            scripts: {
              SQL: {
                expression: 'SELECT * FROM {{ table_name }} WHERE {{ column_name }} IS NULL',
                language: 'SQL',
                description: '返回字段为空的数据行。'
              },
              GE: {
                expression: 'ge_df.expect_column_values_to_not_be_null("{{ column_name }}")',
                language: 'Python/Great Expectations',
                description: 'GE非空校验模板。'
              },
              ETL: {
                expression: '{"action":"not_null","column":"{{ column_name }}"}',
                language: 'JSON DSL',
                description: 'ETL非空校验模板。'
              }
            },
            threshold: { pass_rate: 1.0, expected_value: 0, operator: '==', unit: 'rows' },
            validation_level: 'P1_WARNING',
            severity: 'MEDIUM',
            responsible_role: '数据责任人',
            remediation_suggestion: '补齐字段值或修正采集映射后重新执行评价。',
            issue_strategy: '生成质量问题并进入整改闭环。',
            tags: ['页面导入', '示例规则']
          }
        ]
      };
    }

    async function importRules() {
      const raw = prompt('粘贴规则JSON，留空导入一条例子', JSON.stringify(defaultRuleImportPayload(), null, 2));
      if (raw === null) return;
      let payload = defaultRuleImportPayload();
      if (raw.trim()) {
        try {
          payload = JSON.parse(raw);
        } catch (err) {
          alert('规则JSON解析失败：' + err);
          return;
        }
      }
      const data = await postJson('/api/rules/import', payload);
      const status = document.getElementById('status');
      status.style.display = 'block';
      status.className = data.result.errors.length ? 'status fail' : 'status';
      status.textContent = `${data.message}：新增 ${data.result.imported_count}，更新 ${data.result.updated_count}，跳过 ${data.result.skipped_count}`;
      await loadRules();
    }

    async function updateRule(ruleId) {
      const currentName = prompt('请输入新的规则名称，留空不修改');
      if (currentName === null) return;
      const problemCategory = prompt('请输入新的问题归类，留空不修改') || '';
      const dimension = promptDimension('请输入新的规则维度，留空不修改', '', true);
      if (dimension === null) return;
      const updates = {};
      if (currentName.trim()) updates.display_name = currentName.trim();
      if (problemCategory.trim()) updates.problem_category = problemCategory.trim();
      if (dimension) updates.dimension = dimension;
      if (!Object.keys(updates).length) return;
      const data = await postJson('/api/rules/update', { rule_id: ruleId, updates });
      const status = document.getElementById('status');
      status.style.display = 'block';
      status.className = 'status';
      status.textContent = data.message;
      await loadRules();
    }

    async function reuseRule(ruleId) {
      const current = await fetch('/api/data/current').then(res => res.json());
      const table = prompt('请输入复用目标表名', current.scope?.table_name || 'customer_order');
      if (table === null) return;
      const column = prompt('请输入复用目标字段名', current.scope?.fields?.[0] || 'mobile_phone');
      if (column === null) return;
      const data = await postJson('/api/rules/reuse', {
        rule_id: ruleId,
        table_name: table.trim(),
        column_name: column.trim(),
        engine: 'SQL'
      });
      const panel = document.getElementById('ruleReusePanel');
      const text = document.getElementById('ruleReuseText');
      if (panel && text) {
        panel.style.display = 'block';
        text.textContent = JSON.stringify(data.plan, null, 2);
      }
      const status = document.getElementById('status');
      status.style.display = 'block';
      status.className = 'status';
      status.textContent = data.message;
      return data;
    }

    async function previewRule(ruleId) {
      const current = await fetch('/api/data/current').then(res => res.json());
      const table = current.scope?.table_name || 'customer_order';
      const column = current.scope?.fields?.[0] || 'mobile_phone';
      const data = await loadJson(`/api/preview?rule_id=${encodeURIComponent(ruleId)}&table=${encodeURIComponent(table)}&column=${encodeURIComponent(column)}`);
      const panel = document.getElementById('rulePreviewPanel');
      const text = document.getElementById('rulePreviewText');
      if (panel && text) {
        panel.style.display = 'block';
        text.textContent = data.rendered_expression || JSON.stringify(data, null, 2);
      }
      const status = document.getElementById('status');
      status.style.display = 'block';
      status.className = 'status';
      status.textContent = `${ruleId} 规则样式已预览`;
      return data;
    }

    async function deleteRule(ruleId) {
      if (!confirm(`确认删除规则 ${ruleId}？`)) return;
      const data = await postJson('/api/rules/delete', { rule_id: ruleId });
      const status = document.getElementById('status');
      status.style.display = 'block';
      status.className = 'status';
      status.textContent = data.message;
      await loadRules();
    }

    async function loadRecommendations(forceRefresh = false, feedback = '') {
      if (!(await ensureImportedPage())) return;
      const data = await loadJson('/api/recommendations' + (forceRefresh ? '?refresh=true' : ''));
      const allRecommendations = data.recommendations || [];
      const activeDimension = dimensionFilters.recommendations || '';
      const visibleRecommendations = filterByDimension(allRecommendations, activeDimension);
      const recPage = pagedData('recommendations', visibleRecommendations);
      setActions([
        { text: '生成推荐', fn: 'generateRecommendations()' },
        { text: '确认推荐入库', fn: 'confirmRecommendations()', secondary: true },
        { text: '查看推荐JSON', fn: "showJson('/api/recommendations')", secondary: true }
      ]);
      setContent(`
        <section>
          <div class="stats">
            <div class="metric"><div class="metric-label">当前表</div><div class="metric-value" style="font-size:18px">${escapeHtml(data.table_name || data.table.split('.').pop())}</div><div class="metric-foot">${escapeHtml(data.table)}</div></div>
            <div class="metric"><div class="metric-label">推荐数量</div><div class="metric-value">${visibleRecommendations.length}</div><div class="metric-foot">${activeDimension ? dimName[activeDimension] : '规则推荐结果'}</div></div>
            <div class="metric"><div class="metric-label">可执行推荐</div><div class="metric-value">${data.executable_count}</div><div class="metric-foot">可确认入库</div></div>
            <div class="metric"><div class="metric-label">已确认</div><div class="metric-value">${data.confirmed_count}</div><div class="metric-foot">进入参数设定</div></div>
          </div>
          <div class="muted" style="margin-top:10px">${escapeHtml(data.message || '')}</div>
          ${dimensionTabsHtml('recommendations', allRecommendations, 'loadRecommendations', '推荐维度分类')}
        </section>
        <section>
          <h2>六维推荐统计</h2>
          ${dimensionSummaryHtml(allRecommendations, '条推荐')}
        </section>
        <section>
          <h2>推荐结果（${visibleRecommendations.length}）</h2>
        <table>
          <thead><tr><th>推荐规则</th><th>字段</th><th>维度</th><th>置信度</th><th>理由</th></tr></thead>
          <tbody>${recPage.items.length ? recPage.items.map(rec => `
            <tr>
              <td><span class="mono">${escapeHtml(rec.rule_id)}</span><br>${escapeHtml(rec.display_name)}</td>
              <td>${escapeHtml(rec.column_name || '-')}</td>
              <td>${escapeHtml(dimensionLabel(rec))}</td>
              <td>${badge(Math.round((rec.confidence || 0) * 100) + '%', 'green')}</td>
              <td>${escapeHtml(rec.reason || '')}</td>
            </tr>`).join('') : `<tr><td colspan="5" class="muted">当前维度暂无推荐结果，可切换到“全部”或重新生成推荐。</td></tr>`}</tbody>
        </table>
        ${paginationHtml('recommendations', recPage, 'loadRecommendations')}
        </section>`);
      if (feedback || forceRefresh) {
        setStatusMessage(`${feedback || '推荐已重新生成'}：当前显示 ${visibleRecommendations.length} 条，共 ${data.total} 条，可执行 ${data.executable_count} 条，已确认 ${data.confirmed_count} 条`);
      }
    }

    async function generateRecommendations() {
      pageState.recommendations = 1;
      await loadRecommendations(true, '推荐已重新生成');
    }

    async function confirmRecommendations() {
      const data = await postJson('/api/recommendations/confirm', {
        confirmed_by: 'operator'
      });
      const status = document.getElementById('status');
      status.style.display = 'block';
      status.className = 'status';
      status.textContent = `已确认入库 ${data.stored_count} 条推荐规则`;
      await loadRecommendations();
    }

    async function loadParameterLanding() {
      if (!(await ensureImportedPage())) return;
      const current = await loadJson('/api/data/current');
      const scope = current.scope || {};
      setActions([
        { text: '生成参数配置', fn: 'generateParameterConfig()' },
        { text: '保存参数配置', fn: 'saveParameterSettings()', secondary: true },
        { text: '试跑验证', fn: 'runTrialWorkflow()', secondary: true }
      ]);
      setContent(`
        <section>
          <h2>评价对象</h2>
          <div class="stats">
            <div class="metric"><div class="metric-label">数据源</div><div class="metric-value" style="font-size:20px">${escapeHtml(scope.data_source || '-')}</div><div class="metric-foot">${escapeHtml(scope.database || '-')}.${escapeHtml(scope.schema || '-')}</div></div>
            <div class="metric"><div class="metric-label">数据表</div><div class="metric-value" style="font-size:18px">${escapeHtml(scope.table_name || '-')}</div><div class="metric-foot">${escapeHtml(scope.table_fqn || '-')}</div></div>
            <div class="metric"><div class="metric-label">字段数</div><div class="metric-value">${(scope.fields || []).length}</div><div class="metric-foot">${escapeHtml((scope.fields || []).join(', '))}</div></div>
            <div class="metric"><div class="metric-label">批次</div><div class="metric-value" style="font-size:18px">${escapeHtml(scope.batch_id || '-')}</div><div class="metric-foot">${escapeHtml(scope.partition || '-')}</div></div>
          </div>
        </section>
        <section>
          <h2>参数配置</h2>
          <div class="empty">尚未生成参数配置。请点击上方“生成参数配置”，系统会把已确认的推荐规则绑定到具体字段，并自动生成阈值、级别、执行方式和技术执行方案。</div>
        </section>`);
    }

    async function configureWorkflow(feedback = '') {
      if (!(await ensureImportedPage())) return;
      const data = await loadJson('/api/workflow/configure');
      const indexedSettings = (data.settings || []).map((setting, index) => ({ ...setting, __index: index }));
      const activeDimension = dimensionFilters.parameters || '';
      const visibleSettings = filterByDimension(indexedSettings, activeDimension);
      const settingsPage = pagedData('parameters', visibleSettings);
      const previews = data.script_previews || [];
      const previewItems = settingsPage.items.map(setting => previews[setting.__index]).filter(Boolean);
      setActions([
        { text: '生成参数配置', fn: 'generateParameterConfig()' },
        { text: '保存参数配置', fn: 'saveParameterSettings()', secondary: true },
        { text: '试跑验证', fn: 'runTrialWorkflow()', secondary: true }
      ]);
      setContent(`
        <section>
          <h2>评价对象</h2>
          <div class="stats">
            <div class="metric"><div class="metric-label">数据源</div><div class="metric-value" style="font-size:20px">${escapeHtml(data.scope.data_source)}</div><div class="metric-foot">${escapeHtml(data.scope.database)}.${escapeHtml(data.scope.schema)}</div></div>
            <div class="metric"><div class="metric-label">数据表</div><div class="metric-value" style="font-size:18px">${escapeHtml(data.scope.table_name)}</div><div class="metric-foot">${escapeHtml(data.scope.table_fqn)}</div></div>
            <div class="metric"><div class="metric-label">字段数</div><div class="metric-value">${data.scope.fields.length}</div><div class="metric-foot">${escapeHtml(data.scope.fields.join(', '))}</div></div>
            <div class="metric"><div class="metric-label">批次</div><div class="metric-value" style="font-size:18px">${escapeHtml(data.scope.batch_id)}</div><div class="metric-foot">${escapeHtml(data.scope.partition)}</div></div>
          </div>
          ${dimensionTabsHtml('parameters', indexedSettings, 'configureWorkflow', '参数配置维度分类')}
        </section>
        <section>
          <h2>六维配置统计</h2>
          ${dimensionSummaryHtml(indexedSettings, '条配置')}
        </section>
        <section class="two-col">
          <div>
            <h2>参数配置（${visibleSettings.length}）</h2>
        <table>
          <thead><tr><th>规则</th><th>字段</th><th>维度</th><th>状态</th><th>校验级别</th><th>业务参数</th><th>操作</th></tr></thead>
          <tbody>${settingsPage.items.length ? settingsPage.items.map(setting => `
            <tr>
              <td class="mono">${escapeHtml(setting.rule_id)}</td>
              <td>${escapeHtml(setting.target_column)}</td>
              <td>${escapeHtml(dimensionLabel(setting))}</td>
              <td>${badge(setting.enabled === false ? '停用' : '启用', setting.enabled === false ? 'gray' : 'green')}</td>
              <td>${validationLevelBadge(setting.validation_level)}</td>
              <td>${escapeHtml(businessParameterSummary(setting))}</td>
              <td><button class="tiny secondary" onclick="showParameterEditor('${escapeJs(setting.setting_id)}')">编辑</button></td>
            </tr>`).join('') : `<tr><td colspan="7" class="muted">当前维度暂无参数配置，可切换到“全部”。</td></tr>`}</tbody>
        </table>
        ${paginationHtml('parameters', settingsPage, 'configureWorkflow')}
          </div>
          <div>
            <h2>人工调整区</h2>
            <div class="empty">点击左侧“编辑”后，可调整启用状态、绑定字段、阈值、校验级别、执行方式和责任角色。保存后请重新试跑验证。</div>
            <div id="parameterEditor"></div>
          </div>
        </section>`);
      window.currentParameterSettings = indexedSettings;
      window.currentParameterPreviews = previews;
      if (feedback) {
        setStatusMessage(`${feedback}：当前显示 ${visibleSettings.length} 条，已生成 ${data.settings.length} 条参数配置`);
      }
    }

    function showParameterEditor(settingId) {
      const settings = window.currentParameterSettings || [];
      const previews = window.currentParameterPreviews || [];
      const setting = settings.find(item => item.setting_id === settingId);
      if (!setting) {
        setStatusMessage('未找到要编辑的参数配置。', true);
        return;
      }
      const preview = previews[setting.__index] || {};
      const id = safeDomId(setting.setting_id);
      const threshold = setting.threshold || {};
      const fields = (setting.scope && setting.scope.fields) || [];
      const kind = parameterEditorKind(setting);
      const passPercent = percentFromRate(threshold.pass_rate ?? 1);
      const technicalText = JSON.stringify(setting.parameter_overrides || {}, null, 2);
      document.getElementById('parameterEditor').innerHTML = `
        <div class="panel">
          <h3>${escapeHtml(ruleFriendlyName(setting))}</h3>
          <div class="business-note">这里是给业务人员填写的规则要求。系统会把这些中文参数自动转换成可执行校验参数，用户不需要编写 SQL、正则表达式或 JSON。</div>
          <input id="param_${id}_setting_id" type="hidden" value="${escapeHtml(setting.setting_id)}">
          <div class="form-grid">
            <div class="field">
              <label>是否启用</label>
              <select id="param_${id}_enabled">
                <option value="true" ${setting.enabled === false ? '' : 'selected'}>启用</option>
                <option value="false" ${setting.enabled === false ? 'selected' : ''}>停用</option>
              </select>
            </div>
            <div class="field">
              <label>绑定字段</label>
              <select id="param_${id}_target_column">
                ${fields.map(field => `<option value="${escapeHtml(field)}" ${field === setting.target_column ? 'selected' : ''}>${escapeHtml(field)}</option>`).join('')}
              </select>
            </div>
            <div class="field">
              <label>校验级别</label>
              <select id="param_${id}_validation_level">
                ${validationLevelOptions(setting.validation_level)}
              </select>
            </div>
          </div>
          ${businessParameterHtml(setting, id)}
          <div class="form-grid" style="margin-top:12px">
            <div class="field"><label>要求通过率（%）</label><input id="param_${id}_pass_percent" type="number" min="0" max="100" step="0.1" value="${escapeHtml(passPercent)}"><div class="help-text">100 表示一条错误也不允许；99 表示最多允许 1% 异常。</div></div>
            <div class="field"><label>规则权重</label><input id="param_${id}_weight" type="number" min="0" step="0.1" value="${escapeHtml(setting.weight ?? 1)}"><div class="help-text">用于综合评分，数字越大影响越大。</div></div>
            <div class="field"><label>责任角色</label><input id="param_${id}_responsible_role" value="${escapeHtml(setting.responsible_role || '数据责任人')}"><div class="help-text">质量问题默认派给该角色。</div></div>
          </div>
          <div style="margin-top:12px">
            <label>业务备注</label>
            <textarea id="param_${id}_condition" class="business-textarea" placeholder="可选：填写业务说明、豁免场景或处理口径">${escapeHtml(setting.condition || '')}</textarea>
          </div>
          <details class="tech-detail">
            <summary>技术参数与执行脚本（实施人员查看）</summary>
            <div class="form-grid" style="margin-top:12px">
              <div class="field">
                <label>执行引擎</label>
                <select id="param_${id}_execution_engine">
                  ${['SQL','GE','ETL'].map(engine => `<option value="${engine}" ${setting.execution_engine === engine ? 'selected' : ''}>${engine}</option>`).join('')}
                </select>
              </div>
              <div class="field"><label>阈值单位</label><input id="param_${id}_threshold_unit" value="${escapeHtml(threshold.unit || 'failed_rows')}"></div>
              <div class="field"><label>期望值</label><input id="param_${id}_expected_value" value="${escapeHtml(threshold.expected_value ?? 0)}"></div>
            </div>
            <label style="margin-top:12px">当前底层参数</label>
            <textarea id="param_${id}_technical_overrides" class="compact-textarea">${escapeHtml(technicalText)}</textarea>
            <label style="margin-top:12px">当前技术脚本</label>
            <pre>${escapeHtml(preview.rendered_expression || '保存后可重新生成脚本预览')}</pre>
          </details>
          <div class="toolbar">
            <button onclick="saveSingleParameterSetting('${escapeJs(setting.setting_id)}')">保存当前配置</button>
            <button class="secondary" onclick="saveParameterSettings()">保存全部配置</button>
          </div>
        </div>`;
      document.getElementById('parameterEditor').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function collectParameterSetting(setting) {
      const id = safeDomId(setting.setting_id);
      const kind = parameterEditorKind(setting);
      const overridesRaw = document.getElementById(`param_${id}_technical_overrides`)?.value;
      let overrides = setting.parameter_overrides || {};
      if (overridesRaw !== undefined) {
        overrides = overridesRaw.trim() ? JSON.parse(overridesRaw) : {};
      }
      overrides = businessOverridesFromForm(kind, setting, id, overrides);
      return {
        setting_id: setting.setting_id,
        enabled: (document.getElementById(`param_${id}_enabled`)?.value ?? String(setting.enabled !== false)) === 'true',
        target_column: document.getElementById(`param_${id}_target_column`)?.value || setting.target_column,
        validation_level: document.getElementById(`param_${id}_validation_level`)?.value || setting.validation_level,
        execution_engine: document.getElementById(`param_${id}_execution_engine`)?.value || setting.execution_engine,
        responsible_role: document.getElementById(`param_${id}_responsible_role`)?.value || setting.responsible_role,
        condition: document.getElementById(`param_${id}_condition`)?.value || '',
        weight: Number(document.getElementById(`param_${id}_weight`)?.value ?? setting.weight ?? 1),
        threshold: {
          ...(setting.threshold || {}),
          pass_rate: rateFromPercentInput(`param_${id}_pass_percent`, setting.threshold?.pass_rate ?? 1),
          unit: document.getElementById(`param_${id}_threshold_unit`)?.value || setting.threshold?.unit || 'failed_rows',
          expected_value: document.getElementById(`param_${id}_expected_value`)?.value ?? setting.threshold?.expected_value ?? 0
        },
        parameter_overrides: overrides
      };
    }

    async function saveSingleParameterSetting(settingId) {
      const setting = (window.currentParameterSettings || []).find(item => item.setting_id === settingId);
      if (!setting) {
        setStatusMessage('未找到要保存的参数配置。', true);
        return;
      }
      const payload = { settings: [collectParameterSetting(setting)] };
      const data = await postJson('/api/workflow/settings/update', payload);
      setStatusMessage(`${data.message}：已保存 ${data.updated_count} 条`);
      await configureWorkflow('参数配置已保存');
    }

    async function saveParameterSettings() {
      const settings = window.currentParameterSettings || [];
      if (!settings.length) {
        setStatusMessage('请先点击“生成参数配置”。', true);
        return;
      }
      const edited = settings
        .filter(setting => document.getElementById(`param_${safeDomId(setting.setting_id)}_setting_id`))
        .map(setting => collectParameterSetting(setting));
      const payload = { settings: edited.length ? edited : settings.map(setting => ({ setting_id: setting.setting_id })) };
      const data = await postJson('/api/workflow/settings/update', payload);
      setStatusMessage(`${data.message}：已保存 ${data.updated_count} 条`);
      await configureWorkflow('参数配置已保存');
    }

    async function generateParameterConfig() {
      pageState.parameters = 1;
      await configureWorkflow('参数配置已生成');
    }

    async function trialWorkflow(feedback = '') {
      if (!(await ensureImportedPage())) return;
      const data = await loadJson('/api/workflow/trial');
      const allTrialResults = data.trial_results || [];
      const activeDimension = dimensionFilters.trial || '';
      const visibleTrialResults = filterByDimension(allTrialResults, activeDimension);
      const trialPage = pagedData('trial', visibleTrialResults);
      setContent(`
        <section>
          <h2>试跑维度分类</h2>
          ${dimensionTabsHtml('trial', allTrialResults, 'trialWorkflow', '试跑结果维度分类')}
        </section>
        <section>
          <h2>六维试跑统计</h2>
          ${dimensionSummaryHtml(allTrialResults, '条结果')}
        </section>
        <section>
          <h2>试跑验证（${visibleTrialResults.length}）</h2>
        <table>
          <thead><tr><th>规则</th><th>维度</th><th>是否通过</th><th>通过率</th><th>异常样例</th></tr></thead>
          <tbody>${trialPage.items.length ? trialPage.items.map(item => `
            <tr>
              <td class="mono">${escapeHtml(item.rule_id)}</td>
              <td>${escapeHtml(dimensionLabel(item))}</td>
              <td>${badge(item.passed ? '通过' : '未通过', item.passed ? 'green' : 'red')}</td>
              <td>${Math.round(item.pass_rate * 100)}%</td>
              <td>${item.invalid_samples.map(s => `${escapeHtml(s.column_name)}=${escapeHtml(s.value)}：${escapeHtml(s.reason)}`).join('<br>')}</td>
            </tr>`).join('') : `<tr><td colspan="5" class="muted">当前维度暂无试跑结果，可切换到“全部”。</td></tr>`}</tbody>
        </table>
        ${paginationHtml('trial', trialPage, 'trialWorkflow')}
        </section>
        <section>
          <h2>导入数据</h2>
          <pre>${escapeHtml(JSON.stringify(data.sample_rows, null, 2))}</pre>
        </section>`);
      if (feedback) {
        const passed = visibleTrialResults.filter(item => item.passed).length;
        setStatusMessage(`${feedback}：当前显示 ${visibleTrialResults.length} 条，${passed} 条通过，${visibleTrialResults.length - passed} 条未通过`);
      }
    }

    async function runTrialWorkflow() {
      const current = await loadJson('/api/data/current');
      if (!current.configured) {
        setStatusMessage('请先点击“生成参数配置”，再进行试跑验证。', true);
        return;
      }
      pageState.trial = 1;
      await trialWorkflow('试跑验证已完成');
    }

    async function executeWorkflow(feedback = '') {
      if (!(await ensureImportedPage())) return;
      const data = await loadJson('/api/workflow/execute');
      const run = data.run;
      const task = data.task || {};
      const allResults = run.rule_results || [];
      const activeDimension = dimensionFilters.execution || '';
      const visibleResults = filterByDimension(allResults, activeDimension);
      const executionPage = pagedData('execution', visibleResults);
      setActions([
        { text: '重新执行评价', fn: 'runQualityExecution()' },
        { text: '查看质量问题', fn: "location.href='/issues'", secondary: true },
        { text: '查看六维看板', fn: "location.href='/dashboard'", secondary: true }
      ]);
      setContent(`
        <section>
        <div class="stats">
          <div class="metric"><div class="metric-label">评价状态</div><div class="metric-value" style="font-size:20px">${escapeHtml(executionStatusLabel(run.status, run.blocked))}</div><div class="metric-foot">${escapeHtml(executionStatusFoot(run.status, run.blocked))}</div></div>
          <div class="metric"><div class="metric-label">规则检查</div><div class="metric-value">${visibleResults.length}</div><div class="metric-foot">${activeDimension ? dimName[activeDimension] : `通过 ${run.passed_rules} 条 / 未通过 ${run.failed_rules} 条`}</div></div>
          <div class="metric"><div class="metric-label">异常数据</div><div class="metric-value">${run.exception_rows}</div><div class="metric-foot">需要复核的数据行</div></div>
          <div class="metric"><div class="metric-label">质量问题</div><div class="metric-value">${run.issue_ids.length}</div><div class="metric-foot">已生成待处理问题</div></div>
        </div>
        ${dimensionTabsHtml('execution', allResults, 'executeWorkflow', '按六个维度查看执行结果')}
        </section>
        <section>
          <h2>本次评价范围</h2>
          <div class="stats">
            <div class="metric"><div class="metric-label">执行方式</div><div class="metric-value" style="font-size:18px">${escapeHtml(taskScheduleLabel(task.schedule))}</div><div class="metric-foot">${task.dependency ? `依赖：${escapeHtml(task.dependency)}` : '点击按钮后立即检查'}</div></div>
            <div class="metric"><div class="metric-label">检查范围</div><div class="metric-value" style="font-size:18px">${escapeHtml(scanModeLabel(task.scan_mode))}</div><div class="metric-foot">根据页面配置执行</div></div>
            <div class="metric"><div class="metric-label">使用规则</div><div class="metric-value">${run.total_rules}</div><div class="metric-foot">已按规则参数自动执行</div></div>
            <div class="metric"><div class="metric-label">执行人</div><div class="metric-value" style="font-size:18px">${escapeHtml(task.created_by || '操作员')}</div><div class="metric-foot">本次评价操作记录</div></div>
          </div>
        </section>
        <section>
          <h2>六维执行统计</h2>
          ${dimensionSummaryHtml(allResults, '条结果')}
        </section>
        <section>
        <h2>规则执行明细（${visibleResults.length}）</h2>
        <table>
          <thead><tr><th>规则</th><th>维度</th><th>检查结果</th><th>异常行</th><th>处理建议</th></tr></thead>
          <tbody>${executionPage.items.length ? executionPage.items.map(item => `
            <tr>
              <td>${escapeHtml(ruleFriendlyName(item))}</td>
              <td>${escapeHtml(dimensionLabel(item))}</td>
              <td>${ruleRunStatusBadge(item.status)}</td>
              <td>${item.failed_rows}</td>
              <td>${escapeHtml(ruleRunSuggestion(item))}</td>
            </tr>`).join('') : `<tr><td colspan="5" class="muted">当前维度暂无执行结果，可切换到“全部”。</td></tr>`}</tbody>
        </table>
        ${paginationHtml('execution', executionPage, 'executeWorkflow')}
        </section>`);
      if (feedback) {
        setStatusMessage(`${feedback}：当前显示 ${visibleResults.length} 条，评价状态 ${executionStatusLabel(run.status, run.blocked)}，通过 ${run.passed_rules}/${run.total_rules}，问题 ${run.issue_ids.length} 个`);
      }
    }

    async function runQualityExecution() {
      pageState.execution = 1;
      const payload = {
        schedule: document.getElementById('executionSchedule')?.value || 'manual',
        scan_mode: document.getElementById('executionScanMode')?.value || 'full',
        dependency: document.getElementById('executionDependency')?.value || '',
        parallelism: 2,
        created_by: document.getElementById('executionOwner')?.value || '数据责任人'
      };
      const data = await postJson('/api/workflow/execute', payload);
      setOutput(data, false);
      await executeWorkflow('评价任务已执行');
    }

    async function loadExecutionLanding() {
      if (!(await ensureImportedPage())) return;
      const current = await loadJson('/api/data/current');
      setActions([{ text: '执行评价任务', fn: 'runQualityExecution()' }]);
      setContent(`
        <section>
          <h2>质量评价实施</h2>
          <div class="business-note">这里用于正式执行质量评价。确认检查范围后点击“执行评价任务”，系统会自动按已配置规则检查数据，并生成可处理的问题清单。</div>
          <div class="stats">
            <div class="metric"><div class="metric-label">当前数据表</div><div class="metric-value" style="font-size:18px">${escapeHtml(current.scope ? current.scope.table_name : '-')}</div><div class="metric-foot">${escapeHtml(current.scope ? current.scope.table_fqn : '-')}</div></div>
            <div class="metric"><div class="metric-label">参数配置</div><div class="metric-value">${current.rule_setting_count || 0}</div><div class="metric-foot">${current.configured ? '已生成' : '待生成'}</div></div>
            <div class="metric"><div class="metric-label">导入行数</div><div class="metric-value">${current.row_count || 0}</div><div class="metric-foot">待评价数据</div></div>
            <div class="metric"><div class="metric-label">执行方式</div><div class="metric-value" style="font-size:18px">立即执行</div><div class="metric-foot">点击按钮触发</div></div>
          </div>
        </section>
        <section>
          <h2>执行前确认</h2>
          <div class="form-grid">
            <div class="field"><label>什么时候执行</label><select id="executionSchedule">
              <option value="manual">现在执行</option>
              <option value="dependency">等上游数据准备好后执行</option>
            </select></div>
            <div class="field"><label>检查哪些数据</label><select id="executionScanMode">
              <option value="full">检查全部导入数据</option>
              <option value="incremental">只检查新增或变更数据</option>
            </select></div>
            <div class="field"><label>执行人</label><input id="executionOwner" value="数据责任人"></div>
            <div class="field"><label>上游说明（可选）</label><input id="executionDependency" placeholder="例如：客户表已完成同步"></div>
          </div>
          <div class="muted" style="margin-top:10px">页面只保留业务上需要确认的信息；具体执行脚本和技术过程由系统自动完成。</div>
        </section>
        <section><div class="empty">尚未执行本次质量评价。请点击“执行评价任务”，系统会按已生成的参数配置运行 10 条规则并生成问题结果。</div></section>`);
    }

    async function loadDashboard(feedback = '') {
      if (!(await ensureImportedPage())) return;
      const data = await loadJson('/api/workflow/dashboard');
      setActions([{ text: '刷新看板', fn: 'refreshDashboard()' }, { text: '查看看板JSON', fn: "showJson('/api/workflow/dashboard')", secondary: true }]);
      const chartItems = Object.entries(data.dimension_scores).map(([key, item]) => ({
        key,
        label: item.dimension_zh || dimName[key] || key,
        score: Number(item.score || 0),
        passRate: item.rule_pass_rate || 0,
        totalRules: item.total_rules || 0,
        failedRules: item.failed_rules || 0
      }));
      const dimensionPage = pagedData('dashboardDimensions', chartItems);
      setContent(`
        <section>
        <div class="stats">
          <div class="metric"><div class="metric-label">总体得分</div><div class="metric-value">${data.overall_score}</div><div class="metric-foot">${escapeHtml(data.quality_level)}</div></div>
          <div class="metric"><div class="metric-label">规则通过率</div><div class="metric-value">${Math.round(data.rule_pass_rate * 100)}%</div><div class="metric-foot">当前执行批次</div></div>
          <div class="metric"><div class="metric-label">问题数量</div><div class="metric-value">${data.impact_scope.issue_count}</div><div class="metric-foot">影响 ${data.impact_scope.affected_rows} 行</div></div>
          <div class="metric"><div class="metric-label">下游影响</div><div class="metric-value">${data.impact_scope.downstream_objects.length}</div><div class="metric-foot">报表/API</div></div>
        </div>
        </section>
        <section>
          <h2>六维图形展示</h2>
          <div class="chart-grid">
            <div class="chart-box">
              <h3>得分占比</h3>
              <canvas id="dimensionPie"></canvas>
            </div>
            <div class="chart-box">
              <h3>六维得分对比</h3>
              <canvas id="dimensionBar"></canvas>
            </div>
          </div>
        </section>
        <section>
        <h2>六维评分</h2>
        <table>
          <thead><tr><th>维度</th><th>得分</th><th>通过率</th><th>规则</th><th>状态条</th></tr></thead>
          <tbody>${dimensionPage.items.map(item => {
            const score = Number(item.score || 0);
            const cls = score >= 90 ? '' : (score >= 70 ? 'warn' : 'bad');
            return `<tr>
              <td>${escapeHtml(item.label)}</td>
              <td>${score}</td>
              <td>${Math.round((item.passRate || 0) * 100)}%</td>
              <td>${item.totalRules - item.failedRules}/${item.totalRules}</td>
              <td><div class="progress"><div class="bar ${cls}" style="width:${score}%"></div></div></td>
            </tr>`;
          }).join('')}</tbody>
        </table>
        ${paginationHtml('dashboardDimensions', dimensionPage, 'loadDashboard')}
        </section>`);
      drawPieChart('dimensionPie', chartItems);
      drawBarChart('dimensionBar', chartItems);
      if (feedback) {
        setStatusMessage(`${feedback}：总体得分 ${data.overall_score}，质量等级 ${data.quality_level}，问题 ${data.impact_scope.issue_count} 个`);
      }
    }

    async function refreshDashboard() {
      await loadDashboard('看板已刷新');
    }

    async function loadDashboardLanding() {
      if (!(await ensureImportedPage())) return;
      setActions([{ text: '刷新看板', fn: 'refreshDashboard()' }, { text: '查看看板JSON', fn: "showJson('/api/workflow/dashboard')", secondary: true }]);
      setContent(`<section><h2>六维质量看板</h2><div class="empty">尚未加载六维看板。请点击“刷新看板”，系统会基于最近一次评价执行结果计算总体得分、质量等级和六维得分。</div></section>`);
    }

    function issueQueryString(includeDimension = true) {
      const params = new URLSearchParams();
      Object.entries(issueFilters).forEach(([key, value]) => {
        if (!includeDimension && key === 'dimension') return;
        if (value !== undefined && value !== null && String(value).trim() !== '') {
          params.set(key, value);
        }
      });
      if (!params.has('include_archived')) params.set('include_archived', 'true');
      return params.toString();
    }

    function applyIssueFilters() {
      ['batch_id', 'resource', 'status', 'data_source', 'business_domain', 'dimension'].forEach(key => {
        const el = document.getElementById('issueFilter_' + key);
        issueFilters[key] = el ? el.value.trim() : '';
      });
      issueFilters.include_archived = document.getElementById('issueFilter_include_archived')?.checked ? 'true' : 'false';
      pageState.issues = 1;
      loadIssues('查询完成');
    }

    function clearIssueFilters() {
      Object.keys(issueFilters).forEach(key => delete issueFilters[key]);
      pageState.issues = 1;
      loadIssues('筛选条件已清空');
    }

    async function updateIssueWorkflow(issueId) {
      const safeId = escapeJs(issueId);
      const status = document.getElementById('issueStatus_' + safeId)?.value || 'ticketed';
      const assignee = prompt('请输入责任人/处理人', '数据责任人');
      if (assignee === null) return;
      const remediation = prompt('请输入整改说明，留空则保留原整改建议', '');
      if (remediation === null) return;
      const reviewNotes = prompt('请输入审核/复核意见，留空则不填写', status === 'closed' || status === 'archived' ? '复核通过' : '');
      if (reviewNotes === null) return;
      const data = await postJson('/api/workflow/issues/update', {
        issue_id: issueId,
        status,
        assignee,
        remediation,
        review_notes: reviewNotes
      });
      await loadIssues(`${data.message}：${issueStatusName[status] || status}`);
    }

    async function loadIssues(feedback = '') {
      if (!(await ensureImportedPage())) return;
      const query = issueQueryString();
      const data = await loadJson('/api/workflow/issues' + (query ? '?' + query : ''));
      const dimensionQuery = issueQueryString(false);
      const dimensionData = issueFilters.dimension ? await loadJson('/api/workflow/issues' + (dimensionQuery ? '?' + dimensionQuery : '')) : data;
      const dimensionRows = dimensionData.issues || [];
      const issuesPage = pagedData('issues', data.issues || []);
      setActions([{ text: '加载问题分析', fn: 'loadIssues()' }, { text: '进入计分规则', fn: "location.href='/scoring'", secondary: true }, { text: '进入问题溯源', fn: "location.href='/lineage'", secondary: true }, { text: '生成流程报告', fn: 'loadWorkflowReport()', secondary: true }, { text: '下载报告', fn: 'downloadWorkflowReport()', secondary: true }, { text: '模拟推送', fn: 'mockPushWorkflowReport()', secondary: true }]);
      setContent(`
        <section>
          <h2>问题筛选</h2>
          <div class="form-grid">
            <div class="field"><label>批次</label><input id="issueFilter_batch_id" value="${escapeHtml(issueFilters.batch_id || '')}" placeholder="batch_id"></div>
            <div class="field"><label>资源</label><input id="issueFilter_resource" value="${escapeHtml(issueFilters.resource || '')}" placeholder="表名/资源名"></div>
            <div class="field"><label>状态</label><select id="issueFilter_status">
              <option value="">全部状态</option>
              ${['discovered','alerted','ticketed','remediating','reviewing','closed','archived'].map(item => `<option value="${item}" ${issueFilters.status === item ? 'selected' : ''}>${item}</option>`).join('')}
            </select></div>
            <div class="field"><label>数据源</label><input id="issueFilter_data_source" value="${escapeHtml(issueFilters.data_source || '')}" placeholder="mysql/oracle/api"></div>
            <div class="field"><label>业务域</label><input id="issueFilter_business_domain" value="${escapeHtml(issueFilters.business_domain || '')}" placeholder="客户订单"></div>
            <div class="field"><label>维度</label><select id="issueFilter_dimension">
              <option value="">全部维度</option>
              ${Object.entries(dimName).map(([key, name]) => `<option value="${key}" ${issueFilters.dimension === key ? 'selected' : ''}>${name}</option>`).join('')}
            </select></div>
          </div>
          <div class="toolbar">
            <button onclick="applyIssueFilters()">查询</button>
            <button class="secondary" onclick="clearIssueFilters()">清空</button>
            <label style="display:flex;align-items:center;gap:8px;margin:0;color:#344054;font-weight:700"><input id="issueFilter_include_archived" type="checkbox" style="width:auto" ${(issueFilters.include_archived || 'true') === 'true' ? 'checked' : ''}>包含已归档</label>
          </div>
          ${dimensionTabsHtml('issues', dimensionRows, 'loadIssues', '问题维度分类')}
        </section>
        <section>
          <h2>六维问题统计</h2>
          ${dimensionSummaryHtml(dimensionRows, '个问题')}
        </section>
        <section class="two-col">
          <div>
            <h2>本次质量问题列表（${data.total}）</h2>
        <table>
          <thead><tr><th>问题ID</th><th>规则</th><th>维度</th><th>状态</th><th>责任人</th><th>整改建议</th><th>工单操作</th></tr></thead>
          <tbody>${issuesPage.items.length ? issuesPage.items.map(issue => `
            <tr>
              <td class="mono">${escapeHtml(issue.issue_id)}</td>
              <td class="mono">${escapeHtml(issue.rule_id)}</td>
              <td>${escapeHtml(dimensionLabel(issue))}</td>
              <td>${badge(issueStatusName[issue.status] || issue.status, issue.status === 'archived' || issue.status === 'closed' ? 'green' : 'amber')}</td>
              <td>${escapeHtml(issue.assignee)}</td>
              <td>${escapeHtml(issue.remediation)}</td>
              <td>
                <div class="row-actions">
                  <select id="issueStatus_${escapeJs(issue.issue_id)}" style="min-width:112px">
                    ${issueStatusOptions(issue.status)}
                  </select>
                  <button class="tiny secondary" onclick="updateIssueWorkflow('${escapeJs(issue.issue_id)}')">更新工单</button>
                  <button class="tiny secondary" onclick="location.href='/lineage'">查看溯源</button>
                </div>
              </td>
            </tr>`).join('') : `<tr><td colspan="7" class="muted">当前筛选条件下没有质量问题。</td></tr>`}</tbody>
        </table>
          ${paginationHtml('issues', issuesPage, 'loadIssues')}
          </div>
          <div>
            <h2>真实血缘提示</h2>
            ${data.lineage_sample && data.lineage_sample.available
              ? `<pre>${escapeHtml(JSON.stringify(data.lineage_sample, null, 2))}</pre>`
              : `<div class="empty">质量问题已生成，但溯源结果必须来自真实字段级血缘数据。请进入“质量问题溯源”页面导入真实血缘后查看。</div>`}
          </div>
        </section>`);
      if (feedback) {
        setStatusMessage(`${feedback}：本次评价匹配 ${data.total} 个质量问题`);
      }
    }

    async function loadIssuesLanding() {
      if (!(await ensureImportedPage())) return;
      setActions([{ text: '加载问题分析', fn: "loadIssues('问题分析已加载')" }, { text: '进入计分规则', fn: "location.href='/scoring'", secondary: true }, { text: '进入问题溯源', fn: "location.href='/lineage'", secondary: true }, { text: '生成流程报告', fn: 'loadWorkflowReport()', secondary: true }, { text: '下载报告', fn: 'downloadWorkflowReport()', secondary: true }, { text: '模拟推送', fn: 'mockPushWorkflowReport()', secondary: true }]);
      setContent(`<section><h2>质量问题分析</h2><div class="empty">尚未加载质量问题列表。请点击“加载问题分析”，系统会查询最近一次质量评价产生的问题，并支持按状态、资源、数据源、业务域和维度筛选。</div></section>`);
    }

    async function loadArchive(feedback = '') {
      const data = await loadJson('/api/workflow/archive');
      setContent(`<section><h2>计分规则归档</h2><pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre></section>`);
      if (feedback) {
        setStatusMessage(`${feedback}：${data.archive ? data.archive.archive_id : ''}`);
      }
    }

    const defaultWeights = {
      normativity: 0.20,
      completeness: 0.20,
      accuracy: 0.15,
      consistency: 0.15,
      timeliness: 0.15,
      accessibility: 0.15
    };

    const issueStatusName = {
      discovered: '已发现',
      alerted: '已告警',
      ticketed: '已建工单',
      remediating: '整改中',
      reviewing: '复核中',
      closed: '已关闭',
      archived: '已归档'
    };

    function issueStatusOptions(selected = 'ticketed') {
      return Object.entries(issueStatusName)
        .map(([key, name]) => `<option value="${key}" ${selected === key ? 'selected' : ''}>${name}</option>`)
        .join('');
    }

    function defaultLineagePayload() {
      const currentTable = 'customer_order';
      return {
        lineage_records: [
          {
            lineage_id: 'real_lineage_customer_order_mobile',
            target_table: currentTable,
            target_column: 'mobile_phone',
            source_system: 'crm',
            source_table: 'crm_customer',
            source_column: 'mobile_phone',
            etl_task: 'ods_to_dw_customer_order',
            transform_rule: '清洗手机号后写入订单宽表',
            downstream_objects: ['customer_order_quality_report', 'customer_order_api'],
            owner: '数据责任人'
          }
        ]
      };
    }

    async function importLineageData() {
      const raw = prompt('请粘贴真实字段级血缘JSON。该数据应来自血缘表、ETL配置或外部血缘系统。', JSON.stringify(defaultLineagePayload(), null, 2));
      if (raw === null) return;
      let payload;
      try {
        payload = JSON.parse(raw);
      } catch (err) {
        setStatusMessage('血缘JSON解析失败：' + err, true);
        return;
      }
      const data = await postJson('/api/lineage/import', payload);
      await loadLineage('', `${data.message}：${data.total} 条`);
    }

    async function loadScoring(feedback = '') {
      if (!(await ensureImportedPage())) return;
      const dashboard = await loadJson('/api/workflow/dashboard');
      const scoreItems = Object.entries(dashboard.dimension_scores || {}).map(([key, item]) => ({
        key,
        label: item.dimension_zh || dimName[key] || key,
        score: Number(item.score || 0),
        passRate: item.rule_pass_rate || 0,
        failedRules: item.failed_rules || 0,
        totalRules: item.total_rules || 0
      }));
      const scoringPage = pagedData('scoringDimensions', scoreItems);
      setActions([
        { text: '归档计分规则', fn: 'archiveScoring()' },
        { text: '刷新计分规则', fn: 'refreshScoring()', secondary: true },
        { text: '查看看板JSON', fn: "showJson('/api/workflow/dashboard')", secondary: true }
      ]);
      setContent(`
        <section>
          <div class="stats">
            <div class="metric"><div class="metric-label">总体得分</div><div class="metric-value">${dashboard.overall_score}</div><div class="metric-foot">${escapeHtml(dashboard.quality_level)}</div></div>
            <div class="metric"><div class="metric-label">规则通过率</div><div class="metric-value">${Math.round((dashboard.rule_pass_rate || 0) * 100)}%</div><div class="metric-foot">当前批次</div></div>
            <div class="metric"><div class="metric-label">问题数量</div><div class="metric-value">${dashboard.impact_scope.issue_count}</div><div class="metric-foot">计分扣减依据</div></div>
            <div class="metric"><div class="metric-label">等级阈值</div><div class="metric-value" style="font-size:18px">优秀/良好/一般</div><div class="metric-foot">支持归档调整</div></div>
          </div>
        </section>
        <section class="two-col">
          <div>
            <h2>六维权重</h2>
            <div class="form-grid">
              ${Object.entries(defaultWeights).map(([key, value]) => `
                <div class="field">
                  <label>${dimName[key]}</label>
                  <input id="weight_${key}" type="number" min="0" max="1" step="0.01" value="${value}">
                </div>`).join('')}
            </div>
            <h2 style="margin-top:16px">等级阈值</h2>
            <div class="form-grid">
              <div class="field"><label>优秀下限</label><input id="grade_excellent_min" type="number" value="90"></div>
              <div class="field"><label>良好下限</label><input id="grade_good_min" type="number" value="80"></div>
              <div class="field"><label>一般下限</label><input id="grade_normal_min" type="number" value="70"></div>
            </div>
            <div class="toolbar"><button onclick="archiveScoring()">归档计分规则</button></div>
          </div>
          <div>
            <h2>计分公式</h2>
            <pre>总分 = Σ(维度得分 × 维度权重)
P0失败任务可阻断下游处理。
等级阈值可归档保存，作为本次质量评价批次的评分口径。</pre>
          </div>
        </section>
        <section>
          <h2>当前维度得分</h2>
          <table>
            <thead><tr><th>维度</th><th>得分</th><th>通过率</th><th>失败规则</th></tr></thead>
            <tbody>${scoringPage.items.map(item => `
              <tr>
                <td>${escapeHtml(item.label)}</td>
                <td>${item.score}</td>
                <td>${Math.round((item.passRate || 0) * 100)}%</td>
                <td>${item.failedRules}/${item.totalRules}</td>
              </tr>`).join('')}</tbody>
          </table>
          ${paginationHtml('scoringDimensions', scoringPage, 'loadScoring')}
        </section>
        <section id="scoringArchivePanel" style="display:none">
          <h2>归档结果</h2>
          <pre id="scoringArchiveText"></pre>
        </section>`);
      if (feedback) {
        setStatusMessage(`${feedback}：当前总分 ${dashboard.overall_score}，等级 ${dashboard.quality_level}`);
      }
    }

    async function refreshScoring() {
      await loadScoring('计分规则已刷新');
    }

    async function loadScoringLanding() {
      if (!(await ensureImportedPage())) return;
      setActions([
        { text: '归档计分规则', fn: 'archiveScoring()' },
        { text: '刷新计分规则', fn: 'refreshScoring()', secondary: true },
        { text: '查看看板JSON', fn: "showJson('/api/workflow/dashboard')", secondary: true }
      ]);
      setContent(`<section><h2>计分规则</h2><div class="empty">尚未加载计分规则。请点击“刷新计分规则”查看当前得分口径，或点击“归档计分规则”保存六维权重和等级阈值。</div></section>`);
    }

    async function archiveScoring() {
      const weights = {};
      Object.keys(defaultWeights).forEach(key => {
        const raw = document.getElementById('weight_' + key)?.value;
        const number = Number(raw);
        weights[key] = Number.isFinite(number) ? number : defaultWeights[key];
      });
      const excellentMin = Number(document.getElementById('grade_excellent_min')?.value || 90);
      const goodMin = Number(document.getElementById('grade_good_min')?.value || 80);
      const normalMin = Number(document.getElementById('grade_normal_min')?.value || 70);
      const payload = {
        weights,
        grade_thresholds: {
          '优秀': { min: excellentMin, max: 100 },
          '良好': { min: goodMin, max: excellentMin - 0.01 },
          '一般': { min: normalMin, max: goodMin - 0.01 },
          '待提升': { min: 60, max: normalMin - 0.01 },
          '高风险': { min: 0, max: 59.99 }
        },
        archived_by: 'operator',
        description: '页面归档计分规则'
      };
      const data = await postJson('/api/workflow/archive', payload);
      const panel = document.getElementById('scoringArchivePanel');
      const text = document.getElementById('scoringArchiveText');
      if (panel && text) {
        panel.style.display = 'block';
        text.textContent = JSON.stringify(data.archive, null, 2);
      }
      setStatusMessage(`计分规则已归档：${data.archive.archive_id}`);
    }

    async function loadLineage(issueId, feedback = '') {
      if (!(await ensureImportedPage())) return;
      const path = '/api/workflow/lineage' + (issueId ? `?issue_id=${encodeURIComponent(issueId)}` : '');
      const data = await loadJson(path);
      const issuesPage = pagedData('lineageIssues', data.issues || []);
      const lineage = data.lineage || {};
      setActions([
        { text: '加载问题溯源', fn: 'refreshLineage()' },
        { text: '导入真实血缘', fn: 'importLineageData()', secondary: true },
        { text: '进入问题分析', fn: "location.href='/issues'", secondary: true }
      ]);
      setContent(`
        <section>
          <h2>真实血缘接入状态</h2>
          <div class="stats">
            <div class="metric"><div class="metric-label">血缘数据</div><div class="metric-value" style="font-size:18px">${data.lineage_imported ? '已接入' : '未接入'}</div><div class="metric-foot">${data.lineage_record_count || 0} 条真实记录</div></div>
            <div class="metric"><div class="metric-label">当前问题匹配</div><div class="metric-value">${lineage.matched_count || 0}</div><div class="metric-foot">${lineage.available ? '已匹配真实链路' : '未匹配真实链路'}</div></div>
            <div class="metric"><div class="metric-label">溯源来源</div><div class="metric-value" style="font-size:18px">${lineage.available ? '真实血缘' : '待导入'}</div><div class="metric-foot">不展示模拟链路</div></div>
            <div class="metric"><div class="metric-label">接口</div><div class="metric-value" style="font-size:18px">POST</div><div class="metric-foot">/api/lineage/import</div></div>
          </div>
          ${lineage.available ? '' : `<div class="empty" style="margin-top:12px">${escapeHtml(lineage.message || '请先导入真实字段级血缘数据，系统不会用模拟链路代替真实溯源。')}</div>`}
        </section>
        <section>
          <h2>六维问题分布</h2>
          ${dimensionSummaryHtml(data.issues || [], '个问题')}
        </section>
        <section class="two-col">
          <div>
            <h2>问题选择（${data.total || 0}）</h2>
            ${(data.issues || []).length ? `<table>
              <thead><tr><th>问题ID</th><th>规则</th><th>维度</th><th>资源</th><th>操作</th></tr></thead>
              <tbody>${issuesPage.items.map(issue => `
                <tr>
                  <td class="mono">${escapeHtml(issue.issue_id)}</td>
                  <td class="mono">${escapeHtml(issue.rule_id)}</td>
                  <td>${escapeHtml(dimensionLabel(issue))}</td>
                  <td>${escapeHtml(issue.resource)}</td>
                  <td><button class="tiny secondary" onclick="viewIssueLineage('${escapeJs(issue.issue_id)}')">查看溯源</button></td>
                </tr>`).join('')}</tbody>
            </table>
            ${paginationHtml('lineageIssues', issuesPage, 'loadLineage')}` : `<div class="empty">${escapeHtml(data.message || '当前没有质量问题')}</div>`}
          </div>
          <div>
            <h2>溯源结果</h2>
            ${lineage.available ? `<pre>${escapeHtml(JSON.stringify(lineage, null, 2))}</pre>` : `<div class="empty">当前没有可展示的真实溯源结果。请导入与问题表/字段匹配的真实血缘记录。</div>`}
          </div>
        </section>
        <section>
          <h2>链路摘要</h2>
          <div class="stats">
            <div class="metric"><div class="metric-label">当前问题</div><div class="metric-value" style="font-size:18px">${escapeHtml(data.selected_issue_id || '-')}</div><div class="metric-foot">${escapeHtml(lineage.resource || '-')}</div></div>
            <div class="metric"><div class="metric-label">上游对象</div><div class="metric-value">${(lineage.upstream_trace || []).length}</div><div class="metric-foot">源系统/源表</div></div>
            <div class="metric"><div class="metric-label">下游影响</div><div class="metric-value">${(lineage.downstream_impacts || []).length}</div><div class="metric-foot">报表/API/同步链路</div></div>
            <div class="metric"><div class="metric-label">整改建议</div><div class="metric-value">${(lineage.recommendations || []).length}</div><div class="metric-foot">闭环动作</div></div>
          </div>
        </section>`);
      if (feedback) {
        setStatusMessage(`${feedback}：当前问题 ${data.selected_issue_id || '-'}，真实血缘匹配 ${lineage.matched_count || 0} 条`);
      }
    }

    async function refreshLineage() {
      await loadLineage('', '问题溯源已加载');
    }

    async function loadLineageLanding() {
      if (!(await ensureImportedPage())) return;
      setActions([
        { text: '加载问题溯源', fn: 'refreshLineage()' },
        { text: '导入真实血缘', fn: 'importLineageData()', secondary: true },
        { text: '进入问题分析', fn: "location.href='/issues'", secondary: true }
      ]);
      setContent(`<section><h2>质量问题溯源</h2><div class="empty">溯源模块仅展示真实导入的字段级血缘数据。请先点击“导入真实血缘”，或在完成评价后点击“加载问题溯源”查看是否已匹配真实链路。</div></section>`);
    }

    async function viewIssueLineage(issueId) {
      await loadLineage(issueId, '问题溯源已切换');
    }

    async function loadWorkflowReport(feedback = '流程报告已生成') {
      const data = await loadJson('/api/workflow/report');
      setContent(`<section><h2>流程报告</h2><pre>${escapeHtml(data.markdown)}</pre></section>`);
      setStatusMessage(`${feedback}：报告长度 ${data.markdown.length} 字符`);
    }

    async function downloadWorkflowReport() {
      const data = await loadJson('/api/workflow/report');
      const blob = new Blob([data.markdown], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `质量评价报告_${new Date().toISOString().slice(0, 10)}.md`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setStatusMessage('质量评价报告已生成并下载');
    }

    async function mockPushWorkflowReport() {
      const data = await loadJson('/api/workflow/report');
      setStatusMessage(`质量报告已模拟推送给数据责任人：报告长度 ${data.markdown.length} 字符`);
    }

    async function refreshPage() {
      await renderCurrentPage();
    }

    async function renderCurrentPage() {
      if (currentPage === 'import') return loadImportPage();
      if (currentPage === 'rules') return loadRules();
      if (currentPage === 'recommend') return loadRecommendations();
      if (currentPage === 'parameters') return loadParameterLanding();
      if (currentPage === 'execution') return loadExecutionLanding();
      if (currentPage === 'dashboard') return loadDashboardLanding();
      if (currentPage === 'issues') return loadIssuesLanding();
      if (currentPage === 'scoring') return loadScoringLanding();
      if (currentPage === 'lineage') return loadLineageLanding();
      setContent('<section><div class="empty">未找到页面</div></section>');
    }

    async function init() {
      activateNav();
      await renderCurrentPage();
    }
    init();
  </script>
</body>
</html>"""
    return template.replace("__PAGE__", page)


class DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            static_path = self.resolve_vue_static(parsed.path)
            if static_path:
                self.send_file(static_path)
                return
            if parsed.path in {"/", "/index.html"}:
                if VUE_DIST.exists():
                    self.send_file(VUE_DIST / "index.html")
                else:
                    self.send_html(page_html("rules"))
            elif parsed.path == "/import":
                self.send_file(VUE_DIST / "index.html") if VUE_DIST.exists() else self.send_html(page_html("import"))
            elif parsed.path == "/rules":
                self.send_file(VUE_DIST / "index.html") if VUE_DIST.exists() else self.send_html(page_html("rules"))
            elif parsed.path == "/recommend":
                self.send_file(VUE_DIST / "index.html") if VUE_DIST.exists() else self.send_html(page_html("recommend"))
            elif parsed.path == "/parameters":
                self.send_file(VUE_DIST / "index.html") if VUE_DIST.exists() else self.send_html(page_html("parameters"))
            elif parsed.path == "/execution":
                self.send_file(VUE_DIST / "index.html") if VUE_DIST.exists() else self.send_html(page_html("execution"))
            elif parsed.path == "/dashboard":
                self.send_file(VUE_DIST / "index.html") if VUE_DIST.exists() else self.send_html(page_html("dashboard"))
            elif parsed.path == "/issues":
                self.send_file(VUE_DIST / "index.html") if VUE_DIST.exists() else self.send_html(page_html("issues"))
            elif parsed.path == "/scoring":
                self.send_file(VUE_DIST / "index.html") if VUE_DIST.exists() else self.send_html(page_html("scoring"))
            elif parsed.path == "/lineage":
                self.send_file(VUE_DIST / "index.html") if VUE_DIST.exists() else self.send_html(page_html("lineage"))
            elif parsed.path == "/api/summary":
                self.send_json(api_summary())
            elif parsed.path == "/api/rules":
                self.send_json(api_rules(parse_qs(parsed.query)))
            elif parsed.path == "/api/rules/spec":
                self.send_json(api_rules_spec())
            elif parsed.path == "/api/rules/metadata":
                self.send_json(api_rules_metadata())
            elif parsed.path == "/api/recommendations":
                self.send_json(api_recommendations(parse_qs(parsed.query)))
            elif parsed.path == "/api/preview":
                self.send_json(api_preview(parse_qs(parsed.query)))
            elif parsed.path == "/api/report":
                self.send_json(api_report())
            elif parsed.path == "/api/run-test":
                self.send_json(api_run_test())
            elif parsed.path == "/api/data/current":
                self.send_json(api_data_current())
            elif parsed.path == "/api/lineage/current":
                self.send_json(api_lineage_current())
            elif parsed.path == "/api/workflow/overview":
                self.send_json(api_workflow_overview())
            elif parsed.path == "/api/workflow/configure":
                self.send_json(api_workflow_configure())
            elif parsed.path == "/api/workflow/trial":
                self.send_json(api_workflow_trial())
            elif parsed.path == "/api/workflow/execute":
                self.send_json(api_workflow_execute())
            elif parsed.path == "/api/workflow/dashboard":
                self.send_json(api_workflow_dashboard())
            elif parsed.path == "/api/workflow/issues":
                self.send_json(api_workflow_issues(parse_qs(parsed.query)))
            elif parsed.path == "/api/workflow/archive":
                self.send_json(api_workflow_archive())
            elif parsed.path == "/api/workflow/lineage":
                self.send_json(api_workflow_lineage(parse_qs(parsed.query)))
            elif parsed.path == "/api/workflow/report":
                self.send_json(api_workflow_report())
            elif parsed.path == "/api/workflow/reset":
                reset_workflow_state()
                self.send_json({"status": "reset", "message": "运行数据已重置"})
            elif VUE_DIST.exists() and not parsed.path.startswith("/api/"):
                self.send_file(VUE_DIST / "index.html")
            else:
                self.send_error(404, "Not found")
        except Exception as exc:
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = self.read_json_body()
            if parsed.path == "/api/data/import":
                self.send_json(api_data_import(payload))
            elif parsed.path == "/api/lineage/import":
                self.send_json(api_lineage_import(payload))
            elif parsed.path == "/api/recommendations/confirm":
                self.send_json(api_recommendations_confirm(payload))
            elif parsed.path == "/api/rules/create":
                self.send_json(api_rule_create(payload))
            elif parsed.path == "/api/rules/import":
                self.send_json(api_rule_import(payload))
            elif parsed.path == "/api/rules/update":
                self.send_json(api_rule_update(payload))
            elif parsed.path == "/api/rules/reuse":
                self.send_json(api_rule_reuse(payload))
            elif parsed.path == "/api/rules/delete":
                self.send_json(api_rule_delete(payload))
            elif parsed.path == "/api/workflow/execute":
                self.send_json(api_workflow_execute(payload))
            elif parsed.path == "/api/workflow/settings/update":
                self.send_json(api_workflow_settings_update(payload))
            elif parsed.path == "/api/workflow/issues/update":
                self.send_json(api_workflow_issue_update(payload))
            elif parsed.path == "/api/workflow/archive":
                self.send_json(api_workflow_archive(payload))
            else:
                self.send_error(404, "Not found")
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=400)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)

    def log_message(self, format: str, *args: Any) -> None:
        print("[%s] %s" % (self.log_date_time_string(), format % args))

    def send_html(self, html: str) -> None:
        payload = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def resolve_vue_static(self, request_path: str) -> Optional[Path]:
        if not VUE_DIST.exists() or request_path.startswith("/api/"):
            return None
        clean_path = request_path.lstrip("/")
        if not clean_path:
            return None
        candidate = (VUE_DIST / clean_path).resolve()
        try:
            candidate.relative_to(VUE_DIST.resolve())
        except ValueError:
            return None
        return candidate if candidate.is_file() else None

    def send_file(self, path: Path) -> None:
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".ico": "image/x-icon",
        }
        payload = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_types.get(path.suffix.lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON解析失败: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("请求体必须是JSON对象")
        return payload

    def send_json(self, data: Dict[str, Any], status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="质量评价规则库与智能推荐项目运行接口")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), DemoHandler)
    print(f"Quality data service running at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
