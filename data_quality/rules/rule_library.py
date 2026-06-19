#  Copyright 2025 Collate
#  Licensed under the Collate Community License, Version 1.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#  https://github.com/open-metadata/OpenMetadata/blob/main/ingestion/LICENSE
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""
数据质量评价规则库。

规则库面向白皮书中的“规则模板、规则查询与统计、检核任务、问题管理”
能力，统一维护标准规则、业务规则、技术规则和自定义规则，并提供：

1. 内置六维评价规则模板
2. 规则导入、新增、修改、删除、复用
3. GE / SQL / ETL 脚本预览
4. 按维度、问题归类、执行引擎等口径统计
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

from metadata.data_quality.dimension.evaluator import RuleSeverity
from metadata.data_quality.dimension.models import QualityDimension


RULE_SPEC_SCHEMA = "https://om.local/specs/data-quality-rule-library.schema.json"
RULE_SPEC_VERSION = "1.0.0"
DEFAULT_RULE_SPEC_PATH = Path(__file__).resolve().parents[1] / "specs" / "quality_rule_library.spec.json"


DIMENSION_ZH_NAMES: Dict[QualityDimension, str] = {
    QualityDimension.NORMATIVITY: "规范性",
    QualityDimension.COMPLETENESS: "完整性",
    QualityDimension.ACCURACY: "准确性",
    QualityDimension.CONSISTENCY: "一致性",
    QualityDimension.TIMELINESS: "时效性",
    QualityDimension.ACCESSIBILITY: "可访问性",
}

DIMENSION_ALIASES: Dict[str, QualityDimension] = {
    "normativity": QualityDimension.NORMATIVITY,
    "规范性": QualityDimension.NORMATIVITY,
    "standardization": QualityDimension.NORMATIVITY,
    "completeness": QualityDimension.COMPLETENESS,
    "完整性": QualityDimension.COMPLETENESS,
    "accuracy": QualityDimension.ACCURACY,
    "准确性": QualityDimension.ACCURACY,
    "consistency": QualityDimension.CONSISTENCY,
    "一致性": QualityDimension.CONSISTENCY,
    "timeliness": QualityDimension.TIMELINESS,
    "时效性": QualityDimension.TIMELINESS,
    "accessibility": QualityDimension.ACCESSIBILITY,
    "可访问性": QualityDimension.ACCESSIBILITY,
    "availability": QualityDimension.ACCESSIBILITY,
    "可用性": QualityDimension.ACCESSIBILITY,
}


class RuleExecutionEngine(str, Enum):
    """规则落地方式。"""

    GE = "GE"
    SQL = "SQL"
    ETL = "ETL"


class RuleSourceType(str, Enum):
    """规则来源类型。"""

    STANDARD = "STANDARD"  # 标准规则
    BUSINESS = "BUSINESS"  # 业务规则
    TECHNICAL = "TECHNICAL"  # 技术规则
    CUSTOM = "CUSTOM"  # 自定义规则


class RuleEntityType(str, Enum):
    """规则适用对象。"""

    COLUMN = "COLUMN"
    TABLE = "TABLE"
    FIELD_GROUP = "FIELD_GROUP"
    DATASET = "DATASET"
    SERVICE = "SERVICE"
    API = "API"


class RuleStatus(str, Enum):
    """规则生命周期状态。"""

    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    DEPRECATED = "DEPRECATED"


class RuleValidationLevel(str, Enum):
    """强弱校验级别。"""

    P0_BLOCKING = "P0_BLOCKING"  # 强校验，失败阻断入库/同步
    P1_WARNING = "P1_WARNING"  # 告警校验，失败触发核查
    P2_MONITORING = "P2_MONITORING"  # 弱校验，失败进入监控分析


@dataclass
class RuleThreshold:
    """规则阈值配置。"""

    operator: str = "=="
    expected_value: Any = 0
    pass_rate: float = 1.0
    unit: str = "rows"
    description: str = "失败记录数应为0"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Union["RuleThreshold", Dict[str, Any]]]) -> "RuleThreshold":
        if isinstance(data, RuleThreshold):
            return data
        if not data:
            return cls()
        values = dict(data)
        if "expected" in values and "expected_value" not in values:
            values["expected_value"] = values.pop("expected")
        return cls(**{k: v for k, v in values.items() if k in cls.__dataclass_fields__})


@dataclass
class RuleApplicability:
    """规则适用范围。"""

    entity_type: RuleEntityType = RuleEntityType.COLUMN
    data_types: List[str] = field(default_factory=list)
    column_name_patterns: List[str] = field(default_factory=list)
    table_types: List[str] = field(default_factory=list)
    business_tags: List[str] = field(default_factory=list)
    required_context: List[str] = field(default_factory=list)
    related_objects: Dict[str, str] = field(default_factory=dict)
    condition: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["entity_type"] = self.entity_type.value
        return result

    @classmethod
    def from_dict(
        cls,
        data: Optional[Union["RuleApplicability", Dict[str, Any]]],
        default_entity_type: RuleEntityType = RuleEntityType.COLUMN,
    ) -> "RuleApplicability":
        if isinstance(data, RuleApplicability):
            return data
        if not data:
            return cls(entity_type=default_entity_type)

        values = dict(data)

        # 兼容 specs/data_quality_rules.yml 中的 applicability.appliesTo 写法。
        applies_to = values.pop("appliesTo", None) or values.pop("applies_to", None)
        if applies_to and isinstance(applies_to, list):
            data_types: List[str] = []
            column_patterns: List[str] = []
            table_types: List[str] = []
            required_context: List[str] = []
            for item in applies_to:
                if not isinstance(item, dict):
                    continue
                if item.get("dataType") and item["dataType"] not in data_types:
                    data_types.append(str(item["dataType"]))
                if item.get("columnNamePatterns"):
                    column_patterns.extend(str(p) for p in item["columnNamePatterns"])
                if item.get("tableType") and item["tableType"] not in table_types:
                    table_types.append(str(item["tableType"]))
                for key in ("columnType", "hasUniqueKey", "hasUpdateTime", "isBusinessKey"):
                    if key in item:
                        required_context.append(f"{key}={item[key]}")
            values.setdefault("data_types", data_types)
            values.setdefault("column_name_patterns", column_patterns)
            values.setdefault("table_types", table_types)
            values.setdefault("required_context", required_context)

        entity_type = values.pop("entity_type", values.pop("entityType", default_entity_type))
        values["entity_type"] = _coerce_enum(entity_type, RuleEntityType, RuleEntityType.COLUMN)
        return cls(**{k: v for k, v in values.items() if k in cls.__dataclass_fields__})


@dataclass
class RuleScript:
    """规则执行脚本模板。"""

    engine: RuleExecutionEngine
    expression: str
    language: str = ""
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine": self.engine.value,
            "expression": self.expression,
            "language": self.language,
            "description": self.description,
        }

    @classmethod
    def from_dict(
        cls,
        engine: Union[str, RuleExecutionEngine],
        data: Union[str, Dict[str, Any], "RuleScript"],
    ) -> "RuleScript":
        if isinstance(data, RuleScript):
            return data
        eng = _coerce_enum(engine, RuleExecutionEngine, RuleExecutionEngine.SQL)
        if isinstance(data, str):
            return cls(engine=eng, expression=data)
        values = dict(data)
        values["engine"] = _coerce_enum(values.get("engine", eng), RuleExecutionEngine, eng)
        return cls(**{k: v for k, v in values.items() if k in cls.__dataclass_fields__})


@dataclass
class RuleTemplate:
    """规则模板。"""

    rule_id: str
    name: str
    display_name: str
    dimension: QualityDimension
    source_type: RuleSourceType
    problem_category: str
    core_definition: str
    applicability: RuleApplicability
    scripts: Dict[RuleExecutionEngine, RuleScript]

    test_definition_name: str = "tableCustomSQLQuery"
    parameters: Dict[str, Any] = field(default_factory=dict)
    threshold: RuleThreshold = field(default_factory=RuleThreshold)
    validation_level: RuleValidationLevel = RuleValidationLevel.P1_WARNING
    severity: RuleSeverity = RuleSeverity.MEDIUM
    responsible_role: str = "数据责任人"
    remediation_suggestion: str = "核查源数据、修正规则参数并重新执行检核。"
    issue_strategy: str = "不符合规则的数据进入问题库，并生成整改工单。"
    tags: List[str] = field(default_factory=list)
    status: RuleStatus = RuleStatus.ACTIVE
    version: int = 1
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def dimension_zh(self) -> str:
        return DIMENSION_ZH_NAMES.get(self.dimension, self.dimension.value)

    @property
    def enabled(self) -> bool:
        return self.status == RuleStatus.ACTIVE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "display_name": self.display_name,
            "dimension": self.dimension.value,
            "dimension_zh": self.dimension_zh,
            "source_type": self.source_type.value,
            "problem_category": self.problem_category,
            "core_definition": self.core_definition,
            "applicability": self.applicability.to_dict(),
            "scripts": {
                engine.value: script.to_dict() for engine, script in self.scripts.items()
            },
            "test_definition_name": self.test_definition_name,
            "parameters": copy.deepcopy(self.parameters),
            "threshold": self.threshold.to_dict(),
            "validation_level": self.validation_level.value,
            "severity": self.severity.value,
            "responsible_role": self.responsible_role,
            "remediation_suggestion": self.remediation_suggestion,
            "issue_strategy": self.issue_strategy,
            "tags": list(self.tags),
            "status": self.status.value,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Union["RuleTemplate", Dict[str, Any]]) -> "RuleTemplate":
        if isinstance(data, RuleTemplate):
            return data

        values = dict(data)
        rule_id = str(values.pop("rule_id", values.pop("id", ""))).strip()
        if not rule_id:
            raise ValueError("规则编号(rule_id/id)不能为空")

        name = str(values.pop("name", rule_id))
        display_name = str(values.pop("display_name", values.pop("displayName", name)))
        dimension = _coerce_dimension(
            values.pop("dimension", values.pop("qualityDimension", values.pop("category", "")))
        )
        source_type = _coerce_enum(
            values.pop("source_type", values.pop("sourceType", RuleSourceType.CUSTOM)),
            RuleSourceType,
            RuleSourceType.CUSTOM,
        )
        entity_type = _coerce_enum(
            values.get("entity_type", values.get("entityType", RuleEntityType.COLUMN)),
            RuleEntityType,
            RuleEntityType.COLUMN,
        )
        applicability = RuleApplicability.from_dict(
            values.pop("applicability", None),
            default_entity_type=entity_type,
        )
        scripts = _coerce_scripts(values.pop("scripts", None), values)
        parameters = _coerce_parameters(values.pop("parameters", {}))

        created_at = _coerce_datetime(values.pop("created_at", values.pop("createdAt", None)))
        updated_at = _coerce_datetime(values.pop("updated_at", values.pop("updatedAt", None)))

        return cls(
            rule_id=rule_id,
            name=name,
            display_name=display_name,
            dimension=dimension,
            source_type=source_type,
            problem_category=str(
                values.pop("problem_category", values.pop("problemCategory", "自定义问题"))
            ),
            core_definition=str(
                values.pop("core_definition", values.pop("coreDefinition", values.pop("description", "")))
            ),
            applicability=applicability,
            scripts=scripts,
            test_definition_name=str(
                values.pop(
                    "test_definition_name",
                    values.pop("testDefinitionName", "tableCustomSQLQuery"),
                )
            ),
            parameters=parameters,
            threshold=RuleThreshold.from_dict(values.pop("threshold", None)),
            validation_level=_coerce_enum(
                values.pop("validation_level", values.pop("validationLevel", RuleValidationLevel.P1_WARNING)),
                RuleValidationLevel,
                RuleValidationLevel.P1_WARNING,
            ),
            severity=_coerce_enum(
                str(values.pop("severity", RuleSeverity.MEDIUM)).upper(),
                RuleSeverity,
                RuleSeverity.MEDIUM,
            ),
            responsible_role=str(
                values.pop("responsible_role", values.pop("responsibleRole", "数据责任人"))
            ),
            remediation_suggestion=str(
                values.pop(
                    "remediation_suggestion",
                    values.pop("remediationSuggestion", "核查源数据、修正规则参数并重新执行检核。"),
                )
            ),
            issue_strategy=str(
                values.pop(
                    "issue_strategy",
                    values.pop("issueStrategy", "不符合规则的数据进入问题库，并生成整改工单。"),
                )
            ),
            tags=list(values.pop("tags", [])),
            status=_coerce_enum(values.pop("status", RuleStatus.ACTIVE), RuleStatus, RuleStatus.ACTIVE),
            version=int(values.pop("version", 1)),
            created_at=created_at or datetime.now(),
            updated_at=updated_at or datetime.now(),
        )


@dataclass
class ScriptPreview:
    """脚本预览结果。"""

    rule_id: str
    engine: RuleExecutionEngine
    expression: str
    rendered_expression: str
    parameters: Dict[str, Any]
    unresolved_placeholders: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["engine"] = self.engine.value
        return result


@dataclass
class RuleReusePlan:
    """规则复用计划。"""

    rule_id: str
    rule_name: str
    target_object: Dict[str, Any]
    engine: RuleExecutionEngine
    test_case_config: Dict[str, Any]
    script_preview: ScriptPreview
    threshold: RuleThreshold
    responsible_role: str
    remediation_suggestion: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "target_object": self.target_object,
            "engine": self.engine.value,
            "test_case_config": self.test_case_config,
            "script_preview": self.script_preview.to_dict(),
            "threshold": self.threshold.to_dict(),
            "responsible_role": self.responsible_role,
            "remediation_suggestion": self.remediation_suggestion,
        }


