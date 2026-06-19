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
质量规则智能推荐 API。

提供规则推荐、人工确认、参数/阈值调整后入库的后端服务门面。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from metadata.data_quality.dimension.models import QualityDimension
from metadata.data_quality.rules.intelligent_rule_recommender import (
    DataDictionaryEntry,
    FieldLineageHint,
    FieldMetadata,
    IntelligentRuleRecommendation,
    IntelligentRuleRecommender,
    TableMetadata,
)
from metadata.data_quality.rules.rule_library import (
    RuleLibrary,
    RuleThreshold,
    RuleValidationLevel,
)
from metadata.data_quality.rules.rule_validator import (
    RuleValidator,
    ValidationPriority,
)


class DataDictionaryEntryRequest(BaseModel):
    """数据字典请求模型。"""

    name: str = ""
    display_name: str = ""
    description: str = ""
    allowed_values: List[Any] = Field(default_factory=list)
    value_descriptions: Dict[str, str] = Field(default_factory=dict)
    code_table: str = ""
    regex: str = ""
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    required: bool = False
    unique: bool = False


class FieldLineageHintRequest(BaseModel):
    """字段血缘提示请求模型。"""

    upstream_fields: List[str] = Field(default_factory=list)
    downstream_fields: List[str] = Field(default_factory=list)
    source_system: str = ""
    target_systems: List[str] = Field(default_factory=list)
    related_table: str = ""
    related_column: str = ""
    transform_expression: str = ""
    relationship_type: str = ""


class FieldMetadataRequest(BaseModel):
    """字段元数据请求模型。"""

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
    tags: List[str] = Field(default_factory=list)
    sample_values: List[Any] = Field(default_factory=list)
    enum_values: List[Any] = Field(default_factory=list)
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    null_ratio: Optional[float] = None
    unique_ratio: Optional[float] = None
    dictionary: Optional[DataDictionaryEntryRequest] = None
    lineage: Optional[FieldLineageHintRequest] = None
    related_columns: Dict[str, str] = Field(default_factory=dict)


class TableMetadataRequest(BaseModel):
    """表元数据请求模型。"""

    table_fqn: str
    table_name: str = ""
    columns: List[FieldMetadataRequest] = Field(default_factory=list)
    business_domain: str = ""
    data_classification: str = ""
    row_count: int = 0
    tags: List[str] = Field(default_factory=list)
    lineage: Optional[FieldLineageHintRequest] = None


class IntelligentRecommendationRequest(BaseModel):
    """智能推荐请求。"""

    table: TableMetadataRequest
    dimensions: Optional[List[str]] = Field(None, description="筛选评价维度")
    min_confidence: float = Field(0.5, ge=0, le=1, description="最低置信度")
    include_script_preview: bool = Field(True, description="是否返回脚本预览")
    max_rules_per_column: Optional[int] = Field(None, description="每列最多推荐规则数")


class RecommendationEvidenceResponse(BaseModel):
    """推荐证据响应。"""

    source: str
    message: str
    weight: float = 0.0


class IntelligentRuleRecommendationResponse(BaseModel):
    """智能推荐结果响应。"""

    recommendation_id: str
    rule_id: str
    rule_name: str
    display_name: str
    test_definition_name: str
    dimension: str
    dimension_zh: str
    entity_type: str
    column_name: Optional[str] = None
    confidence: float
    severity: str
    validation_level: str
    reason: str
    parameters: Dict[str, Any]
    threshold: Dict[str, Any]
    responsible_role: str
    remediation_suggestion: str
    issue_strategy: str
    evidence: List[RecommendationEvidenceResponse]
    source_signals: List[str]
    script_preview: Optional[Dict[str, Any]] = None
    requires_confirmation: bool
    library_rule_id: Optional[str] = None


class IntelligentRecommendationResponse(BaseModel):
    """智能推荐响应。"""

    table_fqn: str
    table_name: str
    total_columns: int
    total_recommendations: int
    generated_at: datetime
    recommendations: List[IntelligentRuleRecommendationResponse]
    dimension_summary: Dict[str, int]
    confidence_summary: Dict[str, int]
    request_id: str


class RecommendationConfirmation(BaseModel):
    """单条推荐确认。"""

    recommendation_id: str
    parameter_overrides: Dict[str, Any] = Field(default_factory=dict)
    threshold_override: Optional[Dict[str, Any]] = None
    validation_level: Optional[str] = None
    enabled: bool = True
    comment: str = ""


class RecommendationConfirmRequest(BaseModel):
    """推荐确认入库请求。"""

    request_id: str
    confirmed_by: str
    confirmations: List[RecommendationConfirmation]
    auto_approve: bool = False


class ConfirmedRecommendationResponse(BaseModel):
    """确认入库响应。"""

    recommendation_id: str
    validation_id: str
    rule_id: str
    rule_name: str
    status: str
    enabled: bool
    parameters: Dict[str, Any]
    threshold: Dict[str, Any]


