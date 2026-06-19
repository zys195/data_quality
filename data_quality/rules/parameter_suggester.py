#  Copyright 2025 Collate
#  Licensed under the Collate Community License, Version 1.0 (the "License");
#  you may not use this file except in compliance with the License.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""
规则参数自动建议器

基于采样数据分析，自动设置规则参数
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import re

from metadata.data_quality.rules.rule_recommender import (
    ColumnCategory,
    ColumnProfile,
    ColumnType,
    RuleRecommender,
)


@dataclass
class SampleAnalysis:
    """采样数据分析结果"""
    column_name: str
    sample_size: int
    null_count: int = 0
    null_ratio: float = 0.0
    unique_count: int = 0
    unique_ratio: float = 0.0
    
    # 数值类型统计
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    avg_value: Optional[float] = None
    std_dev: Optional[float] = None
    
    # 字符串类型统计
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    avg_length: Optional[float] = None
    
    # 值域分析
    value_distribution: Dict[str, int] = None  # 值 -> 次数
    frequent_values: List[Tuple[Any, int]] = None  # (值, 次数) 按频率排序
    
    # 格式分析
    detected_patterns: Set[str] = None
    matches_regex_patterns: Dict[str, bool] = None  # 模式 -> 是否匹配


@dataclass
class ParameterSuggestion:
    """参数建议"""
    parameter_name: str
    suggested_value: Any
    confidence: float  # 0-1
    rationale: str


@dataclass
class RuleParameterConfig:
    """规则参数配置"""
    rule_name: str
    column_name: Optional[str]
    parameters: Dict[str, ParameterSuggestion]
    execution_priority: int = 0  # 越小优先级越高


