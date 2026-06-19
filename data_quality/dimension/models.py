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
数据质量评价维度模型

依据《GB/T 36344-2018 信息技术 数据质量评价指标》国家标准
定义六大质量评价维度及其权重配置
"""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class QualityDimension(str, Enum):
    """数据质量评价维度枚举"""
    
    NORMATIVITY = "normativity"      # 规范性
    COMPLETENESS = "completeness"    # 完整性
    ACCURACY = "accuracy"            # 准确性
    CONSISTENCY = "consistency"      # 一致性
    TIMELINESS = "timeliness"       # 时效性
    ACCESSIBILITY = "accessibility"  # 可访问性
    
    # 中文名称映射
    ZH_NAMES = {
        NORMATIVITY: "规范性",
        COMPLETENESS: "完整性",
        ACCURACY: "准确性",
        CONSISTENCY: "一致性",
        TIMELINESS: "时效性",
        ACCESSIBILITY: "可访问性",
    }
    
    # 英文名称映射
    EN_NAMES = {
        NORMATIVITY: "Normativity",
        COMPLETENESS: "Completeness",
        ACCURACY: "Accuracy",
        CONSISTENCY: "Consistency",
        TIMELINESS: "Timeliness",
        ACCESSIBILITY: "Accessibility",
    }


class DimensionWeight(BaseModel):
    """维度权重配置"""
    
    dimension: QualityDimension
    weight: float = Field(..., ge=0, le=1, description="维度权重（0-1）")
    sub_dimensions: Dict[str, float] = Field(
        default_factory=dict,
        description="子维度权重映射"
    )
    
    class Config:
        use_enum_values = True


class QualityRuleCategory(str, Enum):
    """质量规则分类"""
    
    # 规范性规则
    FORMAT_CHECK = "format_check"          # 格式校验
    ENUM_CHECK = "enum_check"              # 枚举值校验
    REGEX_CHECK = "regex_check"            # 正则表达式校验
    
    # 完整性规则
    NULL_CHECK = "null_check"              # 空值校验
    FILL_RATE_CHECK = "fill_rate_check"    # 填充率校验
    REFERENCE_CHECK = "reference_check"     # 引用完整性校验
    
    # 准确性规则
    RANGE_CHECK = "range_check"            # 范围校验
    PRECISION_CHECK = "precision_check"    # 精度校验
    DUPLICATE_CHECK = "duplicate_check"    # 重复值校验
    DIRTY_DATA_CHECK = "dirty_data_check"  # 脏数据检测
    
    # 一致性规则
    CROSS_TABLE_CHECK = "cross_table_check"      # 跨表一致性
    CROSS_SYSTEM_CHECK = "cross_system_check"     # 跨系统一致性
    CALCULATION_CHECK = "calculation_check"       # 计算一致性
    
    # 时效性规则
    UPDATE_LATENCY_CHECK = "update_latency_check"  # 更新延迟校验
    TIME_SEQUENCE_CHECK = "time_sequence_check"   # 时间顺序校验
    HISTORY_VALIDITY_CHECK = "history_validity_check"  # 历史数据有效性
    
    # 可访问性规则
    ACCESSIBLE_CHECK = "accessible_check"          # 可访问性校验
    PERFORMANCE_CHECK = "performance_check"       # 性能校验
    UNIQUENESS_CHECK = "uniqueness_check"        # 唯一性校验


# 国标推荐的六大维度权重配置
DEFAULT_DIMENSION_WEIGHTS: List[DimensionWeight] = [
    DimensionWeight(
        dimension=QualityDimension.NORMATIVITY,
        weight=0.20,
        sub_dimensions={
            "dataStandard": 0.60,  # 数据标准
            "businessRule": 0.40,  # 业务规则
        }
    ),
    DimensionWeight(
        dimension=QualityDimension.COMPLETENESS,
        weight=0.20,
        sub_dimensions={
            "elementCompleteness": 0.50,  # 数据元素完整性
            "recordCompleteness": 0.50,   # 数据记录完整性
        }
    ),
    DimensionWeight(
        dimension=QualityDimension.ACCURACY,
        weight=0.15,
        sub_dimensions={
            "formatAccuracy": 0.25,       # 数据格式准确性
            "duplicationRate": 0.25,      # 数据重复率
            "dirtyDataRate": 0.25,        # 脏数据出现率
            "valueRangeValidation": 0.25,  # 值域校验
        }
    ),
    DimensionWeight(
        dimension=QualityDimension.CONSISTENCY,
        weight=0.15,
        sub_dimensions={
            "sameDataConsistency": 0.25,    # 相同数据一致性
            "relatedDataLogic": 0.75,       # 关联数据逻辑性
        }
    ),
    DimensionWeight(
        dimension=QualityDimension.TIMELINESS,
        weight=0.15,
        sub_dimensions={
            "timePeriodAccuracy": 0.40,     # 基于时间段的正确性
            "timePointTimeliness": 0.30,   # 基于时间点的及时性
            "sequenceTimeliness": 0.30,    # 时序性
        }
    ),
    DimensionWeight(
        dimension=QualityDimension.ACCESSIBILITY,
        weight=0.15,
        sub_dimensions={
            "accessibility": 0.35,         # 可访问性
            "availability": 0.30,           # 可用性
            "understandability": 0.35,      # 数据可理解性
        }
    ),
]


# 规则分类到维度的映射
RULE_CATEGORY_TO_DIMENSION: Dict[QualityRuleCategory, QualityDimension] = {
    # 规范性维度
    QualityRuleCategory.FORMAT_CHECK: QualityDimension.NORMATIVITY,
    QualityRuleCategory.ENUM_CHECK: QualityDimension.NORMATIVITY,
    QualityRuleCategory.REGEX_CHECK: QualityDimension.NORMATIVITY,
    
    # 完整性维度
    QualityRuleCategory.NULL_CHECK: QualityDimension.COMPLETENESS,
    QualityRuleCategory.FILL_RATE_CHECK: QualityDimension.COMPLETENESS,
    QualityRuleCategory.REFERENCE_CHECK: QualityDimension.COMPLETENESS,
    
    # 准确性维度
    QualityRuleCategory.RANGE_CHECK: QualityDimension.ACCURACY,
    QualityRuleCategory.PRECISION_CHECK: QualityDimension.ACCURACY,
    QualityRuleCategory.DUPLICATE_CHECK: QualityDimension.ACCURACY,
    QualityRuleCategory.DIRTY_DATA_CHECK: QualityDimension.ACCURACY,
    
    # 一致性维度
    QualityRuleCategory.CROSS_TABLE_CHECK: QualityDimension.CONSISTENCY,
    QualityRuleCategory.CROSS_SYSTEM_CHECK: QualityDimension.CONSISTENCY,
    QualityRuleCategory.CALCULATION_CHECK: QualityDimension.CONSISTENCY,
    
    # 时效性维度
    QualityRuleCategory.UPDATE_LATENCY_CHECK: QualityDimension.TIMELINESS,
    QualityRuleCategory.TIME_SEQUENCE_CHECK: QualityDimension.TIMELINESS,
    QualityRuleCategory.HISTORY_VALIDITY_CHECK: QualityDimension.TIMELINESS,
    
    # 可访问性维度
    QualityRuleCategory.ACCESSIBLE_CHECK: QualityDimension.ACCESSIBILITY,
    QualityRuleCategory.PERFORMANCE_CHECK: QualityDimension.ACCESSIBILITY,
    QualityRuleCategory.UNIQUENESS_CHECK: QualityDimension.ACCESSIBILITY,
}


# 测试定义名称到规则分类的映射
TEST_DEFINITION_TO_CATEGORY: Dict[str, QualityRuleCategory] = {
    # 规范性
    "columnValuesToMatchRegex": QualityRuleCategory.REGEX_CHECK,
    "columnValuesToBeInSet": QualityRuleCategory.ENUM_CHECK,
    "tableColumnToMatchSet": QualityRuleCategory.FORMAT_CHECK,
    
    # 完整性
    "columnValuesToBeNotNull": QualityRuleCategory.NULL_CHECK,
    "columnValuesMissingCount": QualityRuleCategory.NULL_CHECK,
    
    # 准确性
    "columnValuesToBeBetween": QualityRuleCategory.RANGE_CHECK,
    "columnValueMinToBeBetween": QualityRuleCategory.RANGE_CHECK,
    "columnValueMaxToBeBetween": QualityRuleCategory.RANGE_CHECK,
    "columnValueMeanToBeBetween": QualityRuleCategory.RANGE_CHECK,
    "columnValueMedianToBeBetween": QualityRuleCategory.RANGE_CHECK,
    "columnValuesSumToBeBetween": QualityRuleCategory.RANGE_CHECK,
    "columnValueStdDevToBeBetween": QualityRuleCategory.RANGE_CHECK,
    
    # 一致性
    "tableDiff": QualityRuleCategory.CROSS_TABLE_CHECK,
    "tableCustomSQLQuery": QualityRuleCategory.CALCULATION_CHECK,
    
    # 时效性
    "tableRowInsertedCountToBeBetween": QualityRuleCategory.UPDATE_LATENCY_CHECK,
    
    # 可访问性
    "tableRowCountToBeBetween": QualityRuleCategory.ACCESSIBLE_CHECK,
    "tableRowCountToEqual": QualityRuleCategory.ACCESSIBLE_CHECK,
    "columnValuesToBeUnique": QualityRuleCategory.UNIQUENESS_CHECK,
    "tableColumnCountToBeBetween": QualityRuleCategory.ACCESSIBLE_CHECK,
    "tableColumnNameToExist": QualityRuleCategory.ACCESSIBLE_CHECK,
}


def get_dimension_by_test_definition(test_definition_name: str) -> Optional[QualityDimension]:
    """根据测试定义名称获取对应的质量维度
    
    Args:
        test_definition_name: 测试定义名称
        
    Returns:
        对应的质量维度，如果未找到则返回 None
    """
    category = TEST_DEFINITION_TO_CATEGORY.get(test_definition_name)
    if category:
        return RULE_CATEGORY_TO_DIMENSION.get(category)
    return None


def get_dimension_weight(
    dimension: QualityDimension,
    weights: Optional[List[DimensionWeight]] = None
) -> float:
    """获取指定维度的权重值
    
    Args:
        dimension: 质量维度
        weights: 权重配置列表，默认使用国标配置
        
    Returns:
        维度权重值
    """
    weights = weights or DEFAULT_DIMENSION_WEIGHTS
    for w in weights:
        if w.dimension == dimension:
            return w.weight
    return 0.0