@dataclass
class RuleImportResult:
    """规则导入结果。"""

    imported_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RuleLibrarySummary:
    """规则库统计汇总。"""

    total_rules: int
    active_rules: int
    disabled_rules: int
    deprecated_rules: int
    builtin_rules: int
    custom_rules: int
    by_dimension: Dict[str, int]
    by_problem_category: Dict[str, int]
    by_validation_level: Dict[str, int]
    by_engine: Dict[str, int]
    by_source_type: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RuleLibrary:
    """数据质量评价规则库服务。"""

    def __init__(
        self,
        storage_path: Optional[Union[str, Path]] = None,
        load_builtin: bool = True,
    ):
        self.storage_path = Path(storage_path) if storage_path else DEFAULT_RULE_SPEC_PATH
        self._rules: Dict[str, RuleTemplate] = {}
        self._reuse_counts: Dict[str, int] = {}
        self.metadata: Dict[str, Any] = build_default_rule_spec_metadata()

        loaded_from_spec = False
        if load_builtin and self.storage_path and self.storage_path.exists():
            self.import_rules_from_file(self.storage_path, overwrite=True, persist=False)
            loaded_from_spec = True

        if load_builtin and not loaded_from_spec:
            for rule in build_default_rule_templates():
                self._rules[rule.rule_id] = rule

        if not load_builtin and self.storage_path and self.storage_path.exists():
            self.import_rules_from_file(self.storage_path, overwrite=True, persist=False)

    def import_rules_from_file(
        self,
        path: Union[str, Path],
        overwrite: bool = False,
        persist: bool = True,
    ) -> RuleImportResult:
        """从 JSON/YAML 文件导入规则。"""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"规则文件不存在: {file_path}")

        with open(file_path, "r", encoding="utf-8") as file:
            if file_path.suffix.lower() in {".yaml", ".yml"}:
                try:
                    import yaml
                except ImportError as exc:
                    raise RuntimeError("导入 YAML 规则文件需要安装 PyYAML") from exc
                payload = yaml.safe_load(file) or {}
            else:
                payload = json.load(file)

        return self.import_rules(payload, overwrite=overwrite, persist=persist)

    def import_rules(
        self,
        payload: Union[Dict[str, Any], Sequence[Dict[str, Any]], Sequence[RuleTemplate]],
        overwrite: bool = False,
        persist: bool = True,
    ) -> RuleImportResult:
        """导入规则列表，兼容白皮书模板结构和 specs 中的维度分组结构。"""
        result = RuleImportResult()

        if isinstance(payload, dict) and isinstance(payload.get("reuse_counts"), dict):
            for rule_id, count in payload["reuse_counts"].items():
                try:
                    self._reuse_counts[str(rule_id)] = int(count)
                except (TypeError, ValueError):
                    result.errors.append(f"规则复用次数导入失败: {rule_id}={count}")

        if isinstance(payload, dict) and isinstance(payload.get("metadata"), dict):
            self.metadata = _merge_metadata(
                build_default_rule_spec_metadata(),
                payload.get("metadata") or {},
            )

        for item in _flatten_rule_payload(payload):
            try:
                rule = RuleTemplate.from_dict(item)
            except Exception as exc:  # noqa: BLE001 - 导入需要逐条容错
                result.errors.append(f"规则导入失败: {exc}")
                continue

            if rule.rule_id in self._rules:
                if not overwrite:
                    result.skipped_count += 1
                    continue
                existing = self._rules[rule.rule_id]
                rule.version = max(existing.version + 1, rule.version)
                rule.created_at = existing.created_at
                rule.updated_at = datetime.now()
                result.updated_count += 1
            else:
                result.imported_count += 1

            self._rules[rule.rule_id] = rule

        if persist:
            self._save_rules()
        return result

    def create_rule(
        self,
        rule: Union[RuleTemplate, Dict[str, Any]],
        overwrite: bool = False,
    ) -> RuleTemplate:
        """新增规则。"""
        template = RuleTemplate.from_dict(rule)
        if template.rule_id in self._rules and not overwrite:
            raise ValueError(f"规则已存在: {template.rule_id}")
        if template.rule_id in self._rules:
            template.version = self._rules[template.rule_id].version + 1
            template.created_at = self._rules[template.rule_id].created_at
        template.updated_at = datetime.now()
        self._rules[template.rule_id] = template
        self._save_rules()
        return template

    def update_rule(self, rule_id: str, updates: Dict[str, Any]) -> RuleTemplate:
        """修改规则。"""
        current = self.get_rule(rule_id)
        if not current:
            raise ValueError(f"规则不存在: {rule_id}")

        data = current.to_dict()
        _deep_update(data, updates)
        data["rule_id"] = rule_id
        data["version"] = current.version + 1
        data["created_at"] = current.created_at.isoformat()
        data["updated_at"] = datetime.now().isoformat()

        updated = RuleTemplate.from_dict(data)
        self._rules[rule_id] = updated
        self._save_rules()
        return updated

    def delete_rule(self, rule_id: str, soft_delete: bool = False) -> bool:
        """删除规则。soft_delete=True 时仅将规则置为废弃。"""
        if rule_id not in self._rules:
            return False
        if soft_delete:
            self.update_rule(rule_id, {"status": RuleStatus.DEPRECATED.value})
        else:
            del self._rules[rule_id]
            self._reuse_counts.pop(rule_id, None)
            self._save_rules()
        return True

    def get_rule(self, rule_id: str) -> Optional[RuleTemplate]:
        """按编号获取规则。"""
        return self._rules.get(rule_id)

    def list_rules(
        self,
        dimension: Optional[Union[str, QualityDimension]] = None,
        entity_type: Optional[Union[str, RuleEntityType]] = None,
        engine: Optional[Union[str, RuleExecutionEngine]] = None,
        problem_category: Optional[str] = None,
        source_type: Optional[Union[str, RuleSourceType]] = None,
        status: Optional[Union[str, RuleStatus]] = None,
        keyword: Optional[str] = None,
        include_disabled: bool = True,
    ) -> List[RuleTemplate]:
        """查询规则列表。"""
        rules = list(self._rules.values())

        if dimension:
            dim = _coerce_dimension(dimension)
            rules = [rule for rule in rules if rule.dimension == dim]
        if entity_type:
            ent = _coerce_enum(entity_type, RuleEntityType, RuleEntityType.COLUMN)
            rules = [rule for rule in rules if rule.applicability.entity_type == ent]
        if engine:
            eng = _coerce_enum(engine, RuleExecutionEngine, RuleExecutionEngine.SQL)
            rules = [rule for rule in rules if eng in rule.scripts]
        if problem_category:
            rules = [
                rule
                for rule in rules
                if problem_category.lower() in rule.problem_category.lower()
            ]
        if source_type:
            src = _coerce_enum(source_type, RuleSourceType, RuleSourceType.CUSTOM)
            rules = [rule for rule in rules if rule.source_type == src]
        if status:
            st = _coerce_enum(status, RuleStatus, RuleStatus.ACTIVE)
            rules = [rule for rule in rules if rule.status == st]
        elif not include_disabled:
            rules = [rule for rule in rules if rule.enabled]
        if keyword:
            kw = keyword.lower()
            rules = [
                rule
                for rule in rules
                if kw in rule.rule_id.lower()
                or kw in rule.name.lower()
                or kw in rule.display_name.lower()
                or kw in rule.core_definition.lower()
                or any(kw in tag.lower() for tag in rule.tags)
            ]

        return sorted(rules, key=lambda r: (r.dimension.value, r.rule_id))

    def preview_script(
        self,
        rule_id: str,
        engine: Union[str, RuleExecutionEngine] = RuleExecutionEngine.SQL,
        target_object: Optional[Union[str, Dict[str, Any]]] = None,
        parameter_overrides: Optional[Dict[str, Any]] = None,
    ) -> ScriptPreview:
        """预览规则脚本。"""
        rule = self.get_rule(rule_id)
        if not rule:
            raise ValueError(f"规则不存在: {rule_id}")

        requested_engine = _coerce_enum(engine, RuleExecutionEngine, RuleExecutionEngine.SQL)
        script = rule.scripts.get(requested_engine)
        if script is None:
            if not rule.scripts:
                raise ValueError(f"规则没有可预览脚本: {rule_id}")
            requested_engine, script = next(iter(rule.scripts.items()))

        params = copy.deepcopy(rule.parameters)
        context = copy.deepcopy(params)
        context.update(_normalize_target_object(target_object))
        context.update(parameter_overrides or {})
        context.setdefault("pass_rate", rule.threshold.pass_rate)
        context.setdefault("expected_value", rule.threshold.expected_value)

        rendered = _render_template(script.expression, context)
        unresolved = _find_unresolved_placeholders(rendered)
        return ScriptPreview(
            rule_id=rule.rule_id,
            engine=requested_engine,
            expression=script.expression,
            rendered_expression=rendered,
            parameters=params,
            unresolved_placeholders=unresolved,
        )

    def reuse_rule(
        self,
        rule_id: str,
        target_object: Union[str, Dict[str, Any]],
        engine: Union[str, RuleExecutionEngine] = RuleExecutionEngine.SQL,
        parameter_overrides: Optional[Dict[str, Any]] = None,
        test_case_name: Optional[str] = None,
    ) -> RuleReusePlan:
        """复用规则到指定表/字段，生成可落地的测试用例配置。"""
        rule = self.get_rule(rule_id)
        if not rule:
            raise ValueError(f"规则不存在: {rule_id}")

        target = _normalize_target_object(target_object)
        preview = self.preview_script(rule_id, engine, target, parameter_overrides)
        params = copy.deepcopy(rule.parameters)
        params.update(parameter_overrides or {})

        name_suffix = target.get("column_name") or target.get("table_name") or "target"
        test_case_config: Dict[str, Any] = {
            "testDefinitionName": rule.test_definition_name,
            "name": test_case_name or f"{rule.name}_{_sanitize_name(str(name_suffix))}",
            "parameterValues": _to_parameter_values(params),
        }
        if target.get("column_name"):
            test_case_config["columnName"] = target["column_name"]

        if rule.test_definition_name in {"tableCustomSQLQuery", "columnRuleLibrarySqlExpressionValidator"}:
            test_case_config["parameterValues"].append(
                {"name": "sqlExpression", "value": preview.rendered_expression}
            )
            test_case_config["parameterValues"].append({"name": "strategy", "value": "COUNT"})

        self._reuse_counts[rule_id] = self._reuse_counts.get(rule_id, 0) + 1
        self._save_rules()

        return RuleReusePlan(
            rule_id=rule.rule_id,
            rule_name=rule.display_name,
            target_object=target,
            engine=preview.engine,
            test_case_config=test_case_config,
            script_preview=preview,
            threshold=rule.threshold,
            responsible_role=rule.responsible_role,
            remediation_suggestion=rule.remediation_suggestion,
        )

    def get_summary(self) -> RuleLibrarySummary:
        """获取规则库统计汇总。"""
        rules = list(self._rules.values())
        return RuleLibrarySummary(
            total_rules=len(rules),
            active_rules=sum(1 for rule in rules if rule.status == RuleStatus.ACTIVE),
            disabled_rules=sum(1 for rule in rules if rule.status == RuleStatus.DISABLED),
            deprecated_rules=sum(1 for rule in rules if rule.status == RuleStatus.DEPRECATED),
            builtin_rules=sum(1 for rule in rules if rule.source_type != RuleSourceType.CUSTOM),
            custom_rules=sum(1 for rule in rules if rule.source_type == RuleSourceType.CUSTOM),
            by_dimension=_count_by(rules, lambda rule: rule.dimension.value),
            by_problem_category=_count_by(rules, lambda rule: rule.problem_category),
            by_validation_level=_count_by(rules, lambda rule: rule.validation_level.value),
            by_engine=_count_by(
                [engine for rule in rules for engine in rule.scripts],
                lambda engine: engine.value,
            ),
            by_source_type=_count_by(rules, lambda rule: rule.source_type.value),
        )

    def get_reuse_count(self, rule_id: str) -> int:
        """获取规则复用次数。"""
        return self._reuse_counts.get(rule_id, 0)

    def export_rules(self, include_disabled: bool = True) -> Dict[str, Any]:
        """导出规则库。"""
        return {
            "$schema": RULE_SPEC_SCHEMA,
            "kind": "DataQualityRuleLibrarySpec",
            "apiVersion": f"om.dataQuality/v{RULE_SPEC_VERSION}",
            "version": RULE_SPEC_VERSION,
            "metadata": self.get_metadata(),
            "dimensions": build_dimension_metadata(),
            "exported_at": datetime.now().isoformat(),
            "rules": [
                rule.to_dict()
                for rule in self.list_rules(include_disabled=include_disabled)
            ],
            "reuse_counts": dict(self._reuse_counts),
        }

    def get_metadata(self) -> Dict[str, Any]:
        """Return JSON Spec metadata for platform and Java integration."""
        metadata = copy.deepcopy(self.metadata)
        metadata["rule_count"] = len(self._rules)
        metadata.setdefault("storage", {})
        metadata["storage"]["type"] = "JSON_SPEC"
        metadata["storage"]["default_path"] = str(DEFAULT_RULE_SPEC_PATH.as_posix())
        if self.storage_path:
            metadata["storage"]["active_path"] = str(self.storage_path.as_posix())
        return metadata

    def _save_rules(self) -> None:
        if not self.storage_path:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as file:
            json.dump(self.export_rules(), file, ensure_ascii=False, indent=2)


def build_default_rule_spec_metadata() -> Dict[str, Any]:
    """Build business metadata carried by the JSON Spec."""
    return {
        "name": "quality-evaluation-rule-library",
        "display_name": "Quality Evaluation Rule Library",
        "description": (
            "Rules are stored as JSON Spec so Python, Java and OM adapters can "
            "share the same rule source without depending on a database table."
        ),
        "business_goal": "Support six-dimension data quality evaluation, rule recommendation, parameter setting and task execution.",
        "owner": "data-quality-team",
        "maintainers": ["data-quality-team", "platform-team"],
        "source": "Data Asset Management Operation Platform Whitepaper",
        "compatible_backends": ["Python standalone service", "Java OM backend", "OpenMetadata style APIs"],
        "storage": {
            "type": "JSON_SPEC",
            "format": "application/json",
            "default_path": str(DEFAULT_RULE_SPEC_PATH.as_posix()),
        },
        "field_metadata": {
            "rule_id": "Stable rule identifier used by API, frontend and Java backend.",
            "display_name": "Business-facing rule name.",
            "dimension": "One of normativity, completeness, accuracy, consistency, timeliness, accessibility.",
            "applicability": "Target object, data type, column patterns and required context.",
            "parameters": "Business-adjustable parameters. Frontend should render these as friendly form fields.",
            "threshold": "Pass condition and allowed failure rate.",
            "scripts": "SQL, GE and ETL landing templates. Business users should not edit these directly.",
            "issue_strategy": "Issue routing and remediation strategy after rule failure.",
        },
        "om_alignment": {
            "test_definition_name": "Maps to OpenMetadata Test Definition.",
            "reuse_rule": "Can generate OpenMetadata-style TestCase configuration.",
            "rest_prefix": "/api",
            "java_prefix_recommendation": "/om/data-quality",
        },
    }


def build_dimension_metadata() -> Dict[str, Dict[str, Any]]:
    """Return six-dimension metadata for API and frontend rendering."""
    return {
        "normativity": {
            "display_name": "Normativity",
            "weight": 0.20,
            "description": "Whether data complies with standards, naming, encoding, format and value-domain rules.",
            "examples": ["format", "encoding", "naming", "value domain"],
        },
        "completeness": {
            "display_name": "Completeness",
            "weight": 0.20,
            "description": "Whether required fields, records and relationships are complete.",
            "examples": ["not null", "fill rate", "primary key", "reference integrity"],
        },
        "accuracy": {
            "display_name": "Accuracy",
            "weight": 0.15,
            "description": "Whether values, numeric precision, length and business logic are correct.",
            "examples": ["range", "precision", "length", "multi-field condition"],
        },
        "consistency": {
            "display_name": "Consistency",
            "weight": 0.15,
            "description": "Whether the same business object is consistent across fields, tables, systems and lineage.",
            "examples": ["cross-system", "dictionary", "master-detail", "lineage transform"],
        },
        "timeliness": {
            "display_name": "Timeliness",
            "weight": 0.15,
            "description": "Whether data freshness, update delay and publish timeliness meet expectations.",
            "examples": ["freshness", "ETL latency", "partition arrival", "watermark"],
        },
        "accessibility": {
            "display_name": "Accessibility",
            "weight": 0.15,
            "description": "Whether data can be accessed safely, reliably and within response-time requirements.",
            "examples": ["permission", "SLA", "masking", "audit", "response time"],
        },
    }


