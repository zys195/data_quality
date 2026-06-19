#  Copyright 2025 Collate
#  Licensed under the Collate Community License, Version 1.0 (the "License");
#  you may not use this file except in compliance with the License.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""
数据质量评估 API 模块

提供 REST API 接口用于质量评估、规则推荐和血缘分析
"""

from metadata.data_quality.api.quality_assessment_api import (
    QualityAssessmentAPI,
    QualityAssessmentRequest,
    QualityAssessmentResponse,
    BatchAssessmentRequest,
    BatchAssessmentResponse,
    DimensionScoreResponse,
    AssessmentTrendResponse,
    CriticalFailureResponse,
)

from metadata.data_quality.api.rule_recommendation_api import (
    RuleRecommendationAPI,
    RuleRecommendationRequest,
    RecommendationResponse,
    RecommendedRuleResponse,
    RuleValidationRequest,
    ValidationSummaryResponse,
    ValidationDetailResponse,
)

from metadata.data_quality.api.rule_library_api import (
    RuleLibraryAPI,
    RuleImportRequest,
    RuleCreateRequest,
    RuleUpdateRequest,
    RuleDeleteRequest,
    RuleQueryRequest,
    RuleScriptPreviewRequest,
    RuleReuseRequest,
    RuleTemplateResponse,
    RuleImportResponse,
    RuleListResponse,
    RuleScriptPreviewResponse,
    RuleReuseResponse,
    RuleLibrarySummaryResponse,
)

from metadata.data_quality.api.intelligent_rule_recommendation_api import (
    DataDictionaryEntryRequest,
    FieldLineageHintRequest,
    FieldMetadataRequest,
    TableMetadataRequest,
    IntelligentRecommendationRequest,
    RecommendationEvidenceResponse,
    IntelligentRuleRecommendationResponse,
    IntelligentRecommendationResponse,
    RecommendationConfirmation,
    RecommendationConfirmRequest,
    ConfirmedRecommendationResponse,
    IntelligentRuleRecommendationAPI,
)

from metadata.data_quality.api.lineage_analysis_api import (
    LineageAnalysisAPI,
    QualityIssueRequest,
    LineageGraphResponse,
    ImpactAnalysisRequest,
    ImpactedTableResponse,
    RootCauseRequest,
    RootCauseResponse,
)

from metadata.data_quality.api.quality_workflow_api import (
    DataScopeRequest,
    ConfigureRuleParameterRequest,
    PreviewWorkflowRuleRequest,
    TrialRunRequest,
    CreateQualityTaskRequest,
    ExecuteQualityTaskRequest,
    DashboardQueryRequest,
    IssueQueryRequest,
    IssueStatusUpdateRequest,
    ScoringArchiveRequest,
    WorkflowReportRequest,
    QualityWorkflowAPI,
)

__all__ = [
    # 质量评估 API
    "QualityAssessmentAPI",
    "QualityAssessmentRequest",
    "QualityAssessmentResponse",
    "BatchAssessmentRequest",
    "BatchAssessmentResponse",
    "DimensionScoreResponse",
    "AssessmentTrendResponse",
    "CriticalFailureResponse",
    
    # 规则推荐 API
    "RuleRecommendationAPI",
    "RuleRecommendationRequest",
    "RecommendationResponse",
    "RecommendedRuleResponse",
    "RuleValidationRequest",
    "ValidationSummaryResponse",
    "ValidationDetailResponse",

    # 规则库 API
    "RuleLibraryAPI",
    "RuleImportRequest",
    "RuleCreateRequest",
    "RuleUpdateRequest",
    "RuleDeleteRequest",
    "RuleQueryRequest",
    "RuleScriptPreviewRequest",
    "RuleReuseRequest",
    "RuleTemplateResponse",
    "RuleImportResponse",
    "RuleListResponse",
    "RuleScriptPreviewResponse",
    "RuleReuseResponse",
    "RuleLibrarySummaryResponse",

    # 智能规则推荐 API
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
    
    # 血缘分析 API
    "LineageAnalysisAPI",
    "QualityIssueRequest",
    "LineageGraphResponse",
    "ImpactAnalysisRequest",
    "ImpactedTableResponse",
    "RootCauseRequest",
    "RootCauseResponse",

    # 质量评价流程 API
    "DataScopeRequest",
    "ConfigureRuleParameterRequest",
    "PreviewWorkflowRuleRequest",
    "TrialRunRequest",
    "CreateQualityTaskRequest",
    "ExecuteQualityTaskRequest",
    "DashboardQueryRequest",
    "IssueQueryRequest",
    "IssueStatusUpdateRequest",
    "ScoringArchiveRequest",
    "WorkflowReportRequest",
    "QualityWorkflowAPI",
]
