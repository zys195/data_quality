#  Copyright 2025 Collate
#  Licensed under the Collate Community License, Version 1.0 (the "License");
#  you may not use this file except in compliance with the License.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""
数据质量报告生成模块

支持生成多种格式的质量评估报告：
1. JSON 格式报告
2. Markdown 格式报告
3. HTML 格式报告
4. 趋势分析报告
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from metadata.data_quality.dimension.evaluator import (
    DimensionEvaluator,
    DimensionResult,
    QualityAssessmentResult,
    RuleSeverity,
)
from metadata.data_quality.dimension.models import QualityDimension


@dataclass
class ReportMetadata:
    """报告元数据"""
    title: str
    generated_at: datetime
    generated_by: str = "OpenMetadata DQ System"
    version: str = "1.0"
    description: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass
class DimensionReport:
    """维度报告"""
    dimension: str
    dimension_zh: str
    weight: float
    score: float
    test_pass_rate: float
    row_pass_rate: float
    total_tests: int
    passed_tests: int
    failed_tests: int
    critical_failures: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class QualityReport:
    """质量报告"""
    metadata: ReportMetadata
    table_fqn: str
    overall_score: float
    quality_level: str
    dimensions: List[DimensionReport]
    total_tests: int
    passed_tests: int
    failed_tests: int
    execution_time_ms: int
    critical_failures_count: int = 0
    executive_summary: str = ""
    key_findings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