def _merge_metadata(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(base)
    _deep_update(merged, copy.deepcopy(updates))
    return merged


def build_default_rule_templates() -> List[RuleTemplate]:
    """构建白皮书六维评价内置规则模板。"""
    rules = [
        _column_regex_rule(
            rule_id="N-F01",
            name="china_id_card_format",
            display_name="公民身份证号码格式校验",
            regex=r"^[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[0-9Xx]$",
            patterns=["*id_card*", "*cert_no*", "*identity*", "*身份证*", "*证件号*"],
            definition="校验身份证号码符合6位行政区划码、8位出生日期码、3位顺序码和1位校验码结构。",
            problem_category="格式不规范",
            severity=RuleSeverity.HIGH,
            remediation="按GB 11643规则核验身份证号，无法修正的数据进入问题库并回溯采集源。",
            tags=["身份证", "格式校验", "标准规则"],
        ),
        _column_regex_rule(
            rule_id="N-F02",
            name="china_mobile_format",
            display_name="手机号格式校验",
            regex=r"^\d{17}$",
            patterns=["*phone*", "*mobile*", "*tel*", "*手机号*", "*联系电话*"],
            definition="校验手机号为17位数字。",
            problem_category="格式不规范",
            severity=RuleSeverity.HIGH,
            remediation="核对手机号来源，修正非数字或位数不正确的数据后重新入库。",
            tags=["手机号", "格式校验", "标准规则"],
        ),
        _column_regex_rule(
            rule_id="N-F03",
            name="vehicle_plate_format",
            display_name="车牌号格式校验",
            regex=r"^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领][A-Z][A-Z0-9挂学警港澳]{5,6}$",
            patterns=["*plate*", "*car_no*", "*vehicle_no*", "*车牌*"],
            definition="校验车牌号符合省份简称、发牌机关代码及序号的常见编码结构。",
            problem_category="格式不规范",
            severity=RuleSeverity.MEDIUM,
            remediation="按车牌登记信息修正格式，特殊号牌补充白名单或业务说明。",
            tags=["车牌号", "格式校验"],
        ),
        _column_regex_rule(
            rule_id="N-F04",
            name="imei_format",
            display_name="IMEI格式校验",
            regex=r"^\d{15}$",
            patterns=["*imei*", "*device_id*", "*设备号*"],
            definition="校验移动设备IMEI为15位数字。",
            problem_category="格式不规范",
            severity=RuleSeverity.MEDIUM,
            remediation="检查设备采集逻辑，修正非15位或含非数字字符的IMEI。",
            tags=["IMEI", "格式校验"],
        ),
        _column_regex_rule(
            rule_id="N-F05",
            name="mac_address_format",
            display_name="MAC地址格式校验",
            regex=r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$",
            patterns=["*mac*", "*mac_addr*", "*物理地址*"],
            definition="校验MAC地址符合6组十六进制字节，分隔符为冒号或短横线。",
            problem_category="格式不规范",
            severity=RuleSeverity.MEDIUM,
            remediation="统一MAC地址分隔符和大小写格式，异常值进入问题库。",
            tags=["MAC", "格式校验"],
        ),
        _column_regex_rule(
            rule_id="N-F06",
            name="ipv4_format",
            display_name="IP地址格式校验",
            regex=r"^((25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(25[0-5]|2[0-4]\d|[01]?\d\d?)$",
            patterns=["*ip*", "*ip_addr*", "*ipv4*", "*IP地址*"],
            definition="校验IPv4地址四段取值均在0到255之间。",
            problem_category="格式不规范",
            severity=RuleSeverity.MEDIUM,
            remediation="修正非法IP段或补充IPv6专项规则，非法访问来源进入安全核查。",
            tags=["IP", "格式校验"],
        ),
        _column_regex_rule(
            rule_id="N-F07",
            name="url_format",
            display_name="URL地址格式校验",
            regex=r"^https?://[A-Za-z0-9.-]+(:[0-9]+)?(/[A-Za-z0-9._~:/?#\[\]@!$&()*+,;=%-]*)?$",
            patterns=["*url*", "*link*", "*uri*", "*网址*", "*链接*"],
            definition="校验URL地址包含HTTP/HTTPS协议、合法域名或主机名以及可选路径参数。",
            problem_category="格式不规范",
            severity=RuleSeverity.MEDIUM,
            remediation="统一URL采集格式，缺少协议或非法路径的数据进入问题库。",
            tags=["URL", "格式校验"],
        ),
        _column_regex_rule(
            rule_id="N-F08",
            name="email_format",
            display_name="邮箱格式校验",
            regex=r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$",
            patterns=["*email*", "*mail*", "*邮箱*", "*电子邮件*"],
            definition="校验邮箱地址包含本地部分、@符号和合法域名后缀。",
            problem_category="格式不规范",
            severity=RuleSeverity.MEDIUM,
            remediation="修正邮箱地址格式；无法确认时标记待核实并进入问题库。",
            tags=["邮箱", "格式校验"],
        ),
        _column_regex_rule(
            rule_id="N-C01",
            name="business_code_format",
            display_name="编码规范性校验",
            regex=r"^[A-Z0-9_-]+$",
            patterns=["*code*", "*编码*", "*编号*", "*sku*"],
            definition="校验编码类字段使用统一的大写字母、数字、下划线或短横线。",
            problem_category="编码不规范",
            severity=RuleSeverity.MEDIUM,
            remediation="按企业编码规则统一转换，新增编码需同步维护编码字典。",
            tags=["编码", "规范性"],
        ),
        _column_regex_rule(
            rule_id="N-C02",
            name="administrative_region_code",
            display_name="行政区划编码校验",
            regex=r"^[1-9]\d{5}$",
            patterns=["*region_code*", "*area_code*", "*district_code*", "*行政区划*", "*地区编码*"],
            definition="校验行政区划编码为6位数字，首位不为0，可结合权威区划字典进一步核验。",
            problem_category="编码不规范",
            severity=RuleSeverity.MEDIUM,
            remediation="按最新行政区划字典修正编码，撤并地区需维护映射关系。",
            tags=["行政区划", "编码"],
        ),
        _column_regex_rule(
            rule_id="N-N01",
            name="text_naming_standard",
            display_name="命名规范性校验",
            regex=r"^[\u4e00-\u9fa5A-Za-z0-9_]+$",
            patterns=["*name*", "*名称*", "*title*", "*项目名*"],
            definition="校验名称类字段不含非法特殊字符、换行符和不可见字符。",
            problem_category="命名不规范",
            severity=RuleSeverity.LOW,
            remediation="清洗名称中的特殊字符并同步业务命名规范。",
            tags=["命名", "特殊字符"],
        ),
        _column_rule(
            rule_id="N-V01",
            name="enum_value_domain",
            display_name="值域枚举规范性校验",
            dimension=QualityDimension.NORMATIVITY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="值域不合理",
            definition="校验字段值仅允许出现在预设枚举集合内。",
            test_definition="columnValuesToBeInSet",
            parameters={"allowed_values": "'${ALLOWED_VALUES}'"},
            sql="SELECT * FROM {{ table_name }} WHERE {{ column_name }} IS NOT NULL AND {{ column_name }} NOT IN ({{ allowed_values }})",
            ge='ge_df.expect_column_values_to_be_in_set(column="{{ column_name }}", value_set=[{{ allowed_values }}], mostly={{ pass_rate }})',
            etl='{"action":"validate_in_set","column":"{{ column_name }}","allowed_values":[{{ allowed_values }}],"on_fail":"issue_table"}',
            patterns=["*status*", "*type*", "*flag*", "*状态*", "*类型*"],
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="核对枚举字典，补齐合法值或修正字段取值。",
            tags=["枚举", "值域"],
        ),
        _column_rule(
            rule_id="C-F01",
            name="required_field_not_null",
            display_name="必填字段空值校验",
            dimension=QualityDimension.COMPLETENESS,
            source_type=RuleSourceType.STANDARD,
            problem_category="字段不完整",
            definition="校验主键、关键标识、金额、时间、责任人等业务必填字段不为空。",
            test_definition="columnValuesToBeNotNull",
            parameters={},
            sql="SELECT * FROM {{ table_name }} WHERE {{ column_name }} IS NULL OR TRIM(CAST({{ column_name }} AS CHAR)) = ''",
            ge='ge_df.expect_column_values_to_not_be_null(column="{{ column_name }}", mostly={{ pass_rate }})',
            etl='{"action":"not_null","column":"{{ column_name }}","on_fail":"issue_table"}',
            patterns=["*id*", "*amount*", "*time*", "*owner*", "*主键*", "*责任人*"],
            severity=RuleSeverity.CRITICAL,
            validation_level=RuleValidationLevel.P0_BLOCKING,
            remediation="按业务来源补录必填字段；无法补录的数据阻断入库并生成整改工单。",
            tags=["空值", "完整性", "强校验"],
        ),
        _column_rule(
            rule_id="C-F02",
            name="field_fill_rate",
            display_name="字段填充率校验",
            dimension=QualityDimension.COMPLETENESS,
            source_type=RuleSourceType.BUSINESS,
            problem_category="字段不完整",
            definition="校验非核心字段覆盖率达到业务阈值，默认不低于95%。",
            test_definition="columnValuesToBeNotNull",
            parameters={"min_fill_rate": "0.95"},
            sql="SELECT COUNT(*) AS total_rows, SUM(CASE WHEN {{ column_name }} IS NULL OR TRIM(CAST({{ column_name }} AS CHAR)) = '' THEN 1 ELSE 0 END) AS empty_rows FROM {{ table_name }} HAVING (1 - empty_rows / NULLIF(total_rows, 0)) < {{ min_fill_rate }}",
            ge='ge_df.expect_column_values_to_not_be_null(column="{{ column_name }}", mostly={{ min_fill_rate }})',
            etl='{"action":"fill_rate","column":"{{ column_name }}","min_fill_rate":{{ min_fill_rate }},"on_fail":"issue_table"}',
            patterns=["*nickname*", "*remark*", "*描述*", "*备注*"],
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P2_MONITORING,
            remediation="分析字段缺失原因，优化采集表单或调低非核心字段阈值。",
            tags=["填充率", "完整性"],
        ),
        _column_rule(
            rule_id="C-F03",
            name="blank_string_check",
            display_name="空白字符串校验",
            dimension=QualityDimension.COMPLETENESS,
            source_type=RuleSourceType.STANDARD,
            problem_category="字段不完整",
            definition="校验文本字段不允许只包含空格、制表符或换行等空白字符。",
            test_definition="columnValuesToNotMatchRegex",
            parameters={"regex": r"^\s*$"},
            sql="SELECT * FROM {{ table_name }} WHERE {{ column_name }} IS NOT NULL AND TRIM(CAST({{ column_name }} AS CHAR)) = ''",
            ge='ge_df.expect_column_values_to_not_match_regex(column="{{ column_name }}", regex=r"{{ regex }}", mostly={{ pass_rate }})',
            etl='{"action":"blank_string","column":"{{ column_name }}","on_fail":"issue_table"}',
            patterns=["*name*", "*desc*", "*address*", "*名称*", "*地址*", "*描述*"],
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="清洗空白字符串并回填有效值，必要时调整采集端必填校验。",
            tags=["空白字符串", "完整性"],
        ),
        _column_rule(
            rule_id="C-F04",
            name="primary_key_uniqueness",
            display_name="主键唯一性校验",
            dimension=QualityDimension.COMPLETENESS,
            source_type=RuleSourceType.STANDARD,
            problem_category="记录不完整",
            definition="校验主键或业务唯一键在表内不存在重复值，避免重复记录进入下游。",
            test_definition="columnValuesToBeUnique",
            parameters={},
            sql="SELECT {{ column_name }}, COUNT(*) AS duplicate_count FROM {{ table_name }} WHERE {{ column_name }} IS NOT NULL GROUP BY {{ column_name }} HAVING COUNT(*) > 1",
            ge='ge_df.expect_column_values_to_be_unique(column="{{ column_name }}", mostly={{ pass_rate }})',
            etl='{"action":"unique_key","column":"{{ column_name }}","on_fail":"block_or_issue"}',
            patterns=["*id*", "*key*", "*主键*", "*唯一键*", "*编号*"],
            severity=RuleSeverity.CRITICAL,
            validation_level=RuleValidationLevel.P0_BLOCKING,
            remediation="定位重复主键来源，按业务规则合并、去重或回滚重复记录。",
            tags=["唯一性", "主键", "强校验"],
        ),
        _table_rule(
            rule_id="C-R01",
            name="business_record_complete",
            display_name="记录完整性校验",
            dimension=QualityDimension.COMPLETENESS,
            source_type=RuleSourceType.BUSINESS,
            problem_category="记录不完整",
            definition="校验核心业务流程记录无漏采、漏存，例如订单创建后应有支付或取消记录。",
            sql="SELECT * FROM {{ table_name }} WHERE {{ record_complete_condition }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ table_name }} WHERE {{ record_complete_condition }}")',
            etl='{"action":"record_completeness","invalid_condition":"{{ record_complete_condition }}","on_fail":"issue_table"}',
            parameters={"record_complete_condition": "${INVALID_RECORD_CONDITION}"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="补齐业务链路记录，检查采集、同步或ETL是否漏传。",
            tags=["记录完整性", "业务流程"],
        ),
        _table_rule(
            rule_id="C-L01",
            name="reference_integrity",
            display_name="关联完整性校验",
            dimension=QualityDimension.COMPLETENESS,
            source_type=RuleSourceType.BUSINESS,
            problem_category="关联不完整",
            definition="校验子表关联字段值必须在主表中存在。",
            sql="SELECT t.* FROM {{ table_name }} t LEFT JOIN {{ referenced_table }} r ON t.{{ foreign_key }} = r.{{ referenced_key }} WHERE t.{{ foreign_key }} IS NOT NULL AND r.{{ referenced_key }} IS NULL",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT t.* FROM {{ table_name }} t LEFT JOIN {{ referenced_table }} r ON t.{{ foreign_key }} = r.{{ referenced_key }} WHERE t.{{ foreign_key }} IS NOT NULL AND r.{{ referenced_key }} IS NULL")',
            etl='{"action":"reference_integrity","source_key":"{{ foreign_key }}","reference":"{{ referenced_table }}.{{ referenced_key }}","on_fail":"issue_table"}',
            parameters={
                "referenced_table": "${REFERENCED_TABLE}",
                "foreign_key": "${FOREIGN_KEY}",
                "referenced_key": "id",
            },
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P0_BLOCKING,
            remediation="补齐主数据或修正外键，必要时回滚孤儿记录。",
            tags=["关联完整性", "外键"],
        ),
        _column_rule(
            rule_id="A-N01",
            name="numeric_type_check",
            display_name="数值型格式校验",
            dimension=QualityDimension.ACCURACY,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="数值逻辑错误",
            definition="校验数值型字段可以被转换为数值，无法转换的数据进入问题库。",
            test_definition="tableCustomSQLQuery",
            parameters={},
            sql="SELECT * FROM {{ table_name }} WHERE {{ column_name }} IS NOT NULL AND TRY_CAST({{ column_name }} AS DECIMAL(38, 10)) IS NULL",
            ge='ge_df.expect_column_values_to_be_of_type(column="{{ column_name }}", type_="number", mostly={{ pass_rate }})',
            etl='{"action":"cast_numeric","column":"{{ column_name }}","on_cast_fail":"issue_table"}',
            patterns=["*amount*", "*price*", "*quantity*", "*score*", "*金额*", "*数量*"],
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="按数值转换规则清洗字段，无法转换的值进入问题库。",
            tags=["数值校验", "准确性"],
        ),
        _column_rule(
            rule_id="A-N02",
            name="numeric_range_check",
            display_name="取值范围校验",
            dimension=QualityDimension.ACCURACY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="值域不合理",
            definition="校验数值字段在业务合理区间内，例如年龄0-120、折扣0-1、工时0-24。",
            test_definition="columnValuesToBeBetween",
            parameters={"min_value": "0", "max_value": "120"},
            sql="SELECT * FROM {{ table_name }} WHERE {{ column_name }} < {{ min_value }} OR {{ column_name }} > {{ max_value }}",
            ge='ge_df.expect_column_values_to_be_between(column="{{ column_name }}", min_value={{ min_value }}, max_value={{ max_value }}, mostly={{ pass_rate }})',
            etl='{"action":"range_check","column":"{{ column_name }}","min":{{ min_value }},"max":{{ max_value }},"on_fail":"issue_table"}',
            patterns=["*age*", "*score*", "*discount*", "*work_hours*", "*年龄*", "*评分*"],
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="按业务阈值修正异常值；业务阈值变化时同步更新规则参数。",
            tags=["取值范围", "准确性"],
        ),
        _column_rule(
            rule_id="A-N03",
            name="amount_precision_check",
            display_name="金额精度校验",
            dimension=QualityDimension.ACCURACY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="数值逻辑错误",
            definition="校验金额、单价、费率等数值字段的小数精度不超过业务允许位数。",
            test_definition="tableCustomSQLQuery",
            parameters={"decimal_scale": "2"},
            sql="SELECT * FROM {{ table_name }} WHERE {{ column_name }} IS NOT NULL AND ABS({{ column_name }} - ROUND({{ column_name }}, {{ decimal_scale }})) > 0",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ table_name }} WHERE {{ column_name }} IS NOT NULL AND ABS({{ column_name }} - ROUND({{ column_name }}, {{ decimal_scale }})) > 0")',
            etl='{"action":"decimal_precision","column":"{{ column_name }}","scale":{{ decimal_scale }},"on_fail":"issue_table"}',
            patterns=["*amount*", "*price*", "*fee*", "*money*", "*金额*", "*价格*", "*费用*"],
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="按财务精度规则四舍五入或回溯源系统修正超精度金额。",
            tags=["金额", "精度", "准确性"],
        ),
        _column_rule(
            rule_id="A-L01",
            name="text_length_check",
            display_name="长度校验",
            dimension=QualityDimension.ACCURACY,
            source_type=RuleSourceType.STANDARD,
            problem_category="格式不规范",
            definition="校验字段长度在预设范围内，过长或过短的数据进入问题库或按截断规则处理。",
            test_definition="columnValueLengthsToBeBetween",
            parameters={"min_length": "1", "max_length": "128"},
            sql="SELECT * FROM {{ table_name }} WHERE CHAR_LENGTH({{ column_name }}) < {{ min_length }} OR CHAR_LENGTH({{ column_name }}) > {{ max_length }}",
            ge='ge_df.expect_column_value_lengths_to_be_between(column="{{ column_name }}", min_value={{ min_length }}, max_value={{ max_length }}, mostly={{ pass_rate }})',
            etl='{"action":"length_check","column":"{{ column_name }}","min":{{ min_length }},"max":{{ max_length }},"on_fail":"truncate_or_issue"}',
            patterns=["*name*", "*code*", "*desc*", "*名称*", "*描述*"],
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P2_MONITORING,
            remediation="按字段标准修正长度；允许截断时保留原值并记录处理日志。",
            tags=["长度校验", "准确性"],
        ),
        _table_rule(
            rule_id="A-B01",
            name="multi_field_condition",
            display_name="多字段条件校验",
            dimension=QualityDimension.ACCURACY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="业务逻辑错误",
            definition="校验多个相关字段之间无矛盾，例如身份证出生日期与出生日期字段一致。",
            sql="SELECT * FROM {{ table_name }} WHERE {{ invalid_condition }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ table_name }} WHERE {{ invalid_condition }}")',
            etl='{"action":"multi_field_condition","invalid_condition":"{{ invalid_condition }}","on_fail":"issue_table"}',
            parameters={"invalid_condition": "${INVALID_CONDITION}"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="核查相关字段来源和加工逻辑，修正互相矛盾的数据。",
            tags=["多字段条件", "业务规则"],
        ),
        _table_rule(
            rule_id="A-T01",
            name="time_order_logic",
            display_name="时间先后逻辑校验",
            dimension=QualityDimension.ACCURACY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="时间逻辑错误",
            definition="校验存在依赖关系的时间字段满足先后顺序，例如结束时间不早于开始时间。",
            sql="SELECT * FROM {{ table_name }} WHERE {{ end_time_column }} < {{ start_time_column }} AND {{ end_time_column }} IS NOT NULL",
            ge='ge_df.expect_column_pair_values_A_to_be_less_than_or_equal_to_B(column_A="{{ start_time_column }}", column_B="{{ end_time_column }}")',
            etl='{"action":"time_order","start":"{{ start_time_column }}","end":"{{ end_time_column }}","on_fail":"issue_table"}',
            parameters={"start_time_column": "start_time", "end_time_column": "end_time"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="修正时间字段采集或加工顺序，排查时区和格式转换问题。",
            tags=["时间逻辑", "准确性"],
        ),
        _column_rule(
            rule_id="A-T02",
            name="future_time_check",
            display_name="未来时间校验",
            dimension=QualityDimension.ACCURACY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="时间逻辑错误",
            definition="校验发生时间、创建时间、业务日期等字段不应晚于当前时间或允许容忍窗口。",
            test_definition="tableCustomSQLQuery",
            parameters={"tolerance_minutes": "5"},
            sql="SELECT * FROM {{ table_name }} WHERE {{ column_name }} > DATE_ADD(NOW(), INTERVAL {{ tolerance_minutes }} MINUTE)",
            ge='ge_df.expect_column_values_to_be_less_than_or_equal_to(column="{{ column_name }}", max_value=datetime.now() + timedelta(minutes={{ tolerance_minutes }}), mostly={{ pass_rate }})',
            etl='{"action":"future_time","column":"{{ column_name }}","tolerance_minutes":{{ tolerance_minutes }},"on_fail":"issue_table"}',
            patterns=["*create_time*", "*event_time*", "*occur_time*", "*date*", "*创建时间*", "*发生时间*"],
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="核查系统时钟、时区转换和采集延迟，修正未来日期或补充业务豁免说明。",
            tags=["未来时间", "时间逻辑", "准确性"],
        ),
        _table_rule(
            rule_id="CS-S01",
            name="cross_system_consistency",
            display_name="跨系统一致性校验",
            dimension=QualityDimension.CONSISTENCY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="跨系统不一致",
            definition="校验核心数据在业务系统与数据平台之间保持一致，无同步偏差。",
            sql="SELECT s.{{ source_key }} FROM {{ source_table }} s JOIN {{ target_table }} t ON s.{{ source_key }} = t.{{ target_key }} WHERE s.{{ compare_column }} <> t.{{ compare_column }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT s.{{ source_key }} FROM {{ source_table }} s JOIN {{ target_table }} t ON s.{{ source_key }} = t.{{ target_key }} WHERE s.{{ compare_column }} <> t.{{ compare_column }}")',
            etl='{"action":"cross_system_compare","source":"{{ source_table }}","target":"{{ target_table }}","key":"{{ source_key }}","compare":"{{ compare_column }}","on_fail":"issue_table"}',
            parameters={
                "source_table": "${SOURCE_TABLE}",
                "target_table": "${TARGET_TABLE}",
                "source_key": "id",
                "target_key": "id",
                "compare_column": "${COMPARE_COLUMN}",
            },
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="核查上下游同步延迟、转换逻辑和重试机制，必要时重新同步差异数据。",
            tags=["跨系统一致性", "一致性"],
        ),
        _table_rule(
            rule_id="CS-C01",
            name="calculation_consistency",
            display_name="计算逻辑一致性校验",
            dimension=QualityDimension.CONSISTENCY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="数值逻辑错误",
            definition="校验派生字段与原始字段计算结果一致，例如总金额=单价×数量。",
            sql="SELECT * FROM {{ table_name }} WHERE {{ calculation_expression }} <> {{ result_column }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ table_name }} WHERE {{ calculation_expression }} <> {{ result_column }}")',
            etl='{"action":"calculation_consistency","expression":"{{ calculation_expression }}","result":"{{ result_column }}","on_fail":"issue_table"}',
            parameters={
                "calculation_expression": "price * quantity",
                "result_column": "total_amount",
            },
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="统一指标口径和计算脚本，修复ETL或报表计算逻辑。",
            tags=["计算一致性", "一致性"],
        ),
        _table_rule(
            rule_id="CS-T01",
            name="master_detail_field_consistency",
            display_name="主从表核心字段一致性校验",
            dimension=QualityDimension.CONSISTENCY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="关联数据不一致",
            definition="校验主表与从表在核心业务字段上保持一致，例如客户状态、币种、组织编码等。",
            sql="SELECT d.* FROM {{ detail_table }} d JOIN {{ master_table }} m ON d.{{ master_key }} = m.{{ master_key }} WHERE d.{{ detail_compare_column }} <> m.{{ master_compare_column }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT d.* FROM {{ detail_table }} d JOIN {{ master_table }} m ON d.{{ master_key }} = m.{{ master_key }} WHERE d.{{ detail_compare_column }} <> m.{{ master_compare_column }}")',
            etl='{"action":"master_detail_consistency","master":"{{ master_table }}","detail":"{{ detail_table }}","key":"{{ master_key }}","compare":["{{ master_compare_column }}","{{ detail_compare_column }}"],"on_fail":"issue_table"}',
            parameters={
                "master_table": "${MASTER_TABLE}",
                "detail_table": "${DETAIL_TABLE}",
                "master_key": "id",
                "master_compare_column": "${MASTER_COMPARE_COLUMN}",
                "detail_compare_column": "${DETAIL_COMPARE_COLUMN}",
            },
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="核查主从表同步链路和字段映射关系，必要时以主数据为准重新同步。",
            tags=["主从一致性", "关联业务规则", "一致性"],
        ),
        _table_rule(
            rule_id="T-F01",
            name="data_freshness",
            display_name="数据新鲜度校验",
            dimension=QualityDimension.TIMELINESS,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="数据不新鲜",
            definition="校验核心业务数据最后更新时间不超过业务阈值。",
            sql="SELECT * FROM {{ table_name }} WHERE {{ update_time_column }} < DATE_SUB(NOW(), INTERVAL {{ max_delay_hours }} HOUR)",
            ge='ge_df.expect_column_values_to_be_greater_than_or_equal_to(column="{{ update_time_column }}", min_value=datetime.now() - timedelta(hours={{ max_delay_hours }}))',
            etl='{"action":"freshness","time_column":"{{ update_time_column }}","max_delay_hours":{{ max_delay_hours }},"on_fail":"alert_and_issue"}',
            parameters={"update_time_column": "update_time", "max_delay_hours": "24"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="检查采集、同步、调度是否延迟，必要时补跑任务。",
            tags=["新鲜度", "时效性"],
        ),
        _table_rule(
            rule_id="T-D01",
            name="etl_processing_latency",
            display_name="ETL加工延迟校验",
            dimension=QualityDimension.TIMELINESS,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="响应时效不达标",
            definition="校验数据从入库到加工完成的时间差不超过预设阈值。",
            sql="SELECT * FROM {{ table_name }} WHERE TIMESTAMPDIFF(MINUTE, {{ load_time_column }}, {{ process_time_column }}) > {{ max_delay_minutes }}",
            ge='ge_df.expect_column_values_to_be_less_than_or_equal_to(column="process_delay_minutes", max_value={{ max_delay_minutes }})',
            etl='{"action":"etl_latency","start":"{{ load_time_column }}","end":"{{ process_time_column }}","max_delay_minutes":{{ max_delay_minutes }},"on_fail":"alert"}',
            parameters={
                "load_time_column": "load_time",
                "process_time_column": "process_time",
                "max_delay_minutes": "120",
            },
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P2_MONITORING,
            remediation="优化调度链路、资源配置或重试策略，补跑超时批次。",
            tags=["ETL", "时效性"],
        ),
        _table_rule(
            rule_id="T-B01",
            name="batch_completion_timeliness",
            display_name="批次完成时效校验",
            dimension=QualityDimension.TIMELINESS,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="响应时效不达标",
            definition="校验数据批次在调度窗口内完成，且批次状态达到预期完成状态。",
            sql="SELECT * FROM {{ table_name }} WHERE {{ batch_status_column }} <> '{{ expected_status }}' OR TIMESTAMPDIFF(MINUTE, {{ batch_start_time_column }}, {{ batch_end_time_column }}) > {{ max_finish_minutes }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ table_name }} WHERE {{ batch_status_column }} <> \'{{ expected_status }}\' OR TIMESTAMPDIFF(MINUTE, {{ batch_start_time_column }}, {{ batch_end_time_column }}) > {{ max_finish_minutes }}")',
            etl='{"action":"batch_timeliness","status_column":"{{ batch_status_column }}","expected_status":"{{ expected_status }}","max_finish_minutes":{{ max_finish_minutes }},"on_fail":"alert"}',
            parameters={
                "batch_status_column": "batch_status",
                "expected_status": "FINISHED",
                "batch_start_time_column": "batch_start_time",
                "batch_end_time_column": "batch_end_time",
                "max_finish_minutes": "60",
            },
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="检查调度依赖、资源队列和失败重试记录，补跑超时或未完成批次。",
            tags=["批次", "调度", "时效性"],
        ),
        _table_rule(
            rule_id="AC-C01",
            name="table_accessible",
            display_name="表可访问性校验",
            dimension=QualityDimension.ACCESSIBILITY,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="访问不可达",
            definition="校验数据表可被正常查询访问。",
            sql="SELECT 1 FROM {{ table_name }} LIMIT 1",
            ge='ge_df.expect_query_to_return_valid_result(query="SELECT 1 FROM {{ table_name }} LIMIT 1")',
            etl='{"action":"connection_check","object":"{{ table_name }}","on_fail":"alert"}',
            parameters={},
            severity=RuleSeverity.CRITICAL,
            validation_level=RuleValidationLevel.P0_BLOCKING,
            remediation="检查数据库连接、网络、服务状态和元数据路径配置。",
            tags=["可访问性", "连通性"],
        ),
        _table_rule(
            rule_id="AC-P01",
            name="access_permission_valid",
            display_name="访问权限校验",
            dimension=QualityDimension.ACCESSIBILITY,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="访问权限不达标",
            definition="校验授权用户或角色具备对应数据访问权限，无权限缺失或越权。",
            sql="SELECT * FROM information_schema.schema_privileges WHERE grantee='{{ grantee }}' AND table_name='{{ table_name }}' AND privilege_type='{{ privilege_type }}'",
            ge='ge_df.expect_query_to_return_valid_result(query="SELECT * FROM information_schema.schema_privileges WHERE grantee=\'{{ grantee }}\' AND table_name=\'{{ table_name }}\' AND privilege_type=\'{{ privilege_type }}\'")',
            etl='{"action":"permission_check","grantee":"{{ grantee }}","object":"{{ table_name }}","privilege":"{{ privilege_type }}","on_fail":"security_ticket"}',
            parameters={"grantee": "${GRANTEE}", "privilege_type": "SELECT"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="补齐授权、调整权限粒度，敏感数据需同步脱敏和审计策略。",
            tags=["权限", "可访问性"],
        ),
        _table_rule(
            rule_id="AC-S01",
            name="query_response_time",
            display_name="查询响应时效校验",
            dimension=QualityDimension.ACCESSIBILITY,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="响应时效不达标",
            definition="校验常规查询响应时间不超过预设阈值，默认核心数据≤1000毫秒。",
            sql="SELECT COUNT(*) FROM {{ table_name }}",
            ge='ge_df.expect_query_to_return_valid_result(query="SELECT COUNT(*) FROM {{ table_name }}", meta={"max_response_ms": {{ max_response_ms }}})',
            etl='{"action":"response_time","query":"SELECT COUNT(*) FROM {{ table_name }}","max_response_ms":{{ max_response_ms }},"on_fail":"performance_ticket"}',
            parameters={"max_response_ms": "1000"},
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P2_MONITORING,
            remediation="优化索引、分区、缓存或资源配置，必要时拆分查询场景。",
            tags=["响应时效", "性能"],
        ),
        _api_rule(
            rule_id="AC-S02",
            name="api_status_available",
            display_name="API接口可用性校验",
            problem_category="访问不可达",
            definition="校验数据服务API返回成功状态码且响应时间不超过预设阈值。",
            sql="SELECT * FROM {{ api_monitor_table }} WHERE api_name = '{{ api_name }}' AND (status_code < 200 OR status_code >= 300 OR response_ms > {{ max_response_ms }})",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ api_monitor_table }} WHERE api_name = \'{{ api_name }}\' AND (status_code < 200 OR status_code >= 300 OR response_ms > {{ max_response_ms }})")',
            etl='{"action":"api_health_check","api_name":"{{ api_name }}","max_response_ms":{{ max_response_ms }},"on_fail":"ops_ticket"}',
            parameters={"api_monitor_table": "api_monitor_log", "api_name": "${API_NAME}", "max_response_ms": "1000"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="检查API网关、鉴权、网络和后端服务状态，恢复后重新执行可用性校验。",
            tags=["API", "可访问性", "响应状态"],
        ),
    ]
    rules.extend(_build_whitepaper_extended_rule_templates())
    return rules


