#  Copyright 2025 Collate
#  Licensed under the Collate Community License, Version 1.0 (the "License");
#  you may not use this file except in compliance with the License.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""
数据质量评价扩展模块

基于《GB/T 36344-2018 信息技术 数据质量评价指标》国家标准

功能模块：
1. 维度评估 - 六维度全面支持和评分
2. 规则推荐 - 基于表/列属性自动选择规则
3. 参数建议 - 基于采样数据自动设置参数
4. 血缘溯源 - 基于血缘关系分析质量问题根源
"""

from metadata.data_quality.dimension.models import (
    QualityDimension,
    QualityRuleCategory,
    DimensionWeight,
    DEFAULT_DIMENSION_WEIGHTS,
    RULE_CATEGORY_TO_DIMENSION,
    TEST_DEFINITION_TO_CATEGORY,
    get_dimension_by_test_definition,
    get_dimension_weight,
)

from metadata.data_quality.dimension.evaluator import (
    DimensionEvaluator,
    DimensionResult,
    QualityAssessmentResult,
    TestResultSummary,
    RuleSeverity,
    SEVERITY_WEIGHTS,
)

from metadata.data_quality.rules.rule_recommender import (
    RuleRecommender,
    ColumnType,
    ColumnCategory,
    ColumnProfile,
    RuleRecommendation,
)

from metadata.data_quality.rules.parameter_suggester import (
    ParameterSuggester,
    SampleAnalysis,
    ParameterSuggestion,
    RuleParameterConfig,
)

from metadata.data_quality.lineage.quality_lineage_analyzer import (
    QualityLineageAnalyzer,
    LineageDirection,
    LineageNode,
    QualityIssue,
    QualityPropagation,
    RootCauseAnalysis,
    LineageQualitySummary,
)

from metadata.data_quality.rules.rule_validator import (
    RuleValidator,
    ValidationStatus,
    ValidationPriority,
    ValidationRecord,
    ValidationSummary,
    ParameterChange,
)

from metadata.data_quality.rules.rule_library import (
    RuleLibrary,
    RuleTemplate,
    RuleScript,
    RuleThreshold,
    RuleApplicability,
    RuleExecutionEngine,
    RuleSourceType,
    RuleEntityType,
    RuleStatus,
    RuleValidationLevel,
    ScriptPreview,
    RuleReusePlan,
    RuleImportResult,
    RuleLibrarySummary,
    build_default_rule_templates,
)

from metadata.data_quality.rules.intelligent_rule_recommender import (
    DataDictionaryEntry,
    FieldLineageHint,
    FieldMetadata,
    TableMetadata,
    RecommendationEvidence,
    IntelligentRuleRecommendation,
    IntelligentRuleRecommender,
)

from metadata.data_quality.api.quality_assessment_api import (
    QualityAssessmentAPI,
    QualityAssessmentRequest,
    QualityAssessmentResponse,
    DimensionScoreResponse,
    AssessmentTrendResponse,
)

from metadata.data_quality.api.rule_recommendation_api import (
    RuleRecommendationAPI,
    RuleRecommendationRequest,
    RecommendationResponse,
    ValidationSummaryResponse,
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
    LineageGraphResponse,
    ImpactedTableResponse,
    RootCauseResponse,
)

from metadata.data_quality.workflow.quality_assessment_workflow import (
    DataScope,
    IssueStatus,
    QualityAssessmentWorkflow,
    QualityDashboard,
    QualityIssueRecord,
    QualityTaskConfig,
    QualityTaskRunResult,
    RuleParameterSetting,
    ScanMode,
    ScoringArchive,
    TaskRunStatus,
    TaskScheduleType,
    ValidationTrialResult,
)

from metadata.data_quality.api.quality_workflow_api import (
    QualityWorkflowAPI,
    DataScopeRequest,
    ConfigureRuleParameterRequest,
    TrialRunRequest,
    CreateQualityTaskRequest,
    ExecuteQualityTaskRequest,
    IssueQueryRequest,
    IssueStatusUpdateRequest,
    ScoringArchiveRequest,
    WorkflowReportRequest,
)

from metadata.data_quality.reports.quality_report import (
    QualityReportGenerator,
    QualityReport,
)

__all__ = [
    # 维度模型
    "QualityDimension",
    "QualityRuleCategory", 
    "DimensionWeight",
    "DEFAULT_DIMENSION_WEIGHTS",
    "get_dimension_by_test_definition",
    "get_dimension_weight",
    
    # 维度评估
    "DimensionEvaluator",
    "DimensionResult",
    "QualityAssessmentResult",
    "TestResultSummary",
    "RuleSeverity",
    "SEVERITY_WEIGHTS",
    
    # 规则推荐
    "RuleRecommender",
    "ColumnType",
    "ColumnCategory",
    "ColumnProfile",
    "RuleRecommendation",
    
    # 参数建议
    "ParameterSuggester",
    "SampleAnalysis",
    "ParameterSuggestion",
    "RuleParameterConfig",
    
    # 血缘分析
    "QualityLineageAnalyzer",
    "LineageDirection",
    "LineageNode",
    "QualityIssue",
    "QualityPropagation",
    "RootCauseAnalysis",
    "LineageQualitySummary",
    
    # 规则校验
    "RuleValidator",
    "ValidationStatus",
    "ValidationPriority",
    "ValidationRecord",
    "ValidationSummary",
    "ParameterChange",

    # 规则库
    "RuleLibrary",
    "RuleTemplate",
    "RuleScript",
    "RuleThreshold",
    "RuleApplicability",
    "RuleExecutionEngine",
    "RuleSourceType",
    "RuleEntityType",
    "RuleStatus",
    "RuleValidationLevel",
    "ScriptPreview",
    "RuleReusePlan",
    "RuleImportResult",
    "RuleLibrarySummary",
    "build_default_rule_templates",

    # 智能规则推荐
    "DataDictionaryEntry",
    "FieldLineageHint",
    "FieldMetadata",
    "TableMetadata",
    "RecommendationEvidence",
    "IntelligentRuleRecommendation",
    "IntelligentRuleRecommender",
    
    # 质量评估 API
    "QualityAssessmentAPI",
    "QualityAssessmentRequest",
    "QualityAssessmentResponse",
    "DimensionScoreResponse",
    "AssessmentTrendResponse",
    
    # 规则推荐 API
    "RuleRecommendationAPI",
    "RuleRecommendationRequest",
    "RecommendationResponse",
    "ValidationSummaryResponse",

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
    "LineageGraphResponse",
    "ImpactedTableResponse",
    "RootCauseResponse",

    # 质量评价流程
    "DataScope",
    "IssueStatus",
    "QualityAssessmentWorkflow",
    "QualityDashboard",
    "QualityIssueRecord",
    "QualityTaskConfig",
    "QualityTaskRunResult",
    "RuleParameterSetting",
    "ScanMode",
    "ScoringArchive",
    "TaskRunStatus",
    "TaskScheduleType",
    "ValidationTrialResult",

    # 质量评价流程 API
    "QualityWorkflowAPI",
    "DataScopeRequest",
    "ConfigureRuleParameterRequest",
    "TrialRunRequest",
    "CreateQualityTaskRequest",
    "ExecuteQualityTaskRequest",
    "IssueQueryRequest",
    "IssueStatusUpdateRequest",
    "ScoringArchiveRequest",
    "WorkflowReportRequest",
    
    # 报告生成
    "QualityReportGenerator",
    "QualityReport",
]
