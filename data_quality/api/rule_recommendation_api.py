#  Copyright 2025 Collate
#  Licensed under the Collate Community License, Version 1.0 (the "License");
#  you may not use this file except in compliance with the License.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""
规则推荐 API 模块

提供 REST API 接口用于：
1. 基于表/列属性的规则推荐
2. 推荐结果的校验和审批
3. 规则库的查询和管理
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field

from metadata.data_quality.dimension.models import QualityDimension, QualityRuleCategory
from metadata.data_quality.rules.parameter_suggester import ParameterSuggester, ParameterSuggestion
from metadata.data_quality.rules.rule_recommender import (
    ColumnCategory,
    ColumnProfile,
    RuleRecommender,
    RuleRecommendation,
)
from metadata.data_quality.rules.rule_validator import (
    RuleValidator,
    ValidationRecord,
    ValidationStatus,
    ValidationPriority,
)


# ============================================================================
# 请求模型
# ============================================================================

class ColumnProfileRequest(BaseModel):
    """列特征请求"""
    name: str
    data_type: str
    is_nullable: bool = True
    is_primary_key: bool = False
    is_foreign_key: bool = False
    is_unique: bool = False
    sample_values: List[str] = Field(default_factory=list)


class TableProfileRequest(BaseModel):
    """表特征请求"""
    table_fqn: str
    table_name: Optional[str] = None
    columns: List[ColumnProfileRequest] = Field(default_factory=list)
    row_count: int = 0


class RuleRecommendationRequest(BaseModel):
    """规则推荐请求"""
    table: TableProfileRequest
    dimensions: Optional[List[str]] = Field(None, description="筛选特定维度")
    min_confidence: float = Field(0.5, ge=0, le=1, description="最小置信度")
    min_severity: Optional[str] = Field(None, description="最小严重程度")
    include_parameters: bool = Field(True, description="是否包含参数建议")


class RuleValidationRequest(BaseModel):
    """规则校验请求"""
    recommendation: RuleRecommendationRequest
    selected_rules: List[str] = Field(default_factory=list, description="选中的规则ID")
    parameter_overrides: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="参数覆盖配置 {rule_id: {param_name: value}}"
    )
    validated_by: str = Field(..., description="校验人")


class BatchRecommendationRequest(BaseModel):
    """批量推荐请求"""
    tables: List[TableProfileRequest]
    dimensions: Optional[List[str]] = None
    min_confidence: float = 0.5


# ============================================================================
# 响应模型
# ============================================================================

class RecommendedRuleResponse(BaseModel):
    """推荐规则响应"""
    rule_id: str
    test_definition_name: str
    column_name: Optional[str] = None
    dimension: str
    dimension_zh: str
    category: str
    severity: str
    confidence: float
    reason: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    status: str = "PENDING"
    validation_id: Optional[str] = None


class RecommendationResponse(BaseModel):
    """推荐响应"""
    table_fqn: str
    table_name: str
    total_columns: int
    recommended_rules: List[RecommendedRuleResponse]
    dimension_summary: Dict[str, int]
    severity_summary: Dict[str, int]
    generated_at: datetime
    request_id: str


class BatchRecommendationResponse(BaseModel):
    """批量推荐响应"""
    total_tables: int
    successful: int
    failed: int
    total_rules: int
    results: List[RecommendationResponse]
    failed_tables: List[str] = field(default_factory=list)


class ValidationSummaryResponse(BaseModel):
    """校验汇总响应"""
    total_rules: int
    pending_count: int
    approved_count: int
    rejected_count: int
    modified_count: int
    deprecated_count: int
    enabled_count: int
    disabled_count: int
    overdue_count: int
    urgent_count: int


class ValidationDetailResponse(BaseModel):
    """校验详情响应"""
    validation_id: str
    rule_id: str
    rule_name: str
    status: str
    enabled: bool
    created_at: datetime
    created_by: str
    validated_by: Optional[str] = None
    validated_at: Optional[datetime] = None
    priority: str
    due_date: Optional[datetime] = None
    original_parameters: Dict[str, Any]
    modified_parameters: Dict[str, Any]
    parameter_changes: List[Dict[str, Any]]
    tags: List[str]
    statistics: Dict[str, Any]


# ============================================================================
# API 服务类
# ============================================================================