def _build_whitepaper_extended_rule_templates() -> List[RuleTemplate]:
    """构建白皮书补充规则：六个评价维度各10条。"""
    return (
        _build_normativity_extended_rules()
        + _build_completeness_extended_rules()
        + _build_accuracy_extended_rules()
        + _build_consistency_extended_rules()
        + _build_timeliness_extended_rules()
        + _build_accessibility_extended_rules()
    )


def _build_normativity_extended_rules() -> List[RuleTemplate]:
    """规范性扩展规则。"""
    return [
        _column_rule(
            rule_id="N-W01",
            name="date_format_yyyy_mm_dd",
            display_name="日期格式规范校验",
            dimension=QualityDimension.NORMATIVITY,
            source_type=RuleSourceType.STANDARD,
            problem_category="格式不规范",
            definition="校验日期字段统一采用YYYY-MM-DD格式，避免多格式混用影响统计和交换。",
            test_definition="columnValuesToMatchRegex",
            parameters={"regex": r"^\d{4}-(0[1-9]|1[0-2])-([0-2]\d|3[01])$"},
            sql="SELECT * FROM {{ table_name }} WHERE {{ column_name }} IS NOT NULL AND {{ column_name }} NOT REGEXP '{{ regex }}'",
            ge='ge_df.expect_column_values_to_match_regex(column="{{ column_name }}", regex=r"{{ regex }}", mostly={{ pass_rate }})',
            etl='{"action":"date_format","column":"{{ column_name }}","format":"yyyy-MM-dd","on_fail":"issue_table"}',
            patterns=["*date*", "*dt*", "*日期*", "*业务日*"],
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="按统一日期格式清洗字段，采集端和交换接口同步固化日期格式。",
            tags=["白皮书扩展", "日期", "格式校验", "规范性"],
        ),
        _column_rule(
            rule_id="N-W02",
            name="datetime_format_standard",
            display_name="时间戳格式规范校验",
            dimension=QualityDimension.NORMATIVITY,
            source_type=RuleSourceType.STANDARD,
            problem_category="格式不规范",
            definition="校验时间戳字段统一采用YYYY-MM-DD HH:MM:SS格式。",
            test_definition="columnValuesToMatchRegex",
            parameters={"regex": r"^\d{4}-(0[1-9]|1[0-2])-([0-2]\d|3[01]) ([01]\d|2[0-3]):[0-5]\d:[0-5]\d$"},
            sql="SELECT * FROM {{ table_name }} WHERE {{ column_name }} IS NOT NULL AND {{ column_name }} NOT REGEXP '{{ regex }}'",
            ge='ge_df.expect_column_values_to_match_regex(column="{{ column_name }}", regex=r"{{ regex }}", mostly={{ pass_rate }})',
            etl='{"action":"datetime_format","column":"{{ column_name }}","format":"yyyy-MM-dd HH:mm:ss","on_fail":"issue_table"}',
            patterns=["*time*", "*timestamp*", "*时间*", "*时刻*"],
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="统一时间戳格式并核查时区转换规则，异常值进入问题库。",
            tags=["白皮书扩展", "时间", "格式校验", "规范性"],
        ),
        _column_rule(
            rule_id="N-W03",
            name="credit_code_format",
            display_name="统一社会信用代码格式校验",
            dimension=QualityDimension.NORMATIVITY,
            source_type=RuleSourceType.STANDARD,
            problem_category="编码不规范",
            definition="校验企业统一社会信用代码为18位大写字母或数字编码。",
            test_definition="columnValuesToMatchRegex",
            parameters={"regex": r"^[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}$"},
            sql="SELECT * FROM {{ table_name }} WHERE {{ column_name }} IS NOT NULL AND {{ column_name }} NOT REGEXP '{{ regex }}'",
            ge='ge_df.expect_column_values_to_match_regex(column="{{ column_name }}", regex=r"{{ regex }}", mostly={{ pass_rate }})',
            etl='{"action":"credit_code_format","column":"{{ column_name }}","regex":"{{ regex }}","on_fail":"issue_table"}',
            patterns=["*credit_code*", "*social_code*", "*统一社会信用代码*", "*信用代码*"],
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="按市场主体登记信息修正信用代码，无法确认时回溯主数据来源。",
            tags=["白皮书扩展", "统一社会信用代码", "编码", "规范性"],
        ),
        _column_rule(
            rule_id="N-W04",
            name="bank_card_number_format",
            display_name="银行卡号格式校验",
            dimension=QualityDimension.NORMATIVITY,
            source_type=RuleSourceType.STANDARD,
            problem_category="格式不规范",
            definition="校验银行卡号为12到19位数字，满足常见银行账号采集格式。",
            test_definition="columnValuesToMatchRegex",
            parameters={"regex": r"^\d{12,19}$"},
            sql="SELECT * FROM {{ table_name }} WHERE {{ column_name }} IS NOT NULL AND {{ column_name }} NOT REGEXP '{{ regex }}'",
            ge='ge_df.expect_column_values_to_match_regex(column="{{ column_name }}", regex=r"{{ regex }}", mostly={{ pass_rate }})',
            etl='{"action":"bank_card_format","column":"{{ column_name }}","on_fail":"issue_table"}',
            patterns=["*bank_card*", "*bank_account*", "*银行卡*", "*银行账号*"],
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="核对银行账号来源，清理空格、短横线等非数字字符，敏感数据同步脱敏。",
            tags=["白皮书扩展", "银行卡", "格式校验", "规范性"],
        ),
        _column_rule(
            rule_id="N-W05",
            name="postal_code_format",
            display_name="邮政编码格式校验",
            dimension=QualityDimension.NORMATIVITY,
            source_type=RuleSourceType.STANDARD,
            problem_category="编码不规范",
            definition="校验邮政编码为6位数字编码。",
            test_definition="columnValuesToMatchRegex",
            parameters={"regex": r"^\d{6}$"},
            sql="SELECT * FROM {{ table_name }} WHERE {{ column_name }} IS NOT NULL AND {{ column_name }} NOT REGEXP '{{ regex }}'",
            ge='ge_df.expect_column_values_to_match_regex(column="{{ column_name }}", regex=r"{{ regex }}", mostly={{ pass_rate }})',
            etl='{"action":"postal_code_format","column":"{{ column_name }}","on_fail":"issue_table"}',
            patterns=["*post_code*", "*zip_code*", "*邮编*", "*邮政编码*"],
            severity=RuleSeverity.LOW,
            validation_level=RuleValidationLevel.P2_MONITORING,
            remediation="按地址标准化结果补正邮政编码，无法匹配的记录进入人工核查。",
            tags=["白皮书扩展", "邮政编码", "编码", "规范性"],
        ),
        _column_rule(
            rule_id="N-W06",
            name="currency_code_format",
            display_name="币种编码规范校验",
            dimension=QualityDimension.NORMATIVITY,
            source_type=RuleSourceType.STANDARD,
            problem_category="编码不规范",
            definition="校验币种字段采用三位大写字母编码，例如CNY、USD、EUR。",
            test_definition="columnValuesToMatchRegex",
            parameters={"regex": r"^[A-Z]{3}$"},
            sql="SELECT * FROM {{ table_name }} WHERE {{ column_name }} IS NOT NULL AND {{ column_name }} NOT REGEXP '{{ regex }}'",
            ge='ge_df.expect_column_values_to_match_regex(column="{{ column_name }}", regex=r"{{ regex }}", mostly={{ pass_rate }})',
            etl='{"action":"currency_code_format","column":"{{ column_name }}","on_fail":"issue_table"}',
            patterns=["*currency*", "*currency_code*", "*币种*", "*币种编码*"],
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="按企业币种字典统一大小写和编码，缺失币种需补齐业务默认值。",
            tags=["白皮书扩展", "币种", "编码", "规范性"],
        ),
        _column_rule(
            rule_id="N-W07",
            name="country_code_format",
            display_name="国家地区编码规范校验",
            dimension=QualityDimension.NORMATIVITY,
            source_type=RuleSourceType.STANDARD,
            problem_category="编码不规范",
            definition="校验国家或地区编码采用2位或3位大写字母标准代码。",
            test_definition="columnValuesToMatchRegex",
            parameters={"regex": r"^[A-Z]{2,3}$"},
            sql="SELECT * FROM {{ table_name }} WHERE {{ column_name }} IS NOT NULL AND {{ column_name }} NOT REGEXP '{{ regex }}'",
            ge='ge_df.expect_column_values_to_match_regex(column="{{ column_name }}", regex=r"{{ regex }}", mostly={{ pass_rate }})',
            etl='{"action":"country_code_format","column":"{{ column_name }}","on_fail":"issue_table"}',
            patterns=["*country_code*", "*nation_code*", "*国家编码*", "*地区代码*"],
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="按国家地区代码字典修正编码，跨境数据交换需统一代码版本。",
            tags=["白皮书扩展", "国家地区编码", "规范性"],
        ),
        _column_rule(
            rule_id="N-W08",
            name="boolean_flag_standard",
            display_name="布尔标志值规范校验",
            dimension=QualityDimension.NORMATIVITY,
            source_type=RuleSourceType.STANDARD,
            problem_category="值域不合理",
            definition="校验标志位字段只使用统一的Y/N或1/0取值，避免是/否、true/false混用。",
            test_definition="columnValuesToBeInSet",
            parameters={"allowed_values": "'Y','N','1','0'"},
            sql="SELECT * FROM {{ table_name }} WHERE {{ column_name }} IS NOT NULL AND {{ column_name }} NOT IN ({{ allowed_values }})",
            ge='ge_df.expect_column_values_to_be_in_set(column="{{ column_name }}", value_set=[{{ allowed_values }}], mostly={{ pass_rate }})',
            etl='{"action":"flag_domain","column":"{{ column_name }}","allowed_values":[{{ allowed_values }}],"on_fail":"issue_table"}',
            patterns=["*flag*", "*is_*", "*是否*", "*标志*"],
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="统一标志位值域并维护转换映射，历史混用值批量清洗。",
            tags=["白皮书扩展", "标志位", "枚举", "规范性"],
        ),
        _table_rule(
            rule_id="N-W09",
            name="column_english_name_standard",
            display_name="字段英文命名规范校验",
            dimension=QualityDimension.NORMATIVITY,
            source_type=RuleSourceType.STANDARD,
            problem_category="命名不规范",
            definition="校验字段英文名符合小写字母、数字和下划线命名规范。",
            sql="SELECT column_name FROM information_schema.columns WHERE table_name='{{ table_name }}' AND column_name NOT REGEXP '^[a-z][a-z0-9_]*$'",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT column_name FROM information_schema.columns WHERE table_name=\'{{ table_name }}\' AND column_name NOT REGEXP \'^[a-z][a-z0-9_]*$\'")',
            etl='{"action":"metadata_column_name_standard","table":"{{ table_name }}","pattern":"^[a-z][a-z0-9_]*$","on_fail":"standard_ticket"}',
            parameters={},
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="按数据标准修正字段英文名，涉及下游接口时同步发布变更计划。",
            tags=["白皮书扩展", "命名规范", "元数据", "规范性"],
        ),
        _table_rule(
            rule_id="N-W10",
            name="table_name_standard",
            display_name="数据表命名规范校验",
            dimension=QualityDimension.NORMATIVITY,
            source_type=RuleSourceType.STANDARD,
            problem_category="命名不规范",
            definition="校验数据表名称符合分层前缀和小写下划线命名规范。",
            sql="SELECT '{{ table_name }}' AS table_name WHERE '{{ table_name }}' NOT REGEXP '^(ods|dwd|dws|ads|dim|fact)_[a-z0-9_]+$'",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT \'{{ table_name }}\' AS table_name WHERE \'{{ table_name }}\' NOT REGEXP \'^(ods|dwd|dws|ads|dim|fact)_[a-z0-9_]+$\'")',
            etl='{"action":"metadata_table_name_standard","table":"{{ table_name }}","prefixes":["ods","dwd","dws","ads","dim","fact"],"on_fail":"standard_ticket"}',
            parameters={},
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="按数据分层和主题域命名规范调整表名，发布元数据变更通知。",
            tags=["白皮书扩展", "表命名", "元数据", "规范性"],
        ),
    ]


