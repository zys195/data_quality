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
基于血缘关系的数据质量分析器

功能：
1. 追溯质量问题根源
2. 评估质量问题影响范围
3. 识别数据质量传播路径
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import deque

from metadata.ingestion.ometa.mixins.lineage_mixin import EntityWithLineage


class LineageDirection(str, Enum):
    """血缘方向"""
    UPSTREAM = "UPSTREAM"   # 上游（数据源）
    DOWNSTREAM = "DOWNSTREAM"  # 下游（数据消费者）
    BOTH = "BOTH"          # 双向


@dataclass
class LineageNode:
    """血缘节点"""
    fqn: str
    entity_type: str
    name: str
    quality_score: float = 100.0  # 质量评分
    quality_issue_count: int = 0
    upstream_count: int = 0
    downstream_count: int = 0
    columns: List[str] = field(default_factory=list)


@dataclass
class QualityIssue:
    """质量问题"""
    entity_fqn: str
    column_name: Optional[str]
    rule_name: str
    rule_dimension: str
    severity: str
    failure_rate: float
    affected_rows: int
    detected_at: datetime
    root_cause: bool = False
    propagated: bool = False  # 是否是传播导致的问题


@dataclass
class QualityPropagation:
    """质量传播路径"""
    source_fqn: str
    target_fqn: str
    source_column: Optional[str]
    target_column: Optional[str]
    propagation_confidence: float  # 传播置信度
    propagation_reason: str


@dataclass
class RootCauseAnalysis:
    """根因分析结果"""
    target_entity: str
    issues: List[QualityIssue]
    root_causes: List[QualityIssue]  # 根因问题
    propagation_paths: List[QualityPropagation]
    impact_assessment: Dict[str, Any]
    recommendations: List[str]


@dataclass
class LineageQualitySummary:
    """血缘质量汇总"""
    total_entities: int = 0
    entities_with_issues: int = 0
    root_causes: int = 0
    impacted_downstream_entities: int = 0
    affected_columns: int = 0
    affected_rows: int = 0
    
    # 按维度统计
    issues_by_dimension: Dict[str, int] = field(default_factory=dict)
    
    # 按严重程度统计
    issues_by_severity: Dict[str, int] = field(default_factory=dict)
    
    # 上游影响分析
    upstream_impact_score: float = 0.0
    
    # 下游影响分析
    downstream_impact_score: float = 0.0