# 常用正则表达式模式
REGEX_PATTERNS = {
    "chinese_mobile": (r"^1[3-9]\d{9}$", "中国大陆手机号"),
    "email": (r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", "邮箱"),
    "id_card_15": (r"^\d{15}$", "15位身份证号"),
    "id_card_18": (r"^[1-9]\d{5}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dX]$", "18位身份证号"),
    "license_plate": (r"^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领][A-Z][A-Z0-9挂学警港澳]{5,6}$", "车牌号"),
    "imei": (r"^\d{15}$", "IMEI"),
    "mac_address": (r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$", "MAC地址"),
    "date_iso": (r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$", "ISO日期格式"),
    "date_chinese": (r"^\d{4}年(0[1-9]|1[0-2])月(0[1-9]|[12]\d|3[01])日$", "中文日期格式"),
    "ip_v4": (r"^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$", "IPv4地址"),
    "url": (r"^https?://[^\s/$.?#].[^\s]*$", "URL"),
    "postal_code": (r"^\d{6}$", "邮政编码"),
    "chinese_id": (r"^[\u4e00-\u9fa5]+$", "纯中文"),
    "has_special_chars": (r"[!@#$%^&*(),.?\":{}|<>]", "包含特殊字符"),
    "numeric_only": (r"^\d+$", "纯数字"),
    "alpha_only": (r"^[a-zA-Z]+$", "纯字母"),
}


class ParameterSuggester:
    """
    规则参数自动建议器
    
    基于采样数据分析，为质量规则自动设置合理的参数值
    """
    
    def __init__(self, default_sample_size: int = 1000):
        """
        Args:
            default_sample_size: 默认采样大小
        """
        self.default_sample_size = default_sample_size
        self.rule_recommender = RuleRecommender()
        self._compiled_patterns = {
            name: re.compile(pattern) 
            for name, (pattern, _) in REGEX_PATTERNS.items()
        }
    
    def analyze_sample_data(
        self,
        column_name: str,
        samples: List[Any],
    ) -> SampleAnalysis:
        """
        分析采样数据
        
        Args:
            column_name: 列名
            samples: 采样数据列表
            
        Returns:
            采样分析结果
        """
        sample_size = len(samples)
        if sample_size == 0:
            return SampleAnalysis(
                column_name=column_name,
                sample_size=0,
                value_distribution={},
                frequent_values=[],
                detected_patterns=set(),
                matches_regex_patterns={},
            )
        
        # 基本统计
        non_null_samples = [s for s in samples if s is not None]
        null_count = sample_size - len(non_null_samples)
        unique_values = set(non_null_samples)
        
        # 检测数据类型
        detected_type = self._detect_value_type(non_null_samples)
        
        analysis = SampleAnalysis(
            column_name=column_name,
            sample_size=sample_size,
            null_count=null_count,
            null_ratio=null_count / sample_size if sample_size > 0 else 0.0,
            unique_count=len(unique_values),
            unique_ratio=len(unique_values) / len(non_null_samples) if non_null_samples else 0.0,
            value_distribution={},
            frequent_values=[],
            detected_patterns=set(),
            matches_regex_patterns={},
        )
        
        # 根据数据类型进行专门分析
        if detected_type == "numeric":
            self._analyze_numeric_samples(non_null_samples, analysis)
        elif detected_type == "datetime":
            self._analyze_datetime_samples(non_null_samples, analysis)
        else:
            self._analyze_string_samples(non_null_samples, analysis)
        
        # 值域分析（通用）
        self._analyze_value_distribution(non_null_samples, analysis)
        
        # 格式模式检测
        self._detect_regex_patterns(non_null_samples, analysis)
        
        return analysis
    
    def _detect_value_type(self, samples: List[Any]) -> str:
        """检测值类型"""
        if not samples:
            return "unknown"
        
        types = set()
        for s in samples[:100]:  # 只检查前100个
            if s is None:
                continue
            s_str = str(s)
            
            # 尝试转换为数值
            try:
                float(s_str)
                types.add("numeric")
            except (ValueError, TypeError):
                pass
            
            # 检查日期格式
            if self._looks_like_date(s_str):
                types.add("datetime")
        
        if "numeric" in types:
            return "numeric"
        elif "datetime" in types:
            return "datetime"
        return "string"
    
    def _looks_like_date(self, s: str) -> bool:
        """检查是否像日期格式"""
        date_patterns = [
            r"^\d{4}-\d{2}-\d{2}",  # YYYY-MM-DD
            r"^\d{4}/\d{2}/\d{2}",  # YYYY/MM/DD
            r"^\d{8}$",             # YYYYMMDD
        ]
        for pattern in date_patterns:
            if re.match(pattern, s):
                return True
        return False
    
    def _analyze_numeric_samples(
        self,
        samples: List[Any],
        analysis: SampleAnalysis,
    ):
        """分析数值类型样本"""
        numeric_values = []
        for s in samples:
            try:
                numeric_values.append(float(s))
            except (ValueError, TypeError):
                continue
        
        if numeric_values:
            analysis.min_value = min(numeric_values)
            analysis.max_value = max(numeric_values)
            analysis.avg_value = sum(numeric_values) / len(numeric_values)
            
            # 计算标准差
            mean = analysis.avg_value
            variance = sum((x - mean) ** 2 for x in numeric_values) / len(numeric_values)
            analysis.std_dev = variance ** 0.5
    
    def _analyze_datetime_samples(
        self,
        samples: List[Any],
        analysis: SampleAnalysis,
    ):
        """分析日期类型样本"""
        # 日期类型的字符串长度分析
        string_samples = [str(s) for s in samples]
        lengths = [len(s) for s in string_samples]
        if lengths:
            analysis.min_length = min(lengths)
            analysis.max_length = max(lengths)
            analysis.avg_length = sum(lengths) / len(lengths)
    
    def _analyze_string_samples(
        self,
        samples: List[Any],
        analysis: SampleAnalysis,
    ):
        """分析字符串类型样本"""
        string_samples = [str(s) for s in samples if s is not None]
        lengths = [len(s) for s in string_samples]
        
        if lengths:
            analysis.min_length = min(lengths)
            analysis.max_length = max(lengths)
            analysis.avg_length = sum(lengths) / len(lengths)
    
    def _analyze_value_distribution(
        self,
        samples: List[Any],
        analysis: SampleAnalysis,
    ):
        """分析值分布"""
        value_counts: Dict[str, int] = {}
        for s in samples:
            value_str = str(s)
            value_counts[value_str] = value_counts.get(value_str, 0) + 1
        
        # 按频率排序
        sorted_values = sorted(value_counts.items(), key=lambda x: x[1], reverse=True)
        
        analysis.value_distribution = value_counts
        analysis.frequent_values = sorted_values[:10]  # Top 10
    
    def _detect_regex_patterns(
        self,
        samples: List[Any],
        analysis: SampleAnalysis,
    ):
        """检测正则表达式模式"""
        string_samples = [str(s) for s in samples if s is not None]
        
        for pattern_name, (pattern, description) in REGEX_PATTERNS.items():
            compiled = self._compiled_patterns[pattern_name]
            matches = sum(1 for s in string_samples if compiled.match(s))
            match_ratio = matches / len(string_samples) if string_samples else 0
            
            if match_ratio > 0.9:  # 90%以上匹配
                analysis.detected_patterns.add(pattern_name)
            
            analysis.matches_regex_patterns[pattern_name] = match_ratio > 0.5
    
    def suggest_parameters(
        self,
        analysis: SampleAnalysis,
        rule_name: str,
        column_profile: Optional[ColumnProfile] = None,
    ) -> List[ParameterSuggestion]:
        """
        为规则建议参数
        
        Args:
            analysis: 采样数据分析结果
            rule_name: 规则名称
            column_profile: 列特征画像
            
        Returns:
            参数建议列表
        """
        suggestions = []
        
        if rule_name == "columnValuesToBeBetween":
            suggestions.extend(self._suggest_range_params(analysis))
        elif rule_name == "columnValueMinToBeBetween":
            suggestions.extend(self._suggest_min_params(analysis))
        elif rule_name == "columnValueMaxToBeBetween":
            suggestions.extend(self._suggest_max_params(analysis))
        elif rule_name == "columnValuesToBeInSet":
            suggestions.extend(self._suggest_enum_params(analysis))
        elif rule_name == "columnValuesToMatchRegex":
            suggestions.extend(self._suggest_regex_params(analysis))
        elif rule_name == "columnValueLengthsToBeBetween":
            suggestions.extend(self._suggest_length_params(analysis))
        
        return suggestions
    
    def _suggest_range_params(
        self,
        analysis: SampleAnalysis,
    ) -> List[ParameterSuggestion]:
        """建议范围参数"""
        suggestions = []
        
        if analysis.min_value is not None:
            # 根据数据分布调整下限（允许一定的容差）
            confidence = 0.8 if analysis.std_dev else 0.5
            suggestions.append(ParameterSuggestion(
                parameter_name="minValue",
                suggested_value=str(int(analysis.min_value)),
                confidence=confidence,
                rationale=f"基于样本最小值 {analysis.min_value} 设置",
            ))
        
        if analysis.max_value is not None:
            confidence = 0.8 if analysis.std_dev else 0.5
            suggestions.append(ParameterSuggestion(
                parameter_name="maxValue",
                suggested_value=str(int(analysis.max_value)),
                confidence=confidence,
                rationale=f"基于样本最大值 {analysis.max_value} 设置",
            ))
        
        return suggestions
    
    def _suggest_min_params(
        self,
        analysis: SampleAnalysis,
    ) -> List[ParameterSuggestion]:
        """建议最小值参数"""
        suggestions = []
        
        if analysis.min_value is not None:
            # 根据列类型调整
            if "age" in analysis.column_name.lower():
                suggestions.append(ParameterSuggestion(
                    parameter_name="minValue",
                    suggested_value="0",
                    confidence=0.9,
                    rationale="年龄最小值为0",
                ))
            elif "amount" in analysis.column_name.lower() or "price" in analysis.column_name.lower():
                suggestions.append(ParameterSuggestion(
                    parameter_name="minValue",
                    suggested_value="0",
                    confidence=0.9,
                    rationale="金额/价格不能为负数",
                ))
            else:
                suggestions.append(ParameterSuggestion(
                    parameter_name="minValue",
                    suggested_value=str(int(analysis.min_value)),
                    confidence=0.7,
                    rationale=f"基于样本最小值 {analysis.min_value} 设置",
                ))
        
        return suggestions
    
    def _suggest_max_params(
        self,
        analysis: SampleAnalysis,
    ) -> List[ParameterSuggestion]:
        """建议最大值参数"""
        suggestions = []
        
        if analysis.max_value is not None:
            if "age" in analysis.column_name.lower():
                suggestions.append(ParameterSuggestion(
                    parameter_name="maxValue",
                    suggested_value="120",
                    confidence=0.9,
                    rationale="人类年龄上限约120岁",
                ))
            elif "score" in analysis.column_name.lower():
                suggestions.append(ParameterSuggestion(
                    parameter_name="maxValue",
                    suggested_value="100",
                    confidence=0.9,
                    rationale="分数通常满分100",
                ))
            else:
                # 添加一定的容差（如10%）
                max_with_tolerance = analysis.max_value * 1.1
                suggestions.append(ParameterSuggestion(
                    parameter_name="maxValue",
                    suggested_value=str(int(max_with_tolerance)),
                    confidence=0.6,
                    rationale=f"基于样本最大值 {analysis.max_value}，添加10%容差",
                ))
        
        return suggestions
    
    def _suggest_enum_params(
        self,
        analysis: SampleAnalysis,
    ) -> List[ParameterSuggestion]:
        """建议枚举值参数"""
        suggestions = []
        
        # 基于频繁值建议枚举
        if analysis.frequent_values:
            # 取前5个最频繁的值
            top_values = [str(v) for v, _ in analysis.frequent_values[:5]]
            
            # 检查是否适合作为枚举
            unique_ratio_threshold = 0.1  # 唯一值比例小于10%才建议枚举
            if analysis.unique_ratio < unique_ratio_threshold:
                suggestions.append(ParameterSuggestion(
                    parameter_name="columnValues",
                    suggested_value=str(top_values),
                    confidence=0.8,
                    rationale=f"基于样本频繁值: {', '.join(top_values)}",
                ))
        
        return suggestions
    
    def _suggest_regex_params(
        self,
        analysis: SampleAnalysis,
    ) -> List[ParameterSuggestion]:
        """建议正则表达式参数"""
        suggestions = []
        
        # 基于检测到的模式建议正则
        if "chinese_mobile" in analysis.detected_patterns:
            suggestions.append(ParameterSuggestion(
                parameter_name="regex",
                suggested_value=REGEX_PATTERNS["chinese_mobile"][0],
                confidence=0.95,
                rationale="检测到符合中国大陆手机号格式",
            ))
        elif "email" in analysis.detected_patterns:
            suggestions.append(ParameterSuggestion(
                parameter_name="regex",
                suggested_value=REGEX_PATTERNS["email"][0],
                confidence=0.95,
                rationale="检测到符合邮箱格式",
            ))
        elif "id_card_18" in analysis.detected_patterns:
            suggestions.append(ParameterSuggestion(
                parameter_name="regex",
                suggested_value=REGEX_PATTERNS["id_card_18"][0],
                confidence=0.95,
                rationale="检测到符合18位身份证号格式",
            ))
        elif "license_plate" in analysis.detected_patterns:
            suggestions.append(ParameterSuggestion(
                parameter_name="regex",
                suggested_value=REGEX_PATTERNS["license_plate"][0],
                confidence=0.95,
                rationale="检测到符合车牌号格式",
            ))
        elif "imei" in analysis.detected_patterns:
            suggestions.append(ParameterSuggestion(
                parameter_name="regex",
                suggested_value=REGEX_PATTERNS["imei"][0],
                confidence=0.95,
                rationale="检测到符合IMEI格式",
            ))
        elif "mac_address" in analysis.detected_patterns:
            suggestions.append(ParameterSuggestion(
                parameter_name="regex",
                suggested_value=REGEX_PATTERNS["mac_address"][0],
                confidence=0.95,
                rationale="检测到符合MAC地址格式",
            ))
        elif "ip_v4" in analysis.detected_patterns:
            suggestions.append(ParameterSuggestion(
                parameter_name="regex",
                suggested_value=REGEX_PATTERNS["ip_v4"][0],
                confidence=0.95,
                rationale="检测到符合IPv4地址格式",
            ))
        elif "date_iso" in analysis.detected_patterns:
            suggestions.append(ParameterSuggestion(
                parameter_name="regex",
                suggested_value=REGEX_PATTERNS["date_iso"][0],
                confidence=0.95,
                rationale="检测到符合ISO日期格式",
            ))
        
        return suggestions
    
    def _suggest_length_params(
        self,
        analysis: SampleAnalysis,
    ) -> List[ParameterSuggestion]:
        """建议长度范围参数"""
        suggestions = []
        
        if analysis.min_length is not None:
            suggestions.append(ParameterSuggestion(
                parameter_name="minLength",
                suggested_value=str(max(0, analysis.min_length)),
                confidence=0.8,
                rationale=f"基于样本最小长度 {analysis.min_length}",
            ))
        
        if analysis.max_length is not None:
            # 添加一定容差
            max_with_tolerance = int(analysis.max_length * 1.2)
            suggestions.append(ParameterSuggestion(
                parameter_name="maxLength",
                suggested_value=str(max_with_tolerance),
                confidence=0.7,
                rationale=f"基于样本最大长度 {analysis.max_length}，添加20%容差",
            ))
        
        return suggestions
    
    def generate_rule_config(
        self,
        column: Any,
        samples: List[Any],
        rules: List[str],
    ) -> List[RuleParameterConfig]:
        """
        为列生成规则配置
        
        Args:
            column: 列对象
            samples: 采样数据
            rules: 要应用的规则列表
            
        Returns:
            规则参数配置列表
        """
        column_name = column.name.root if hasattr(column.name, 'root') else str(column.name)
        
        # 分析采样数据
        analysis = self.analyze_sample_data(column_name, samples)
        
        # 获取列特征
        profile = self.rule_recommender.analyze_column(column)
        
        configs = []
        for rule_name in rules:
            suggestions = self.suggest_parameters(analysis, rule_name, profile)
            
            params = {}
            for suggestion in suggestions:
                params[suggestion.parameter_name] = suggestion
            
            configs.append(RuleParameterConfig(
                rule_name=rule_name,
                column_name=column_name,
                parameters=params,
            ))
        
        return configs