def _build_completeness_extended_rules() -> List[RuleTemplate]:
    """完整性扩展规则。"""
    return [
        _table_rule(
            rule_id="C-W01",
            name="contact_method_group_complete",
            display_name="联系方式组合完整性校验",
            dimension=QualityDimension.COMPLETENESS,
            source_type=RuleSourceType.BUSINESS,
            problem_category="字段不完整",
            definition="校验联系人至少具备手机号、邮箱、固定电话中的一种有效联系方式。",
            sql="SELECT * FROM {{ table_name }} WHERE COALESCE(NULLIF(TRIM({{ mobile_column }}), ''), NULLIF(TRIM({{ email_column }}), ''), NULLIF(TRIM({{ tel_column }}), '')) IS NULL",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ table_name }} WHERE COALESCE(NULLIF(TRIM({{ mobile_column }}), \'\'), NULLIF(TRIM({{ email_column }}), \'\'), NULLIF(TRIM({{ tel_column }}), \'\')) IS NULL")',
            etl='{"action":"field_group_required_any","columns":["{{ mobile_column }}","{{ email_column }}","{{ tel_column }}"],"on_fail":"issue_table"}',
            parameters={"mobile_column": "mobile_phone", "email_column": "email", "tel_column": "tel"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="补齐至少一种联系方式，采集端增加联系方式组合必填校验。",
            tags=["白皮书扩展", "组合完整性", "联系方式", "完整性"],
        ),
        _table_rule(
            rule_id="C-W02",
            name="composite_key_complete",
            display_name="联合业务主键完整性校验",
            dimension=QualityDimension.COMPLETENESS,
            source_type=RuleSourceType.STANDARD,
            problem_category="字段不完整",
            definition="校验联合业务主键中的各组成字段均不能为空。",
            sql="SELECT * FROM {{ table_name }} WHERE {{ key_column_a }} IS NULL OR {{ key_column_b }} IS NULL OR TRIM(CAST({{ key_column_a }} AS CHAR))='' OR TRIM(CAST({{ key_column_b }} AS CHAR))=''",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ table_name }} WHERE {{ key_column_a }} IS NULL OR {{ key_column_b }} IS NULL")',
            etl='{"action":"composite_key_not_null","columns":["{{ key_column_a }}","{{ key_column_b }}"],"on_fail":"block_or_issue"}',
            parameters={"key_column_a": "business_id", "key_column_b": "source_system"},
            severity=RuleSeverity.CRITICAL,
            validation_level=RuleValidationLevel.P0_BLOCKING,
            remediation="补齐联合主键字段或阻断入库，避免下游无法定位唯一业务对象。",
            tags=["白皮书扩展", "联合主键", "完整性", "强校验"],
        ),
        _table_rule(
            rule_id="C-W03",
            name="table_min_record_count",
            display_name="表记录数下限完整性校验",
            dimension=QualityDimension.COMPLETENESS,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="记录不完整",
            definition="校验关键数据表记录数达到最低业务阈值，避免空表或漏批。",
            sql="SELECT COUNT(*) AS row_count FROM {{ table_name }} HAVING COUNT(*) < {{ min_row_count }}",
            ge='ge_df.expect_table_row_count_to_be_between(min_value={{ min_row_count }})',
            etl='{"action":"row_count_min","table":"{{ table_name }}","min_row_count":{{ min_row_count }},"on_fail":"alert_and_issue"}',
            parameters={"min_row_count": "1"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="检查采集、同步、调度是否漏批，必要时补跑或回滚空批次。",
            tags=["白皮书扩展", "记录完整性", "空表", "完整性"],
        ),
        _table_rule(
            rule_id="C-W04",
            name="partition_record_complete",
            display_name="分区数据完整性校验",
            dimension=QualityDimension.COMPLETENESS,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="记录不完整",
            definition="校验指定业务日期或分区存在数据且记录数不低于阈值。",
            sql="SELECT {{ partition_column }}, COUNT(*) AS row_count FROM {{ table_name }} WHERE {{ partition_column }}='{{ partition_value }}' GROUP BY {{ partition_column }} HAVING COUNT(*) < {{ min_row_count }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT {{ partition_column }}, COUNT(*) AS row_count FROM {{ table_name }} WHERE {{ partition_column }}=\'{{ partition_value }}\' GROUP BY {{ partition_column }} HAVING COUNT(*) < {{ min_row_count }}")',
            etl='{"action":"partition_completeness","partition_column":"{{ partition_column }}","partition_value":"{{ partition_value }}","min_row_count":{{ min_row_count }},"on_fail":"alert"}',
            parameters={"partition_column": "biz_date", "partition_value": "${BIZ_DATE}", "min_row_count": "1"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="检查分区装载任务和数据源供数，补齐缺失分区数据。",
            tags=["白皮书扩展", "分区完整性", "批次", "完整性"],
        ),
        _table_rule(
            rule_id="C-W05",
            name="conditional_attachment_complete",
            display_name="条件附件完整性校验",
            dimension=QualityDimension.COMPLETENESS,
            source_type=RuleSourceType.BUSINESS,
            problem_category="关联不完整",
            definition="校验需要附件的业务记录必须存在附件编号或附件路径。",
            sql="SELECT * FROM {{ table_name }} WHERE {{ required_flag_column }}='{{ required_flag_value }}' AND ({{ attachment_column }} IS NULL OR TRIM(CAST({{ attachment_column }} AS CHAR))='')",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ table_name }} WHERE {{ required_flag_column }}=\'{{ required_flag_value }}\' AND ({{ attachment_column }} IS NULL OR TRIM(CAST({{ attachment_column }} AS CHAR))=\'\')")',
            etl='{"action":"conditional_required","condition":"{{ required_flag_column }}={{ required_flag_value }}","required_column":"{{ attachment_column }}","on_fail":"issue_table"}',
            parameters={"required_flag_column": "need_attachment_flag", "required_flag_value": "Y", "attachment_column": "attachment_id"},
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="补齐附件信息或修正是否需要附件标志，完善业务表单校验。",
            tags=["白皮书扩展", "条件完整性", "附件", "完整性"],
        ),
        _table_rule(
            rule_id="C-W06",
            name="coordinate_pair_complete",
            display_name="经纬度成对完整性校验",
            dimension=QualityDimension.COMPLETENESS,
            source_type=RuleSourceType.BUSINESS,
            problem_category="字段不完整",
            definition="校验经度和纬度必须成对出现，不能只填其中一个。",
            sql="SELECT * FROM {{ table_name }} WHERE ({{ longitude_column }} IS NULL AND {{ latitude_column }} IS NOT NULL) OR ({{ longitude_column }} IS NOT NULL AND {{ latitude_column }} IS NULL)",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ table_name }} WHERE ({{ longitude_column }} IS NULL AND {{ latitude_column }} IS NOT NULL) OR ({{ longitude_column }} IS NOT NULL AND {{ latitude_column }} IS NULL)")',
            etl='{"action":"paired_fields_complete","columns":["{{ longitude_column }}","{{ latitude_column }}"],"on_fail":"issue_table"}',
            parameters={"longitude_column": "longitude", "latitude_column": "latitude"},
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="补齐缺失的经纬度字段或整体置为空并标记待采集。",
            tags=["白皮书扩展", "经纬度", "成对完整性", "完整性"],
        ),
        _table_rule(
            rule_id="C-W07",
            name="time_pair_complete",
            display_name="起止时间成对完整性校验",
            dimension=QualityDimension.COMPLETENESS,
            source_type=RuleSourceType.BUSINESS,
            problem_category="字段不完整",
            definition="校验开始时间和结束时间必须根据业务状态成对完整。",
            sql="SELECT * FROM {{ table_name }} WHERE ({{ start_time_column }} IS NULL AND {{ end_time_column }} IS NOT NULL) OR ({{ start_time_column }} IS NOT NULL AND {{ end_time_column }} IS NULL AND {{ status_column }}='{{ finished_status }}')",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ table_name }} WHERE ({{ start_time_column }} IS NULL AND {{ end_time_column }} IS NOT NULL) OR ({{ start_time_column }} IS NOT NULL AND {{ end_time_column }} IS NULL AND {{ status_column }}=\'{{ finished_status }}\')")',
            etl='{"action":"time_pair_complete","start":"{{ start_time_column }}","end":"{{ end_time_column }}","finished_status":"{{ finished_status }}","on_fail":"issue_table"}',
            parameters={"start_time_column": "start_time", "end_time_column": "end_time", "status_column": "status", "finished_status": "FINISHED"},
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="补齐流程起止时间，排查状态流转和时间采集逻辑。",
            tags=["白皮书扩展", "时间字段", "成对完整性", "完整性"],
        ),
        _table_rule(
            rule_id="C-W08",
            name="status_required_time_complete",
            display_name="状态时间完整性校验",
            dimension=QualityDimension.COMPLETENESS,
            source_type=RuleSourceType.BUSINESS,
            problem_category="字段不完整",
            definition="校验特定业务状态下必须填写对应状态时间，例如关闭状态必须有关闭时间。",
            sql="SELECT * FROM {{ table_name }} WHERE {{ status_column }}='{{ target_status }}' AND ({{ status_time_column }} IS NULL OR TRIM(CAST({{ status_time_column }} AS CHAR))='')",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ table_name }} WHERE {{ status_column }}=\'{{ target_status }}\' AND {{ status_time_column }} IS NULL")',
            etl='{"action":"status_time_required","status_column":"{{ status_column }}","status":"{{ target_status }}","time_column":"{{ status_time_column }}","on_fail":"issue_table"}',
            parameters={"status_column": "status", "target_status": "CLOSED", "status_time_column": "close_time"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="补齐状态时间或修正状态值，避免流程闭环无法追踪。",
            tags=["白皮书扩展", "状态时间", "完整性"],
        ),
        _table_rule(
            rule_id="C-W09",
            name="code_name_pair_complete",
            display_name="代码名称成对完整性校验",
            dimension=QualityDimension.COMPLETENESS,
            source_type=RuleSourceType.BUSINESS,
            problem_category="字段不完整",
            definition="校验编码字段与名称字段成对完整，避免只有代码或只有名称。",
            sql="SELECT * FROM {{ table_name }} WHERE ({{ code_column }} IS NULL AND {{ name_column }} IS NOT NULL) OR ({{ code_column }} IS NOT NULL AND ({{ name_column }} IS NULL OR TRIM(CAST({{ name_column }} AS CHAR))=''))",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ table_name }} WHERE ({{ code_column }} IS NULL AND {{ name_column }} IS NOT NULL) OR ({{ code_column }} IS NOT NULL AND {{ name_column }} IS NULL)")',
            etl='{"action":"code_name_pair_complete","code":"{{ code_column }}","name":"{{ name_column }}","on_fail":"issue_table"}',
            parameters={"code_column": "org_code", "name_column": "org_name"},
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="从数据字典或主数据补齐名称，维护编码和名称同步映射。",
            tags=["白皮书扩展", "编码名称", "完整性"],
        ),
        _table_rule(
            rule_id="C-W10",
            name="lineage_required_reference_complete",
            display_name="血缘关联对象完整性校验",
            dimension=QualityDimension.COMPLETENESS,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="关联不完整",
            definition="校验已登记血缘关系的目标字段存在对应上游来源对象记录。",
            sql="SELECT l.* FROM {{ lineage_table }} l LEFT JOIN {{ metadata_table }} m ON l.source_table=m.table_name AND l.source_column=m.column_name WHERE l.target_table='{{ table_name }}' AND m.table_name IS NULL",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT l.* FROM {{ lineage_table }} l LEFT JOIN {{ metadata_table }} m ON l.source_table=m.table_name AND l.source_column=m.column_name WHERE l.target_table=\'{{ table_name }}\' AND m.table_name IS NULL")',
            etl='{"action":"lineage_reference_completeness","lineage_table":"{{ lineage_table }}","metadata_table":"{{ metadata_table }}","target":"{{ table_name }}","on_fail":"metadata_ticket"}',
            parameters={"lineage_table": "data_lineage", "metadata_table": "metadata_column"},
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P2_MONITORING,
            remediation="补齐血缘来源对象元数据，或删除无效血缘关系并记录变更。",
            tags=["白皮书扩展", "血缘", "关联完整性", "完整性"],
        ),
    ]


def _build_accuracy_extended_rules() -> List[RuleTemplate]:
    """准确性扩展规则。"""
    return [
        _column_rule(
            rule_id="A-W01",
            name="amount_non_negative",
            display_name="金额非负准确性校验",
            dimension=QualityDimension.ACCURACY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="数值逻辑错误",
            definition="校验金额、余额、费用等字段不小于0，退款等负值场景需单独配置豁免。",
            test_definition="columnValuesToBeBetween",
            parameters={"min_value": "0"},
            sql="SELECT * FROM {{ table_name }} WHERE {{ column_name }} < {{ min_value }}",
            ge='ge_df.expect_column_values_to_be_between(column="{{ column_name }}", min_value={{ min_value }}, mostly={{ pass_rate }})',
            etl='{"action":"non_negative","column":"{{ column_name }}","min":{{ min_value }},"on_fail":"issue_table"}',
            patterns=["*amount*", "*balance*", "*fee*", "*金额*", "*余额*", "*费用*"],
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="核查负值业务含义，非退款或冲正场景需回溯源系统修正。",
            tags=["白皮书扩展", "金额", "非负", "准确性"],
        ),
        _column_rule(
            rule_id="A-W02",
            name="percentage_range",
            display_name="百分比范围准确性校验",
            dimension=QualityDimension.ACCURACY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="值域不合理",
            definition="校验百分比、比例、率字段取值处于0到100之间。",
            test_definition="columnValuesToBeBetween",
            parameters={"min_value": "0", "max_value": "100"},
            sql="SELECT * FROM {{ table_name }} WHERE {{ column_name }} < {{ min_value }} OR {{ column_name }} > {{ max_value }}",
            ge='ge_df.expect_column_values_to_be_between(column="{{ column_name }}", min_value={{ min_value }}, max_value={{ max_value }}, mostly={{ pass_rate }})',
            etl='{"action":"range_check","column":"{{ column_name }}","min":{{ min_value }},"max":{{ max_value }},"on_fail":"issue_table"}',
            patterns=["*rate*", "*ratio*", "*percent*", "*比例*", "*百分比*", "*率*"],
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="统一百分比存储口径，明确0-1和0-100之间的转换规则。",
            tags=["白皮书扩展", "百分比", "值域", "准确性"],
        ),
        _column_rule(
            rule_id="A-W03",
            name="latitude_range",
            display_name="纬度范围准确性校验",
            dimension=QualityDimension.ACCURACY,
            source_type=RuleSourceType.STANDARD,
            problem_category="值域不合理",
            definition="校验纬度字段取值在-90到90之间。",
            test_definition="columnValuesToBeBetween",
            parameters={"min_value": "-90", "max_value": "90"},
            sql="SELECT * FROM {{ table_name }} WHERE {{ column_name }} < {{ min_value }} OR {{ column_name }} > {{ max_value }}",
            ge='ge_df.expect_column_values_to_be_between(column="{{ column_name }}", min_value={{ min_value }}, max_value={{ max_value }}, mostly={{ pass_rate }})',
            etl='{"action":"geo_latitude_range","column":"{{ column_name }}","on_fail":"issue_table"}',
            patterns=["*latitude*", "*lat*", "*纬度*"],
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="修正经纬度字段映射和坐标系转换，非法坐标进入问题库。",
            tags=["白皮书扩展", "纬度", "地理坐标", "准确性"],
        ),
        _column_rule(
            rule_id="A-W04",
            name="longitude_range",
            display_name="经度范围准确性校验",
            dimension=QualityDimension.ACCURACY,
            source_type=RuleSourceType.STANDARD,
            problem_category="值域不合理",
            definition="校验经度字段取值在-180到180之间。",
            test_definition="columnValuesToBeBetween",
            parameters={"min_value": "-180", "max_value": "180"},
            sql="SELECT * FROM {{ table_name }} WHERE {{ column_name }} < {{ min_value }} OR {{ column_name }} > {{ max_value }}",
            ge='ge_df.expect_column_values_to_be_between(column="{{ column_name }}", min_value={{ min_value }}, max_value={{ max_value }}, mostly={{ pass_rate }})',
            etl='{"action":"geo_longitude_range","column":"{{ column_name }}","on_fail":"issue_table"}',
            patterns=["*longitude*", "*lng*", "*lon*", "*经度*"],
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="修正经纬度字段映射和坐标系转换，非法坐标进入问题库。",
            tags=["白皮书扩展", "经度", "地理坐标", "准确性"],
        ),
        _table_rule(
            rule_id="A-W05",
            name="id_card_birthdate_consistency",
            display_name="身份证出生日期准确性校验",
            dimension=QualityDimension.ACCURACY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="业务逻辑错误",
            definition="校验身份证号中出生日期与出生日期字段一致。",
            sql="SELECT * FROM {{ table_name }} WHERE {{ id_card_column }} IS NOT NULL AND {{ birth_date_column }} IS NOT NULL AND SUBSTRING({{ id_card_column }}, 7, 8) <> DATE_FORMAT({{ birth_date_column }}, '%Y%m%d')",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ table_name }} WHERE {{ id_card_column }} IS NOT NULL AND {{ birth_date_column }} IS NOT NULL AND SUBSTRING({{ id_card_column }}, 7, 8) <> DATE_FORMAT({{ birth_date_column }}, \'%Y%m%d\')")',
            etl='{"action":"id_card_birthdate_consistency","id_card":"{{ id_card_column }}","birth_date":"{{ birth_date_column }}","on_fail":"issue_table"}',
            parameters={"id_card_column": "id_card", "birth_date_column": "birth_date"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="以权威身份信息为准修正出生日期或身份证号码，保留修正依据。",
            tags=["白皮书扩展", "身份证", "出生日期", "准确性"],
        ),
        _table_rule(
            rule_id="A-W06",
            name="id_card_gender_consistency",
            display_name="身份证性别准确性校验",
            dimension=QualityDimension.ACCURACY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="业务逻辑错误",
            definition="校验身份证号顺序码性别位与性别字段一致。",
            sql="SELECT * FROM {{ table_name }} WHERE {{ id_card_column }} IS NOT NULL AND {{ gender_column }} IS NOT NULL AND ((MOD(CAST(SUBSTRING({{ id_card_column }}, 17, 1) AS UNSIGNED), 2)=1 AND {{ gender_column }} NOT IN ('M','男')) OR (MOD(CAST(SUBSTRING({{ id_card_column }}, 17, 1) AS UNSIGNED), 2)=0 AND {{ gender_column }} NOT IN ('F','女')))",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ table_name }} WHERE {{ id_card_column }} IS NOT NULL AND {{ gender_column }} IS NOT NULL AND ((MOD(CAST(SUBSTRING({{ id_card_column }}, 17, 1) AS UNSIGNED), 2)=1 AND {{ gender_column }} NOT IN (\'M\',\'男\')) OR (MOD(CAST(SUBSTRING({{ id_card_column }}, 17, 1) AS UNSIGNED), 2)=0 AND {{ gender_column }} NOT IN (\'F\',\'女\')))")',
            etl='{"action":"id_card_gender_consistency","id_card":"{{ id_card_column }}","gender":"{{ gender_column }}","on_fail":"issue_table"}',
            parameters={"id_card_column": "id_card", "gender_column": "gender"},
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="核查性别字段来源和身份证解析逻辑，按权威主数据修正。",
            tags=["白皮书扩展", "身份证", "性别", "准确性"],
        ),
        _column_rule(
            rule_id="A-W07",
            name="quantity_integer_non_negative",
            display_name="数量整数非负校验",
            dimension=QualityDimension.ACCURACY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="数值逻辑错误",
            definition="校验数量、件数、库存等字段为非负整数。",
            test_definition="columnValuesToMatchRegex",
            parameters={"regex": r"^\d+$"},
            sql="SELECT * FROM {{ table_name }} WHERE {{ column_name }} IS NOT NULL AND {{ column_name }} NOT REGEXP '{{ regex }}'",
            ge='ge_df.expect_column_values_to_match_regex(column="{{ column_name }}", regex=r"{{ regex }}", mostly={{ pass_rate }})',
            etl='{"action":"integer_non_negative","column":"{{ column_name }}","on_fail":"issue_table"}',
            patterns=["*quantity*", "*qty*", "*count*", "*库存*", "*数量*", "*件数*"],
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="确认数量字段口径，非整数或负数需回溯订单、库存或采集来源。",
            tags=["白皮书扩展", "数量", "整数", "准确性"],
        ),
        _table_rule(
            rule_id="A-W08",
            name="tax_amount_logic",
            display_name="税额计算准确性校验",
            dimension=QualityDimension.ACCURACY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="数值逻辑错误",
            definition="校验税额与含税金额、税率之间的计算关系符合业务口径。",
            sql="SELECT * FROM {{ table_name }} WHERE ABS({{ tax_amount_column }} - ROUND({{ taxable_amount_column }} * {{ tax_rate_column }}, {{ decimal_scale }})) > {{ tolerance_amount }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ table_name }} WHERE ABS({{ tax_amount_column }} - ROUND({{ taxable_amount_column }} * {{ tax_rate_column }}, {{ decimal_scale }})) > {{ tolerance_amount }}")',
            etl='{"action":"tax_amount_logic","tax_amount":"{{ tax_amount_column }}","taxable_amount":"{{ taxable_amount_column }}","tax_rate":"{{ tax_rate_column }}","tolerance":{{ tolerance_amount }},"on_fail":"issue_table"}',
            parameters={"tax_amount_column": "tax_amount", "taxable_amount_column": "taxable_amount", "tax_rate_column": "tax_rate", "decimal_scale": "2", "tolerance_amount": "0.01"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="统一税率和四舍五入口径，修复计税逻辑或源数据税额。",
            tags=["白皮书扩展", "税额", "计算逻辑", "准确性"],
        ),
        _column_rule(
            rule_id="A-W09",
            name="dirty_placeholder_value",
            display_name="脏占位值准确性校验",
            dimension=QualityDimension.ACCURACY,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="脏数据",
            definition="校验字段不应出现unknown、N/A、null、--等占位脏值。",
            test_definition="columnValuesToNotMatchRegex",
            parameters={"regex": r"^(unknown|unk|n/a|na|null|none|--|-|待定|未知)$"},
            sql="SELECT * FROM {{ table_name }} WHERE LOWER(TRIM(CAST({{ column_name }} AS CHAR))) REGEXP '{{ regex }}'",
            ge='ge_df.expect_column_values_to_not_match_regex(column="{{ column_name }}", regex=r"{{ regex }}", mostly={{ pass_rate }})',
            etl='{"action":"dirty_placeholder_check","column":"{{ column_name }}","regex":"{{ regex }}","on_fail":"issue_table"}',
            patterns=["*name*", "*code*", "*status*", "*名称*", "*编码*", "*状态*"],
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="将占位值转为空值或回填真实值，采集端禁止提交占位脏值。",
            tags=["白皮书扩展", "脏数据", "占位值", "准确性"],
        ),
        _table_rule(
            rule_id="A-W10",
            name="age_birthdate_logic",
            display_name="年龄出生日期准确性校验",
            dimension=QualityDimension.ACCURACY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="业务逻辑错误",
            definition="校验年龄字段与出生日期推算结果在允许偏差范围内。",
            sql="SELECT * FROM {{ table_name }} WHERE {{ age_column }} IS NOT NULL AND {{ birth_date_column }} IS NOT NULL AND ABS({{ age_column }} - TIMESTAMPDIFF(YEAR, {{ birth_date_column }}, CURRENT_DATE)) > {{ tolerance_years }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ table_name }} WHERE {{ age_column }} IS NOT NULL AND {{ birth_date_column }} IS NOT NULL AND ABS({{ age_column }} - TIMESTAMPDIFF(YEAR, {{ birth_date_column }}, CURRENT_DATE)) > {{ tolerance_years }}")',
            etl='{"action":"age_birthdate_logic","age":"{{ age_column }}","birth_date":"{{ birth_date_column }}","tolerance_years":{{ tolerance_years }},"on_fail":"issue_table"}',
            parameters={"age_column": "age", "birth_date_column": "birth_date", "tolerance_years": "1"},
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="核查年龄计算口径，建议以出生日期实时计算年龄并减少冗余存储。",
            tags=["白皮书扩展", "年龄", "出生日期", "准确性"],
        ),
    ]


