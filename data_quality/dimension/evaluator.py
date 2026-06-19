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
数据质量维度评估器

支持：
1. 基于维度的测试筛选和执行
2. 按维度聚合测试结果
3. 维度级别的质量评分计算
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum

from metadata.data_quality.dimension.models import (
    QualityDimension,
    QualityRuleCategory,
    DEFAULT_DIMENSION_WEIGHTS,
    DimensionWeight,
    get_dimension_by_test_definition,
)
from metadata.generated.schema.tests.basic import TestCaseStatus
from metadata.generated.schema.tests.testCase import TestCase
from metadata.generated.schema.tests.testDefinition import TestDefinition


class RuleSeverity(str, Enum):
    """规则严重程度"""
    CRITICAL = "CRITICAL"  # 关键规则，失败阻断
    HIGH = "HIGH"         # 高优先级
    MEDIUM = "MEDIUM"     # 中等优先级
    LOW = "LOW"           # 低优先级


# 规则严重程度权重
SEVERITY_WEIGHTS: Dict[RuleSeverity, float] = {
    RuleSeverity.CRITICAL: 1.0,
    RuleSeverity.HIGH: 0.75,
    RuleSeverity.MEDIUM: 0.5,
    RuleSeverity.LOW: 0.25,
}


@dataclass
class TestResultSummary:
    """单个测试结果摘要"""
    
    test_case: TestCase
    test_definition: TestDefinition
    status: TestCaseStatus
    passed_rows: int = 0
    failed_rows: int = 0
    total_rows: int = 0
    dimension: Optional[QualityDimension] = None
    category: Optional[QualityRuleCategory] = None
    severity: RuleSeverity = RuleSeverity.MEDIUM
    
    @property
    def failure_rate(self) -> float:
        """计算失败率"""
        if self.total_rows <= 0:
            return 0.0
        return self.failed_rows / self.total_rows
    
    @property
    def pass_rate(self) -> float:
        """计算通过率"""
        return 1.0 - self.failure_rate
    
    @property
    def is_passed(self) -> bool:
        """是否通过"""
        return self.status == TestCaseStatus.Success


@dataclass
class DimensionResult:
    """单个维度的评估结果"""
    
    dimension: QualityDimension
    weight: float
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    aborted_tests: int = 0
    
    # 聚合统计
    total_rows: int = 0
    passed_rows: int = 0
    failed_rows: int = 0
    
    # 评分相关
    raw_score: float = 0.0
    weighted_score: float = 0.0
    impact_score: float = 0.0
    
    # 测试结果列表
    test_results: List[TestResultSummary] = field(default_factory=list)
    
    @property
    def test_pass_rate(self) -> float:
        """测试用例通过率"""
        if self.total_tests <= 0:
            return 1.0
        return self.passed_tests / self.total_tests
    
    @property
    def row_pass_rate(self) -> float:
        """数据行通过率"""
        if self.total_rows <= 0:
            return 1.0
        return self.passed_rows / self.total_rows
    
    @property
    def dimension_score(self) -> float:
        """维度评分（0-100）"""
        return (self.test_pass_rate * 0.4 + self.row_pass_rate * 0.6) * 100


@dataclass
class QualityAssessmentResult:
    """完整的数据质量评估结果"""
    
    table_fqn: str
    assessment_time: datetime
    
    # 总体评分
    overall_score: float = 0.0  # 0-100
    quality_level: str = ""  # 优秀/良好/合格/不合格
    
    # 维度结果
    dimension_results: Dict[QualityDimension, DimensionResult] = field(default_factory=dict)
    
    # 全部测试结果
    all_test_results: List[TestResultSummary] = field(default_factory=list)
    
    # 行数信息
    total_rows_tested: int = 0
    row_count_weight_factor: float = 1.0
    
    # 元数据
    execution_time_ms: int = 0
    error_message: Optional[str] = None
    
    def get_dimension_score(self, dimension: QualityDimension) -> float:
        """获取指定维度的评分"""
        if dimension in self.dimension_results:
            return self.dimension_results[dimension].dimension_score
        return 100.0
    
    def get_critical_failures(self) -> List[TestResultSummary]:
        """获取关键规则失败列表"""
        return [
            r for r in self.all_test_results
            if r.severity == RuleSeverity.CRITICAL and not r.is_passed
        ]


