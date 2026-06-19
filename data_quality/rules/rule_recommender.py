#  Copyright 2025 Collate
#  Licensed under the Collate Community License, Version 1.0 (the "License");
#  you may not use this file except in compliance with the License.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""
规则推荐引擎

根据表和列的元数据属性，自动推荐适用的质量规则
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum

from metadata.data_quality.dimension.models import (
    QualityDimension,
    QualityRuleCategory,
    get_dimension_by_test_definition,
)
from metadata.data_quality.dimension.evaluator import RuleSeverity
from metadata.generated.schema.entity.data.table import Column, Table


class ColumnType(str, Enum):
    """列数据类型分类"""
    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    DATE = "date"
    TIME = "time"
    TIMESTAMP = "timestamp"
    BINARY = "binary"
    COMPLEX = "complex"  # ARRAY, MAP, STRUCT
    UNKNOWN = "unknown"


class ColumnCategory(str, Enum):
    """列业务分类"""
    ID = "id"                    # 主键/外键
    NAME = "name"               # 名称
    PHONE = "phone"             # 电话
    EMAIL = "email"              # 邮箱
    ADDRESS = "address"          # 地址
    AMOUNT = "amount"            # 金额
    QUANTITY = "quantity"        # 数量
    DATETIME = "datetime"        # 时间
    STATUS = "status"            # 状态
    CODE = "code"               # 编码
    DESCRIPTION = "description" # 描述
    AGE = "age"                  # 年龄
    GENDER = "gender"           # 性别
    URL = "url"                 # URL
    IP = "ip"                   # IP 地址
    LICENSE_PLATE = "license_plate"  # 车牌号
    IMEI = "imei"               # 移动设备识别码
    MAC = "mac"                 # MAC 地址
    ID_CARD = "id_card"         # 身份证
    CREDIT_CARD = "credit_card" # 信用卡
    OTHER = "other"


@dataclass
class RuleRecommendation:
    """规则推荐"""
    test_definition_name: str
    column_name: Optional[str] = None
    dimension: Optional[QualityDimension] = None
    category: Optional[QualityRuleCategory] = None
    severity: RuleSeverity = RuleSeverity.MEDIUM
    confidence: float = 1.0  # 推荐置信度 0-1
    reason: str = ""  # 推荐理由
    parameters: Dict[str, str] = field(default_factory=dict)  # 预填充参数


@dataclass
class ColumnProfile:
    """列特征画像"""
    name: str
    data_type: ColumnType
    category: ColumnCategory
    is_nullable: bool
    is_primary_key: bool
    is_foreign_key: bool
    is_unique: bool
    nullable_ratio: float = 0.0  # 空值比例
    unique_ratio: float = 0.0  # 唯一值比例
    min_value: Optional[str] = None
    max_value: Optional[str] = None
    avg_value: Optional[float] = None
    sample_values: List[str] = field(default_factory=list)
    matched_patterns: Set[str] = field(default_factory=set)  # 匹配的模式