def _build_consistency_extended_rules() -> List[RuleTemplate]:
    """一致性扩展规则。"""
    return [
        _table_rule(
            rule_id="CS-W01",
            name="code_name_dictionary_consistency",
            display_name="码值名称字典一致性校验",
            dimension=QualityDimension.CONSISTENCY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="关联数据不一致",
            definition="校验业务表中的编码名称与数据字典登记名称一致。",
            sql="SELECT t.* FROM {{ table_name }} t JOIN {{ dictionary_table }} d ON t.{{ code_column }}=d.{{ dict_code_column }} WHERE t.{{ name_column }} <> d.{{ dict_name_column }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT t.* FROM {{ table_name }} t JOIN {{ dictionary_table }} d ON t.{{ code_column }}=d.{{ dict_code_column }} WHERE t.{{ name_column }} <> d.{{ dict_name_column }}")',
            etl='{"action":"code_name_dictionary_consistency","dictionary":"{{ dictionary_table }}","code":"{{ code_column }}","name":"{{ name_column }}","on_fail":"issue_table"}',
            parameters={"dictionary_table": "dim_dictionary", "code_column": "status_code", "name_column": "status_name", "dict_code_column": "dict_code", "dict_name_column": "dict_name"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="以数据字典为准修正名称，或同步更新字典版本和业务映射。",
            tags=["白皮书扩展", "码值一致性", "数据字典", "一致性"],
        ),
        _table_rule(
            rule_id="CS-W02",
            name="same_entity_cross_table_consistency",
            display_name="同一实体跨表一致性校验",
            dimension=QualityDimension.CONSISTENCY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="跨表不一致",
            definition="校验同一实体在两张业务表中的关键属性值保持一致。",
            sql="SELECT a.{{ entity_key }} FROM {{ table_name }} a JOIN {{ compare_table }} b ON a.{{ entity_key }}=b.{{ entity_key }} WHERE a.{{ compare_column }} <> b.{{ compare_column }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT a.{{ entity_key }} FROM {{ table_name }} a JOIN {{ compare_table }} b ON a.{{ entity_key }}=b.{{ entity_key }} WHERE a.{{ compare_column }} <> b.{{ compare_column }}")',
            etl='{"action":"same_entity_cross_table_compare","left":"{{ table_name }}","right":"{{ compare_table }}","key":"{{ entity_key }}","column":"{{ compare_column }}","on_fail":"issue_table"}',
            parameters={"compare_table": "${COMPARE_TABLE}", "entity_key": "id", "compare_column": "${COMPARE_COLUMN}"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="确认主数据权威来源，以权威表重新同步差异字段。",
            tags=["白皮书扩展", "跨表一致性", "实体属性", "一致性"],
        ),
        _table_rule(
            rule_id="CS-W03",
            name="fact_dimension_status_consistency",
            display_name="事实维表状态一致性校验",
            dimension=QualityDimension.CONSISTENCY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="关联数据不一致",
            definition="校验事实表引用的维度对象状态与维表状态一致，例如客户、机构、产品状态。",
            sql="SELECT f.* FROM {{ table_name }} f JOIN {{ dimension_table }} d ON f.{{ dimension_key }}=d.{{ dimension_key }} WHERE f.{{ fact_status_column }} <> d.{{ dimension_status_column }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT f.* FROM {{ table_name }} f JOIN {{ dimension_table }} d ON f.{{ dimension_key }}=d.{{ dimension_key }} WHERE f.{{ fact_status_column }} <> d.{{ dimension_status_column }}")',
            etl='{"action":"fact_dimension_status_consistency","dimension":"{{ dimension_table }}","key":"{{ dimension_key }}","on_fail":"issue_table"}',
            parameters={"dimension_table": "dim_customer", "dimension_key": "customer_id", "fact_status_column": "customer_status", "dimension_status_column": "status"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="核查事实表宽表冗余字段刷新逻辑，按最新维表状态重算。",
            tags=["白皮书扩展", "事实维表", "状态一致性", "一致性"],
        ),
        _table_rule(
            rule_id="CS-W04",
            name="master_detail_sum_consistency",
            display_name="主明细金额汇总一致性校验",
            dimension=QualityDimension.CONSISTENCY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="数值逻辑错误",
            definition="校验明细金额汇总值与主表总金额一致。",
            sql="SELECT m.* FROM {{ master_table }} m JOIN (SELECT {{ foreign_key }}, SUM({{ detail_amount_column }}) AS detail_sum FROM {{ detail_table }} GROUP BY {{ foreign_key }}) d ON m.{{ master_key }}=d.{{ foreign_key }} WHERE ABS(m.{{ master_amount_column }} - d.detail_sum) > {{ tolerance_amount }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT m.* FROM {{ master_table }} m JOIN (SELECT {{ foreign_key }}, SUM({{ detail_amount_column }}) AS detail_sum FROM {{ detail_table }} GROUP BY {{ foreign_key }}) d ON m.{{ master_key }}=d.{{ foreign_key }} WHERE ABS(m.{{ master_amount_column }} - d.detail_sum) > {{ tolerance_amount }}")',
            etl='{"action":"master_detail_sum_consistency","master":"{{ master_table }}","detail":"{{ detail_table }}","tolerance":{{ tolerance_amount }},"on_fail":"issue_table"}',
            parameters={"master_table": "${MASTER_TABLE}", "detail_table": "${DETAIL_TABLE}", "master_key": "id", "foreign_key": "master_id", "master_amount_column": "total_amount", "detail_amount_column": "amount", "tolerance_amount": "0.01"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="重新汇总明细金额，排查明细漏传、重复或主表计算逻辑错误。",
            tags=["白皮书扩展", "主明细", "金额汇总", "一致性"],
        ),
        _table_rule(
            rule_id="CS-W05",
            name="master_detail_count_consistency",
            display_name="主明细数量一致性校验",
            dimension=QualityDimension.CONSISTENCY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="数值逻辑错误",
            definition="校验明细记录数量与主表记录数量字段一致。",
            sql="SELECT m.* FROM {{ master_table }} m JOIN (SELECT {{ foreign_key }}, COUNT(*) AS detail_count FROM {{ detail_table }} GROUP BY {{ foreign_key }}) d ON m.{{ master_key }}=d.{{ foreign_key }} WHERE m.{{ master_count_column }} <> d.detail_count",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT m.* FROM {{ master_table }} m JOIN (SELECT {{ foreign_key }}, COUNT(*) AS detail_count FROM {{ detail_table }} GROUP BY {{ foreign_key }}) d ON m.{{ master_key }}=d.{{ foreign_key }} WHERE m.{{ master_count_column }} <> d.detail_count")',
            etl='{"action":"master_detail_count_consistency","master":"{{ master_table }}","detail":"{{ detail_table }}","on_fail":"issue_table"}',
            parameters={"master_table": "${MASTER_TABLE}", "detail_table": "${DETAIL_TABLE}", "master_key": "id", "foreign_key": "master_id", "master_count_column": "detail_count"},
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="重新计算主表明细数量，排查明细数据同步完整性。",
            tags=["白皮书扩展", "主明细", "数量一致性", "一致性"],
        ),
        _table_rule(
            rule_id="CS-W06",
            name="dictionary_version_consistency",
            display_name="字典版本一致性校验",
            dimension=QualityDimension.CONSISTENCY,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="跨系统不一致",
            definition="校验业务表使用的数据字典版本与当前生效版本一致。",
            sql="SELECT t.* FROM {{ table_name }} t JOIN {{ dictionary_version_table }} v ON t.{{ dict_type_column }}=v.{{ dict_type_column }} WHERE t.{{ dict_version_column }} <> v.{{ active_version_column }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT t.* FROM {{ table_name }} t JOIN {{ dictionary_version_table }} v ON t.{{ dict_type_column }}=v.{{ dict_type_column }} WHERE t.{{ dict_version_column }} <> v.{{ active_version_column }}")',
            etl='{"action":"dictionary_version_consistency","version_table":"{{ dictionary_version_table }}","on_fail":"metadata_ticket"}',
            parameters={"dictionary_version_table": "dict_version", "dict_type_column": "dict_type", "dict_version_column": "dict_version", "active_version_column": "active_version"},
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P2_MONITORING,
            remediation="同步最新字典版本，重算受影响的码值解释字段。",
            tags=["白皮书扩展", "字典版本", "一致性"],
        ),
        _table_rule(
            rule_id="CS-W07",
            name="organization_hierarchy_consistency",
            display_name="组织层级一致性校验",
            dimension=QualityDimension.CONSISTENCY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="关联数据不一致",
            definition="校验组织编码与上级组织编码在组织主数据层级关系中一致。",
            sql="SELECT t.* FROM {{ table_name }} t JOIN {{ org_table }} o ON t.{{ org_code_column }}=o.{{ org_code_column }} WHERE t.{{ parent_org_code_column }} <> o.{{ parent_org_code_column }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT t.* FROM {{ table_name }} t JOIN {{ org_table }} o ON t.{{ org_code_column }}=o.{{ org_code_column }} WHERE t.{{ parent_org_code_column }} <> o.{{ parent_org_code_column }}")',
            etl='{"action":"organization_hierarchy_consistency","org_table":"{{ org_table }}","on_fail":"issue_table"}',
            parameters={"org_table": "dim_org", "org_code_column": "org_code", "parent_org_code_column": "parent_org_code"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="以组织主数据为准修正上级组织，排查组织变更同步延迟。",
            tags=["白皮书扩展", "组织层级", "主数据", "一致性"],
        ),
        _table_rule(
            rule_id="CS-W08",
            name="unit_conversion_consistency",
            display_name="计量单位换算一致性校验",
            dimension=QualityDimension.CONSISTENCY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="数值逻辑错误",
            definition="校验原始数量按换算系数转换后的标准数量与标准数量字段一致。",
            sql="SELECT * FROM {{ table_name }} WHERE ABS({{ source_quantity_column }} * {{ conversion_rate_column }} - {{ standard_quantity_column }}) > {{ tolerance_value }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ table_name }} WHERE ABS({{ source_quantity_column }} * {{ conversion_rate_column }} - {{ standard_quantity_column }}) > {{ tolerance_value }}")',
            etl='{"action":"unit_conversion_consistency","source_qty":"{{ source_quantity_column }}","rate":"{{ conversion_rate_column }}","standard_qty":"{{ standard_quantity_column }}","on_fail":"issue_table"}',
            parameters={"source_quantity_column": "quantity", "conversion_rate_column": "conversion_rate", "standard_quantity_column": "standard_quantity", "tolerance_value": "0.0001"},
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="统一计量单位换算规则，修正换算系数或标准数量字段。",
            tags=["白皮书扩展", "计量单位", "换算", "一致性"],
        ),
        _table_rule(
            rule_id="CS-W09",
            name="cross_system_key_mapping_consistency",
            display_name="跨系统主键映射一致性校验",
            dimension=QualityDimension.CONSISTENCY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="跨系统不一致",
            definition="校验跨系统主键映射表中同一源主键只映射到一个目标主键。",
            sql="SELECT {{ source_system_column }}, {{ source_key_column }}, COUNT(DISTINCT {{ target_key_column }}) AS target_count FROM {{ mapping_table }} GROUP BY {{ source_system_column }}, {{ source_key_column }} HAVING COUNT(DISTINCT {{ target_key_column }}) > 1",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT {{ source_system_column }}, {{ source_key_column }}, COUNT(DISTINCT {{ target_key_column }}) AS target_count FROM {{ mapping_table }} GROUP BY {{ source_system_column }}, {{ source_key_column }} HAVING COUNT(DISTINCT {{ target_key_column }}) > 1")',
            etl='{"action":"cross_system_key_mapping_consistency","mapping_table":"{{ mapping_table }}","on_fail":"issue_table"}',
            parameters={"mapping_table": "id_mapping", "source_system_column": "source_system", "source_key_column": "source_id", "target_key_column": "target_id"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="清理重复映射关系，按主数据ID合并跨系统实体。",
            tags=["白皮书扩展", "跨系统", "主键映射", "一致性"],
        ),
        _table_rule(
            rule_id="CS-W10",
            name="lineage_transform_consistency",
            display_name="血缘转换结果一致性校验",
            dimension=QualityDimension.CONSISTENCY,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="跨系统不一致",
            definition="校验目标字段值与血缘登记的来源字段转换表达式结果一致。",
            sql="SELECT t.* FROM {{ target_table }} t JOIN {{ source_table }} s ON t.{{ target_key }}=s.{{ source_key }} WHERE t.{{ target_column }} <> {{ transform_expression }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT t.* FROM {{ target_table }} t JOIN {{ source_table }} s ON t.{{ target_key }}=s.{{ source_key }} WHERE t.{{ target_column }} <> {{ transform_expression }}")',
            etl='{"action":"lineage_transform_consistency","source":"{{ source_table }}","target":"{{ target_table }}","expression":"{{ transform_expression }}","on_fail":"issue_table"}',
            parameters={"source_table": "${SOURCE_TABLE}", "target_table": "${TARGET_TABLE}", "source_key": "id", "target_key": "id", "target_column": "${TARGET_COLUMN}", "transform_expression": "${TRANSFORM_EXPRESSION}"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="核查ETL转换脚本和血缘登记表达式，修正后重跑受影响数据。",
            tags=["白皮书扩展", "血缘", "转换一致性", "一致性"],
        ),
    ]


