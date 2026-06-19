#  Copyright 2025 Collate
#  Licensed under the Collate Community License, Version 1.0 (the "License");
#  you may not use this file except in compliance with the License.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""
数据质量评估 API 模块

提供 REST API 接口用于：
1. 质量评估执行和结果查询
2. 维度评分展示
3. 历史评估趋势分析
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from metadata.data_quality.dimension.evaluator import (
    DimensionEvaluator,
    DimensionResult,
    QualityAssessmentResult,
    RuleSeverity,
)
from metadata.data_quality.dimension.models import QualityDimension


# ============================================================================
# 请求模型
# ============================================================================

class QualityAssessmentRequest(BaseModel):
    """质量评估请求"""
    table_fqn: str = Field(..., description="表的完全限定名")
    dimensions: Optional[List[str]] = Field(
        None,
        description="要评估的维度列表，默认评估所有维度"
    )
    include_test_cases: bool = Field(
        True,
        description="是否在结果中包含测试用例详情"
    )
    threshold_overrides: Optional[Dict[str, float]] = Field(
        None,
        description="维度阈值覆盖配置"
    )


class BatchAssessmentRequest(BaseModel):
    """批量质量评估请求"""
    table_fqns: List[str] = Field(..., description="要评估的表列表")
    dimensions: Optional[List[str]] = Field(None, description="要评估的维度")
    parallel: bool = Field(True, description="是否并行执行")


class AssessmentQueryRequest(BaseModel):
    """评估查询请求"""
    table_fqn: Optional[str] = Field(None, description="表限定名")
    start_date: Optional[datetime] = Field(None, description="开始日期")
    end_date: Optional[datetime] = Field(None, description="结束日期")
    dimension: Optional[str] = Field(None, description="维度筛选")
    min_score: Optional[float] = Field(None, ge=0, le=100, description="最低分数")
    max_score: Optional[float] = Field(None, ge=0, le=100, description="最高分数")


# ============================================================================
# 响应模型
# ============================================================================

class DimensionScoreResponse(BaseModel):
    """维度评分响应"""
    dimension: str
    dimension_zh: str
    weight: float
    score: float
    test_pass_rate: float
    row_pass_rate: float
    total_tests: int
    passed_tests: int
    failed_tests: int
    critical_failures: int = 0


class QualityAssessmentResponse(BaseModel):
    """质量评估响应"""
    table_fqn: str
    assessment_time: datetime
    overall_score: float
    quality_level: str
    
    # 维度评分
    dimension_scores: List[DimensionScoreResponse]
    
    # 汇总统计
    total_tests: int
    passed_tests: int
    failed_tests: int
    total_rows_tested: int
    
    # 执行信息
    execution_time_ms: int
    error_message: Optional[str] = None
    
    # 详细结果链接
    result_id: Optional[str] = None


class BatchAssessmentResponse(BaseModel):
    """批量评估响应"""
    total_tables: int
    successful: int
    failed: int
    execution_time_ms: int
    results: List[QualityAssessmentResponse]
    failed_tables: List[str] = field(default_factory=list)


class AssessmentTrendResponse(BaseModel):
    """评估趋势响应"""
    table_fqn: str
    start_date: datetime
    end_date: datetime
    total_assessments: int
    
    # 总体评分趋势
    overall_trend: List[Dict[str, Any]]
    
    # 维度趋势
    dimension_trends: Dict[str, List[Dict[str, Any]]]
    
    # 统计摘要
    summary: Dict[str, Any]


class CriticalFailureResponse(BaseModel):
    """关键失败响应"""
    table_fqn: str
    dimension: str
    test_name: str
    test_definition: str
    failure_count: int
    failure_rate: float
    severity: str
    recommendation: str


# ============================================================================
# API 服务类
# ============================================================================