# 列名模式匹配规则
COLUMN_NAME_PATTERNS: Dict[ColumnCategory, List[str]] = {
    ColumnCategory.ID: [
        r".*_?id$", r"^id$", r".*_?key$", r".*_?pk$", r".*_?uuid$",
    ],
    ColumnCategory.NAME: [
        r".*_?name$", r".*_?name$", r"^name$", r"^full_?name$",
        r".*_?username$", r".*_?customer_?name", r".*_?user_?name",
    ],
    ColumnCategory.PHONE: [
        r".*_?phone", r".*_?mobile", r".*_?tel", r".*_?cell",
    ],
    ColumnCategory.EMAIL: [
        r".*_?email", r".*_?mail",
    ],
    ColumnCategory.ADDRESS: [
        r".*_?address", r".*_?addr", r".*_?location", r".*_?city",
        r".*_?province", r".*_?region", r".*_?country",
    ],
    ColumnCategory.AMOUNT: [
        r".*_?amount", r".*_?price", r".*_?cost", r".*_?total",
        r".*_?balance", r".*_?credit", r".*_?debit", r".*_?fee",
        r".*_?revenue", r".*_?profit",
    ],
    ColumnCategory.QUANTITY: [
        r".*_?qty", r".*_?quantity", r".*_?count", r".*_?num",
        r".*_?stock", r".*_?inventory",
    ],
    ColumnCategory.DATETIME: [
        r".*_?time", r".*_?date", r".*_?created", r".*_?updated",
        r".*_?modified", r".*_?deleted", r".*_?start", r".*_?end",
        r"^dt$", r"^timestamp$",
    ],
    ColumnCategory.STATUS: [
        r".*_?status", r".*_?state", r".*_?flag", r".*_?type",
        r".*_?category$", r".*_?kind$",
    ],
    ColumnCategory.CODE: [
        r".*_?code", r".*_?no$", r".*_?number", r".*_?zip",
        r".*_?postal", r".*_?industry", r".*_?region",
    ],
    ColumnCategory.DESCRIPTION: [
        r".*_?desc", r".*_?description", r".*_?remark",
        r".*_?note", r".*_?comment", r".*_?memo",
    ],
    ColumnCategory.AGE: [
        r".*_?age$",
    ],
    ColumnCategory.GENDER: [
        r".*_?gender$", r".*_?sex$",
    ],
    ColumnCategory.URL: [
        r".*_?url$", r".*_?link$", r".*_?href$", r".*_?website",
    ],
    ColumnCategory.IP: [
        r".*_?ip", r".*_?ipv4", r".*_?ipv6",
    ],
    ColumnCategory.LICENSE_PLATE: [
        r".*_?plate", r".*_?car_?no", r".*_?vehicle_?no", r".*_?license_?no",
        r".*_?车牌",
    ],
    ColumnCategory.IMEI: [
        r".*_?imei", r".*_?device_?id", r".*_?设备号",
    ],
    ColumnCategory.MAC: [
        r".*_?mac", r".*_?mac_?addr", r".*_?物理地址",
    ],
    ColumnCategory.ID_CARD: [
        r".*_?id_?card", r".*_?cert", r".*_?证件", r".*_?sfz",
    ],
    ColumnCategory.CREDIT_CARD: [
        r".*_?card", r".*_?credit", r".*_?bank",
    ],
}


# 数据类型到列类型的映射
DATA_TYPE_TO_COLUMN_TYPE: Dict[str, ColumnType] = {
    # String types
    "varchar": ColumnType.STRING,
    "char": ColumnType.STRING,
    "text": ColumnType.STRING,
    "string": ColumnType.STRING,
    "nvarchar": ColumnType.STRING,
    "nchar": ColumnType.STRING,
    "ntext": ColumnType.STRING,
    
    # Integer types
    "int": ColumnType.INTEGER,
    "bigint": ColumnType.INTEGER,
    "smallint": ColumnType.INTEGER,
    "tinyint": ColumnType.INTEGER,
    "integer": ColumnType.INTEGER,
    "int64": ColumnType.INTEGER,
    "int32": ColumnType.INTEGER,
    "int16": ColumnType.INTEGER,
    
    # Decimal types
    "decimal": ColumnType.DECIMAL,
    "numeric": ColumnType.DECIMAL,
    "float": ColumnType.DECIMAL,
    "double": ColumnType.DECIMAL,
    "real": ColumnType.DECIMAL,
    "money": ColumnType.DECIMAL,
    
    # Boolean types
    "boolean": ColumnType.BOOLEAN,
    "bool": ColumnType.BOOLEAN,
    "bit": ColumnType.BOOLEAN,
    
    # Date/Time types
    "date": ColumnType.DATE,
    "time": ColumnType.TIME,
    "datetime": ColumnType.DATETIME,
    "datetime2": ColumnType.DATETIME,
    "timestamp": ColumnType.TIMESTAMP,
    "datetimeoffset": ColumnType.TIMESTAMP,
    
    # Binary types
    "binary": ColumnType.BINARY,
    "varbinary": ColumnType.BINARY,
    "blob": ColumnType.BINARY,
    
    # Complex types
    "array": ColumnType.COMPLEX,
    "map": ColumnType.COMPLEX,
    "struct": ColumnType.COMPLEX,
    "json": ColumnType.COMPLEX,
    "variant": ColumnType.COMPLEX,
}