def _build_timeliness_extended_rules() -> List[RuleTemplate]:
    """时效性扩展规则。"""
    return [
        _table_rule(
            rule_id="T-W01",
            name="source_to_ods_sync_delay",
            display_name="源端到ODS同步时延校验",
            dimension=QualityDimension.TIMELINESS,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="数据不新鲜",
            definition="校验源系统产生时间到ODS入库时间的时延不超过阈值。",
            sql="SELECT * FROM {{ table_name }} WHERE TIMESTAMPDIFF(MINUTE, {{ source_time_column }}, {{ ods_load_time_column }}) > {{ max_delay_minutes }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ table_name }} WHERE TIMESTAMPDIFF(MINUTE, {{ source_time_column }}, {{ ods_load_time_column }}) > {{ max_delay_minutes }}")',
            etl='{"action":"source_to_ods_delay","source_time":"{{ source_time_column }}","load_time":"{{ ods_load_time_column }}","max_delay_minutes":{{ max_delay_minutes }},"on_fail":"alert"}',
            parameters={"source_time_column": "source_update_time", "ods_load_time_column": "ods_load_time", "max_delay_minutes": "30"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="检查采集链路、网络和源端推送任务，补采延迟数据。",
            tags=["白皮书扩展", "同步时延", "ODS", "时效性"],
        ),
        _table_rule(
            rule_id="T-W02",
            name="ods_to_dw_sync_delay",
            display_name="ODS到数仓加工时延校验",
            dimension=QualityDimension.TIMELINESS,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="数据不新鲜",
            definition="校验ODS入库到数仓加工完成的时延不超过阈值。",
            sql="SELECT * FROM {{ table_name }} WHERE TIMESTAMPDIFF(MINUTE, {{ ods_load_time_column }}, {{ dw_process_time_column }}) > {{ max_delay_minutes }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ table_name }} WHERE TIMESTAMPDIFF(MINUTE, {{ ods_load_time_column }}, {{ dw_process_time_column }}) > {{ max_delay_minutes }}")',
            etl='{"action":"ods_to_dw_delay","ods_time":"{{ ods_load_time_column }}","dw_time":"{{ dw_process_time_column }}","max_delay_minutes":{{ max_delay_minutes }},"on_fail":"alert"}',
            parameters={"ods_load_time_column": "ods_load_time", "dw_process_time_column": "dw_process_time", "max_delay_minutes": "120"},
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P2_MONITORING,
            remediation="优化数仓调度依赖、计算资源和重试策略，必要时补跑任务。",
            tags=["白皮书扩展", "加工时延", "数仓", "时效性"],
        ),
        _table_rule(
            rule_id="T-W03",
            name="partition_arrival_deadline",
            display_name="分区到达时点校验",
            dimension=QualityDimension.TIMELINESS,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="数据不新鲜",
            definition="校验业务日期分区在规定截止时间前到达。",
            sql="SELECT * FROM {{ table_name }} WHERE {{ partition_column }}='{{ partition_value }}' AND {{ arrival_time_column }} > '{{ deadline_time }}'",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ table_name }} WHERE {{ partition_column }}=\'{{ partition_value }}\' AND {{ arrival_time_column }} > \'{{ deadline_time }}\'")',
            etl='{"action":"partition_arrival_deadline","partition":"{{ partition_value }}","deadline":"{{ deadline_time }}","on_fail":"alert"}',
            parameters={"partition_column": "biz_date", "partition_value": "${BIZ_DATE}", "arrival_time_column": "arrival_time", "deadline_time": "${DEADLINE_TIME}"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="检查上游供数和分区发布任务，超时分区补跑并通知责任人。",
            tags=["白皮书扩展", "分区到达", "截止时间", "时效性"],
        ),
        _table_rule(
            rule_id="T-W04",
            name="report_publish_deadline",
            display_name="报表发布时间校验",
            dimension=QualityDimension.TIMELINESS,
            source_type=RuleSourceType.BUSINESS,
            problem_category="响应时效不达标",
            definition="校验报表或指标结果在业务约定时间前发布。",
            sql="SELECT * FROM {{ table_name }} WHERE {{ report_date_column }}='{{ report_date }}' AND {{ publish_time_column }} > '{{ publish_deadline }}'",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ table_name }} WHERE {{ report_date_column }}=\'{{ report_date }}\' AND {{ publish_time_column }} > \'{{ publish_deadline }}\'")',
            etl='{"action":"report_publish_deadline","report_date":"{{ report_date }}","deadline":"{{ publish_deadline }}","on_fail":"business_alert"}',
            parameters={"report_date_column": "report_date", "report_date": "${REPORT_DATE}", "publish_time_column": "publish_time", "publish_deadline": "${PUBLISH_DEADLINE}"},
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="排查指标加工、审核发布和权限同步耗时，补发延迟报表。",
            tags=["白皮书扩展", "报表发布", "时效性"],
        ),
        _table_rule(
            rule_id="T-W05",
            name="api_cache_freshness",
            display_name="API缓存新鲜度校验",
            dimension=QualityDimension.TIMELINESS,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="数据不新鲜",
            definition="校验数据服务API缓存更新时间不超过约定时长。",
            sql="SELECT * FROM {{ api_cache_table }} WHERE api_name='{{ api_name }}' AND last_refresh_time < DATE_SUB(NOW(), INTERVAL {{ max_cache_minutes }} MINUTE)",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ api_cache_table }} WHERE api_name=\'{{ api_name }}\' AND last_refresh_time < DATE_SUB(NOW(), INTERVAL {{ max_cache_minutes }} MINUTE)")',
            etl='{"action":"api_cache_freshness","api_name":"{{ api_name }}","max_cache_minutes":{{ max_cache_minutes }},"on_fail":"ops_ticket"}',
            parameters={"api_cache_table": "api_cache_status", "api_name": "${API_NAME}", "max_cache_minutes": "15"},
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P2_MONITORING,
            remediation="刷新API缓存，检查缓存调度和依赖数据更新时间。",
            tags=["白皮书扩展", "API缓存", "新鲜度", "时效性"],
        ),
        _table_rule(
            rule_id="T-W06",
            name="incremental_watermark_continuity",
            display_name="增量水位连续性校验",
            dimension=QualityDimension.TIMELINESS,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="数据不新鲜",
            definition="校验增量采集水位连续推进，避免跳水位或长时间不更新。",
            sql="SELECT * FROM {{ watermark_table }} WHERE {{ current_watermark_column }} <= {{ last_watermark_column }} OR TIMESTAMPDIFF(MINUTE, {{ update_time_column }}, NOW()) > {{ max_idle_minutes }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ watermark_table }} WHERE {{ current_watermark_column }} <= {{ last_watermark_column }} OR TIMESTAMPDIFF(MINUTE, {{ update_time_column }}, NOW()) > {{ max_idle_minutes }}")',
            etl='{"action":"watermark_continuity","watermark_table":"{{ watermark_table }}","max_idle_minutes":{{ max_idle_minutes }},"on_fail":"alert"}',
            parameters={"watermark_table": "etl_watermark", "current_watermark_column": "current_watermark", "last_watermark_column": "last_watermark", "update_time_column": "update_time", "max_idle_minutes": "60"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="检查增量抽取条件和水位提交逻辑，必要时从上次成功水位重跑。",
            tags=["白皮书扩展", "增量水位", "时效性"],
        ),
        _table_rule(
            rule_id="T-W07",
            name="event_arrival_latency",
            display_name="事件到达延迟校验",
            dimension=QualityDimension.TIMELINESS,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="数据不新鲜",
            definition="校验事件发生时间到平台接收时间的延迟不超过阈值。",
            sql="SELECT * FROM {{ table_name }} WHERE TIMESTAMPDIFF(SECOND, {{ event_time_column }}, {{ receive_time_column }}) > {{ max_latency_seconds }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ table_name }} WHERE TIMESTAMPDIFF(SECOND, {{ event_time_column }}, {{ receive_time_column }}) > {{ max_latency_seconds }}")',
            etl='{"action":"event_arrival_latency","event_time":"{{ event_time_column }}","receive_time":"{{ receive_time_column }}","max_latency_seconds":{{ max_latency_seconds }},"on_fail":"alert"}',
            parameters={"event_time_column": "event_time", "receive_time_column": "receive_time", "max_latency_seconds": "300"},
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="检查消息队列积压、网络链路和消费者处理能力。",
            tags=["白皮书扩展", "事件延迟", "实时数据", "时效性"],
        ),
        _table_rule(
            rule_id="T-W08",
            name="history_validity_period",
            display_name="历史有效期时效校验",
            dimension=QualityDimension.TIMELINESS,
            source_type=RuleSourceType.BUSINESS,
            problem_category="时间逻辑错误",
            definition="校验历史拉链或有效期数据满足生效时间早于失效时间，且当前有效记录未过期。",
            sql="SELECT * FROM {{ table_name }} WHERE {{ valid_from_column }} > {{ valid_to_column }} OR ({{ current_flag_column }}='Y' AND {{ valid_to_column }} < CURRENT_DATE)",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ table_name }} WHERE {{ valid_from_column }} > {{ valid_to_column }} OR ({{ current_flag_column }}=\'Y\' AND {{ valid_to_column }} < CURRENT_DATE)")',
            etl='{"action":"history_validity_period","valid_from":"{{ valid_from_column }}","valid_to":"{{ valid_to_column }}","current_flag":"{{ current_flag_column }}","on_fail":"issue_table"}',
            parameters={"valid_from_column": "valid_from", "valid_to_column": "valid_to", "current_flag_column": "is_current"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="修正拉链表有效期边界，重新生成当前有效标识。",
            tags=["白皮书扩展", "历史有效期", "拉链表", "时效性"],
        ),
        _table_rule(
            rule_id="T-W09",
            name="scheduler_retry_timeliness",
            display_name="调度重试时效校验",
            dimension=QualityDimension.TIMELINESS,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="响应时效不达标",
            definition="校验失败任务在规定时间内完成重试或人工处置。",
            sql="SELECT * FROM {{ scheduler_log_table }} WHERE status='FAILED' AND retry_count < {{ min_retry_count }} AND TIMESTAMPDIFF(MINUTE, end_time, NOW()) > {{ max_handle_minutes }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ scheduler_log_table }} WHERE status=\'FAILED\' AND retry_count < {{ min_retry_count }} AND TIMESTAMPDIFF(MINUTE, end_time, NOW()) > {{ max_handle_minutes }}")',
            etl='{"action":"scheduler_retry_timeliness","log_table":"{{ scheduler_log_table }}","max_handle_minutes":{{ max_handle_minutes }},"on_fail":"ops_ticket"}',
            parameters={"scheduler_log_table": "scheduler_task_log", "min_retry_count": "1", "max_handle_minutes": "30"},
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P2_MONITORING,
            remediation="检查自动重试策略和告警值班响应，及时补跑失败任务。",
            tags=["白皮书扩展", "调度重试", "时效性"],
        ),
        _table_rule(
            rule_id="T-W10",
            name="metadata_update_timeliness",
            display_name="元数据更新时效校验",
            dimension=QualityDimension.TIMELINESS,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="数据不新鲜",
            definition="校验表结构、字段说明、血缘等元数据在变更后及时更新。",
            sql="SELECT * FROM {{ metadata_change_table }} WHERE change_time IS NOT NULL AND (metadata_update_time IS NULL OR TIMESTAMPDIFF(HOUR, change_time, metadata_update_time) > {{ max_update_hours }})",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ metadata_change_table }} WHERE change_time IS NOT NULL AND (metadata_update_time IS NULL OR TIMESTAMPDIFF(HOUR, change_time, metadata_update_time) > {{ max_update_hours }})")',
            etl='{"action":"metadata_update_timeliness","change_table":"{{ metadata_change_table }}","max_update_hours":{{ max_update_hours }},"on_fail":"metadata_ticket"}',
            parameters={"metadata_change_table": "metadata_change_log", "max_update_hours": "24"},
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P2_MONITORING,
            remediation="补采元数据变更，完善元数据采集调度和变更监听机制。",
            tags=["白皮书扩展", "元数据", "时效性"],
        ),
    ]


