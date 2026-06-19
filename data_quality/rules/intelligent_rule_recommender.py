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
质量规则智能推荐引擎。

该模块在基础规则推荐器之上补充更贴近白皮书的推荐依据：
字段名、字段类型、长度、样例值、元数据说明、数据字典、业务域、
数据分类分级、值域统计和血缘关系。
"""

from __future__ import annotations

import copy
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from metadata.data_quality.dimension.evaluator import RuleSeverity
from metadata.data_quality.dimension.models import QualityDimension
from metadata.data_quality.rules.parameter_suggester import (
    ParameterSuggester,
    ParameterSuggestion,
)
from metadata.data_quality.rules.rule_library import (
    DIMENSION_ZH_NAMES,
    RuleApplicability,
    RuleEntityType,
    RuleExecutionEngine,
    RuleLibrary,
    RuleScript,
    RuleSourceType,
    RuleStatus,
    RuleTemplate,
    RuleThreshold,
    RuleValidationLevel,
    ScriptPreview,
)


SEVERITY_ORDER: Dict[RuleSeverity, int] = {
    RuleSeverity.LOW: 1,
    RuleSeverity.MEDIUM: 2,
    RuleSeverity.HIGH: 3,
    RuleSeverity.CRITICAL: 4,
}


@dataclass
class DataDictionaryEntry:
    """字段数据字典信息。"""

    name: str = ""
    display_name: str = ""
    description: str = ""
    allowed_values: List[Any] = field(default_factory=list)
    value_descriptions: Dict[str, str] = field(default_factory=dict)
    code_table: str = ""
    regex: str = ""
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    required: bool = False
    unique: bool = False


@dataclass
class FieldLineageHint:
    """字段血缘和关联关系提示。"""

    upstream_fields: List[str] = field(default_factory=list)
    downstream_fields: List[str] = field(default_factory=list)
    source_system: str = ""
    target_systems: List[str] = field(default_factory=list)
    related_table: str = ""
    related_column: str = ""
    transform_expression: str = ""
    relationship_type: str = ""

    @property
    def has_cross_system_lineage(self) -> bool:
        return bool(self.source_system and self.target_systems)


@dataclass
class FieldMetadata:
    """推荐输入的字段画像。"""

    name: str
    data_type: str = ""
    length: Optional[int] = None
    nullable: bool = True
    is_primary_key: bool = False
    is_foreign_key: bool = False
    is_unique: bool = False
    description: str = ""
    comment: str = ""
    business_domain: str = ""
    data_classification: str = ""
    security_level: str = ""
    tags: List[str] = field(default_factory=list)
    sample_values: List[Any] = field(default_factory=list)
    enum_values: List[Any] = field(default_factory=list)
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    null_ratio: Optional[float] = None
    unique_ratio: Optional[float] = None
    dictionary: Optional[DataDictionaryEntry] = None
    lineage: Optional[FieldLineageHint] = None
    related_columns: Dict[str, str] = field(default_factory=dict)

    @property
    def text_for_semantic_match(self) -> str:
        pieces = [
            self.name,
            self.description,
            self.comment,
            self.business_domain,
            self.data_classification,
            self.security_level,
            " ".join(self.tags),
        ]
        if self.dictionary:
            pieces.extend(
                [
                    self.dictionary.name,
                    self.dictionary.display_name,
                    self.dictionary.description,
                    self.dictionary.code_table,
                ]
            )
        return " ".join(p for p in pieces if p).lower()


@dataclass
class TableMetadata:
    """推荐输入的表画像。"""

    table_fqn: str
    table_name: str = ""
    columns: List[FieldMetadata] = field(default_factory=list)
    business_domain: str = ""
    data_classification: str = ""
    row_count: int = 0
    tags: List[str] = field(default_factory=list)
    lineage: Optional[FieldLineageHint] = None

    def get_column(self, name: str) -> Optional[FieldMetadata]:
        normalized = name.lower()
        for column in self.columns:
            if column.name.lower() == normalized:
                return column
        return None


@dataclass
class RecommendationEvidence:
    """推荐证据。"""

    source: str
    message: str
    weight: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IntelligentRuleRecommendation:
    """智能推荐结果。"""

    recommendation_id: str
    rule_id: str
    rule_name: str
    display_name: str
    test_definition_name: str
    dimension: QualityDimension
    entity_type: RuleEntityType
    confidence: float
    severity: RuleSeverity
    reason: str
    column_name: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    threshold: RuleThreshold = field(default_factory=RuleThreshold)
    validation_level: RuleValidationLevel = RuleValidationLevel.P1_WARNING
    responsible_role: str = "数据责任人"
    remediation_suggestion: str = "核查源数据、调整规则参数并重新执行检核。"
    issue_strategy: str = "不符合规则的数据进入问题库，并生成整改工单。"
    evidence: List[RecommendationEvidence] = field(default_factory=list)
    source_signals: List[str] = field(default_factory=list)
    script_preview: Optional[ScriptPreview] = None
    requires_confirmation: bool = True
    library_rule_id: Optional[str] = None

    @property
    def dimension_zh(self) -> str:
        return DIMENSION_ZH_NAMES.get(self.dimension, self.dimension.value)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "display_name": self.display_name,
            "test_definition_name": self.test_definition_name,
            "dimension": self.dimension.value,
            "dimension_zh": self.dimension_zh,
            "entity_type": self.entity_type.value,
            "column_name": self.column_name,
            "confidence": self.confidence,
            "severity": self.severity.value,
            "validation_level": self.validation_level.value,
            "reason": self.reason,
            "parameters": copy.deepcopy(self.parameters),
            "threshold": self.threshold.to_dict(),
            "responsible_role": self.responsible_role,
            "remediation_suggestion": self.remediation_suggestion,
            "issue_strategy": self.issue_strategy,
            "evidence": [item.to_dict() for item in self.evidence],
            "source_signals": list(self.source_signals),
            "script_preview": self.script_preview.to_dict()
            if self.script_preview
            else None,
            "requires_confirmation": self.requires_confirmation,
            "library_rule_id": self.library_rule_id,
        }


class IntelligentRuleRecommender:
    """质量规则智能推荐引擎。"""

    def __init__(
        self,
        rule_library: Optional[RuleLibrary] = None,
        parameter_suggester: Optional[ParameterSuggester] = None,
    ):
        self.rule_library = rule_library or RuleLibrary()
        self.parameter_suggester = parameter_suggester or ParameterSuggester()

    def recommend_table(
        self,
        table: TableMetadata,
        dimensions: Optional[Sequence[QualityDimension]] = None,
        min_confidence: float = 0.5,
        include_script_preview: bool = True,
        max_rules_per_column: Optional[int] = None,
    ) -> List[IntelligentRuleRecommendation]:
        """为整张表推荐质量规则。"""
        recommendations: List[IntelligentRuleRecommendation] = []
        dimension_filter = set(dimensions or [])

        recommendations.extend(
            self._recommend_table_level_rules(
                table,
                include_script_preview=include_script_preview,
            )
        )

        for column in table.columns:
            column_recs = self.recommend_column(
                table,
                column,
                include_script_preview=include_script_preview,
            )
            if dimension_filter:
                column_recs = [
                    rec for rec in column_recs if rec.dimension in dimension_filter
                ]
            column_recs = [
                rec for rec in column_recs if rec.confidence >= min_confidence
            ]
            column_recs.sort(
                key=lambda rec: (rec.confidence, SEVERITY_ORDER.get(rec.severity, 0)),
                reverse=True,
            )
            if max_rules_per_column:
                column_recs = column_recs[:max_rules_per_column]
            recommendations.extend(column_recs)

        if dimension_filter:
            recommendations = [
                rec for rec in recommendations if rec.dimension in dimension_filter
            ]
        recommendations = [
            rec for rec in recommendations if rec.confidence >= min_confidence
        ]
        return self._deduplicate_recommendations(recommendations)

    def recommend_column(
        self,
        table: TableMetadata,
        column: FieldMetadata,
        include_script_preview: bool = True,
    ) -> List[IntelligentRuleRecommendation]:
        """为单个字段推荐质量规则。"""
        semantics = self._detect_semantics(column)
        data_kind = self._classify_data_type(column.data_type)
        sample_patterns = self._detect_sample_patterns(column)
        semantics.update(sample_patterns)

        evidence = self._base_evidence(column, semantics, data_kind, sample_patterns)
        recommendations: List[IntelligentRuleRecommendation] = []

        target = {
            "table_name": table.table_name or table.table_fqn,
            "column_name": column.name,
        }

        if "phone" in semantics:
            recommendations.append(
                self._from_library(
                    "N-F02",
                    table,
                    column,
                    0.94,
                    "字段语义或样例值匹配手机号，推荐手机号格式校验。",
                    evidence,
                    target,
                    include_script_preview,
                )
            )
            recommendations.append(
                self._not_null_rule(table, column, 0.78, evidence, target, include_script_preview)
            )
            recommendations.append(
                self._unique_rule(
                    table,
                    column,
                    0.72,
                    "手机号通常作为联系标识，建议检查唯一性。",
                    evidence,
                )
            )

        if "id_card" in semantics:
            recommendations.append(
                self._from_library(
                    "N-F01",
                    table,
                    column,
                    0.95,
                    "字段语义或样例值匹配身份证号，推荐身份证号码格式校验。",
                    evidence,
                    target,
                    include_script_preview,
                )
            )
            recommendations.append(
                self._not_null_rule(table, column, 0.82, evidence, target, include_script_preview)
            )
            recommendations.append(
                self._unique_rule(
                    table,
                    column,
                    0.80,
                    "身份证号通常为自然人唯一标识，建议检查唯一性。",
                    evidence,
                )
            )
            recommendations.extend(
                self._id_card_related_rules(table, column, evidence)
            )

        if "email" in semantics:
            recommendations.append(
                self._adhoc_column_rule(
                    table=table,
                    column=column,
                    rule_id="AUTO-EMAIL-FORMAT",
                    display_name="邮箱格式校验",
                    test_definition_name="columnValuesToMatchRegex",
                    dimension=QualityDimension.NORMATIVITY,
                    severity=RuleSeverity.MEDIUM,
                    confidence=0.90,
                    reason="字段语义或样例值匹配邮箱，推荐邮箱格式正则校验。",
                    parameters={
                        "regex": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
                    },
                    evidence=evidence,
                    script_expression=(
                        "SELECT * FROM {{ table_name }} WHERE {{ column_name }} IS NOT NULL "
                        "AND {{ column_name }} NOT REGEXP '{{ regex }}'"
                    ),
                    target=target,
                    include_script_preview=include_script_preview,
                )
            )

        if "code" in semantics:
            recommendations.append(
                self._from_library(
                    "N-C01",
                    table,
                    column,
                    0.84,
                    "字段语义匹配编码类字段，推荐编码规范性校验。",
                    evidence,
                    target,
                    include_script_preview,
                )
            )

        if "date" in semantics or data_kind in {"date", "datetime"}:
            recommendations.append(
                self._adhoc_column_rule(
                    table=table,
                    column=column,
                    rule_id="AUTO-DATE-FORMAT",
                    display_name="日期格式校验",
                    test_definition_name="columnValuesToMatchRegex",
                    dimension=QualityDimension.NORMATIVITY,
                    severity=RuleSeverity.MEDIUM,
                    confidence=0.80 if data_kind == "string" else 0.68,
                    reason="字段语义匹配日期/时间字段，建议统一日期格式。",
                    parameters={
                        "regex": r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])"
                    },
                    evidence=evidence,
                    script_expression=(
                        "SELECT * FROM {{ table_name }} WHERE {{ column_name }} IS NOT NULL "
                        "AND {{ column_name }} NOT REGEXP '{{ regex }}'"
                    ),
                    target=target,
                    include_script_preview=include_script_preview,
                )
            )
            recommendations.extend(self._time_pair_rules(table, column, evidence))

        if "amount" in semantics or "quantity" in semantics or data_kind == "numeric":
            if data_kind == "string":
                recommendations.append(
                    self._from_library(
                        "A-N01",
                        table,
                        column,
                        0.82,
                        "字段为数值业务语义但类型为字符串，建议进行数值型格式校验。",
                        evidence,
                        target,
                        include_script_preview,
                    )
                )
            recommendations.append(
                self._from_library(
                    "A-N02",
                    table,
                    column,
                    0.86 if ("amount" in semantics or "quantity" in semantics) else 0.70,
                    "金额、数量、工时等数值字段通常需要非负和值域校验。",
                    evidence,
                    target,
                    include_script_preview,
                    parameter_overrides=self._range_parameters(column, semantics),
                )
            )
            recommendations.append(
                self._precision_rule(table, column, evidence)
            )

        if "enum" in semantics or self._looks_like_enum(column):
            enum_values = self._enum_values(column)
            recommendations.append(
                self._from_library(
                    "N-V01",
                    table,
                    column,
                    0.88 if enum_values else 0.72,
                    "字段语义、数据字典或样例值显示为枚举，推荐枚举值校验。",
                    evidence,
                    target,
                    include_script_preview,
                    parameter_overrides={"allowed_values": _sql_literal_list(enum_values)}
                    if enum_values
                    else None,
                )
            )

        if self._should_recommend_length(column):
            recommendations.append(
                self._from_library(
                    "A-L01",
                    table,
                    column,
                    0.76,
                    "字段长度、数据字典或样例值可推断长度范围，推荐长度校验。",
                    evidence,
                    target,
                    include_script_preview,
                    parameter_overrides=self._length_parameters(column),
                )
            )

        if self._should_recommend_not_null(column, semantics):
            recommendations.append(
                self._not_null_rule(table, column, 0.90, evidence, target, include_script_preview)
            )

        if self._should_recommend_unique(column, semantics):
            recommendations.append(
                self._unique_rule(
                    table,
                    column,
                    0.90 if column.is_primary_key or column.is_unique else 0.75,
                    "主键、唯一约束或高唯一率字段建议检查唯一性。",
                    evidence,
                )
            )

        if self._should_recommend_reference(column):
            recommendations.append(
                self._reference_rule(table, column, evidence, include_script_preview)
            )

        if column.lineage and column.lineage.has_cross_system_lineage:
            recommendations.append(
                self._cross_system_rule(table, column, evidence, include_script_preview)
            )

        return self._deduplicate_recommendations(
            [rec for rec in recommendations if rec is not None]
        )

    def _recommend_table_level_rules(
        self,
        table: TableMetadata,
        include_script_preview: bool,
    ) -> List[IntelligentRuleRecommendation]:
        evidence = [
            RecommendationEvidence(
                source="metadata",
                message="表级质量任务建议至少包含可访问性检查。",
                weight=0.4,
            )
        ]
        target = {"table_name": table.table_name or table.table_fqn}
        rec = self._from_library(
            "AC-C01",
            table,
            None,
            0.68,
            "为表级检核任务推荐基础可访问性校验。",
            evidence,
            target,
            include_script_preview,
        )
        return [rec] if rec else []

    def _from_library(
        self,
        rule_id: str,
        table: TableMetadata,
        column: Optional[FieldMetadata],
        confidence: float,
        reason: str,
        evidence: List[RecommendationEvidence],
        target: Dict[str, Any],
        include_script_preview: bool,
        parameter_overrides: Optional[Dict[str, Any]] = None,
    ) -> Optional[IntelligentRuleRecommendation]:
        rule = self.rule_library.get_rule(rule_id)
        if not rule:
            return None

        parameters = copy.deepcopy(rule.parameters)
        parameters.update(parameter_overrides or {})
        script_preview = None
        if include_script_preview:
            try:
                script_preview = self.rule_library.preview_script(
                    rule_id,
                    RuleExecutionEngine.SQL,
                    target,
                    parameters,
                )
            except Exception:
                script_preview = None

        column_name = column.name if column else None
        return IntelligentRuleRecommendation(
            recommendation_id=self._recommendation_id(table, column_name, rule.rule_id),
            rule_id=rule.rule_id,
            rule_name=rule.name,
            display_name=rule.display_name,
            test_definition_name=rule.test_definition_name,
            dimension=rule.dimension,
            entity_type=rule.applicability.entity_type,
            column_name=column_name,
            confidence=round(min(confidence + self._confidence_bonus(column), 0.99), 3),
            severity=rule.severity,
            validation_level=rule.validation_level,
            reason=reason,
            parameters=parameters,
            threshold=copy.deepcopy(rule.threshold),
            responsible_role=rule.responsible_role,
            remediation_suggestion=rule.remediation_suggestion,
            issue_strategy=rule.issue_strategy,
            evidence=copy.deepcopy(evidence),
            source_signals=self._source_signals(evidence),
            script_preview=script_preview,
            library_rule_id=rule.rule_id,
        )

    def _adhoc_column_rule(
        self,
        table: TableMetadata,
        column: FieldMetadata,
        rule_id: str,
        display_name: str,
        test_definition_name: str,
        dimension: QualityDimension,
        severity: RuleSeverity,
        confidence: float,
        reason: str,
        parameters: Dict[str, Any],
        evidence: List[RecommendationEvidence],
        script_expression: str,
        target: Dict[str, Any],
        include_script_preview: bool,
    ) -> IntelligentRuleRecommendation:
        script_preview = None
        if include_script_preview:
            expression = _render_template(script_expression, {**target, **parameters})
            script_preview = ScriptPreview(
                rule_id=rule_id,
                engine=RuleExecutionEngine.SQL,
                expression=script_expression,
                rendered_expression=expression,
                parameters=copy.deepcopy(parameters),
                unresolved_placeholders=_find_unresolved_placeholders(expression),
            )

        return IntelligentRuleRecommendation(
            recommendation_id=self._recommendation_id(table, column.name, rule_id),
            rule_id=rule_id,
            rule_name=rule_id.lower().replace("-", "_"),
            display_name=display_name,
            test_definition_name=test_definition_name,
            dimension=dimension,
            entity_type=RuleEntityType.COLUMN,
            column_name=column.name,
            confidence=round(min(confidence + self._confidence_bonus(column), 0.99), 3),
            severity=severity,
            validation_level=RuleValidationLevel.P1_WARNING,
            reason=reason,
            parameters=copy.deepcopy(parameters),
            threshold=RuleThreshold(pass_rate=0.999),
            evidence=copy.deepcopy(evidence),
            source_signals=self._source_signals(evidence),
            script_preview=script_preview,
        )

    def _not_null_rule(
        self,
        table: TableMetadata,
        column: FieldMetadata,
        confidence: float,
        evidence: List[RecommendationEvidence],
        target: Dict[str, Any],
        include_script_preview: bool,
    ) -> Optional[IntelligentRuleRecommendation]:
        return self._from_library(
            "C-F01",
            table,
            column,
            confidence,
            "字段约束、字典或业务语义显示为关键字段，推荐非空校验。",
            evidence,
            target,
            include_script_preview,
        )

    def _unique_rule(
        self,
        table: TableMetadata,
        column: FieldMetadata,
        confidence: float,
        reason: str,
        evidence: List[RecommendationEvidence],
    ) -> IntelligentRuleRecommendation:
        return IntelligentRuleRecommendation(
            recommendation_id=self._recommendation_id(
                table, column.name, "AUTO-UNIQUE"
            ),
            rule_id="AUTO-UNIQUE",
            rule_name="column_values_to_be_unique",
            display_name="唯一性校验",
            test_definition_name="columnValuesToBeUnique",
            dimension=QualityDimension.COMPLETENESS,
            entity_type=RuleEntityType.COLUMN,
            column_name=column.name,
            confidence=round(min(confidence + self._confidence_bonus(column), 0.99), 3),
            severity=RuleSeverity.HIGH
            if column.is_primary_key or column.is_unique
            else RuleSeverity.MEDIUM,
            validation_level=RuleValidationLevel.P1_WARNING,
            reason=reason,
            parameters={},
            threshold=RuleThreshold(pass_rate=1.0),
            responsible_role="数据责任人",
            remediation_suggestion="排查重复采集、重复同步或主键生成逻辑，合并或清理重复记录。",
            issue_strategy="重复记录进入问题库并生成整改工单。",
            evidence=copy.deepcopy(evidence),
            source_signals=self._source_signals(evidence),
        )

    def _precision_rule(
        self,
        table: TableMetadata,
        column: FieldMetadata,
        evidence: List[RecommendationEvidence],
    ) -> IntelligentRuleRecommendation:
        scale = "2" if "amount" in self._detect_semantics(column) else "4"
        expression = (
            "SELECT * FROM {{ table_name }} WHERE {{ column_name }} IS NOT NULL "
            "AND {{ column_name }} <> ROUND({{ column_name }}, {{ scale }})"
        )
        return self._adhoc_column_rule(
            table=table,
            column=column,
            rule_id="AUTO-NUMERIC-PRECISION",
            display_name="数值精度校验",
            test_definition_name="tableCustomSQLQuery",
            dimension=QualityDimension.ACCURACY,
            severity=RuleSeverity.MEDIUM,
            confidence=0.72,
            reason="金额、数量或工时类字段建议控制数值精度。",
            parameters={"scale": scale},
            evidence=evidence,
            script_expression=expression,
            target={
                "table_name": table.table_name or table.table_fqn,
                "column_name": column.name,
            },
            include_script_preview=True,
        )

    def _reference_rule(
        self,
        table: TableMetadata,
        column: FieldMetadata,
        evidence: List[RecommendationEvidence],
        include_script_preview: bool,
    ) -> Optional[IntelligentRuleRecommendation]:
        related_table = ""
        related_column = "id"
        if column.lineage:
            related_table = column.lineage.related_table
            related_column = column.lineage.related_column or related_column
        related_table = related_table or column.related_columns.get("referenced_table", "")
        related_column = column.related_columns.get("referenced_column", related_column)

        if not related_table:
            related_table = "${REFERENCED_TABLE}"

        return self._from_library(
            "C-L01",
            table,
            column,
            0.84,
            "字段具有外键、关联字段或血缘关联提示，推荐关联完整性校验。",
            evidence,
            {
                "table_name": table.table_name or table.table_fqn,
                "column_name": column.name,
                "referenced_table": related_table,
                "foreign_key": column.name,
                "referenced_key": related_column,
            },
            include_script_preview,
            {
                "referenced_table": related_table,
                "foreign_key": column.name,
                "referenced_key": related_column,
            },
        )

    def _cross_system_rule(
        self,
        table: TableMetadata,
        column: FieldMetadata,
        evidence: List[RecommendationEvidence],
        include_script_preview: bool,
    ) -> Optional[IntelligentRuleRecommendation]:
        lineage = column.lineage or FieldLineageHint()
        target_table = lineage.target_systems[0] if lineage.target_systems else "${TARGET_TABLE}"
        return self._from_library(
            "CS-S01",
            table,
            column,
            0.78,
            "字段存在跨系统血缘，推荐跨系统一致性校验。",
            evidence,
            {
                "table_name": table.table_name or table.table_fqn,
                "column_name": column.name,
                "source_table": table.table_name or table.table_fqn,
                "target_table": target_table,
                "source_key": column.related_columns.get("source_key", "id"),
                "target_key": column.related_columns.get("target_key", "id"),
                "compare_column": column.name,
            },
            include_script_preview,
            {
                "source_table": table.table_name or table.table_fqn,
                "target_table": target_table,
                "source_key": column.related_columns.get("source_key", "id"),
                "target_key": column.related_columns.get("target_key", "id"),
                "compare_column": column.name,
            },
        )

    def _id_card_related_rules(
        self,
        table: TableMetadata,
        column: FieldMetadata,
        evidence: List[RecommendationEvidence],
    ) -> List[IntelligentRuleRecommendation]:
        recommendations: List[IntelligentRuleRecommendation] = []
        birth_column = self._find_related_column(
            table, ["birth_date", "birthday", "date_of_birth", "出生日期", "生日"]
        )
        if birth_column:
            recommendations.append(
                self._adhoc_column_rule(
                    table=table,
                    column=column,
                    rule_id="AUTO-IDCARD-BIRTHDAY-CONSISTENCY",
                    display_name="身份证出生日期一致性校验",
                    test_definition_name="tableCustomSQLQuery",
                    dimension=QualityDimension.ACCURACY,
                    severity=RuleSeverity.HIGH,
                    confidence=0.86,
                    reason="表中同时存在身份证号和出生日期字段，推荐校验二者日期一致。",
                    parameters={"birth_date_column": birth_column.name},
                    evidence=evidence
                    + [
                        RecommendationEvidence(
                            source="metadata",
                            message=f"发现相关出生日期字段: {birth_column.name}",
                            weight=0.2,
                        )
                    ],
                    script_expression=(
                        "SELECT * FROM {{ table_name }} WHERE {{ column_name }} IS NOT NULL "
                        "AND {{ birth_date_column }} IS NOT NULL "
                        "AND SUBSTRING({{ column_name }}, 7, 8) <> "
                        "DATE_FORMAT({{ birth_date_column }}, '%Y%m%d')"
                    ),
                    target={
                        "table_name": table.table_name or table.table_fqn,
                        "column_name": column.name,
                    },
                    include_script_preview=True,
                )
            )

        gender_column = self._find_related_column(
            table, ["gender", "sex", "性别"]
        )
        if gender_column:
            recommendations.append(
                self._adhoc_column_rule(
                    table=table,
                    column=column,
                    rule_id="AUTO-IDCARD-GENDER-CONSISTENCY",
                    display_name="身份证性别一致性校验",
                    test_definition_name="tableCustomSQLQuery",
                    dimension=QualityDimension.ACCURACY,
                    severity=RuleSeverity.MEDIUM,
                    confidence=0.74,
                    reason="表中同时存在身份证号和性别字段，推荐校验身份证顺序码与性别一致。",
                    parameters={"gender_column": gender_column.name},
                    evidence=evidence
                    + [
                        RecommendationEvidence(
                            source="metadata",
                            message=f"发现相关性别字段: {gender_column.name}",
                            weight=0.15,
                        )
                    ],
                    script_expression=(
                        "SELECT * FROM {{ table_name }} WHERE {{ column_name }} IS NOT NULL "
                        "AND {{ gender_column }} IS NOT NULL "
                        "AND ((MOD(CAST(SUBSTRING({{ column_name }}, 17, 1) AS UNSIGNED), 2) = 1 "
                        "AND {{ gender_column }} NOT IN ('男','M','male')) "
                        "OR (MOD(CAST(SUBSTRING({{ column_name }}, 17, 1) AS UNSIGNED), 2) = 0 "
                        "AND {{ gender_column }} NOT IN ('女','F','female')))"
                    ),
                    target={
                        "table_name": table.table_name or table.table_fqn,
                        "column_name": column.name,
                    },
                    include_script_preview=True,
                )
            )
        return recommendations

    def _time_pair_rules(
        self,
        table: TableMetadata,
        column: FieldMetadata,
        evidence: List[RecommendationEvidence],
    ) -> List[IntelligentRuleRecommendation]:
        name = column.name.lower()
        if not any(key in name for key in ["start", "begin", "create", "开始", "创建"]):
            return []
        end_column = self._find_related_column(
            table, ["end", "finish", "complete", "结束", "完成"]
        )
        if not end_column:
            return []
        return [
            self._from_library(
                "A-T01",
                table,
                column,
                0.78,
                "发现起止时间字段组合，推荐时间先后逻辑校验。",
                evidence,
                {
                    "table_name": table.table_name or table.table_fqn,
                    "column_name": column.name,
                    "start_time_column": column.name,
                    "end_time_column": end_column.name,
                },
                True,
                {
                    "start_time_column": column.name,
                    "end_time_column": end_column.name,
                },
            )
        ]

    def _detect_semantics(self, column: FieldMetadata) -> Set[str]:
        text = column.text_for_semantic_match
        semantics: Set[str] = set()
        patterns: List[Tuple[str, List[str]]] = [
            ("phone", [r"phone", r"mobile", r"tel", r"cell", r"手机号", r"电话", r"联系方式"]),
            ("id_card", [r"id[_-]?card", r"identity", r"cert", r"sfz", r"身份证", r"证件号"]),
            ("email", [r"email", r"mail", r"邮箱"]),
            ("code", [r"code", r"编码", r"编号", r"sku", r"no$"]),
            ("date", [r"date", r"time", r"dt$", r"日期", r"时间"]),
            ("amount", [r"amount", r"price", r"cost", r"fee", r"balance", r"金额", r"价格", r"费用"]),
            ("quantity", [r"qty", r"quantity", r"count", r"num", r"hours?", r"数量", r"库存", r"工时"]),
            ("enum", [r"status", r"type", r"level", r"grade", r"flag", r"状态", r"类型", r"等级", r"枚举"]),
            ("gender", [r"gender", r"sex", r"性别"]),
            ("ip", [r"\bip\b", r"ipv4", r"ip地址"]),
            ("mac", [r"\bmac\b", r"物理地址"]),
            ("imei", [r"imei", r"设备号"]),
            ("license_plate", [r"plate", r"vehicle", r"car_no", r"车牌"]),
            ("id", [r"(^|[_-])id$", r"key$", r"uuid", r"主键"]),
        ]
        for semantic, regexes in patterns:
            if any(re.search(regex, text, re.IGNORECASE) for regex in regexes):
                semantics.add(semantic)

        if column.dictionary and column.dictionary.allowed_values:
            semantics.add("enum")
        return semantics

    def _detect_sample_patterns(self, column: FieldMetadata) -> Set[str]:
        if not column.sample_values:
            return set()
        analysis = self.parameter_suggester.analyze_sample_data(
            column.name, column.sample_values
        )
        mapping = {
            "chinese_mobile": "phone",
            "email": "email",
            "id_card_18": "id_card",
            "ip_v4": "ip",
            "mac_address": "mac",
            "imei": "imei",
            "license_plate": "license_plate",
            "date_iso": "date",
        }
        return {
            mapping[pattern]
            for pattern in analysis.detected_patterns
            if pattern in mapping
        }

    def _base_evidence(
        self,
        column: FieldMetadata,
        semantics: Set[str],
        data_kind: str,
        sample_patterns: Set[str],
    ) -> List[RecommendationEvidence]:
        evidence: List[RecommendationEvidence] = []
        if semantics:
            evidence.append(
                RecommendationEvidence(
                    source="field_semantic",
                    message=f"字段语义匹配: {', '.join(sorted(semantics))}",
                    weight=0.35,
                )
            )
        if column.data_type:
            evidence.append(
                RecommendationEvidence(
                    source="field_type",
                    message=f"字段类型为 {column.data_type}，归类为 {data_kind}",
                    weight=0.2,
                )
            )
        if sample_patterns:
            evidence.append(
                RecommendationEvidence(
                    source="sample_values",
                    message=f"样例值匹配模式: {', '.join(sorted(sample_patterns))}",
                    weight=0.3,
                )
            )
        if column.dictionary:
            evidence.append(
                RecommendationEvidence(
                    source="data_dictionary",
                    message="字段关联数据字典，可用于枚举、值域、必填和唯一性判断。",
                    weight=0.25,
                )
            )
        if column.data_classification or column.security_level:
            evidence.append(
                RecommendationEvidence(
                    source="classification",
                    message=f"分级分类: {column.data_classification or '-'} / {column.security_level or '-'}",
                    weight=0.15,
                )
            )
        if column.lineage:
            evidence.append(
                RecommendationEvidence(
                    source="lineage",
                    message="存在字段血缘或关联关系提示。",
                    weight=0.2,
                )
            )
        return evidence

    def _classify_data_type(self, data_type: str) -> str:
        normalized = (data_type or "").lower()
        if any(token in normalized for token in ["int", "decimal", "numeric", "float", "double", "number", "money"]):
            return "numeric"
        if any(token in normalized for token in ["date", "time", "timestamp"]):
            return "datetime"
        if any(token in normalized for token in ["bool", "bit"]):
            return "boolean"
        if any(token in normalized for token in ["char", "text", "string", "varchar"]):
            return "string"
        return "unknown"

    def _range_parameters(
        self,
        column: FieldMetadata,
        semantics: Set[str],
    ) -> Dict[str, str]:
        min_value = column.min_value
        max_value = column.max_value
        if column.dictionary:
            min_value = column.dictionary.min_value if column.dictionary.min_value is not None else min_value
            max_value = column.dictionary.max_value if column.dictionary.max_value is not None else max_value
        if min_value is None and ("amount" in semantics or "quantity" in semantics):
            min_value = 0
        if max_value is None:
            if "quantity" in semantics and "hour" in column.name.lower():
                max_value = 24
            elif "amount" in semantics:
                max_value = "${MAX_VALUE}"
            else:
                max_value = "${MAX_VALUE}"
        return {"min_value": str(min_value), "max_value": str(max_value)}

    def _length_parameters(self, column: FieldMetadata) -> Dict[str, str]:
        min_length = 1
        max_length = column.length or 128
        if column.dictionary:
            min_length = column.dictionary.min_length or min_length
            max_length = column.dictionary.max_length or max_length
        if column.sample_values:
            lengths = [len(str(value)) for value in column.sample_values if value is not None]
            if lengths:
                max_length = max(max_length, max(lengths))
        return {"min_length": str(min_length), "max_length": str(max_length)}

    def _enum_values(self, column: FieldMetadata) -> List[Any]:
        if column.enum_values:
            return column.enum_values
        if column.dictionary and column.dictionary.allowed_values:
            return column.dictionary.allowed_values
        if column.sample_values:
            non_empty = [value for value in column.sample_values if value is not None]
            unique_values = list(dict.fromkeys(non_empty))
            if 1 < len(unique_values) <= 20 and len(unique_values) / max(len(non_empty), 1) <= 0.4:
                return unique_values
        return []

    def _looks_like_enum(self, column: FieldMetadata) -> bool:
        if column.enum_values or (column.dictionary and column.dictionary.allowed_values):
            return True
        if column.sample_values:
            non_empty = [value for value in column.sample_values if value is not None]
            unique_values = set(non_empty)
            return 1 < len(unique_values) <= 20 and len(unique_values) / max(len(non_empty), 1) <= 0.4
        return False

    def _should_recommend_length(self, column: FieldMetadata) -> bool:
        data_kind = self._classify_data_type(column.data_type)
        if data_kind != "string":
            return False
        return bool(
            column.length
            or (column.dictionary and (column.dictionary.min_length or column.dictionary.max_length))
            or column.sample_values
        )

    def _should_recommend_not_null(
        self,
        column: FieldMetadata,
        semantics: Set[str],
    ) -> bool:
        if column.is_primary_key or column.nullable is False:
            return True
        if column.dictionary and column.dictionary.required:
            return True
        if column.null_ratio is not None and column.null_ratio == 0:
            return True
        critical_semantics = {"id", "phone", "id_card", "amount", "date", "enum"}
        return bool(semantics.intersection(critical_semantics))

    def _should_recommend_unique(
        self,
        column: FieldMetadata,
        semantics: Set[str],
    ) -> bool:
        if column.is_primary_key or column.is_unique:
            return True
        if column.dictionary and column.dictionary.unique:
            return True
        if column.unique_ratio is not None and column.unique_ratio >= 0.98:
            return True
        return bool(semantics.intersection({"id", "id_card"}))

    def _should_recommend_reference(self, column: FieldMetadata) -> bool:
        if column.is_foreign_key:
            return True
        if column.lineage and (column.lineage.related_table or column.lineage.related_column):
            return True
        return column.name.lower().endswith("_id") and not column.is_primary_key

    def _confidence_bonus(self, column: Optional[FieldMetadata]) -> float:
        if not column:
            return 0.0
        bonus = 0.0
        if column.dictionary:
            bonus += 0.03
        if column.sample_values:
            bonus += 0.03
        if column.description or column.comment:
            bonus += 0.02
        if column.lineage:
            bonus += 0.02
        return bonus

    def _source_signals(self, evidence: Iterable[RecommendationEvidence]) -> List[str]:
        return sorted({item.source for item in evidence})

    def _recommendation_id(
        self,
        table: TableMetadata,
        column_name: Optional[str],
        rule_id: str,
    ) -> str:
        target = column_name or "table"
        base = f"{table.table_fqn}:{target}:{rule_id}"
        return re.sub(r"[^0-9A-Za-z_.:-]+", "_", base)

    def _find_related_column(
        self,
        table: TableMetadata,
        candidates: Sequence[str],
    ) -> Optional[FieldMetadata]:
        normalized_candidates = [candidate.lower() for candidate in candidates]
        for column in table.columns:
            text = column.text_for_semantic_match
            if any(candidate in text for candidate in normalized_candidates):
                return column
        return None

    def _deduplicate_recommendations(
        self,
        recommendations: List[IntelligentRuleRecommendation],
    ) -> List[IntelligentRuleRecommendation]:
        best: Dict[Tuple[str, Optional[str]], IntelligentRuleRecommendation] = {}
        for rec in recommendations:
            key = (rec.rule_id, rec.column_name)
            current = best.get(key)
            if not current or rec.confidence > current.confidence:
                best[key] = rec
        return sorted(
            best.values(),
            key=lambda rec: (rec.confidence, SEVERITY_ORDER.get(rec.severity, 0)),
            reverse=True,
        )


def _sql_literal_list(values: Sequence[Any]) -> str:
    return ", ".join("'" + str(value).replace("'", "''") + "'" for value in values)


def _render_template(template: str, context: Dict[str, Any]) -> str:
    rendered = template
    for key, value in context.items():
        replacement = str(value)
        rendered = re.sub(
            r"\{\{\s*" + re.escape(key) + r"\s*\}\}",
            lambda _match, value=replacement: value,
            rendered,
        )
    return rendered


def _find_unresolved_placeholders(text: str) -> List[str]:
    placeholders = set(re.findall(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", text))
    placeholders.update(re.findall(r"\$\{([^}]+)\}", text))
    return sorted(placeholders)


__all__ = [
    "DataDictionaryEntry",
    "FieldLineageHint",
    "FieldMetadata",
    "TableMetadata",
    "RecommendationEvidence",
    "IntelligentRuleRecommendation",
    "IntelligentRuleRecommender",
]