class QualityReportGenerator:
    """质量报告生成器
    
    提供多种格式的质量评估报告生成能力：
    - JSON: 机器可读的完整报告
    - Markdown: 人类可读的格式文档
    - HTML: 可视化展示的报告
    - Summary: 简洁的汇总报告
    """
    
    def __init__(self, evaluator: Optional[DimensionEvaluator] = None):
        self.evaluator = evaluator or DimensionEvaluator()
    
    def generate_json_report(
        self,
        result: QualityAssessmentResult,
        include_details: bool = True,
        pretty: bool = True,
    ) -> str:
        """生成 JSON 格式报告
        
        Args:
            result: 质量评估结果
            include_details: 是否包含详细信息
            pretty: 是否格式化输出
            
        Returns:
            JSON 格式报告字符串
        """
        report = {
            "metadata": {
                "title": f"Data Quality Report - {result.table_fqn}",
                "generated_at": result.assessment_time.isoformat(),
                "version": "1.0",
            },
            "summary": {
                "table_fqn": result.table_fqn,
                "overall_score": round(result.overall_score, 2),
                "quality_level": result.quality_level,
                "total_tests": sum(d.total_tests for d in result.dimension_results.values()),
                "passed_tests": sum(d.passed_tests for d in result.dimension_results.values()),
                "failed_tests": sum(d.failed_tests for d in result.dimension_results.values()),
                "execution_time_ms": result.execution_time_ms,
            },
            "dimensions": {},
        }
        
        for dim, dim_result in result.dimension_results.items():
            dim_key = dim.value
            report["dimensions"][dim_key] = {
                "name": dim.ZH_NAMES.get(dim, dim.value),
                "weight": dim_result.weight,
                "score": round(dim_result.dimension_score, 2),
                "test_pass_rate": round(dim_result.test_pass_rate, 4),
                "row_pass_rate": round(dim_result.row_pass_rate, 4),
                "total_tests": dim_result.total_tests,
                "passed_tests": dim_result.passed_tests,
                "failed_tests": dim_result.failed_tests,
                "total_rows": dim_result.total_rows,
                "passed_rows": dim_result.passed_rows,
                "failed_rows": dim_result.failed_rows,
            }
            
            if include_details:
                # 添加测试结果详情
                test_details = []
                for test in dim_result.test_results:
                    test_details.append({
                        "name": test.test_case.name.root if test.test_case else "unknown",
                        "status": test.status.value if hasattr(test.status, 'value') else str(test.status),
                        "passed_rows": test.passed_rows,
                        "failed_rows": test.failed_rows,
                        "total_rows": test.total_rows,
                        "failure_rate": round(test.failure_rate, 4),
                        "severity": test.severity.value if hasattr(test.severity, 'value') else str(test.severity),
                    })
                report["dimensions"][dim_key]["test_details"] = test_details
        
        # 添加关键失败
        critical_failures = result.get_critical_failures()
        if critical_failures:
            report["critical_failures"] = [
                {
                    "test_name": t.test_case.name.root if t.test_case else "unknown",
                    "severity": t.severity.value if hasattr(t.severity, 'value') else str(t.severity),
                    "failed_rows": t.failed_rows,
                    "failure_rate": round(t.failure_rate, 4),
                }
                for t in critical_failures
            ]
        
        indent = 2 if pretty else None
        return json.dumps(report, ensure_ascii=False, indent=indent)
    
    def generate_markdown_report(
        self,
        result: QualityAssessmentResult,
        include_details: bool = True,
    ) -> str:
        """生成 Markdown 格式报告
        
        Args:
            result: 质量评估结果
            include_details: 是否包含详细信息
            
        Returns:
            Markdown 格式报告字符串
        """
        lines = []
        
        # 标题
        lines.append(f"# 数据质量评估报告")
        lines.append("")
        lines.append(f"**表**: `{result.table_fqn}`")
        lines.append(f"**评估时间**: {result.assessment_time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**评估层级**: {result.quality_level}")
        lines.append("")
        
        # 执行摘要
        lines.append("## 执行摘要")
        lines.append("")
        
        # 总体评分
        score_bar = self._generate_score_bar(result.overall_score)
        lines.append(f"### 总体评分: {result.overall_score:.2f} {score_bar}")
        lines.append("")
        
        # 维度评分表
        lines.append("### 维度评分")
        lines.append("")
        lines.append("| 维度 | 权重 | 评分 | 测试通过率 | 数据通过率 |")
        lines.append("|------|------|------|------------|------------|")
        
        for dim in QualityDimension:
            if dim in result.dimension_results:
                dim_result = result.dimension_results[dim]
                lines.append(
                    f"| {dim.ZH_NAMES.get(dim, dim.value)} | "
                    f"{dim_result.weight:.0%} | "
                    f"{dim_result.dimension_score:.1f} | "
                    f"{dim_result.test_pass_rate:.1%} | "
                    f"{dim_result.row_pass_rate:.1%} |"
                )
        
        lines.append("")
        
        # 关键失败
        critical_failures = result.get_critical_failures()
        if critical_failures:
            lines.append("## 关键失败 ⚠️")
            lines.append("")
            for failure in critical_failures:
                test_name = failure.test_case.name.root if failure.test_case else "unknown"
                lines.append(f"- **{test_name}**: {failure.failed_rows} 行失败 ({failure.failure_rate:.2%})")
            lines.append("")
        
        # 问题发现和建议
        lines.append("## 问题发现与建议")
        lines.append("")
        
        findings = self._generate_findings(result)
        recommendations = self._generate_recommendations(result)
        
        if findings:
            lines.append("### 主要发现")
            for finding in findings:
                lines.append(f"- {finding}")
            lines.append("")
        
        if recommendations:
            lines.append("### 优化建议")
            for i, rec in enumerate(recommendations, 1):
                lines.append(f"{i}. {rec}")
            lines.append("")
        
        # 详细测试结果
        if include_details:
            lines.append("## 详细测试结果")
            lines.append("")
            
            for dim in QualityDimension:
                if dim not in result.dimension_results:
                    continue
                
                dim_result = result.dimension_results[dim]
                if not dim_result.test_results:
                    continue
                
                lines.append(f"### {dim.ZH_NAMES.get(dim, dim.value)}")
                lines.append("")
                lines.append(f"**评分**: {dim_result.dimension_score:.2f} | **通过率**: {dim_result.test_pass_rate:.1%}")
                lines.append("")
                
                for test in dim_result.test_results:
                    status_icon = "✅" if test.is_passed else "❌"
                    test_name = test.test_case.name.root if test.test_case else "unknown"
                    lines.append(
                        f"{status_icon} **{test_name}** "
                        f"(通过: {test.passed_rows}, 失败: {test.failed_rows}, "
                        f"总计: {test.total_rows}, 失败率: {test.failure_rate:.2%})"
                    )
                lines.append("")
        
        # 页脚
        lines.append("---")
        lines.append(f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        lines.append(f"*OpenMetadata 数据质量评估系统 v1.0*")
        
        return "\n".join(lines)
    
    def generate_html_report(
        self,
        result: QualityAssessmentResult,
        include_details: bool = True,
        theme: str = "light",
    ) -> str:
        """生成 HTML 格式报告
        
        Args:
            result: 质量评估结果
            include_details: 是否包含详细信息
            theme: 主题 (light/dark)
            
        Returns:
            HTML 格式报告字符串
        """
        # 颜色主题
        colors = {
            "light": {
                "bg": "#ffffff",
                "text": "#333333",
                "primary": "#1890ff",
                "success": "#52c41a",
                "warning": "#faad14",
                "danger": "#ff4d4f",
            },
            "dark": {
                "bg": "#1f1f1f",
                "text": "#e0e0e0",
                "primary": "#1890ff",
                "success": "#52c41a",
                "warning": "#faad14",
                "danger": "#ff4d4f",
            }
        }
        c = colors.get(theme, colors["light"])
        
        # 生成维度卡片 HTML
        dimension_cards = ""
        for dim in QualityDimension:
            if dim not in result.dimension_results:
                continue
            
            dim_result = result.dimension_results[dim]
            score_color = self._get_score_color(dim_result.dimension_score)
            
            dimension_cards += f"""
            <div class="dimension-card" style="border-left: 4px solid {score_color};">
                <div class="dimension-header">
                    <span class="dimension-name">{dim.ZH_NAMES.get(dim, dim.value)}</span>
                    <span class="dimension-score" style="color: {score_color};">{dim_result.dimension_score:.1f}</span>
                </div>
                <div class="dimension-details">
                    <span>权重: {dim_result.weight:.0%}</span>
                    <span>测试: {dim_result.passed_tests}/{dim_result.total_tests}</span>
                    <span>数据: {dim_result.row_pass_rate:.1%}</span>
                </div>
            </div>
            """
        
        # 生成测试详情 HTML
        test_details_html = ""
        if include_details:
            for dim in QualityDimension:
                if dim not in result.dimension_results:
                    continue
                
                dim_result = result.dimension_results[dim]
                if not dim_result.test_results:
                    continue
                
                test_rows = ""
                for test in dim_result.test_results:
                    status_class = "passed" if test.is_passed else "failed"
                    test_name = test.test_case.name.root if test.test_case else "unknown"
                    test_rows += f"""
                    <tr class="{status_class}">
                        <td>{test_name}</td>
                        <td>{test.passed_rows}</td>
                        <td>{test.failed_rows}</td>
                        <td>{test.total_rows}</td>
                        <td>{test.failure_rate:.2%}</td>
                    </tr>
                    """
                
                test_details_html += f"""
                <div class="test-section">
                    <h3>{dim.ZH_NAMES.get(dim, dim.value)}</h3>
                    <table class="test-table">
                        <thead>
                            <tr>
                                <th>测试名称</th>
                                <th>通过行数</th>
                                <th>失败行数</th>
                                <th>总行数</th>
                                <th>失败率</th>
                            </tr>
                        </thead>
                        <tbody>
                            {test_rows}
                        </tbody>
                    </table>
                </div>
                """
        
        html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>数据质量报告 - {result.table_fqn}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: {c['bg']};
            color: {c['text']};
            padding: 20px;
            line-height: 1.6;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ 
            background: linear-gradient(135deg, {c['primary']}, #096dd9);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}
        .header h1 {{ margin-bottom: 10px; }}
        .meta {{ opacity: 0.9; font-size: 14px; }}
        .score-section {{
            background: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
            text-align: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .overall-score {{
            font-size: 72px;
            font-weight: bold;
            background: linear-gradient(135deg, {self._get_score_color(result.overall_score)}, {c['primary']});
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .quality-level {{
            font-size: 24px;
            color: {self._get_score_color(result.overall_score)};
            margin-top: 10px;
        }}
        .dimensions-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .dimension-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .dimension-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }}
        .dimension-name {{ font-weight: bold; font-size: 16px; }}
        .dimension-score {{ font-size: 24px; font-weight: bold; }}
        .dimension-details {{
            display: flex;
            gap: 15px;
            font-size: 12px;
            color: #666;
        }}
        .test-section {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}
        .test-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        .test-table th, .test-table td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        .test-table th {{ background: #fafafa; font-weight: 600; }}
        .passed {{ background-color: rgba(82, 196, 26, 0.1); }}
        .failed {{ background-color: rgba(255, 77, 79, 0.1); }}
        .footer {{
            text-align: center;
            padding: 20px;
            color: #666;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>数据质量评估报告</h1>
            <div class="meta">
                <div>表: <strong>{result.table_fqn}</strong></div>
                <div>评估时间: {result.assessment_time.strftime('%Y-%m-%d %H:%M:%S')}</div>
            </div>
        </div>
        
        <div class="score-section">
            <div class="overall-score">{result.overall_score:.1f}</div>
            <div class="quality-level">{result.quality_level}</div>
        </div>
        
        <h2 style="margin-bottom: 15px;">维度评分</h2>
        <div class="dimensions-grid">
            {dimension_cards}
        </div>
        
        {test_details_html}
        
        <div class="footer">
            报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | OpenMetadata 数据质量评估系统
        </div>
    </div>
</body>
</html>
"""
        return html
    
    def generate_trend_report(
        self,
        history: List[QualityAssessmentResult],
        table_fqn: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> str:
        """生成趋势分析报告
        
        Args:
            history: 历史评估结果列表
            table_fqn: 表限定名
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            Markdown 格式趋势报告
        """
        lines = []
        
        # 过滤日期范围
        filtered = history
        if start_date:
            filtered = [r for r in filtered if r.assessment_time >= start_date]
        if end_date:
            filtered = [r for r in filtered if r.assessment_time <= end_date]
        
        if not filtered:
            return "# 趋势分析报告\n\n无历史数据可供分析。"
        
        lines.append(f"# 数据质量趋势分析报告")
        lines.append("")
        lines.append(f"**表**: `{table_fqn}`")
        lines.append(f"**分析周期**: {filtered[0].assessment_time.strftime('%Y-%m-%d')} 至 {filtered[-1].assessment_time.strftime('%Y-%m-%d')}")
        lines.append(f"**评估次数**: {len(filtered)}")
        lines.append("")
        
        # 分数趋势
        lines.append("## 总体评分趋势")
        lines.append("")
        lines.append("| 日期 | 评分 | 等级 | 关键失败数 |")
        lines.append("|------|------|------|----------|")
        
        for result in filtered:
            critical_count = len(result.get_critical_failures())
            lines.append(
                f"| {result.assessment_time.strftime('%Y-%m-%d %H:%M')} | "
                f"{result.overall_score:.1f} | "
                f"{result.quality_level} | "
                f"{critical_count} |"
            )
        
        lines.append("")
        
        # 统计摘要
        scores = [r.overall_score for r in filtered]
        lines.append("## 统计摘要")
        lines.append("")
        lines.append(f"- **平均评分**: {sum(scores)/len(scores):.2f}")
        lines.append(f"- **最高评分**: {max(scores):.2f}")
        lines.append(f"- **最低评分**: {min(scores):.2f}")
        lines.append(f"- **评分波动**: {max(scores) - min(scores):.2f}")
        
        # 趋势判断
        if len(scores) >= 2:
            recent_avg = sum(scores[-3:]) / min(3, len(scores))
            prev_avg = sum(scores[:3]) / min(3, len(scores))
            trend = recent_avg - prev_avg
            
            lines.append("")
            lines.append(f"- **趋势**: {'📈 改善' if trend > 1 else '📉 下降' if trend < -1 else '➡️ 稳定'} (变化 {trend:+.2f})")
        
        # 维度趋势
        lines.append("")
        lines.append("## 维度评分趋势")
        lines.append("")
        
        for dim in QualityDimension:
            dim_scores = []
            for result in filtered:
                if dim in result.dimension_results:
                    dim_scores.append(result.dimension_results[dim].dimension_score)
                else:
                    dim_scores.append(100.0)
            
            if dim_scores:
                dim_name = dim.ZH_NAMES.get(dim, dim.value)
                lines.append(f"### {dim_name}")
                lines.append("")
                lines.append(f"- 平均: {sum(dim_scores)/len(dim_scores):.2f}")
                lines.append(f"- 最高: {max(dim_scores):.2f}")
                lines.append(f"- 最低: {min(dim_scores):.2f}")
                lines.append("")
        
        # 建议
        lines.append("## 改进建议")
        lines.append("")
        
        recent_failures = filtered[-1].get_critical_failures()
        if recent_failures:
            lines.append("### 持续性问题")
            for failure in recent_failures[:5]:
                test_name = failure.test_case.name.root if failure.test_case else "unknown"
                lines.append(f"- {test_name}: {failure.failure_rate:.2%} 失败率")
            lines.append("")
        
        lines.append("---")
        lines.append(f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        
        return "\n".join(lines)
    
    def save_report(
        self,
        report: str,
        output_path: Union[str, Path],
        format: str = "json",
    ) -> str:
        """保存报告到文件
        
        Args:
            report: 报告内容
            output_path: 输出路径
            format: 报告格式
            
        Returns:
            保存的文件路径
        """
        path = Path(output_path)
        
        # 确保目录存在
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # 添加扩展名
        if not path.suffix:
            extensions = {"json": ".json", "markdown": ".md", "html": ".html"}
            path = path.with_suffix(extensions.get(format, ".txt"))
        
        # 写入文件
        with open(path, "w", encoding="utf-8") as f:
            f.write(report)
        
        return str(path)
    
    def _generate_score_bar(self, score: float) -> str:
        """生成评分进度条"""
        filled = int(score / 10)
        return f"[{'█' * filled}{'░' * (10 - filled)}]"
    
    def _get_score_color(self, score: float) -> str:
        """获取评分对应的颜色"""
        if score >= 90:
            return "#52c41a"  # 绿色
        elif score >= 70:
            return "#faad14"  # 黄色
        elif score >= 60:
            return "#fa8c16"  # 橙色
        return "#ff4d4f"  # 红色
    
    def _generate_findings(self, result: QualityAssessmentResult) -> List[str]:
        """生成问题发现"""
        findings = []
        
        # 检查低分维度
        for dim in QualityDimension:
            if dim in result.dimension_results:
                dim_result = result.dimension_results[dim]
                if dim_result.dimension_score < 70:
                    findings.append(
                        f"{dim.ZH_NAMES.get(dim, dim.value)}维度评分偏低({dim_result.dimension_score:.1f})，"
                        f"需要重点关注"
                    )
        
        # 检查关键失败
        critical_failures = result.get_critical_failures()
        if critical_failures:
            findings.append(
                f"存在 {len(critical_failures)} 个关键规则失败，可能影响下游系统"
            )
        
        # 检查失败率高的测试
        high_failure_tests = [
            t for t in result.all_test_results
            if t.failure_rate > 0.1 and not t.is_passed
        ]
        if high_failure_tests:
            findings.append(
                f"存在 {len(high_failure_tests)} 个测试失败率超过10%"
            )
        
        return findings
    
    def _generate_recommendations(self, result: QualityAssessmentResult) -> List[str]:
        """生成优化建议"""
        recommendations = []
        
        # 根据低分维度生成建议
        low_score_dims = []
        for dim in QualityDimension:
            if dim in result.dimension_results:
                dim_result = result.dimension_results[dim]
                if dim_result.dimension_score < 70:
                    low_score_dims.append(dim)
        
        if QualityDimension.COMPLETENESS in low_score_dims:
            recommendations.append("完整性维度偏低，建议检查必填字段和数据采集流程")
        if QualityDimension.ACCURACY in low_score_dims:
            recommendations.append("准确性维度偏低，建议增加数据校验规则和清洗流程")
        if QualityDimension.NORMATIVITY in low_score_dims:
            recommendations.append("规范性维度偏低，建议统一数据格式和编码规范")
        if QualityDimension.CONSISTENCY in low_score_dims:
            recommendations.append("一致性维度偏低，建议检查跨表数据同步逻辑")
        if QualityDimension.TIMELINESS in low_score_dims:
            recommendations.append("时效性维度偏低，建议优化数据更新频率和批处理时间")
        if QualityDimension.ACCESSIBILITY in low_score_dims:
            recommendations.append("可访问性维度偏低，建议检查数据访问权限和性能优化")
        
        # 关键失败建议
        critical_failures = result.get_critical_failures()
        if critical_failures:
            recommendations.append(
                "立即处理关键规则失败，避免影响下游数据质量"
            )
        
        if not recommendations:
            recommendations.append("继续保持当前的数据质量管控措施")
        
        return recommendations
