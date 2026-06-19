#  Copyright 2025 Collate
#  Licensed under the Collate Community License, Version 1.0 (the "License");
#  you may not use this file except in compliance with the License.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""
数据质量报告生成模块

支持生成多种格式的质量评估报告：
- JSON: 机器可读的完整报告
- Markdown: 人类可读的格式文档
- HTML: 可视化展示的报告
"""

from metadata.data_quality.reports.quality_report import (
    QualityReportGenerator,
    ReportMetadata,
    DimensionReport,
    QualityReport,
)

__all__ = [
    "QualityReportGenerator",
    "ReportMetadata",
    "DimensionReport",
    "QualityReport",
]