class IntelligentRuleRecommendationAPI:
    """质量规则智能推荐 API 服务。"""

    def __init__(
        self,
        recommender: Optional[IntelligentRuleRecommender] = None,
        rule_library: Optional[RuleLibrary] = None,
        validator: Optional[RuleValidator] = None,
    ):
        self.rule_library = rule_library or RuleLibrary()
        self.recommender = recommender or IntelligentRuleRecommender(self.rule_library)
        self.validator = validator or RuleValidator()
        self._recommendation_cache: Dict[str, List[IntelligentRuleRecommendation]] = {}

    def recommend(
        self,
        request: IntelligentRecommendationRequest,
        request_id: Optional[str] = None,
    ) -> IntelligentRecommendationResponse:
        """执行智能推荐。"""
        table = self._to_table_metadata(request.table)
        dimensions = (
            [QualityDimension(dim) for dim in request.dimensions]
            if request.dimensions
            else None
        )
        recommendations = self.recommender.recommend_table(
            table,
            dimensions=dimensions,
            min_confidence=request.min_confidence,
            include_script_preview=request.include_script_preview,
            max_rules_per_column=request.max_rules_per_column,
        )

        rid = request_id or str(datetime.now().timestamp())
        self._recommendation_cache[rid] = recommendations

        return IntelligentRecommendationResponse(
            table_fqn=table.table_fqn,
            table_name=table.table_name or table.table_fqn.split(".")[-1],
            total_columns=len(table.columns),
            total_recommendations=len(recommendations),
            generated_at=datetime.now(),
            recommendations=[
                self._build_recommendation_response(rec)
                for rec in recommendations
            ],
            dimension_summary=self._dimension_summary(recommendations),
            confidence_summary=self._confidence_summary(recommendations),
            request_id=rid,
        )

    def confirm_recommendations(
        self,
        request: RecommendationConfirmRequest,
    ) -> List[ConfirmedRecommendationResponse]:
        """人工确认推荐结果，允许调整参数/阈值后入库。"""
        cached = {
            rec.recommendation_id: rec
            for rec in self._recommendation_cache.get(request.request_id, [])
        }
        responses: List[ConfirmedRecommendationResponse] = []

        for confirmation in request.confirmations:
            rec = cached.get(confirmation.recommendation_id)
            if not rec:
                continue

            parameters = copy_parameters(rec.parameters)
            parameters.update(confirmation.parameter_overrides)
            threshold = RuleThreshold.from_dict(rec.threshold)
            if confirmation.threshold_override:
                threshold_data = threshold.to_dict()
                threshold_data.update(confirmation.threshold_override)
                threshold = RuleThreshold.from_dict(threshold_data)

            if confirmation.validation_level:
                rec.validation_level = RuleValidationLevel(confirmation.validation_level)

            rule_id = rec.recommendation_id
            validation = self.validator.create_validation(
                rule_id=rule_id,
                rule_name=rec.display_name,
                created_by=request.confirmed_by,
                parameters={
                    **parameters,
                    "threshold": threshold.to_dict(),
                    "source_recommendation_id": rec.recommendation_id,
                    "library_rule_id": rec.library_rule_id or rec.rule_id,
                },
                priority=self._priority_from_recommendation(rec),
                tags={rec.dimension.value, rec.rule_id},
                business_owner=rec.responsible_role,
            )
            validation.enabled = confirmation.enabled
            if confirmation.comment:
                validation.validation_comment = confirmation.comment

            if request.auto_approve:
                validation = self.validator.approve_validation(
                    validation.validation_id,
                    validated_by=request.confirmed_by,
                    comment=confirmation.comment or "智能推荐确认后自动批准",
                )
            elif hasattr(self.validator, "_save_validations"):
                self.validator._save_validations()

            responses.append(
                ConfirmedRecommendationResponse(
                    recommendation_id=rec.recommendation_id,
                    validation_id=validation.validation_id,
                    rule_id=rule_id,
                    rule_name=rec.display_name,
                    status=validation.status.value,
                    enabled=validation.enabled,
                    parameters=parameters,
                    threshold=threshold.to_dict(),
                )
            )

        return responses

    def get_cached_recommendations(
        self,
        request_id: str,
    ) -> List[IntelligentRuleRecommendationResponse]:
        """获取已缓存推荐结果。"""
        return [
            self._build_recommendation_response(rec)
            for rec in self._recommendation_cache.get(request_id, [])
        ]

    def _to_table_metadata(self, request: TableMetadataRequest) -> TableMetadata:
        return TableMetadata(
            table_fqn=request.table_fqn,
            table_name=request.table_name,
            columns=[self._to_field_metadata(col) for col in request.columns],
            business_domain=request.business_domain,
            data_classification=request.data_classification,
            row_count=request.row_count,
            tags=list(request.tags),
            lineage=self._to_lineage(request.lineage),
        )

    def _to_field_metadata(self, request: FieldMetadataRequest) -> FieldMetadata:
        return FieldMetadata(
            name=request.name,
            data_type=request.data_type,
            length=request.length,
            nullable=request.nullable,
            is_primary_key=request.is_primary_key,
            is_foreign_key=request.is_foreign_key,
            is_unique=request.is_unique,
            description=request.description,
            comment=request.comment,
            business_domain=request.business_domain,
            data_classification=request.data_classification,
            security_level=request.security_level,
            tags=list(request.tags),
            sample_values=list(request.sample_values),
            enum_values=list(request.enum_values),
            min_value=request.min_value,
            max_value=request.max_value,
            null_ratio=request.null_ratio,
            unique_ratio=request.unique_ratio,
            dictionary=self._to_dictionary(request.dictionary),
            lineage=self._to_lineage(request.lineage),
            related_columns=dict(request.related_columns),
        )

    @staticmethod
    def _to_dictionary(
        request: Optional[DataDictionaryEntryRequest],
    ) -> Optional[DataDictionaryEntry]:
        if not request:
            return None
        return DataDictionaryEntry(
            name=request.name,
            display_name=request.display_name,
            description=request.description,
            allowed_values=list(request.allowed_values),
            value_descriptions=dict(request.value_descriptions),
            code_table=request.code_table,
            regex=request.regex,
            min_value=request.min_value,
            max_value=request.max_value,
            min_length=request.min_length,
            max_length=request.max_length,
            required=request.required,
            unique=request.unique,
        )

    @staticmethod
    def _to_lineage(
        request: Optional[FieldLineageHintRequest],
    ) -> Optional[FieldLineageHint]:
        if not request:
            return None
        return FieldLineageHint(
            upstream_fields=list(request.upstream_fields),
            downstream_fields=list(request.downstream_fields),
            source_system=request.source_system,
            target_systems=list(request.target_systems),
            related_table=request.related_table,
            related_column=request.related_column,
            transform_expression=request.transform_expression,
            relationship_type=request.relationship_type,
        )

    @staticmethod
    def _build_recommendation_response(
        recommendation: IntelligentRuleRecommendation,
    ) -> IntelligentRuleRecommendationResponse:
        data = recommendation.to_dict()
        return IntelligentRuleRecommendationResponse(
            recommendation_id=data["recommendation_id"],
            rule_id=data["rule_id"],
            rule_name=data["rule_name"],
            display_name=data["display_name"],
            test_definition_name=data["test_definition_name"],
            dimension=data["dimension"],
            dimension_zh=data["dimension_zh"],
            entity_type=data["entity_type"],
            column_name=data["column_name"],
            confidence=data["confidence"],
            severity=data["severity"],
            validation_level=data["validation_level"],
            reason=data["reason"],
            parameters=data["parameters"],
            threshold=data["threshold"],
            responsible_role=data["responsible_role"],
            remediation_suggestion=data["remediation_suggestion"],
            issue_strategy=data["issue_strategy"],
            evidence=[RecommendationEvidenceResponse(**item) for item in data["evidence"]],
            source_signals=data["source_signals"],
            script_preview=data["script_preview"],
            requires_confirmation=data["requires_confirmation"],
            library_rule_id=data["library_rule_id"],
        )

    @staticmethod
    def _dimension_summary(
        recommendations: List[IntelligentRuleRecommendation],
    ) -> Dict[str, int]:
        summary: Dict[str, int] = {}
        for rec in recommendations:
            summary[rec.dimension.value] = summary.get(rec.dimension.value, 0) + 1
        return summary

    @staticmethod
    def _confidence_summary(
        recommendations: List[IntelligentRuleRecommendation],
    ) -> Dict[str, int]:
        summary = {"high": 0, "medium": 0, "low": 0}
        for rec in recommendations:
            if rec.confidence >= 0.85:
                summary["high"] += 1
            elif rec.confidence >= 0.65:
                summary["medium"] += 1
            else:
                summary["low"] += 1
        return summary

    @staticmethod
    def _priority_from_recommendation(
        recommendation: IntelligentRuleRecommendation,
    ) -> ValidationPriority:
        if recommendation.severity.value in {"CRITICAL", "HIGH"}:
            return ValidationPriority.HIGH
        if recommendation.confidence >= 0.85:
            return ValidationPriority.HIGH
        return ValidationPriority.NORMAL


def copy_parameters(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """复制推荐参数。单独函数避免对 pydantic 运行时引入额外依赖。"""
    return {key: value for key, value in parameters.items()}


__all__ = [
    "DataDictionaryEntryRequest",
    "FieldLineageHintRequest",
    "FieldMetadataRequest",
    "TableMetadataRequest",
    "IntelligentRecommendationRequest",
    "RecommendationEvidenceResponse",
    "IntelligentRuleRecommendationResponse",
    "IntelligentRecommendationResponse",
    "RecommendationConfirmation",
    "RecommendationConfirmRequest",
    "ConfirmedRecommendationResponse",
    "IntelligentRuleRecommendationAPI",
]
