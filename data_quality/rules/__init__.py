#  Copyright 2025 Collate
#  Licensed under the Collate Community License, Version 1.0 (the "License");
#  you may not use this file except in compliance with the License.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""
数据质量规则模块

包含规则推荐、参数建议和规则校验功能
"""

from metadata.data_quality.rules.rule_recommender import (
    RuleRecommender,
    ColumnType,
    ColumnCategory,
    ColumnProfile,
    RuleRecommendation,
)

from metadata.data_quality.rules.parameter_suggester import (
    ParameterSuggester,
    ParameterSuggestion,
    RuleParameterConfig,
    SampleAnalysis,
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

__all__ = [
    # 规则推荐
    "RuleRecommender",
    "ColumnType",
    "ColumnCategory",
    "ColumnProfile",
    "RuleRecommendation",
    
    # 参数建议
    "ParameterSuggester",
    "ParameterSuggestion",
    "RuleParameterConfig",
    "SampleAnalysis",
    
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
]