# 列类型推荐的规则
COLUMN_TYPE_RECOMMENDED_RULES: Dict[ColumnType, List[Tuple[str, RuleSeverity]]] = {
    ColumnType.STRING: [
        ("columnValuesToBeNotNull", RuleSeverity.HIGH),
        ("columnValuesToBeUnique", RuleSeverity.MEDIUM),
    ],
    ColumnType.INTEGER: [
        ("columnValuesToBeNotNull", RuleSeverity.HIGH),
        ("columnValueMinToBeBetween", RuleSeverity.MEDIUM),
        ("columnValueMaxToBeBetween", RuleSeverity.MEDIUM),
    ],
    ColumnType.DECIMAL: [
        ("columnValuesToBeNotNull", RuleSeverity.HIGH),
        ("columnValueMinToBeBetween", RuleSeverity.HIGH),
        ("columnValueMaxToBeBetween", RuleSeverity.HIGH),
    ],
    ColumnType.DATETIME: [
        ("columnValuesToBeNotNull", RuleSeverity.HIGH),
        ("columnValueMinToBeBetween", RuleSeverity.MEDIUM),
        ("columnValueMaxToBeBetween", RuleSeverity.MEDIUM),
    ],
    ColumnType.BOOLEAN: [
        ("columnValuesToBeNotNull", RuleSeverity.MEDIUM),
        ("columnValuesToBeInSet", RuleSeverity.HIGH),
    ],
}


