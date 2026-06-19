#  Copyright 2025 Collate
#  Licensed under the Collate Community License, Version 1.0 (the "License");
#  you may not use this file except in compliance with the License.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""
血缘分析 API 模块

提供 REST API 接口用于：
1. 数据质量问题溯源分析
2. 质量影响范围评估
3. 根因分析报告生成
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from metadata.data_quality.lineage.quality_lineage_analyzer import (
    LineageDirection,
    LineageNode,
    QualityIssue,
    QualityPropagation,
    QualityLineageAnalyzer,
    RootCauseAnalysis,
    LineageQualitySummary,
)


# ============================================================================
# 请求模型
# ============================================================================

class QualityIssueRequest(BaseModel):
    """质量问题请求"""
    table_fqn: str
    column_name: Optional[str] = None
    issue_type: str
    severity: str = "HIGH"
    description: str = ""
    failed_count: int = 0
    failure_rate: float = 0.0


class TraceabilityRequest(BaseModel):
    """溯源请求"""
    table_fqn: str
    column_name: Optional[str] = None
    max_depth: int = Field(10, ge=1, le=50, description="最大追溯深度")
    include_joins: bool = Field(True, description="是否包含 JOIN 信息")


class ImpactAnalysisRequest(BaseModel):
    """影响分析请求"""
    table_fqn: str
    column_name: Optional[str] = None
    max_depth: int = Field(10, ge=1, le=50)


class RootCauseRequest(BaseModel):
    """根因分析请求"""
    issues: List[QualityIssueRequest]
    include_lineage: bool = Field(True, description="是否包含血缘信息")


# ============================================================================
# 响应模型
# ============================================================================

class NodeResponse(BaseModel):
    """节点响应"""
    fqn: str
    name: str
    node_type: str
    quality_score: float
    has_issues: bool
    issues: List[str] = field(default_factory=list)


class EdgeResponse(BaseModel):
    """边响应"""
    source: str
    target: str
    edge_type: str
    transformation: Optional[str] = None


class LineageGraphResponse(BaseModel):
    """血缘图响应"""
    nodes: List[NodeResponse]
    edges: List[EdgeResponse]
    total_nodes: int
    total_edges: int
    quality_score: float


class PropagationPathResponse(BaseModel):
    """传播路径响应"""
    path: List[str]
    path_fqns: List[str]
    issue_type: str
    severity: str
    propagation_count: int
    affected_tables: List[str]


class ImpactedTableResponse(BaseModel):
    """受影响表响应"""
    fqn: str
    name: str
    depth: int
    impact_level: str
    impact_ratio: float
    affected_columns: List[str]


class RootCauseResponse(BaseModel):
    """根因分析响应"""
    root_causes: List[Dict[str, Any]]
    total_root_causes: int
    confidence_scores: Dict[str, float]
    recommendations: List[str]
    affected_tables: int
    affected_columns: int


class LineageQualitySummaryResponse(BaseModel):
    """血缘质量汇总响应"""
    table_fqn: str
    overall_quality_score: float
    quality_level: str
    total_upstream_tables: int
    total_downstream_tables: int
    total_issues: int
    critical_issues: int
    high_priority_issues: int
    generated_at: datetime


# ============================================================================
# API 服务类
# ============================================================================