def _build_accessibility_extended_rules() -> List[RuleTemplate]:
    """可访问性扩展规则。"""
    return [
        _table_rule(
            rule_id="AC-W01",
            name="data_service_availability_sla",
            display_name="数据服务可用率校验",
            dimension=QualityDimension.ACCESSIBILITY,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="访问不可达",
            definition="校验数据服务在统计窗口内可用率达到SLA阈值。",
            sql="SELECT service_name, AVG(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) AS availability_rate FROM {{ service_monitor_table }} WHERE service_name='{{ service_name }}' AND monitor_time >= DATE_SUB(NOW(), INTERVAL {{ window_hours }} HOUR) GROUP BY service_name HAVING availability_rate < {{ min_availability_rate }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT service_name, AVG(CASE WHEN status=\'SUCCESS\' THEN 1 ELSE 0 END) AS availability_rate FROM {{ service_monitor_table }} WHERE service_name=\'{{ service_name }}\' AND monitor_time >= DATE_SUB(NOW(), INTERVAL {{ window_hours }} HOUR) GROUP BY service_name HAVING availability_rate < {{ min_availability_rate }}")',
            etl='{"action":"service_availability_sla","service":"{{ service_name }}","window_hours":{{ window_hours }},"min_rate":{{ min_availability_rate }},"on_fail":"ops_ticket"}',
            parameters={"service_monitor_table": "service_monitor_log", "service_name": "${SERVICE_NAME}", "window_hours": "24", "min_availability_rate": "0.99"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="检查服务实例、网关和依赖组件，恢复后复核SLA达标情况。",
            tags=["白皮书扩展", "可用率", "SLA", "可访问性"],
        ),
        _table_rule(
            rule_id="AC-W02",
            name="least_privilege_permission",
            display_name="最小权限访问校验",
            dimension=QualityDimension.ACCESSIBILITY,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="访问权限不达标",
            definition="校验授权角色不存在超出白名单的敏感权限。",
            sql="SELECT * FROM {{ permission_table }} WHERE object_name='{{ table_name }}' AND privilege_type NOT IN ({{ allowed_privileges }})",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ permission_table }} WHERE object_name=\'{{ table_name }}\' AND privilege_type NOT IN ({{ allowed_privileges }})")',
            etl='{"action":"least_privilege_permission","permission_table":"{{ permission_table }}","object":"{{ table_name }}","allowed":[{{ allowed_privileges }}],"on_fail":"security_ticket"}',
            parameters={"permission_table": "data_permission", "allowed_privileges": "'SELECT'"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="收回越权权限，按岗位和数据分级重新授权并留存审批记录。",
            tags=["白皮书扩展", "权限", "最小权限", "可访问性"],
        ),
        _table_rule(
            rule_id="AC-W03",
            name="sensitive_field_masking_available",
            display_name="敏感字段脱敏可访问校验",
            dimension=QualityDimension.ACCESSIBILITY,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="访问权限不达标",
            definition="校验敏感字段对普通访问角色仅开放脱敏结果，不直接暴露明文。",
            sql="SELECT * FROM {{ access_audit_table }} WHERE table_name='{{ table_name }}' AND column_name='{{ sensitive_column }}' AND role_name='{{ role_name }}' AND masking_enabled <> 'Y'",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ access_audit_table }} WHERE table_name=\'{{ table_name }}\' AND column_name=\'{{ sensitive_column }}\' AND role_name=\'{{ role_name }}\' AND masking_enabled <> \'Y\'")',
            etl='{"action":"sensitive_masking_check","audit_table":"{{ access_audit_table }}","column":"{{ sensitive_column }}","role":"{{ role_name }}","on_fail":"security_ticket"}',
            parameters={"access_audit_table": "access_policy_audit", "sensitive_column": "${SENSITIVE_COLUMN}", "role_name": "general_user"},
            severity=RuleSeverity.CRITICAL,
            validation_level=RuleValidationLevel.P0_BLOCKING,
            remediation="立即启用脱敏策略或收回访问权限，敏感访问需补充审批和审计。",
            tags=["白皮书扩展", "脱敏", "敏感数据", "可访问性"],
        ),
        _table_rule(
            rule_id="AC-W04",
            name="catalog_searchable",
            display_name="数据目录可检索校验",
            dimension=QualityDimension.ACCESSIBILITY,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="访问不可达",
            definition="校验数据表已发布到数据目录并可被授权用户检索。",
            sql="SELECT '{{ table_name }}' AS table_name WHERE NOT EXISTS (SELECT 1 FROM {{ catalog_table }} WHERE table_name='{{ table_name }}' AND searchable='Y')",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT \'{{ table_name }}\' AS table_name WHERE NOT EXISTS (SELECT 1 FROM {{ catalog_table }} WHERE table_name=\'{{ table_name }}\' AND searchable=\'Y\')")',
            etl='{"action":"catalog_searchable","catalog_table":"{{ catalog_table }}","table":"{{ table_name }}","on_fail":"metadata_ticket"}',
            parameters={"catalog_table": "data_catalog"},
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P2_MONITORING,
            remediation="补充目录发布信息、标签和授权范围，刷新检索索引。",
            tags=["白皮书扩展", "数据目录", "可检索", "可访问性"],
        ),
        _table_rule(
            rule_id="AC-W05",
            name="metadata_description_understandable",
            display_name="元数据说明可理解性校验",
            dimension=QualityDimension.ACCESSIBILITY,
            source_type=RuleSourceType.STANDARD,
            problem_category="访问不可达",
            definition="校验表和字段具备业务说明，便于用户理解和正确使用数据。",
            sql="SELECT column_name FROM information_schema.columns WHERE table_name='{{ table_name }}' AND (column_comment IS NULL OR TRIM(column_comment)='' OR CHAR_LENGTH(column_comment) < {{ min_comment_length }})",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT column_name FROM information_schema.columns WHERE table_name=\'{{ table_name }}\' AND (column_comment IS NULL OR TRIM(column_comment)=\'\' OR CHAR_LENGTH(column_comment) < {{ min_comment_length }})")',
            etl='{"action":"metadata_description_check","table":"{{ table_name }}","min_comment_length":{{ min_comment_length }},"on_fail":"metadata_ticket"}',
            parameters={"min_comment_length": "4"},
            severity=RuleSeverity.LOW,
            validation_level=RuleValidationLevel.P2_MONITORING,
            remediation="补齐字段中文名、业务含义、统计口径和使用说明。",
            tags=["白皮书扩展", "元数据说明", "可理解性", "可访问性"],
        ),
        _table_rule(
            rule_id="AC-W06",
            name="data_owner_reachable",
            display_name="数据责任人可联系校验",
            dimension=QualityDimension.ACCESSIBILITY,
            source_type=RuleSourceType.BUSINESS,
            problem_category="访问不可达",
            definition="校验数据资产登记了有效责任人和联系方式，支持问题流转和申请授权。",
            sql="SELECT * FROM {{ asset_owner_table }} WHERE table_name='{{ table_name }}' AND (owner_name IS NULL OR owner_contact IS NULL OR owner_status <> 'ACTIVE')",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ asset_owner_table }} WHERE table_name=\'{{ table_name }}\' AND (owner_name IS NULL OR owner_contact IS NULL OR owner_status <> \'ACTIVE\')")',
            etl='{"action":"data_owner_reachable","owner_table":"{{ asset_owner_table }}","table":"{{ table_name }}","on_fail":"metadata_ticket"}',
            parameters={"asset_owner_table": "data_asset_owner"},
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="补齐数据责任人、运维责任人和联系方式，离职或转岗责任人需及时变更。",
            tags=["白皮书扩展", "责任人", "可访问性"],
        ),
        _table_rule(
            rule_id="AC-W07",
            name="query_success_rate",
            display_name="查询成功率校验",
            dimension=QualityDimension.ACCESSIBILITY,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="响应时效不达标",
            definition="校验数据查询在统计窗口内成功率达到阈值。",
            sql="SELECT object_name, AVG(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) AS success_rate FROM {{ query_log_table }} WHERE object_name='{{ table_name }}' AND query_time >= DATE_SUB(NOW(), INTERVAL {{ window_hours }} HOUR) GROUP BY object_name HAVING success_rate < {{ min_success_rate }}",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT object_name, AVG(CASE WHEN status=\'SUCCESS\' THEN 1 ELSE 0 END) AS success_rate FROM {{ query_log_table }} WHERE object_name=\'{{ table_name }}\' AND query_time >= DATE_SUB(NOW(), INTERVAL {{ window_hours }} HOUR) GROUP BY object_name HAVING success_rate < {{ min_success_rate }}")',
            etl='{"action":"query_success_rate","query_log_table":"{{ query_log_table }}","table":"{{ table_name }}","min_rate":{{ min_success_rate }},"on_fail":"ops_ticket"}',
            parameters={"query_log_table": "query_access_log", "window_hours": "24", "min_success_rate": "0.98"},
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P2_MONITORING,
            remediation="分析查询失败原因，修复权限、资源、SQL兼容性或服务稳定性问题。",
            tags=["白皮书扩展", "查询成功率", "可访问性"],
        ),
        _table_rule(
            rule_id="AC-W08",
            name="index_statistics_available",
            display_name="索引统计信息可用校验",
            dimension=QualityDimension.ACCESSIBILITY,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="响应时效不达标",
            definition="校验大表存在可用索引或统计信息，以保障访问性能。",
            sql="SELECT '{{ table_name }}' AS table_name WHERE {{ table_row_count }} >= {{ large_table_threshold }} AND NOT EXISTS (SELECT 1 FROM {{ index_metadata_table }} WHERE table_name='{{ table_name }}' AND status='VALID')",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT \'{{ table_name }}\' AS table_name WHERE {{ table_row_count }} >= {{ large_table_threshold }} AND NOT EXISTS (SELECT 1 FROM {{ index_metadata_table }} WHERE table_name=\'{{ table_name }}\' AND status=\'VALID\')")',
            etl='{"action":"index_statistics_available","index_table":"{{ index_metadata_table }}","large_table_threshold":{{ large_table_threshold }},"on_fail":"performance_ticket"}',
            parameters={"table_row_count": "0", "large_table_threshold": "1000000", "index_metadata_table": "index_metadata"},
            severity=RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P2_MONITORING,
            remediation="为高频过滤字段补充索引或刷新统计信息，必要时优化分区策略。",
            tags=["白皮书扩展", "索引", "性能", "可访问性"],
        ),
        _table_rule(
            rule_id="AC-W09",
            name="backup_restore_available",
            display_name="备份恢复可用性校验",
            dimension=QualityDimension.ACCESSIBILITY,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="访问不可达",
            definition="校验关键数据表具备最近成功备份且恢复演练状态有效。",
            sql="SELECT * FROM {{ backup_status_table }} WHERE table_name='{{ table_name }}' AND (last_backup_time < DATE_SUB(NOW(), INTERVAL {{ max_backup_hours }} HOUR) OR restore_test_status <> 'SUCCESS')",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT * FROM {{ backup_status_table }} WHERE table_name=\'{{ table_name }}\' AND (last_backup_time < DATE_SUB(NOW(), INTERVAL {{ max_backup_hours }} HOUR) OR restore_test_status <> \'SUCCESS\')")',
            etl='{"action":"backup_restore_available","backup_table":"{{ backup_status_table }}","max_backup_hours":{{ max_backup_hours }},"on_fail":"ops_ticket"}',
            parameters={"backup_status_table": "backup_status", "max_backup_hours": "24"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="补跑备份任务并完成恢复演练，关键表需纳入容灾巡检。",
            tags=["白皮书扩展", "备份恢复", "可用性", "可访问性"],
        ),
        _table_rule(
            rule_id="AC-W10",
            name="access_audit_log_available",
            display_name="访问审计日志可用校验",
            dimension=QualityDimension.ACCESSIBILITY,
            source_type=RuleSourceType.TECHNICAL,
            problem_category="访问权限不达标",
            definition="校验数据访问行为已记录审计日志，便于追踪访问和响应安全要求。",
            sql="SELECT '{{ table_name }}' AS table_name WHERE NOT EXISTS (SELECT 1 FROM {{ access_audit_table }} WHERE object_name='{{ table_name }}' AND access_time >= DATE_SUB(NOW(), INTERVAL {{ window_hours }} HOUR))",
            ge='ge_df.expect_query_to_return_no_rows(query="SELECT \'{{ table_name }}\' AS table_name WHERE NOT EXISTS (SELECT 1 FROM {{ access_audit_table }} WHERE object_name=\'{{ table_name }}\' AND access_time >= DATE_SUB(NOW(), INTERVAL {{ window_hours }} HOUR))")',
            etl='{"action":"access_audit_log_available","audit_table":"{{ access_audit_table }}","table":"{{ table_name }}","window_hours":{{ window_hours }},"on_fail":"security_ticket"}',
            parameters={"access_audit_table": "access_audit_log", "window_hours": "24"},
            severity=RuleSeverity.HIGH,
            validation_level=RuleValidationLevel.P1_WARNING,
            remediation="修复审计日志采集链路，访问控制策略需强制开启审计记录。",
            tags=["白皮书扩展", "访问审计", "安全", "可访问性"],
        ),
    ]


def _column_regex_rule(
    rule_id: str,
    name: str,
    display_name: str,
    regex: str,
    patterns: List[str],
    definition: str,
    problem_category: str,
    severity: RuleSeverity,
    remediation: str,
    tags: List[str],
) -> RuleTemplate:
    return _column_rule(
        rule_id=rule_id,
        name=name,
        display_name=display_name,
        dimension=QualityDimension.NORMATIVITY,
        source_type=RuleSourceType.STANDARD,
        problem_category=problem_category,
        definition=definition,
        test_definition="columnValuesToMatchRegex",
        parameters={"regex": regex},
        sql="SELECT * FROM {{ table_name }} WHERE {{ column_name }} IS NOT NULL AND {{ column_name }} NOT REGEXP '{{ regex }}'",
        ge='ge_df.expect_column_values_to_match_regex(column="{{ column_name }}", regex=r"{{ regex }}", mostly={{ pass_rate }})',
        etl='{"action":"regex_check","column":"{{ column_name }}","regex":"{{ regex }}","on_fail":"issue_table"}',
        patterns=patterns,
        severity=severity,
        validation_level=RuleValidationLevel.P1_WARNING,
        remediation=remediation,
        tags=tags,
    )


def _column_rule(
    rule_id: str,
    name: str,
    display_name: str,
    dimension: QualityDimension,
    source_type: RuleSourceType,
    problem_category: str,
    definition: str,
    test_definition: str,
    parameters: Dict[str, Any],
    sql: str,
    ge: str,
    etl: str,
    patterns: List[str],
    severity: RuleSeverity,
    validation_level: RuleValidationLevel,
    remediation: str,
    tags: List[str],
) -> RuleTemplate:
    return RuleTemplate(
        rule_id=rule_id,
        name=name,
        display_name=display_name,
        dimension=dimension,
        source_type=source_type,
        problem_category=problem_category,
        core_definition=definition,
        applicability=RuleApplicability(
            entity_type=RuleEntityType.COLUMN,
            data_types=["STRING", "NUMBER", "DATE", "DATETIME", "ANY"],
            column_name_patterns=patterns,
        ),
        scripts={
            RuleExecutionEngine.SQL: RuleScript(
                engine=RuleExecutionEngine.SQL,
                expression=sql,
                language="SQL",
                description="返回不符合规则的数据行。",
            ),
            RuleExecutionEngine.GE: RuleScript(
                engine=RuleExecutionEngine.GE,
                expression=ge,
                language="Python/Great Expectations",
                description="Great Expectations落地示例。",
            ),
            RuleExecutionEngine.ETL: RuleScript(
                engine=RuleExecutionEngine.ETL,
                expression=etl,
                language="JSON DSL",
                description="ETL任务可翻译的规则动作。",
            ),
        },
        test_definition_name=test_definition,
        parameters=parameters,
        threshold=RuleThreshold(
            operator="==",
            expected_value=0,
            pass_rate=1.0 if validation_level == RuleValidationLevel.P0_BLOCKING else 0.999,
            unit="failed_rows",
            description="失败记录数为0；弱校验可按pass_rate放宽。",
        ),
        validation_level=validation_level,
        severity=severity,
        responsible_role="数据标准管理员" if source_type == RuleSourceType.STANDARD else "业务数据负责人",
        remediation_suggestion=remediation,
        tags=tags,
    )


def _table_rule(
    rule_id: str,
    name: str,
    display_name: str,
    dimension: QualityDimension,
    source_type: RuleSourceType,
    problem_category: str,
    definition: str,
    sql: str,
    ge: str,
    etl: str,
    parameters: Dict[str, Any],
    severity: RuleSeverity,
    validation_level: RuleValidationLevel,
    remediation: str,
    tags: List[str],
) -> RuleTemplate:
    return RuleTemplate(
        rule_id=rule_id,
        name=name,
        display_name=display_name,
        dimension=dimension,
        source_type=source_type,
        problem_category=problem_category,
        core_definition=definition,
        applicability=RuleApplicability(entity_type=RuleEntityType.TABLE, data_types=["ANY"]),
        scripts={
            RuleExecutionEngine.SQL: RuleScript(
                engine=RuleExecutionEngine.SQL,
                expression=sql,
                language="SQL",
                description="返回不符合规则的数据行或可执行检查语句。",
            ),
            RuleExecutionEngine.GE: RuleScript(
                engine=RuleExecutionEngine.GE,
                expression=ge,
                language="Python/Great Expectations",
                description="Great Expectations落地示例。",
            ),
            RuleExecutionEngine.ETL: RuleScript(
                engine=RuleExecutionEngine.ETL,
                expression=etl,
                language="JSON DSL",
                description="ETL任务可翻译的规则动作。",
            ),
        },
        test_definition_name="tableCustomSQLQuery",
        parameters=parameters,
        threshold=RuleThreshold(
            operator="==",
            expected_value=0,
            pass_rate=1.0 if validation_level == RuleValidationLevel.P0_BLOCKING else 0.999,
            unit="failed_rows",
            description="失败记录数应为0。",
        ),
        validation_level=validation_level,
        severity=severity,
        responsible_role="平台运维负责人" if dimension == QualityDimension.ACCESSIBILITY else "业务数据负责人",
        remediation_suggestion=remediation,
        tags=tags,
    )


def _api_rule(
    rule_id: str,
    name: str,
    display_name: str,
    problem_category: str,
    definition: str,
    sql: str,
    ge: str,
    etl: str,
    parameters: Dict[str, Any],
    severity: RuleSeverity,
    validation_level: RuleValidationLevel,
    remediation: str,
    tags: List[str],
) -> RuleTemplate:
    return RuleTemplate(
        rule_id=rule_id,
        name=name,
        display_name=display_name,
        dimension=QualityDimension.ACCESSIBILITY,
        source_type=RuleSourceType.TECHNICAL,
        problem_category=problem_category,
        core_definition=definition,
        applicability=RuleApplicability(entity_type=RuleEntityType.API, data_types=["ANY"]),
        scripts={
            RuleExecutionEngine.SQL: RuleScript(
                engine=RuleExecutionEngine.SQL,
                expression=sql,
                language="SQL",
                description="基于API监控日志返回不可用或超时记录。",
            ),
            RuleExecutionEngine.GE: RuleScript(
                engine=RuleExecutionEngine.GE,
                expression=ge,
                language="Python/Great Expectations",
                description="Great Expectations落地示例。",
            ),
            RuleExecutionEngine.ETL: RuleScript(
                engine=RuleExecutionEngine.ETL,
                expression=etl,
                language="JSON DSL",
                description="API巡检或DataOps任务可翻译的规则动作。",
            ),
        },
        test_definition_name="tableCustomSQLQuery",
        parameters=parameters,
        threshold=RuleThreshold(
            operator="==",
            expected_value=0,
            pass_rate=1.0 if validation_level == RuleValidationLevel.P0_BLOCKING else 0.999,
            unit="failed_requests",
            description="失败请求数应为0。",
        ),
        validation_level=validation_level,
        severity=severity,
        responsible_role="平台运维负责人",
        remediation_suggestion=remediation,
        tags=tags,
    )


def _coerce_dimension(value: Union[str, QualityDimension]) -> QualityDimension:
    if isinstance(value, QualityDimension):
        return value
    key = str(value or "").strip()
    if not key:
        return QualityDimension.NORMATIVITY
    normalized = key.lower()
    if normalized in DIMENSION_ALIASES:
        return DIMENSION_ALIASES[normalized]
    if key in DIMENSION_ALIASES:
        return DIMENSION_ALIASES[key]
    try:
        return QualityDimension(normalized)
    except ValueError:
        return QualityDimension.NORMATIVITY


def _coerce_enum(value: Any, enum_cls: Any, default: Any) -> Any:
    if isinstance(value, enum_cls):
        return value
    if value is None:
        return default
    try:
        return enum_cls(str(value))
    except ValueError:
        try:
            return enum_cls(str(value).upper())
        except ValueError:
            return default


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _coerce_parameters(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return copy.deepcopy(raw)
    if isinstance(raw, list):
        result: Dict[str, Any] = {}
        for item in raw:
            if isinstance(item, dict) and "name" in item:
                result[str(item["name"])] = item.get("value")
        return result
    return {}


def _coerce_scripts(raw: Any, legacy_values: Dict[str, Any]) -> Dict[RuleExecutionEngine, RuleScript]:
    scripts: Dict[RuleExecutionEngine, RuleScript] = {}
    if isinstance(raw, dict):
        for engine, script_data in raw.items():
            script = RuleScript.from_dict(engine, script_data)
            scripts[script.engine] = script
    elif isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            engine = item.get("engine", RuleExecutionEngine.SQL)
            script = RuleScript.from_dict(engine, item)
            scripts[script.engine] = script

    params = _coerce_parameters(legacy_values.get("parameters", {}))
    sql_expression = params.get("sqlExpression") or legacy_values.get("sqlExpression")
    if sql_expression and RuleExecutionEngine.SQL not in scripts:
        scripts[RuleExecutionEngine.SQL] = RuleScript(
            engine=RuleExecutionEngine.SQL,
            expression=str(sql_expression)
            .replace("{table}", "{{ table_name }}")
            .replace("{column}", "{{ column_name }}"),
            language="SQL",
        )

    if not scripts:
        scripts[RuleExecutionEngine.SQL] = RuleScript(
            engine=RuleExecutionEngine.SQL,
            expression="SELECT * FROM {{ table_name }} WHERE ${RULE_CONDITION}",
            language="SQL",
            description="请补充规则条件。",
        )
    return scripts


def _flatten_rule_payload(
    payload: Union[Dict[str, Any], Sequence[Dict[str, Any]], Sequence[RuleTemplate]],
) -> Iterable[Union[Dict[str, Any], RuleTemplate]]:
    if isinstance(payload, list) or isinstance(payload, tuple):
        yield from payload
        return

    if not isinstance(payload, dict):
        return

    if "rules" in payload and isinstance(payload["rules"], list):
        yield from payload["rules"]
        return

    for dimension_key, dimension_payload in payload.items():
        if not isinstance(dimension_payload, dict) or "rules" not in dimension_payload:
            continue
        for rule in dimension_payload.get("rules") or []:
            if isinstance(rule, dict):
                normalized = dict(rule)
                normalized.setdefault("dimension", dimension_key)
                yield normalized


def _normalize_target_object(
    target_object: Optional[Union[str, Dict[str, Any]]],
) -> Dict[str, Any]:
    if target_object is None:
        return {}
    if isinstance(target_object, str):
        return {
            "table_name": target_object,
            "table": target_object,
        }

    target = dict(target_object)
    if "table" in target and "table_name" not in target:
        target["table_name"] = target["table"]
    if "column" in target and "column_name" not in target:
        target["column_name"] = target["column"]
    if "table_name" in target:
        target.setdefault("table", target["table_name"])
    if "column_name" in target:
        target.setdefault("column", target["column_name"])
    return target


def _render_template(template: str, context: Dict[str, Any]) -> str:
    rendered = template
    for key, value in context.items():
        value_text = str(value)
        rendered = re.sub(
            r"\{\{\s*" + re.escape(key) + r"\s*\}\}",
            lambda _match, replacement=value_text: replacement,
            rendered,
        )
        rendered = rendered.replace("{" + key + "}", value_text)
    return rendered


def _find_unresolved_placeholders(text: str) -> List[str]:
    placeholders = set(re.findall(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", text))
    placeholders.update(re.findall(r"\$\{([^}]+)\}", text))
    return sorted(placeholders)


def _to_parameter_values(parameters: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {"name": str(name), "value": str(value)}
        for name, value in parameters.items()
        if value is not None
    ]


def _sanitize_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_]+", "_", value).strip("_") or "target"


def _count_by(items: Iterable[Any], key_func: Any) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for item in items:
        key = str(key_func(item))
        result[key] = result.get(key, 0) + 1
    return result


def _deep_update(target: Dict[str, Any], updates: Dict[str, Any]) -> None:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value