class RuleRecommendationAPI:
    """规则推荐 API 服务"""
    
    def __init__(
        self,
        recommender: Optional[RuleRecommender] = None,
        parameter_suggester: Optional[ParameterSuggester] = None,
        validator: Optional[RuleValidator] = None,
    ):
        self.recommender = recommender or RuleRecommender()
        self.parameter_suggester = parameter_suggester or ParameterSuggester()
        self.validator = validator or RuleValidator()
        self._request_cache: Dict[str, Any] = {}
    
    def recommend(
        self,
        request: RuleRecommendationRequest,
        request_id: Optional[str] = None,
    ) -> RecommendationResponse:
        """执行规则推荐
        
        Args:
            request: 推荐请求
            request_id: 请求ID
            
        Returns:
            推荐响应
        """
        from metadata.generated.schema.entity.data.table import Column, Table
        from metadata.data_quality.rules.rule_recommender import ColumnType
        
        # 转换表结构
        columns = []
        profiles = {}
        for col_req in request.table.columns:
            col_type = self.recommender.classify_data_type(col_req.data_type)
            col_category = self._infer_category(col_req.name)
            
            column = Column(
                name=Column.Name(root=col_req.name),
                dataType=Column.DataType(value=col_req.data_type.upper()),
                nullable=col_req.is_nullable,
            )
            columns.append(column)
            
            profiles[col_req.name] = ColumnProfile(
                name=col_req.name,
                data_type=col_type,
                category=col_category,
                is_nullable=col_req.is_nullable,
                is_primary_key=col_req.is_primary_key,
                is_foreign_key=col_req.is_foreign_key,
                is_unique=col_req.is_unique,
                sample_values=col_req.sample_values,
            )
        
        # 构建表对象
        table = Table(
            fullyQualifiedName=Table.fullyQualifiedName(root=request.table.table_fqn),
            name=Table.name(root=request.table.table_name or request.table.table_fqn.split('.')[-1]),
            columns=columns,
        )
        
        # 获取推荐
        all_recommendations = self.recommender.recommend_for_table(table)
        
        # 筛选
        if request.dimensions:
            dim_set = {QualityDimension(d) for d in request.dimensions}
            all_recommendations = [r for r in all_recommendations if r.dimension in dim_set]
        
        if request.min_confidence:
            all_recommendations = [r for r in all_recommendations if r.confidence >= request.min_confidence]
        
        # 构建规则响应
        recommended_rules = []
        dimension_summary: Dict[str, int] = {}
        severity_summary: Dict[str, int] = {}
        
        for rec in all_recommendations:
            rule_id = f"{rec.test_definition_name}_{rec.column_name or 'table'}"
            
            # 参数建议
            parameters = rec.parameters.copy()
            if request.include_parameters and rec.column_name and rec.column_name in profiles:
                profile = profiles[rec.column_name]
                param_suggestions = self.parameter_suggester.suggest_parameters(
                    test_definition_name=rec.test_definition_name,
                    column_profile=profile,
                )
                for suggestion in param_suggestions:
                    if suggestion.param_name not in parameters:
                        parameters[suggestion.param_name] = suggestion.suggested_value
            
            recommended_rules.append(RecommendedRuleResponse(
                rule_id=rule_id,
                test_definition_name=rec.test_definition_name,
                column_name=rec.column_name,
                dimension=rec.dimension.value if rec.dimension else "unknown",
                dimension_zh=rec.dimension.ZH_NAMES.get(rec.dimension) if rec.dimension else "未知",
                category=rec.category.value if rec.category else "unknown",
                severity=rec.severity.value if rec.severity else "MEDIUM",
                confidence=rec.confidence,
                reason=rec.reason,
                parameters=parameters,
            ))
            
            # 统计
            dim_key = rec.dimension.value if rec.dimension else "unknown"
            dimension_summary[dim_key] = dimension_summary.get(dim_key, 0) + 1
            sev_key = rec.severity.value if rec.severity else "MEDIUM"
            severity_summary[sev_key] = severity_summary.get(sev_key, 0) + 1
        
        # 缓存请求
        rid = request_id or str(datetime.now().timestamp())
        self._request_cache[rid] = request
        
        return RecommendationResponse(
            table_fqn=request.table.table_fqn,
            table_name=request.table.table_name or request.table.table_fqn.split('.')[-1],
            total_columns=len(request.table.columns),
            recommended_rules=recommended_rules,
            dimension_summary=dimension_summary,
            severity_summary=severity_summary,
            generated_at=datetime.now(),
            request_id=rid,
        )
    
    def batch_recommend(
        self,
        request: BatchRecommendationRequest,
    ) -> BatchRecommendationResponse:
        """批量规则推荐
        
        Args:
            request: 批量推荐请求
            
        Returns:
            批量推荐响应
        """
        results = []
        failed_tables = []
        total_rules = 0
        
        for table_req in request.tables:
            try:
                table_request = RuleRecommendationRequest(
                    table=table_req,
                    dimensions=request.dimensions,
                    min_confidence=request.min_confidence,
                )
                result = self.recommend(table_request)
                results.append(result)
                total_rules += len(result.recommended_rules)
            except Exception:
                failed_tables.append(table_req.table_fqn)
        
        return BatchRecommendationResponse(
            total_tables=len(request.tables),
            successful=len(results),
            failed=len(failed_tables),
            total_rules=total_rules,
            results=results,
            failed_tables=failed_tables,
        )
    
    def validate_recommendations(
        self,
        request: RuleValidationRequest,
    ) -> List[ValidationDetailResponse]:
        """校验推荐结果
        
        Args:
            request: 校验请求
            
        Returns:
            校验详情列表
        """
        # 获取推荐结果
        recommendation = self.recommend(request.recommendation)
        
        responses = []
        for rule in recommendation.recommended_rules:
            if rule.rule_id not in request.selected_rules:
                continue
            
            # 检查是否已存在校验记录
            existing = self.validator.get_validation_by_rule(rule.rule_id)
            
            if existing:
                responses.append(self._build_validation_response(existing))
                continue
            
            # 创建新的校验记录
            override_params = request.parameter_overrides.get(rule.rule_id, {})
            parameters = {**rule.parameters, **override_params}
            
            validation = self.validator.from_recommendation(
                recommendation=rule,
                created_by=request.validated_by,
                parameters=parameters,
            )
            
            responses.append(self._build_validation_response(validation))
        
        return responses
    
    def approve_rules(
        self,
        validation_ids: List[str],
        validated_by: str,
        comment: str = "",
    ) -> List[ValidationDetailResponse]:
        """批准规则
        
        Args:
            validation_ids: 校验记录ID列表
            validated_by: 审批人
            comment: 审批意见
            
        Returns:
            校验详情列表
        """
        updated = self.validator.bulk_approve(validation_ids, validated_by, comment)
        return [self._build_validation_response(v) for v in updated]
    
    def reject_rules(
        self,
        validation_ids: List[str],
        validated_by: str,
        reason: str,
    ) -> List[ValidationDetailResponse]:
        """拒绝规则
        
        Args:
            validation_ids: 校验记录ID列表
            validated_by: 审批人
            reason: 拒绝原因
            
        Returns:
            校验详情列表
        """
        responses = []
        for vid in validation_ids:
            try:
                updated = self.validator.reject_validation(vid, validated_by, reason)
                responses.append(self._build_validation_response(updated))
            except ValueError:
                continue
        return responses
    
    def get_pending_validations(
        self,
        dimension: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> List[ValidationDetailResponse]:
        """获取待校验列表
        
        Args:
            dimension: 维度筛选
            priority: 优先级筛选
            
        Returns:
            校验详情列表
        """
        dim = QualityDimension(dimension) if dimension else None
        pri = ValidationPriority(priority) if priority else None
        
        pending = self.validator.get_pending_validations(dim, pri)
        return [self._build_validation_response(v) for v in pending]
    
    def get_validation_summary(self) -> ValidationSummaryResponse:
        """获取校验汇总
        
        Returns:
            校验汇总响应
        """
        summary = self.validator.get_summary()
        
        return ValidationSummaryResponse(
            total_rules=summary.total_rules,
            pending_count=summary.pending_count,
            approved_count=summary.approved_count,
            rejected_count=summary.rejected_count,
            modified_count=summary.modified_count,
            deprecated_count=summary.deprecated_count,
            enabled_count=summary.enabled_count,
            disabled_count=summary.disabled_count,
            overdue_count=summary.overdue_count,
            urgent_count=summary.urgent_count,
        )
    
    def get_approved_rules(
        self,
        dimension: Optional[str] = None,
    ) -> List[ValidationDetailResponse]:
        """获取已批准的规则
        
        Args:
            dimension: 维度筛选
            
        Returns:
            校验详情列表
        """
        approved = self.validator.get_validations_by_status(ValidationStatus.APPROVED)
        
        if dimension:
            approved = [
                v for v in approved
                if dimension in v.tags
            ]
        
        return [self._build_validation_response(v) for v in approved]
    
    def _infer_category(self, column_name: str) -> ColumnCategory:
        """推断列分类"""
        name_lower = column_name.lower()
        
        patterns = [
            (ColumnCategory.ID, ["_id", "^id$", "_key", "_pk", "_uuid"]),
            (ColumnCategory.NAME, ["_name", "_user", "_customer"]),
            (ColumnCategory.PHONE, ["_phone", "_mobile", "_tel"]),
            (ColumnCategory.EMAIL, ["_email", "_mail"]),
            (ColumnCategory.AMOUNT, ["_amount", "_price", "_cost", "_total", "_balance"]),
            (ColumnCategory.STATUS, ["_status", "_state", "_flag"]),
            (ColumnCategory.DATETIME, ["_time", "_date", "_created", "_updated"]),
        ]
        
        for category, patterns_list in patterns:
            for pattern in patterns_list:
                import re
                if re.search(pattern, name_lower):
                    return category
        
        return ColumnCategory.OTHER
    
    def _build_validation_response(
        self,
        validation: ValidationRecord,
    ) -> ValidationDetailResponse:
        """构建校验响应"""
        return ValidationDetailResponse(
            validation_id=validation.validation_id,
            rule_id=validation.rule_id,
            rule_name=validation.rule_name,
            status=validation.status.value,
            enabled=validation.enabled,
            created_at=validation.created_at,
            created_by=validation.created_by,
            validated_by=validation.validated_by,
            validated_at=validation.validated_at,
            priority=validation.priority.value,
            due_date=validation.due_date,
            original_parameters=validation.original_parameters,
            modified_parameters=validation.modified_parameters,
            parameter_changes=[
                {
                    "parameter_name": pc.parameter_name,
                    "original_value": pc.original_value,
                    "new_value": pc.new_value,
                    "change_reason": pc.change_reason,
                }
                for pc in validation.parameter_changes
            ],
            tags=list(validation.tags),
            statistics=self.validator.get_statistics(validation.rule_id),
        )