class LineageAnalysisAPI:
    """血缘分析 API 服务"""
    
    def __init__(self, analyzer: Optional[QualityLineageAnalyzer] = None):
        self.analyzer = analyzer or QualityLineageAnalyzer()
        self._issue_cache: Dict[str, List[QualityIssue]] = {}
    
    def get_lineage_graph(
        self,
        table_fqn: str,
        direction: str = "BOTH",
        max_depth: int = 10,
    ) -> LineageGraphResponse:
        """获取血缘图
        
        Args:
            table_fqn: 表限定名
            direction: 血缘方向 (UPSTREAM, DOWNSTREAM, BOTH)
            max_depth: 最大深度
            
        Returns:
            血缘图响应
        """
        dir_enum = LineageDirection(direction)
        
        nodes, edges = self.analyzer.get_lineage_graph(
            table_fqn=table_fqn,
            direction=dir_enum,
            max_depth=max_depth,
        )
        
        node_responses = []
        for node in nodes:
            node_responses.append(NodeResponse(
                fqn=node.fqn,
                name=node.name,
                node_type=node.node_type,
                quality_score=node.quality_score,
                has_issues=node.has_issues,
                issues=node.issues,
            ))
        
        edge_responses = []
        for edge in edges:
            edge_responses.append(EdgeResponse(
                source=edge.source,
                target=edge.target,
                edge_type=edge.edge_type,
                transformation=edge.transformation,
            ))
        
        # 计算总体质量分数
        total_score = sum(n.quality_score for n in nodes) / len(nodes) if nodes else 100.0
        
        return LineageGraphResponse(
            nodes=node_responses,
            edges=edge_responses,
            total_nodes=len(nodes),
            total_edges=len(edges),
            quality_score=total_score,
        )
    
    def trace_quality_issue(
        self,
        table_fqn: str,
        column_name: Optional[str] = None,
        max_depth: int = 10,
    ) -> List[PropagationPathResponse]:
        """追溯质量问题传播路径
        
        Args:
            table_fqn: 表限定名
            column_name: 列名（可选）
            max_depth: 最大深度
            
        Returns:
            传播路径列表
        """
        paths = self.analyzer.trace_quality_issue(
            table_fqn=table_fqn,
            column_name=column_name,
            max_depth=max_depth,
        )
        
        responses = []
        for path in paths:
            responses.append(PropagationPathResponse(
                path=[n.name for n in path.path],
                path_fqns=path.path_fqns,
                issue_type=path.issue_type,
                severity=path.severity,
                propagation_count=path.propagation_count,
                affected_tables=path.affected_tables,
            ))
        
        return responses
    
    def analyze_impact(
        self,
        table_fqn: str,
        column_name: Optional[str] = None,
        max_depth: int = 10,
    ) -> List[ImpactedTableResponse]:
        """分析质量问题影响
        
        Args:
            table_fqn: 表限定名
            column_name: 列名（可选）
            max_depth: 最大深度
            
        Returns:
            受影响表列表
        """
        impacted = self.analyzer.analyze_downstream_impact(
            table_fqn=table_fqn,
            column_name=column_name,
            max_depth=max_depth,
        )
        
        responses = []
        for table in impacted:
            # 计算影响级别
            if table.impact_ratio > 0.5:
                impact_level = "CRITICAL"
            elif table.impact_ratio > 0.3:
                impact_level = "HIGH"
            elif table.impact_ratio > 0.1:
                impact_level = "MEDIUM"
            else:
                impact_level = "LOW"
            
            responses.append(ImpactedTableResponse(
                fqn=table.fqn,
                name=table.table_name,
                depth=table.depth,
                impact_level=impact_level,
                impact_ratio=table.impact_ratio,
                affected_columns=table.affected_columns,
            ))
        
        return responses
    
    def analyze_root_causes(
        self,
        issues: List[QualityIssueRequest],
        include_lineage: bool = True,
    ) -> RootCauseResponse:
        """分析问题根因
        
        Args:
            issues: 质量问题列表
            include_lineage: 是否包含血缘信息
            
        Returns:
            根因分析响应
        """
        # 转换问题格式
        quality_issues = [
            QualityIssue(
                table_fqn=issue.table_fqn,
                column_name=issue.column_name,
                issue_type=issue.issue_type,
                severity=issue.severity,
                failed_count=issue.failed_count,
                failure_rate=issue.failure_rate,
            )
            for issue in issues
        ]
        
        # 执行根因分析
        root_causes = self.analyzer.analyze_root_causes(
            issues=quality_issues,
            include_lineage=include_lineage,
        )
        
        # 构建响应
        root_cause_list = []
        confidence_scores: Dict[str, float] = {}
        
        for rc in root_causes:
            root_cause_list.append({
                "cause_type": rc.cause_type,
                "table_fqn": rc.table_fqn,
                "column_name": rc.column_name,
                "confidence": rc.confidence,
                "evidence": rc.evidence,
                "affected_issues": rc.affected_issues,
            })
            confidence_scores[rc.cause_type] = max(
                confidence_scores.get(rc.cause_type, 0),
                rc.confidence,
            )
        
        # 生成建议
        recommendations = self._generate_recommendations(root_causes)
        
        # 统计影响范围
        affected_tables = set()
        affected_columns = set()
        for issue in issues:
            affected_tables.add(issue.table_fqn)
            if issue.column_name:
                affected_columns.add(f"{issue.table_fqn}.{issue.column_name}")
        
        return RootCauseResponse(
            root_causes=root_cause_list,
            total_root_causes=len(root_causes),
            confidence_scores=confidence_scores,
            recommendations=recommendations,
            affected_tables=len(affected_tables),
            affected_columns=len(affected_columns),
        )
    
    def get_quality_summary(
        self,
        table_fqn: str,
    ) -> LineageQualitySummaryResponse:
        """获取血缘质量汇总
        
        Args:
            table_fqn: 表限定名
            
        Returns:
            质量汇总响应
        """
        summary = self.analyzer.get_quality_summary(table_fqn)
        
        # 评估质量等级
        if summary.overall_quality_score >= 95:
            quality_level = "优秀"
        elif summary.overall_quality_score >= 85:
            quality_level = "良好"
        elif summary.overall_quality_score >= 70:
            quality_level = "合格"
        elif summary.overall_quality_score >= 60:
            quality_level = "待改进"
        else:
            quality_level = "不合格"
        
        return LineageQualitySummaryResponse(
            table_fqn=table_fqn,
            overall_quality_score=summary.overall_quality_score,
            quality_level=quality_level,
            total_upstream_tables=summary.upstream_table_count,
            total_downstream_tables=summary.downstream_table_count,
            total_issues=summary.total_issues,
            critical_issues=summary.critical_issues,
            high_priority_issues=summary.high_priority_issues,
            generated_at=datetime.now(),
        )
    
    def get_upstream_tables(
        self,
        table_fqn: str,
        max_depth: int = 5,
    ) -> List[Dict[str, Any]]:
        """获取上游表列表
        
        Args:
            table_fqn: 表限定名
            max_depth: 最大深度
            
        Returns:
            上游表列表
        """
        upstream = self.analyzer.get_upstream_tables(
            table_fqn=table_fqn,
            max_depth=max_depth,
        )
        
        results = []
        for node in upstream:
            results.append({
                "fqn": node.fqn,
                "name": node.name,
                "depth": max_depth - node.depth if hasattr(node, 'depth') else 0,
                "quality_score": node.quality_score,
                "has_issues": node.has_issues,
                "issues": node.issues,
            })
        
        return results
    
    def get_downstream_tables(
        self,
        table_fqn: str,
        max_depth: int = 5,
    ) -> List[Dict[str, Any]]:
        """获取下游表列表
        
        Args:
            table_fqn: 表限定名
            max_depth: 最大深度
            
        Returns:
            下游表列表
        """
        downstream = self.analyzer.get_downstream_tables(
            table_fqn=table_fqn,
            max_depth=max_depth,
        )
        
        results = []
        for node in downstream:
            results.append({
                "fqn": node.fqn,
                "name": node.name,
                "depth": max_depth - node.depth if hasattr(node, 'depth') else 0,
                "quality_score": node.quality_score,
                "has_issues": node.has_issues,
                "issues": node.issues,
            })
        
        return results
    
    def get_issue_statistics(
        self,
        table_fqn: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取问题统计
        
        Args:
            table_fqn: 表限定名（可选）
            
        Returns:
            问题统计
        """
        issues = self._issue_cache.get(table_fqn, []) if table_fqn else []
        
        # 按类型和严重程度统计
        by_type: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        total_failed_count = 0
        
        for issue in issues:
            by_type[issue.issue_type] = by_type.get(issue.issue_type, 0) + 1
            by_severity[issue.severity] = by_severity.get(issue.severity, 0) + 1
            total_failed_count += issue.failed_count
        
        return {
            "total_issues": len(issues),
            "by_type": by_type,
            "by_severity": by_severity,
            "total_failed_count": total_failed_count,
            "avg_failure_rate": sum(i.failure_rate for i in issues) / len(issues) if issues else 0,
        }
    
    def _generate_recommendations(self, root_causes: List[Any]) -> List[str]:
        """生成处理建议"""
        recommendations = []
        
        for rc in root_causes:
            if rc.cause_type == "MISSING_DATA":
                recommendations.append(
                    f"数据缺失问题: 建议检查 {rc.table_fqn} 的数据源和ETL流程"
                )
            elif rc.cause_type == "DUPLICATE_DATA":
                recommendations.append(
                    f"数据重复问题: 建议在 {rc.table_fqn} 执行去重处理"
                )
            elif rc.cause_type == "FORMAT_ERROR":
                recommendations.append(
                    f"格式错误问题: 建议在 {rc.table_fqn}.{rc.column_name} 添加格式校验规则"
                )
            elif rc.cause_type == "INCONSISTENT_DATA":
                recommendations.append(
                    f"数据不一致问题: 建议检查 {rc.table_fqn} 与上游表的数据同步"
                )
            elif rc.cause_type == "STALE_DATA":
                recommendations.append(
                    f"数据滞后问题: 建议优化 {rc.table_fqn} 的数据更新频率"
                )
            elif rc.cause_type == "UPSTREAM_ISSUE":
                recommendations.append(
                    f"上游问题传播: 建议优先修复 {rc.table_fqn} 的上游质量问题"
                )
        
        # 去重
        return list(set(recommendations))
    
    def register_quality_issue(
        self,
        table_fqn: str,
        issue: QualityIssueRequest,
    ) -> None:
        """注册质量问题
        
        Args:
            table_fqn: 表限定名
            issue: 质量问题
        """
        quality_issue = QualityIssue(
            table_fqn=issue.table_fqn,
            column_name=issue.column_name,
            issue_type=issue.issue_type,
            severity=issue.severity,
            failed_count=issue.failed_count,
            failure_rate=issue.failure_rate,
        )
        
        if table_fqn not in self._issue_cache:
            self._issue_cache[table_fqn] = []
        self._issue_cache[table_fqn].append(quality_issue)