# 列分类推荐的规则
COLUMN_CATEGORY_RECOMMENDED_RULES: Dict[ColumnCategory, List[RuleRecommendation]] = {
    ColumnCategory.ID: [
        RuleRecommendation(
            test_definition_name="columnValuesToBeNotNull",
            category=QualityRuleCategory.NULL_CHECK,
            dimension=QualityDimension.COMPLETENESS,
            severity=RuleSeverity.CRITICAL,
            reason="主键字段不允许为空",
        ),
        RuleRecommendation(
            test_definition_name="columnValuesToBeUnique",
            category=QualityRuleCategory.UNIQUENESS_CHECK,
            dimension=QualityDimension.ACCESSIBILITY,
            severity=RuleSeverity.CRITICAL,
            reason="主键值必须唯一",
        ),
    ],
    ColumnCategory.PHONE: [
        RuleRecommendation(
            test_definition_name="columnValuesToMatchRegex",
            dimension=QualityDimension.NORMATIVITY,
            category=QualityRuleCategory.REGEX_CHECK,
            severity=RuleSeverity.HIGH,
            reason="验证手机号格式",
            parameters={"regex": "^1[3-9]\\d{9}$"},
        ),
        RuleRecommendation(
            test_definition_name="columnValuesToBeNotNull",
            category=QualityRuleCategory.NULL_CHECK,
            dimension=QualityDimension.COMPLETENESS,
            severity=RuleSeverity.HIGH,
            reason="手机号为必填字段",
        ),
    ],
    ColumnCategory.EMAIL: [
        RuleRecommendation(
            test_definition_name="columnValuesToMatchRegex",
            dimension=QualityDimension.NORMATIVITY,
            category=QualityRuleCategory.REGEX_CHECK,
            severity=RuleSeverity.MEDIUM,
            reason="验证邮箱格式",
            parameters={"regex": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"},
        ),
        RuleRecommendation(
            test_definition_name="columnValuesToBeNotNull",
            category=QualityRuleCategory.NULL_CHECK,
            dimension=QualityDimension.COMPLETENESS,
            severity=RuleSeverity.MEDIUM,
        ),
    ],
    ColumnCategory.AMOUNT: [
        RuleRecommendation(
            test_definition_name="columnValueMinToBeBetween",
            category=QualityRuleCategory.RANGE_CHECK,
            dimension=QualityDimension.ACCURACY,
            severity=RuleSeverity.HIGH,
            reason="金额不能为负数",
            parameters={"minValue": "0"},
        ),
        RuleRecommendation(
            test_definition_name="columnValuesToBeNotNull",
            category=QualityRuleCategory.NULL_CHECK,
            dimension=QualityDimension.COMPLETENESS,
            severity=RuleSeverity.CRITICAL,
            reason="金额字段不允许为空",
        ),
    ],
    ColumnCategory.AGE: [
        RuleRecommendation(
            test_definition_name="columnValueMinToBeBetween",
            category=QualityRuleCategory.RANGE_CHECK,
            dimension=QualityDimension.ACCURACY,
            severity=RuleSeverity.MEDIUM,
            reason="年龄范围合理性",
            parameters={"minValue": "0", "maxValue": "120"},
        ),
    ],
    ColumnCategory.GENDER: [
        RuleRecommendation(
            test_definition_name="columnValuesToBeInSet",
            dimension=QualityDimension.NORMATIVITY,
            category=QualityRuleCategory.ENUM_CHECK,
            severity=RuleSeverity.MEDIUM,
            reason="性别值必须在有效枚举范围内",
            parameters={"columnValues": "['male', 'female', 'unknown']"},
        ),
    ],
    ColumnCategory.IP: [
        RuleRecommendation(
            test_definition_name="columnValuesToMatchRegex",
            dimension=QualityDimension.NORMATIVITY,
            category=QualityRuleCategory.REGEX_CHECK,
            severity=RuleSeverity.MEDIUM,
            reason="验证IPv4地址格式和取值范围",
            parameters={
                "regex": "^((25[0-5]|2[0-4]\\d|[01]?\\d\\d?)\\.){3}(25[0-5]|2[0-4]\\d|[01]?\\d\\d?)$"
            },
        ),
    ],
    ColumnCategory.LICENSE_PLATE: [
        RuleRecommendation(
            test_definition_name="columnValuesToMatchRegex",
            dimension=QualityDimension.NORMATIVITY,
            category=QualityRuleCategory.REGEX_CHECK,
            severity=RuleSeverity.MEDIUM,
            reason="验证车牌号格式",
            parameters={
                "regex": "^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领][A-Z][A-Z0-9挂学警港澳]{5,6}$"
            },
        ),
    ],
    ColumnCategory.IMEI: [
        RuleRecommendation(
            test_definition_name="columnValuesToMatchRegex",
            dimension=QualityDimension.NORMATIVITY,
            category=QualityRuleCategory.REGEX_CHECK,
            severity=RuleSeverity.MEDIUM,
            reason="验证IMEI为15位数字",
            parameters={"regex": "^\\d{15}$"},
        ),
    ],
    ColumnCategory.MAC: [
        RuleRecommendation(
            test_definition_name="columnValuesToMatchRegex",
            dimension=QualityDimension.NORMATIVITY,
            category=QualityRuleCategory.REGEX_CHECK,
            severity=RuleSeverity.MEDIUM,
            reason="验证MAC地址格式",
            parameters={"regex": "^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$"},
        ),
    ],
    ColumnCategory.STATUS: [
        RuleRecommendation(
            test_definition_name="columnValuesToBeInSet",
            dimension=QualityDimension.NORMATIVITY,
            category=QualityRuleCategory.ENUM_CHECK,
            severity=RuleSeverity.HIGH,
            reason="状态值必须在业务允许的枚举范围内",
        ),
        RuleRecommendation(
            test_definition_name="columnValuesToBeNotNull",
            category=QualityRuleCategory.NULL_CHECK,
            dimension=QualityDimension.COMPLETENESS,
            severity=RuleSeverity.HIGH,
        ),
    ],
    ColumnCategory.DATETIME: [
        RuleRecommendation(
            test_definition_name="columnValuesToBeNotNull",
            category=QualityRuleCategory.NULL_CHECK,
            dimension=QualityDimension.COMPLETENESS,
            severity=RuleSeverity.HIGH,
            reason="时间字段不允许为空",
        ),
        RuleRecommendation(
            test_definition_name="columnValueMaxToBeBetween",
            category=QualityRuleCategory.RANGE_CHECK,
            dimension=QualityDimension.ACCURACY,
            severity=RuleSeverity.LOW,
            reason="检查时间值不超过当前时间",
            parameters={"maxValue": "CURRENT_TIMESTAMP"},
        ),
    ],
    ColumnCategory.ID_CARD: [
        RuleRecommendation(
            test_definition_name="columnValuesToMatchRegex",
            dimension=QualityDimension.NORMATIVITY,
            category=QualityRuleCategory.REGEX_CHECK,
            severity=RuleSeverity.HIGH,
            reason="验证身份证号格式（18位）",
            parameters={"regex": "^[1-9]\\d{5}(19|20)\\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\\d|3[01])\\d{3}[\\dX]$"},
        ),
        RuleRecommendation(
            test_definition_name="columnValuesToBeNotNull",
            category=QualityRuleCategory.NULL_CHECK,
            dimension=QualityDimension.COMPLETENESS,
            severity=RuleSeverity.HIGH,
        ),
    ],
}


class RuleRecommender:
    """
    规则推荐引擎
    
    根据表和列的元数据属性，自动推荐适用的质量规则
    """
    
    def __init__(self):
        self._compile_patterns()
    
    def _compile_patterns(self):
        """预编译正则表达式模式"""
        self._compiled_patterns: Dict[ColumnCategory, List[re.Pattern]] = {}
        for category, patterns in COLUMN_NAME_PATTERNS.items():
            self._compiled_patterns[category] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]
    
    def classify_column(self, column: Column) -> ColumnCategory:
        """根据列名自动分类"""
        name = column.name.root.lower()
        
        for category, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(name):
                    return category
        
        return ColumnCategory.OTHER
    
    def classify_data_type(self, data_type: str) -> ColumnType:
        """将数据库数据类型映射到列类型"""
        if not data_type:
            return ColumnType.UNKNOWN
        
        # 提取基础类型名
        base_type = data_type.lower().split("(")[0].split(" ")[0].strip()
        
        # 查找映射
        return DATA_TYPE_TO_COLUMN_TYPE.get(base_type, ColumnType.UNKNOWN)
    
    def analyze_column(self, column: Column) -> ColumnProfile:
        """分析列特征"""
        data_type = self.classify_data_type(
            column.dataType.value if column.dataType else "unknown"
        )
        category = self.classify_column(column)
        
        return ColumnProfile(
            name=column.name.root,
            data_type=data_type,
            category=category,
            is_nullable=column.nullable if hasattr(column, 'nullable') else True,
            is_primary_key=False,  # 需要从表级别获取
            is_foreign_key=False,   # 需要从表级别获取
            is_unique=False,        # 需要从约束信息获取
        )
    
    def recommend_for_column(
        self,
        column: Column,
        profile: Optional[ColumnProfile] = None,
    ) -> List[RuleRecommendation]:
        """为单个列推荐规则"""
        profile = profile or self.analyze_column(column)
        recommendations = []
        
        # 1. 基于列分类推荐
        category_rules = COLUMN_CATEGORY_RECOMMENDED_RULES.get(profile.category, [])
        for rule in category_rules:
            rec = RuleRecommendation(
                test_definition_name=rule.test_definition_name,
                column_name=profile.name,
                dimension=rule.dimension,
                category=rule.category,
                severity=rule.severity,
                confidence=0.9,
                reason=rule.reason,
                parameters=rule.parameters.copy(),
            )
            recommendations.append(rec)
        
        # 2. 基于数据类型推荐
        type_rules = COLUMN_TYPE_RECOMMENDED_RULES.get(profile.data_type, [])
        for rule_name, severity in type_rules:
            # 避免重复
            if not any(r.test_definition_name == rule_name and r.column_name == profile.name 
                      for r in recommendations):
                rec = RuleRecommendation(
                    test_definition_name=rule_name,
                    column_name=profile.name,
                    dimension=get_dimension_by_test_definition(rule_name),
                    severity=severity,
                    confidence=0.7,
                    reason=f"基于数据类型 {profile.data_type.value} 推荐",
                )
                recommendations.append(rec)
        
        # 3. 空值检查（通用）
        if profile.is_nullable:
            rec = RuleRecommendation(
                test_definition_name="columnValuesToBeNotNull",
                column_name=profile.name,
                dimension=QualityDimension.COMPLETENESS,
                category=QualityRuleCategory.NULL_CHECK,
                severity=RuleSeverity.LOW,
                confidence=0.5,
                reason="检测空值",
            )
            recommendations.append(rec)
        
        return recommendations
    
    def recommend_for_table(
        self,
        table: Table,
        include_column_rules: bool = True,
        include_table_rules: bool = True,
    ) -> List[RuleRecommendation]:
        """为整个表推荐规则"""
        recommendations = []
        
        # 表级规则
        if include_table_rules:
            recommendations.extend(self._recommend_table_rules(table))
        
        # 列级规则
        if include_column_rules and table.columns:
            for column in table.columns:
                col_recs = self.recommend_for_column(column)
                recommendations.extend(col_recs)
        
        return recommendations
    
    def _recommend_table_rules(self, table: Table) -> List[RuleRecommendation]:
        """推荐表级规则"""
        recommendations = []
        
        # 行数检查
        recommendations.append(RuleRecommendation(
            test_definition_name="tableRowCountToBeBetween",
            dimension=QualityDimension.ACCESSIBILITY,
            category=QualityRuleCategory.ACCESSIBLE_CHECK,
            severity=RuleSeverity.MEDIUM,
            confidence=0.8,
            reason="监控数据量异常",
        ))
        
        # 列数检查
        recommendations.append(RuleRecommendation(
            test_definition_name="tableColumnCountToBeBetween",
            dimension=QualityDimension.ACCESSIBILITY,
            category=QualityRuleCategory.ACCESSIBLE_CHECK,
            severity=RuleSeverity.LOW,
            confidence=0.6,
            reason="监控表结构变化",
        ))
        
        return recommendations
    
    def filter_by_dimension(
        self,
        recommendations: List[RuleRecommendation],
        dimension: QualityDimension,
    ) -> List[RuleRecommendation]:
        """按维度筛选推荐规则"""
        return [r for r in recommendations if r.dimension == dimension]
    
    def filter_by_severity(
        self,
        recommendations: List[RuleRecommendation],
        min_severity: RuleSeverity,
    ) -> List[RuleRecommendation]:
        """按严重程度筛选推荐规则"""
        severity_order = [RuleSeverity.LOW, RuleSeverity.MEDIUM, RuleSeverity.HIGH, RuleSeverity.CRITICAL]
        min_index = severity_order.index(min_severity)
        return [
            r for r in recommendations 
            if severity_order.index(r.severity) >= min_index
        ]
    
    def filter_by_confidence(
        self,
        recommendations: List[RuleRecommendation],
        min_confidence: float = 0.5,
    ) -> List[RuleRecommendation]:
        """按置信度筛选推荐规则"""
        return [r for r in recommendations if r.confidence >= min_confidence]