class QualityAssessmentAPI:
    """数据质量评估 API 服务"""
    
    def __init__(self, evaluator: Optional[DimensionEvaluator] = None):
        self.evaluator = evaluator or DimensionEvaluator()
        self._history: Dict[str, List[QualityAssessmentResult]] = {}
    
    def assess_quality(
        self,
        request: QualityAssessmentRequest,
        test_results: List[Any],
    ) -> QualityAssessmentResponse:
        """执行质量评估
        
        Args:
            request: 评估请求
            test_results: 测试结果列表
            
        Returns:
            评估响应
        """
        # 转换测试结果
        from metadata.data_quality.dimension.evaluator import TestResultSummary
        
        result = self.evaluator.evaluate(
            test_results=test_results,
            table_fqn=request.table_fqn,
            table_row_count=0,  # 从请求中获取
        )
        
        # 存储历史记录
        if request.table_fqn not in self._history:
            self._history[request.table_fqn] = []
        self._history[request.table_fqn].append(result)
        
        # 构建响应
        return self._build_response(result)
    
    def get_assessment_result(
        self,
        table_fqn: str,
        assessment_id: Optional[str] = None,
    ) -> Optional[QualityAssessmentResponse]:
        """获取评估结果
        
        Args:
            table_fqn: 表限定名
            assessment_id: 评估ID（可选，返回最新的）
            
        Returns:
            评估响应
        """
        history = self._history.get(table_fqn, [])
        if not history:
            return None
        
        if assessment_id:
            for result in reversed(history):
                if result.assessment_time.isoformat() == assessment_id:
                    return self._build_response(result)
            return None
        
        return self._build_response(history[-1])
    
    def get_assessment_history(
        self,
        table_fqn: str,
        limit: int = 100,
    ) -> List[QualityAssessmentResponse]:
        """获取评估历史
        
        Args:
            table_fqn: 表限定名
            limit: 返回记录数限制
            
        Returns:
            评估响应列表
        """
        history = self._history.get(table_fqn, [])
        return [self._build_response(r) for r in history[-limit:]]
    
    def get_trend(
        self,
        table_fqn: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Optional[AssessmentTrendResponse]:
        """获取评估趋势
        
        Args:
            table_fqn: 表限定名
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            趋势响应
        """
        history = self._history.get(table_fqn, [])
        if not history:
            return None
        
        # 过滤日期范围
        filtered = history
        if start_date:
            filtered = [r for r in filtered if r.assessment_time >= start_date]
        if end_date:
            filtered = [r for r in filtered if r.assessment_time <= end_date]
        
        if not filtered:
            return None
        
        # 构建总体趋势
        overall_trend = [
            {
                "timestamp": r.assessment_time.isoformat(),
                "score": r.overall_score,
                "level": r.quality_level,
            }
            for r in filtered
        ]
        
        # 构建维度趋势
        dimension_trends: Dict[str, List[Dict[str, Any]]] = {
            dim.value: [] for dim in QualityDimension
        }
        
        for r in filtered:
            for dim, dim_result in r.dimension_results.items():
                dimension_trends[dim.value].append({
                    "timestamp": r.assessment_time.isoformat(),
                    "score": dim_result.dimension_score,
                    "passed_tests": dim_result.passed_tests,
                    "failed_tests": dim_result.failed_tests,
                })
        
        # 计算统计摘要
        scores = [r.overall_score for r in filtered]
        summary = {
            "avg_score": sum(scores) / len(scores) if scores else 0,
            "max_score": max(scores) if scores else 0,
            "min_score": min(scores) if scores else 0,
            "latest_score": scores[-1] if scores else 0,
            "trend_direction": self._calculate_trend(scores),
        }
        
        return AssessmentTrendResponse(
            table_fqn=table_fqn,
            start_date=filtered[0].assessment_time,
            end_date=filtered[-1].assessment_time,
            total_assessments=len(filtered),
            overall_trend=overall_trend,
            dimension_trends=dimension_trends,
            summary=summary,
        )
    
    def get_critical_failures(
        self,
        table_fqn: Optional[str] = None,
        min_severity: RuleSeverity = RuleSeverity.HIGH,
    ) -> List[CriticalFailureResponse]:
        """获取关键失败列表
        
        Args:
            table_fqn: 表限定名（可选）
            min_severity: 最小严重程度
            
        Returns:
            关键失败列表
        """
        failures = []
        
        # 确定查询范围
        if table_fqn:
            histories = {table_fqn: self._history.get(table_fqn, [])}
        else:
            histories = self._history
        
        for fqn, history in histories.items():
            for result in history:
                for test_result in result.get_critical_failures():
                    failures.append(CriticalFailureResponse(
                        table_fqn=fqn,
                        dimension=test_result.dimension.value if test_result.dimension else "unknown",
                        test_name=test_result.test_case.name.root if test_result.test_case else "unknown",
                        test_definition=test_result.test_definition.name.root if test_result.test_definition else "unknown",
                        failure_count=test_result.failed_rows,
                        failure_rate=test_result.failure_rate,
                        severity=test_result.severity.value,
                        recommendation=self._get_failure_recommendation(test_result),
                    ))
        
        return failures
    
    def get_dimension_summary(
        self,
        dimension: QualityDimension,
    ) -> Dict[str, Any]:
        """获取维度汇总
        
        Args:
            dimension: 质量维度
            
        Returns:
            维度汇总信息
        """
        all_scores = []
        all_results = []
        
        for history in self._history.values():
            for result in history:
                if dimension in result.dimension_results:
                    dim_result = result.dimension_results[dimension]
                    all_scores.append(dim_result.dimension_score)
                    all_results.append(dim_result)
        
        if not all_scores:
            return {}
        
        return {
            "dimension": dimension.value,
            "dimension_zh": dimension.ZH_NAMES.get(dimension, dimension.value),
            "total_assessments": len(all_scores),
            "avg_score": sum(all_scores) / len(all_scores),
            "max_score": max(all_scores),
            "min_score": min(all_scores),
            "total_tests": sum(r.total_tests for r in all_results),
            "passed_tests": sum(r.passed_tests for r in all_results),
            "failed_tests": sum(r.failed_tests for r in all_results),
        }
    
    def get_table_ranking(
        self,
        dimension: Optional[QualityDimension] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """获取表排名
        
        Args:
            dimension: 维度筛选（可选，默认使用总体评分）
            limit: 返回数量
            
        Returns:
            排名列表
        """
        rankings = []
        
        for fqn, history in self._history.items():
            if not history:
                continue
            
            latest = history[-1]
            if dimension and dimension in latest.dimension_results:
                score = latest.dimension_results[dimension].dimension_score
            else:
                score = latest.overall_score
            
            rankings.append({
                "table_fqn": fqn,
                "score": score,
                "quality_level": latest.quality_level,
                "assessment_time": latest.assessment_time.isoformat(),
            })
        
        # 按分数降序排序
        rankings.sort(key=lambda x: x["score"], reverse=True)
        
        return rankings[:limit]
    
    def _build_response(
        self,
        result: QualityAssessmentResult,
    ) -> QualityAssessmentResponse:
        """构建评估响应"""
        dimension_scores = []
        
        for dim in QualityDimension:
            if dim in result.dimension_results:
                dim_result = result.dimension_results[dim]
                dimension_scores.append(DimensionScoreResponse(
                    dimension=dim.value,
                    dimension_zh=dim.ZH_NAMES.get(dim, dim.value),
                    weight=dim_result.weight,
                    score=dim_result.dimension_score,
                    test_pass_rate=dim_result.test_pass_rate,
                    row_pass_rate=dim_result.row_pass_rate,
                    total_tests=dim_result.total_tests,
                    passed_tests=dim_result.passed_tests,
                    failed_tests=dim_result.failed_tests,
                    critical_failures=sum(
                        1 for r in dim_result.test_results
                        if r.severity == RuleSeverity.CRITICAL and not r.is_passed
                    ),
                ))
        
        total_tests = sum(d.total_tests for d in result.dimension_results.values())
        passed_tests = sum(d.passed_tests for d in result.dimension_results.values())
        failed_tests = sum(d.failed_tests for d in result.dimension_results.values())
        
        return QualityAssessmentResponse(
            table_fqn=result.table_fqn,
            assessment_time=result.assessment_time,
            overall_score=result.overall_score,
            quality_level=result.quality_level,
            dimension_scores=dimension_scores,
            total_tests=total_tests,
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            total_rows_tested=result.total_rows_tested,
            execution_time_ms=result.execution_time_ms,
            error_message=result.error_message,
            result_id=result.assessment_time.isoformat(),
        )
    
    def _calculate_trend(self, scores: List[float]) -> str:
        """计算趋势方向"""
        if len(scores) < 2:
            return "STABLE"
        
        # 简单线性回归计算斜率
        n = len(scores)
        x_mean = (n - 1) / 2
        y_mean = sum(scores) / n
        
        numerator = sum((i - x_mean) * (scores[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return "STABLE"
        
        slope = numerator / denominator
        
        if slope > 1:
            return "IMPROVING"
        elif slope < -1:
            return "DECLINING"
        return "STABLE"
    
    def _get_failure_recommendation(self, test_result: Any) -> str:
        """获取失败建议"""
        severity = test_result.severity.value if hasattr(test_result.severity, 'value') else str(test_result.severity)
        
        recommendations = {
            "CRITICAL": "立即处理：此问题可能影响下游系统",
            "HIGH": "尽快处理：此问题对业务有较大影响",
            "MEDIUM": "计划处理：建议纳入迭代优化",
            "LOW": "可选处理：可以后续优化",
        }
        
        return recommendations.get(severity, "请评估处理")