class DimensionEvaluator:
    """数据质量维度评估器"""
    
    def __init__(
        self,
        dimension_weights: Optional[List[DimensionWeight]] = None,
        severity_weights: Optional[Dict[RuleSeverity, float]] = None,
    ):
        self.dimension_weights = dimension_weights or DEFAULT_DIMENSION_WEIGHTS
        self.severity_weights = severity_weights or SEVERITY_WEIGHTS
        self._weight_lookup: Dict[QualityDimension, float] = {
            w.dimension: w.weight for w in self.dimension_weights
        }
    
    def organize_by_dimension(
        self,
        test_results: List[TestResultSummary]
    ) -> Dict[QualityDimension, List[TestResultSummary]]:
        """按维度组织测试结果"""
        organized: Dict[QualityDimension, List[TestResultSummary]] = {
            dim: [] for dim in QualityDimension
        }
        for result in test_results:
            if result.dimension:
                organized[result.dimension].append(result)
            else:
                organized[QualityDimension.ACCESSIBILITY].append(result)
        return organized
    
    def calculate_dimension_result(
        self,
        dimension: QualityDimension,
        test_results: List[TestResultSummary],
        row_count: int = 0,
    ) -> DimensionResult:
        """计算单个维度的评估结果"""
        weight = self._weight_lookup.get(dimension, 0.15)
        total_tests = len(test_results)
        passed_tests = sum(1 for r in test_results if r.is_passed)
        failed_tests = sum(1 for r in test_results if not r.is_passed and r.status == TestCaseStatus.Failed)
        
        total_rows = sum(r.total_rows for r in test_results)
        passed_rows = sum(r.passed_rows for r in test_results)
        failed_rows = sum(r.failed_rows for r in test_results)
        
        row_count_weight = self._calculate_row_count_weight(row_count)
        test_pass_rate = passed_tests / total_tests if total_tests > 0 else 1.0
        raw_score = test_pass_rate * 100
        weighted_score = self._calculate_weighted_score(test_results)
        impact_score = self._calculate_impact_score(test_results, row_count, row_count_weight)
        
        return DimensionResult(
            dimension=dimension,
            weight=weight,
            total_tests=total_tests,
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            total_rows=total_rows,
            passed_rows=passed_rows,
            failed_rows=failed_rows,
            raw_score=raw_score,
            weighted_score=weighted_score,
            impact_score=impact_score,
            test_results=test_results,
        )
    
    def calculate_overall_score(
        self,
        dimension_results: Dict[QualityDimension, DimensionResult],
    ) -> float:
        """计算总体质量评分"""
        total_weight = 0.0
        weighted_sum = 0.0
        
        for dimension, result in dimension_results.items():
            weight = result.weight
            dimension_score = result.dimension_score
            
            # 关键规则失败扣分
            critical_failures = [
                r for r in result.test_results
                if r.severity == RuleSeverity.CRITICAL and not r.is_passed
            ]
            if critical_failures:
                deduction = min(len(critical_failures) * 10, 30)
                dimension_score = max(0, dimension_score - deduction)
            
            weighted_sum += dimension_score * weight
            total_weight += weight
        
        if total_weight <= 0:
            return 100.0
        return weighted_sum / total_weight
    
    def assess_quality_level(self, score: float) -> str:
        """根据评分评估质量等级"""
        if score >= 95:
            return "优秀"
        elif score >= 85:
            return "良好"
        elif score >= 70:
            return "合格"
        elif score >= 60:
            return "待改进"
        return "不合格"
    
    def _calculate_weighted_score(self, test_results: List[TestResultSummary]) -> float:
        """计算加权评分"""
        if not test_results:
            return 100.0
        total_weight = 0.0
        weighted_sum = 0.0
        for result in test_results:
            weight = self.severity_weights.get(result.severity, 0.5)
            score = 100 if result.is_passed else 0
            weighted_sum += score * weight
            total_weight += weight
        return weighted_sum / total_weight if total_weight > 0 else 100.0
    
    def _calculate_impact_score(
        self,
        test_results: List[TestResultSummary],
        row_count: int,
        row_count_weight: float,
    ) -> float:
        """计算影响评分"""
        if not test_results:
            return 0.0
        total_impact = 0.0
        total_severity = 0.0
        for result in test_results:
            if not result.is_passed:
                severity = self.severity_weights.get(result.severity, 0.5)
                impact = result.failure_rate * severity
                total_impact += impact
                total_severity += severity
        if total_severity <= 0:
            return 0.0
        return min(1.0, (total_impact / total_severity) * row_count_weight)
    
    def _calculate_row_count_weight(self, row_count: int) -> float:
        """根据数据行数计算权重因子"""
        if row_count < 100:
            return 0.5
        elif row_count < 1000:
            return 0.75
        elif row_count < 10000:
            return 1.0
        elif row_count < 100000:
            return 1.25
        return 1.5
    
    def evaluate(
        self,
        test_results: List[TestResultSummary],
        table_fqn: str,
        table_row_count: int = 0,
    ) -> QualityAssessmentResult:
        """执行完整的数据质量评估"""
        start_time = datetime.now()
        organized = self.organize_by_dimension(test_results)
        
        dimension_results: Dict[QualityDimension, DimensionResult] = {}
        for dimension, results in organized.items():
            if results:
                dimension_results[dimension] = self.calculate_dimension_result(
                    dimension, results, table_row_count
                )
        
        overall_score = self.calculate_overall_score(dimension_results)
        quality_level = self.assess_quality_level(overall_score)
        execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        
        return QualityAssessmentResult(
            table_fqn=table_fqn,
            assessment_time=datetime.now(),
            overall_score=overall_score,
            quality_level=quality_level,
            dimension_results=dimension_results,
            all_test_results=test_results,
            total_rows_tested=table_row_count,
            row_count_weight_factor=self._calculate_row_count_weight(table_row_count),
            execution_time_ms=execution_time_ms,
        )
    
    def filter_by_dimension(
        self,
        test_cases: List[TestCase],
        test_definitions: Dict[str, TestDefinition],
        dimension: QualityDimension,
    ) -> List[TestCase]:
        """按维度筛选测试用例"""
        filtered = []
        for tc in test_cases:
            td_name = tc.testDefinition.fullyQualifiedName.root
            test_dim = get_dimension_by_test_definition(td_name)
            if test_dim == dimension:
                filtered.append(tc)
        return filtered
