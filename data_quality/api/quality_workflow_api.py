#  Copyright 2025 Collate
#  Licensed under the Collate Community License, Version 1.0 (the "License");
#  you may not use this file except in compliance with the License.

"""
质量评价流程 API 门面。

该模块以服务类方式暴露流程编排能力，方便 FastAPI/Flask 路由层或前端演示
直接调用：参数设定、脚本预览、试跑、任务创建、任务执行、看板、问题闭环、
计分归档和报告输出。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from metadata.data_quality.rules.rule_library import RuleLibrary
from metadata.data_quality.workflow.quality_assessment_workflow import (
    DataScope,
    QualityAssessmentWorkflow,
)


class DataScopeRequest(BaseModel):
    """数据范围请求。"""

    data_source: str = Field(..., description="数据源名称")
    database: str = Field("", description="数据库")
    schema: str = Field("", description="Schema")
    table_fqn: str = Field("", description="表全限定名")
    table_name: str = Field("", description="表名")
    fields: List[str] = Field(default_factory=list, description="字段列表")
    subject_domain: str = Field("", description="主题域")
    business_domain: str = Field("", description="业务域")
    batch_id: str = Field("", description="批次号")
    partition: str = Field("", description="时间分区")
    row_count: int = Field(0, description="行数")
    data_classification: str = Field("", description="分类分级")


class ConfigureRuleParameterRequest(BaseModel):
    """规则参数设定请求。"""

    rule_id: str = Field(..., description="规则编号")
    scope: DataScopeRequest = Field(..., description="数据范围")
    target_table: str = Field("", description="目标表")
    target_column: str = Field("", description="目标字段")
    threshold: Optional[Dict[str, Any]] = Field(None, description="阈值覆盖")
    weight: float = Field(1.0, description="规则权重")
    schedule: str = Field("manual", description="manual/daily/weekly/monthly/dependency")
    scan_mode: str = Field("full", description="full/incremental")
    validation_level: Optional[str] = Field(None, description="P0_BLOCKING/P1_WARNING/P2_MONITORING")
    execution_engine: str = Field("SQL", description="SQL/GE/ETL")
    condition: str = Field("", description="条件生效参数")
    parameter_overrides: Dict[str, Any] = Field(default_factory=dict, description="规则参数覆盖")
    responsible_role: str = Field("", description="责任角色")


class PreviewWorkflowRuleRequest(BaseModel):
    """流程规则脚本预览请求。"""

    setting_or_rule_id: str = Field(..., description="参数配置ID或规则编号")
    target_object: Optional[Dict[str, Any]] = Field(None, description="目标对象覆盖")
    engine: Optional[str] = Field(None, description="SQL/GE/ETL")
    parameter_overrides: Dict[str, Any] = Field(default_factory=dict)


class TrialRunRequest(BaseModel):
    """规则试跑请求。"""

    setting_id: str = Field(..., description="参数配置ID")
    sample_rows: List[Dict[str, Any]] = Field(default_factory=list, description="样例数据")
    max_invalid_samples: int = Field(10, description="最多返回异常样例数")


class CreateQualityTaskRequest(BaseModel):
    """质量任务创建请求。"""

    task_name: str = Field(..., description="任务名称")
    scope: DataScopeRequest = Field(..., description="数据范围")
    rule_setting_ids: List[str] = Field(..., description="规则参数配置ID列表")
    task_id: str = Field("", description="自定义任务ID")
    schedule: str = Field("manual", description="manual/daily/weekly/monthly/dependency")
    scan_mode: str = Field("full", description="full/incremental")
    dependency: str = Field("", description="依赖触发条件")
    parallelism: int = Field(1, description="并行度")
    created_by: str = Field("system", description="创建人")


class ExecuteQualityTaskRequest(BaseModel):
    """质量任务执行请求。"""

    task_id: str = Field(..., description="任务ID")
    sample_rows: List[Dict[str, Any]] = Field(default_factory=list, description="样例或抽样数据")
    batch_id: str = Field("", description="执行批次")


class DashboardQueryRequest(BaseModel):
    """质量看板查询请求。"""

    scope: Optional[DataScopeRequest] = None
    run_ids: Optional[List[str]] = None


class IssueQueryRequest(BaseModel):
    """质量问题查询请求。"""

    batch_id: str = ""
    resource: str = ""
    status: Optional[str] = None
    data_source: str = ""
    business_domain: str = ""
    dimension: Optional[str] = None
    include_archived: bool = False


class IssueStatusUpdateRequest(BaseModel):
    """质量问题状态更新请求。"""

    issue_id: str
    status: str
    assignee: str = ""
    remediation: str = ""
    review_notes: str = ""


class ScoringArchiveRequest(BaseModel):
    """计分规则归档请求。"""

    weights: Optional[Dict[str, float]] = None
    grade_thresholds: Optional[Dict[str, List[float]]] = None
    archived_by: str = "system"
    description: str = ""


class WorkflowReportRequest(BaseModel):
    """流程报告请求。"""

    run_id: Optional[str] = None
    output_format: str = Field("markdown", description="markdown/json")


class QualityWorkflowAPI:
    """质量评价流程 API 服务。"""

    def __init__(
        self,
        workflow: Optional[QualityAssessmentWorkflow] = None,
        rule_library: Optional[RuleLibrary] = None,
    ):
        self.workflow = workflow or QualityAssessmentWorkflow(rule_library=rule_library)

    def configure_rule_parameters(self, request: ConfigureRuleParameterRequest) -> Dict[str, Any]:
        """配置规则参数、阈值、权重、调度和执行方式。"""
        setting = self.workflow.configure_rule_parameters(
            rule_id=request.rule_id,
            scope=self._to_scope(request.scope),
            target_table=request.target_table,
            target_column=request.target_column,
            threshold=request.threshold,
            weight=request.weight,
            schedule=request.schedule,
            scan_mode=request.scan_mode,
            validation_level=request.validation_level,
            execution_engine=request.execution_engine,
            condition=request.condition,
            parameter_overrides=request.parameter_overrides,
            responsible_role=request.responsible_role,
        )
        return setting.to_dict()

    def preview_rule_script(self, request: PreviewWorkflowRuleRequest) -> Dict[str, Any]:
        """预览规则脚本。"""
        return self.workflow.preview_rule_script(
            setting_or_rule_id=request.setting_or_rule_id,
            target_object=request.target_object,
            engine=request.engine,
            parameter_overrides=request.parameter_overrides,
        ).to_dict()

    def trial_run(self, request: TrialRunRequest) -> Dict[str, Any]:
        """样例试跑并返回异常样例。"""
        return self.workflow.trial_run(
            setting_id=request.setting_id,
            sample_rows=request.sample_rows,
            max_invalid_samples=request.max_invalid_samples,
        ).to_dict()

    def create_task(self, request: CreateQualityTaskRequest) -> Dict[str, Any]:
        """创建质量评价任务。"""
        return self.workflow.create_task(
            task_name=request.task_name,
            scope=self._to_scope(request.scope),
            rule_setting_ids=request.rule_setting_ids,
            task_id=request.task_id,
            schedule=request.schedule,
            scan_mode=request.scan_mode,
            dependency=request.dependency,
            parallelism=request.parallelism,
            created_by=request.created_by,
        ).to_dict()

    def execute_task(self, request: ExecuteQualityTaskRequest) -> Dict[str, Any]:
        """执行质量评价任务。"""
        return self.workflow.execute_task(
            task_id=request.task_id,
            sample_rows=request.sample_rows,
            batch_id=request.batch_id,
        ).to_dict()

    def get_dashboard(self, request: Optional[DashboardQueryRequest] = None) -> Dict[str, Any]:
        """获取六维质量看板。"""
        request = request or DashboardQueryRequest()
        scope = self._to_scope(request.scope) if request.scope else None
        return self.workflow.build_dashboard(scope=scope, run_ids=request.run_ids).to_dict()

    def query_issues(self, request: IssueQueryRequest) -> Dict[str, Any]:
        """查询质量问题。"""
        issues = self.workflow.query_issues(
            batch_id=request.batch_id,
            resource=request.resource,
            status=request.status,
            data_source=request.data_source,
            business_domain=request.business_domain,
            dimension=request.dimension,
            include_archived=request.include_archived,
        )
        return {"total": len(issues), "issues": [issue.to_dict() for issue in issues]}

    def analyze_issue_lineage(self, issue_id: str) -> Dict[str, Any]:
        """分析质量问题血缘影响。"""
        return self.workflow.analyze_issue_lineage(issue_id)

    def update_issue_status(self, request: IssueStatusUpdateRequest) -> Dict[str, Any]:
        """更新质量问题闭环状态。"""
        return self.workflow.update_issue_status(
            issue_id=request.issue_id,
            status=request.status,
            assignee=request.assignee,
            remediation=request.remediation,
            review_notes=request.review_notes,
        ).to_dict()

    def archive_scoring_rules(self, request: ScoringArchiveRequest) -> Dict[str, Any]:
        """归档计分规则。"""
        thresholds = None
        if request.grade_thresholds:
            thresholds = {
                name: (float(bounds[0]), float(bounds[1]))
                for name, bounds in request.grade_thresholds.items()
                if len(bounds) >= 2
            }
        return self.workflow.archive_scoring_rules(
            weights=request.weights,
            grade_thresholds=thresholds,
            archived_by=request.archived_by,
            description=request.description,
        ).to_dict()

    def generate_report(self, request: WorkflowReportRequest) -> Any:
        """生成质量评价流程报告。"""
        return self.workflow.generate_workflow_report(
            run_id=request.run_id,
            output_format=request.output_format,
        )

    @staticmethod
    def _to_scope(request: DataScopeRequest) -> DataScope:
        data = request.model_dump() if hasattr(request, "model_dump") else dict(request.__dict__)
        return DataScope(**data)


__all__ = [
    "DataScopeRequest",
    "ConfigureRuleParameterRequest",
    "PreviewWorkflowRuleRequest",
    "TrialRunRequest",
    "CreateQualityTaskRequest",
    "ExecuteQualityTaskRequest",
    "DashboardQueryRequest",
    "IssueQueryRequest",
    "IssueStatusUpdateRequest",
    "ScoringArchiveRequest",
    "WorkflowReportRequest",
    "QualityWorkflowAPI",
]