class QualityLineageAnalyzer:
    """
    基于血缘关系的数据质量分析器
    
    通过分析数据血缘关系，帮助：
    1. 追溯质量问题的根源
    2. 评估质量问题的传播影响
    3. 识别需要优先修复的数据源
    """
    
    def __init__(self, metadata_client: Any):
        """
        Args:
            metadata_client: OpenMetadata 客户端实例
        """
        self.client = metadata_client
    
    def get_entity_lineage(
        self,
        entity_fqn: str,
        direction: LineageDirection = LineageDirection.BOTH,
        depth: int = 3,
    ) -> Dict[str, List[LineageNode]]:
        """
        获取实体的血缘关系
        
        Args:
            entity_fqn: 实体完全限定名
            direction: 血缘方向
            depth: 追溯深度
            
        Returns:
            {'upstream': [...], 'downstream': [...]}
        """
        try:
            # 调用 OpenMetadata API 获取血缘
            lineage_data = self.client.get_lineage_by_name(
                entity_name=entity_fqn,
                fields=["columns", "tags"],
            )
            
            upstream = self._parse_lineage_nodes(lineage_data, "upstream")
            downstream = self._parse_lineage_nodes(lineage_data, "downstream")
            
            # 限制深度
            if depth > 0:
                upstream = upstream[:depth]
                downstream = downstream[:depth]
            
            return {
                "upstream": upstream,
                "downstream": downstream,
            }
        except Exception as e:
            return {"upstream": [], "downstream": []}
    
    def _parse_lineage_nodes(
        self,
        lineage_data: EntityWithLineage,
        direction: str,
    ) -> List[LineageNode]:
        """解析血缘节点"""
        nodes = []
        
        if direction == "upstream":
            entities = lineage_data.upstream_lineage or []
        else:
            entities = lineage_data.downstream_lineage or []
        
        for entity in entities:
            node = LineageNode(
                fqn=entity.fullyQualifiedName.root,
                entity_type=entity.entityType.value,
                name=entity.name.root,
                columns=[c.name.root for c in entity.columns] if hasattr(entity, 'columns') and entity.columns else [],
            )
            nodes.append(node)
        
        return nodes
    
    def analyze_root_cause(
        self,
        entity_fqn: str,
        quality_issues: List[QualityIssue],
        max_depth: int = 5,
    ) -> RootCauseAnalysis:
        """
        分析质量问题的根因
        
        Args:
            entity_fqn: 目标实体 FQN
            quality_issues: 已检测到的质量问题列表
            max_depth: 最大追溯深度
            
        Returns:
            根因分析结果
        """
        # 获取完整血缘
        lineage = self.get_entity_lineage(
            entity_fqn, 
            LineageDirection.UPSTREAM, 
            max_depth
        )
        
        upstream_nodes = lineage.get("upstream", [])
        
        # 分析每个质量问题
        analyzed_issues = []
        root_causes = []
        propagation_paths = []
        
        for issue in quality_issues:
            # 判断是否是根因
            is_root_cause = self._is_root_cause(
                issue, 
                upstream_nodes
            )
            
            issue.root_cause = is_root_cause
            
            if is_root_cause:
                root_causes.append(issue)
            
            analyzed_issues.append(issue)
            
            # 如果是传播导致的问题，追溯传播路径
            if not is_root_cause and upstream_nodes:
                paths = self._trace_propagation(issue, upstream_nodes)
                propagation_paths.extend(paths)
        
        # 评估影响
        impact_assessment = self._assess_impact(
            entity_fqn,
            analyzed_issues,
            lineage
        )
        
        # 生成建议
        recommendations = self._generate_recommendations(
            root_causes,
            propagation_paths
        )
        
        return RootCauseAnalysis(
            target_entity=entity_fqn,
            issues=analyzed_issues,
            root_causes=root_causes,
            propagation_paths=propagation_paths,
            impact_assessment=impact_assessment,
            recommendations=recommendations,
        )
    
    def _is_root_cause(
        self,
        issue: QualityIssue,
        upstream_nodes: List[LineageNode],
    ) -> bool:
        """
        判断质量问题是否是根因
        
        根因条件：
        1. 没有上游血缘节点
        2. 上游节点本身没有质量问题
        """
        if not upstream_nodes:
            # 没有上游，是根因
            return True
        
        # 检查上游节点是否有相同的质量问题
        for node in upstream_nodes:
            # 如果上游节点的质量评分较低，可能是源头
            if node.quality_score < issue.failure_rate * 100:
                return False
        
        # 如果上游节点也有质量问题，可能是传播
        # 简化为：如果上游节点质量评分低，则当前节点不是根因
        return True
    
    def _trace_propagation(
        self,
        issue: QualityIssue,
        upstream_nodes: List[LineageNode],
    ) -> List[QualityPropagation]:
        """追溯质量问题的传播路径"""
        paths = []
        
        for node in upstream_nodes:
            # 检查列级血缘关系
            if issue.column_name and node.columns:
                # 简化逻辑：假设列名匹配就是有血缘关系
                if self._columns_related(issue.column_name, node.columns):
                    propagation = QualityPropagation(
                        source_fqn=node.fqn,
                        target_fqn=issue.entity_fqn,
                        source_column=issue.column_name,
                        target_column=issue.column_name,
                        propagation_confidence=0.8,
                        propagation_reason=f"列 {issue.column_name} 存在血缘关系",
                    )
                    paths.append(propagation)
            else:
                # 表级血缘
                propagation = QualityPropagation(
                    source_fqn=node.fqn,
                    target_fqn=issue.entity_fqn,
                    source_column=None,
                    target_column=None,
                    propagation_confidence=0.6,
                    propagation_reason="表级血缘关系",
                )
                paths.append(propagation)
        
        return paths
    
    def _columns_related(self, col: str, upstream_cols: List[str]) -> bool:
        """检查列是否相关（简化版）"""
        col_lower = col.lower()
        
        # 完全匹配
        if col_lower in [c.lower() for c in upstream_cols]:
            return True
        
        # 名称相似（如 id, xxx_id 等）
        for upstream_col in upstream_cols:
            if col_lower == upstream_col.lower():
                return True
            if col_lower.endswith("_id") and upstream_col.lower().endswith("_id"):
                return True
        
        return False
    
    def _assess_impact(
        self,
        entity_fqn: str,
        issues: List[QualityIssue],
        lineage: Dict[str, List[LineageNode]],
    ) -> Dict[str, Any]:
        """评估质量问题的影响"""
        downstream_nodes = lineage.get("downstream", [])
        
        # 受影响的下游实体数
        impacted_entities = set()
        for issue in issues:
            if issue.propagated:  # 如果是传播的，统计下游
                for node in downstream_nodes:
                    impacted_entities.add(node.fqn)
        
        # 计算影响评分
        total_affected_rows = sum(i.affected_rows for i in issues)
        
        # 按维度统计
        by_dimension: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        
        for issue in issues:
            dim = issue.rule_dimension
            by_dimension[dim] = by_dimension.get(dim, 0) + 1
            
            sev = issue.severity
            by_severity[sev] = by_severity.get(sev, 0) + 1
        
        return {
            "downstream_entities_affected": len(impacted_entities),
            "total_affected_rows": total_affected_rows,
            "downstream_lineage_depth": len(downstream_nodes),
            "issues_by_dimension": by_dimension,
            "issues_by_severity": by_severity,
        }
    
    def _generate_recommendations(
        self,
        root_causes: List[QualityIssue],
        propagation_paths: List[QualityPropagation],
    ) -> List[str]:
        """生成修复建议"""
        recommendations = []
        
        # 根因修复建议
        if root_causes:
            recommendations.append(
                f"优先修复 {len(root_causes)} 个根因问题："
            )
            for issue in root_causes:
                recommendations.append(
                    f"  - {issue.entity_fqn}.{issue.column_name}: "
                    f"规则 {issue.rule_name} 失败率 {issue.failure_rate:.2%}"
                )
        
        # 传播阻断建议
        if propagation_paths:
            unique_sources = set(p.source_fqn for p in propagation_paths)
            recommendations.append(
                f"建议检查上游数据源 {len(unique_sources)} 个："
            )
            for source in unique_sources:
                recommendations.append(f"  - {source}")
        
        return recommendations
    
    def calculate_upstream_quality_score(
        self,
        entity_fqn: str,
        max_depth: int = 5,
    ) -> Tuple[float, List[LineageNode]]:
        """
        计算上游数据源的质量评分
        
        返回：
        - 加权质量评分
        - 问题最严重的上游节点列表
        """
        lineage = self.get_entity_lineage(
            entity_fqn,
            LineageDirection.UPSTREAM,
            max_depth
        )
        
        upstream_nodes = lineage.get("upstream", [])
        
        if not upstream_nodes:
            return 100.0, []
        
        # 加权计算：越近的节点权重越高
        total_score = 0.0
        total_weight = 0.0
        problem_nodes = []
        
        for i, node in enumerate(upstream_nodes):
            # 深度越浅，权重越高
            weight = 1.0 / (i + 1)
            
            total_score += node.quality_score * weight
            total_weight += weight
            
            # 收集有问题的节点
            if node.quality_score < 80:
                problem_nodes.append(node)
        
        weighted_score = total_score / total_weight if total_weight > 0 else 100.0
        
        return weighted_score, problem_nodes
    
    def predict_downstream_impact(
        self,
        entity_fqn: str,
        quality_score: float,
        max_depth: int = 5,
    ) -> Dict[str, Any]:
        """
        预测对下游的影响
        
        Args:
            entity_fqn: 实体 FQN
            quality_score: 当前实体的质量评分
            max_depth: 下游追溯深度
            
        Returns:
            影响预测结果
        """
        lineage = self.get_entity_lineage(
            entity_fqn,
            LineageDirection.DOWNSTREAM,
            max_depth
        )
        
        downstream_nodes = lineage.get("downstream", [])
        
        # 计算预测影响
        if not downstream_nodes:
            return {
                "direct_impact": False,
                "indirect_impact": False,
                "estimated_affected_entities": 0,
                "estimated_affected_columns": 0,
            }
        
        # 直接影响：直接下游
        direct_downstream = downstream_nodes[0] if downstream_nodes else None
        direct_impact = direct_downstream is not None
        
        # 间接影响：深度 > 1 的下游
        indirect_impact = len(downstream_nodes) > 1
        
        # 估算受影响的列
        affected_columns = 0
        for node in downstream_nodes:
            affected_columns += len(node.columns)
        
        return {
            "direct_impact": direct_impact,
            "indirect_impact": indirect_impact,
            "estimated_affected_entities": len(downstream_nodes),
            "estimated_affected_columns": affected_columns,
            "propagation_probability": 1.0 - (quality_score / 100) * 0.5,
        }
    
    def get_quality_priority_order(
        self,
        entity_fqns: List[str],
        quality_issues: Dict[str, List[QualityIssue]],
    ) -> List[str]:
        """
        获取质量修复优先级顺序
        
        基于以下因素排序：
        1. 根因问题优先
        2. 上游问题优先（阻断传播）
        3. 影响范围大的优先
        
        Args:
            entity_fqns: 实体 FQN 列表
            quality_issues: 每个实体的质量问题
            
        Returns:
        按优先级排序的实体列表
        """
        entity_scores = []
        
        for fqn in entity_fqns:
            issues = quality_issues.get(fqn, [])
            
            # 计算优先级分数
            root_cause_count = sum(1 for i in issues if i.root_cause)
            critical_count = sum(1 for i in issues if i.severity == "CRITICAL")
            total_affected = sum(i.affected_rows for i in issues)
            
            # 上游因子（越上游越高）
            upstream_score, _ = self.calculate_upstream_quality_score(fqn)
            
            # 综合分数：根因 * 100 + 关键 * 50 + 影响行数 + 上游加成
            priority_score = (
                root_cause_count * 1000 +
                critical_count * 500 +
                min(total_affected, 100000) +
                (100 - upstream_score) * 10
            )
            
            entity_scores.append((fqn, priority_score))
        
        # 按优先级降序排列
        entity_scores.sort(key=lambda x: x[1], reverse=True)
        
        return [fqn for fqn, _ in entity_scores]
    
    def generate_lineage_quality_report(
        self,
        entity_fqn: str,
        quality_issues: List[QualityIssue],
    ) -> Dict[str, Any]:
        """
        生成血缘质量报告
        
        Args:
            entity_fqn: 目标实体 FQN
            quality_issues: 质量问题列表
            
        Returns:
            血缘质量报告
        """
        # 获取血缘
        lineage = self.get_entity_lineage(entity_fqn, LineageDirection.BOTH, 5)
        
        # 根因分析
        root_cause_analysis = self.analyze_root_cause(
            entity_fqn,
            quality_issues,
        )
        
        # 上游质量评分
        upstream_score, problem_nodes = self.calculate_upstream_quality_score(
            entity_fqn
        )
        
        # 下游影响预测
        current_quality = 100 - sum(
            i.failure_rate * 100 for i in quality_issues
        ) / max(len(quality_issues), 1)
        
        downstream_impact = self.predict_downstream_impact(
            entity_fqn,
            current_quality,
        )
        
        # 汇总
        summary = LineageQualitySummary(
            total_entities=len(lineage.get("upstream", [])) + len(lineage.get("downstream", [])) + 1,
            entities_with_issues=len(set(i.entity_fqn for i in quality_issues)),
            root_causes=len(root_cause_analysis.root_causes),
            impacted_downstream_entities=downstream_impact.get("estimated_affected_entities", 0),
            affected_columns=sum(len(i.column_name or "") > 0 for i in quality_issues),
            affected_rows=sum(i.affected_rows for i in quality_issues),
        )
        
        return {
            "entity": entity_fqn,
            "assessment_time": datetime.now().isoformat(),
            "summary": {
                "total_entities": summary.total_entities,
                "entities_with_issues": summary.entities_with_issues,
                "root_causes": summary.root_causes,
                "affected_downstream": summary.impacted_downstream_entities,
                "affected_rows": summary.affected_rows,
            },
            "upstream": {
                "quality_score": upstream_score,
                "problem_nodes": [
                    {"fqn": n.fqn, "score": n.quality_score}
                    for n in problem_nodes
                ],
                "depth": len(lineage.get("upstream", [])),
            },
            "downstream": {
                "impact_prediction": downstream_impact,
                "depth": len(lineage.get("downstream", [])),
            },
            "root_cause_analysis": {
                "root_causes": [
                    {
                        "entity": i.entity_fqn,
                        "column": i.column_name,
                        "rule": i.rule_name,
                        "failure_rate": i.failure_rate,
                    }
                    for i in root_cause_analysis.root_causes
                ],
                "propagation_paths": [
                    {
                        "source": p.source_fqn,
                        "target": p.target_fqn,
                        "reason": p.propagation_reason,
                    }
                    for p in root_cause_analysis.propagation_paths
                ],
            },
            "recommendations": root_cause_analysis.recommendations,
        }
