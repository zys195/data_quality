#  Copyright 2025 Collate
#  Licensed under the Collate Community License, Version 1.0 (the "License");
#  you may not use this file except in compliance with the License.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""
质量评价流程编排服务。

该模块补齐白皮书流程中“规则参数设定、试跑验证、质量评价任务执行、
六维结果展示、问题分析与整改闭环、计分规则归档与报告输出”的后端能力。
实现保持轻量、无外部存储依赖，便于演示、单元测试和后续接入REST/数据库。
"""

from __future__ import annotations

import copy
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from metadata.data_quality.dimension.models import QualityDimension
from metadata.data_quality.rules.rule_library import (
    DIMENSION_ZH_NAMES,
    RuleExecutionEngine,
    RuleLibrary,
    RuleThreshold,
    RuleValidationLevel,
    ScriptPreview,
)


DEFAULT_DIMENSION_WEIGHTS: Dict[QualityDimension, float] = {
    QualityDimension.NORMATIVITY: 0.20,
    QualityDimension.COMPLETENESS: 0.20,
    QualityDimension.ACCURACY: 0.15,
    QualityDimension.CONSISTENCY: 0.15,
    QualityDimension.TIMELINESS: 0.15,
    QualityDimension.ACCESSIBILITY: 0.15,
}


class TaskScheduleType(str, Enum):
    """任务调度方式。"""

    MANUAL = "manual"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    DEPENDENCY = "dependency"


class ScanMode(str, Enum):
    """扫描方式。"""

    FULL = "full"
    INCREMENTAL = "incremental"


class TaskRunStatus(str, Enum):
    """任务执行状态。"""

    SUCCESS = "success"
    WARNING = "warning"
    BLOCKED = "blocked"
    FAILED = "failed"


class IssueStatus(str, Enum):
    """质量问题闭环状态。"""

    DISCOVERED = "discovered"
    ALERTED = "alerted"
    TICKETED = "ticketed"
    REMEDIATING = "remediating"
    REVIEWING = "reviewing"
    CLOSED = "closed"
    ARCHIVED = "archived"


@dataclass
class DataScope:
    """质量评价数据范围。"""

    data_source: str
    database: str = ""
    schema: str = ""
    table_fqn: str = ""
    table_name: str = ""
    fields: List[str] = field(default_factory=list)
    subject_domain: str = ""
    business_domain: str = ""
    batch_id: str = ""
    partition: str = ""
    row_count: int = 0
    data_classification: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def target_table(self) -> str:
        return self.table_name or (self.table_fqn.split(".")[-1] if self.table_fqn else "")


@dataclass
class RuleParameterSetting:
    """规则参数设定。"""

    setting_id: str
    rule_id: str
    scope: DataScope
    target_table: str = ""
    target_column: str = ""
    dimension: QualityDimension = QualityDimension.NORMATIVITY
    threshold: RuleThreshold = field(default_factory=RuleThreshold)
    weight: float = 1.0
    schedule: TaskScheduleType = TaskScheduleType.MANUAL
    scan_mode: ScanMode = ScanMode.FULL
    validation_level: RuleValidationLevel = RuleValidationLevel.P1_WARNING
    execution_engine: RuleExecutionEngine = RuleExecutionEngine.SQL
    condition: str = ""
    parameter_overrides: Dict[str, Any] = field(default_factory=dict)
    responsible_role: str = "数据责任人"
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def target_object(self) -> Dict[str, Any]:
        target = {
            "table_name": self.target_table or self.scope.target_table,
            "column_name": self.target_column,
            "database": self.scope.database,
            "schema": self.scope.schema,
            "table_fqn": self.scope.table_fqn,
        }
        target.update(self.parameter_overrides)
        return {key: value for key, value in target.items() if value not in ("", None)}

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["dimension"] = self.dimension.value
        data["dimension_zh"] = DIMENSION_ZH_NAMES.get(self.dimension, self.dimension.value)
        data["threshold"] = self.threshold.to_dict()
        data["schedule"] = self.schedule.value
        data["scan_mode"] = self.scan_mode.value
        data["validation_level"] = self.validation_level.value
        data["execution_engine"] = self.execution_engine.value
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        return data


@dataclass
class InvalidSample:
    """试跑异常样例。"""

    row_index: int
    column_name: str
    value: Any
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationTrialResult:
    """规则试跑验证结果。"""

    setting_id: str
    rule_id: str
    passed: bool
    total_rows: int
    failure_count: int
    pass_rate: float
    script_preview: ScriptPreview
    invalid_samples: List[InvalidSample] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    executed_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "setting_id": self.setting_id,
            "rule_id": self.rule_id,
            "passed": self.passed,
            "total_rows": self.total_rows,
            "failure_count": self.failure_count,
            "pass_rate": self.pass_rate,
            "script_preview": self.script_preview.to_dict(),
            "invalid_samples": [sample.to_dict() for sample in self.invalid_samples],
            "warnings": list(self.warnings),
            "executed_at": self.executed_at.isoformat(),
        }


@dataclass
class QualityTaskConfig:
    """质量评价任务配置。"""

    task_id: str
    task_name: str
    scope: DataScope
    rule_setting_ids: List[str]
    schedule: TaskScheduleType = TaskScheduleType.MANUAL
    scan_mode: ScanMode = ScanMode.FULL
    dependency: str = ""
    parallelism: int = 1
    created_by: str = "system"
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["scope"] = self.scope.to_dict()
        data["schedule"] = self.schedule.value
        data["scan_mode"] = self.scan_mode.value
        data["created_at"] = self.created_at.isoformat()
        return data


@dataclass
class RuleExecutionSummary:
    """单条规则执行摘要。"""

    rule_id: str
    setting_id: str
    dimension: QualityDimension
    validation_level: RuleValidationLevel
    status: str
    total_rows: int
    failed_rows: int
    pass_rate: float
    script: str

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["dimension"] = self.dimension.value
        data["dimension_zh"] = DIMENSION_ZH_NAMES.get(self.dimension, self.dimension.value)
        data["validation_level"] = self.validation_level.value
        return data


@dataclass
class QualityIssueRecord:
    """质量问题记录。"""

    issue_id: str
    batch_id: str
    resource: str
    status: IssueStatus
    source: str
    business_domain: str
    dimension: QualityDimension
    severity: str
    rule_id: str
    setting_id: str
    column_name: str = ""
    affected_rows: int = 0
    root_cause: str = ""
    upstream_objects: List[str] = field(default_factory=list)
    downstream_impacts: List[str] = field(default_factory=list)
    assignee: str = "数据责任人"
    remediation: str = ""
    review_notes: str = ""
    archived: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["dimension"] = self.dimension.value
        data["dimension_zh"] = DIMENSION_ZH_NAMES.get(self.dimension, self.dimension.value)
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        return data


@dataclass
class QualityTaskRunResult:
    """质量评价任务执行结果。"""

    run_id: str
    task_id: str
    status: TaskRunStatus
    started_at: datetime
    ended_at: datetime
    total_rules: int
    passed_rules: int
    failed_rules: int
    exception_rows: int
    issue_distribution: Dict[str, int]
    rule_results: List[RuleExecutionSummary] = field(default_factory=list)
    blocked: bool = False
    blocked_reason: str = ""
    notifications: List[str] = field(default_factory=list)
    issue_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
            "duration_ms": int((self.ended_at - self.started_at).total_seconds() * 1000),
            "total_rules": self.total_rules,
            "passed_rules": self.passed_rules,
            "failed_rules": self.failed_rules,
            "exception_rows": self.exception_rows,
            "issue_distribution": dict(self.issue_distribution),
            "rule_results": [result.to_dict() for result in self.rule_results],
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "notifications": list(self.notifications),
            "issue_ids": list(self.issue_ids),
        }


@dataclass
class QualityDashboard:
    """六维质量看板。"""

    scope: DataScope
    generated_at: datetime
    overall_score: float
    quality_level: str
    dimension_scores: Dict[str, Dict[str, Any]]
    rule_pass_rate: float
    issue_counts_by_type: Dict[str, int]
    impact_scope: Dict[str, Any]
    trend: List[Dict[str, Any]]
    health_by_level: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope": self.scope.to_dict(),
            "generated_at": self.generated_at.isoformat(),
            "overall_score": self.overall_score,
            "quality_level": self.quality_level,
            "dimension_scores": copy.deepcopy(self.dimension_scores),
            "rule_pass_rate": self.rule_pass_rate,
            "issue_counts_by_type": dict(self.issue_counts_by_type),
            "impact_scope": copy.deepcopy(self.impact_scope),
            "trend": copy.deepcopy(self.trend),
            "health_by_level": dict(self.health_by_level),
        }


@dataclass
class ScoringArchive:
    """计分规则归档。"""

    archive_id: str
    weights: Dict[str, float]
    scoring_formula: str
    grade_thresholds: Dict[str, Tuple[float, float]]
    archived_by: str = "system"
    description: str = ""
    archived_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "archive_id": self.archive_id,
            "weights": dict(self.weights),
            "scoring_formula": self.scoring_formula,
            "grade_thresholds": {
                name: {"min": bounds[0], "max": bounds[1]}
                for name, bounds in self.grade_thresholds.items()
            },
            "archived_by": self.archived_by,
            "description": self.description,
            "archived_at": self.archived_at.isoformat(),
        }


class QualityAssessmentWorkflow:
    """质量评价流程服务。"""

    def __init__(self, rule_library: Optional[RuleLibrary] = None):
        self.rule_library = rule_library or RuleLibrary()
        self._settings: Dict[str, RuleParameterSetting] = {}
        self._tasks: Dict[str, QualityTaskConfig] = {}
        self._runs: Dict[str, QualityTaskRunResult] = {}
        self._issues: Dict[str, QualityIssueRecord] = {}
        self._scoring_archives: Dict[str, ScoringArchive] = {}
        self._sequence = 0

    def configure_rule_parameters(
        self,
        rule_id: str,
        scope: Union[DataScope, Dict[str, Any]],
        target_table: str = "",
        target_column: str = "",
        threshold: Optional[Union[RuleThreshold, Dict[str, Any]]] = None,
        weight: float = 1.0,
        schedule: Union[TaskScheduleType, str] = TaskScheduleType.MANUAL,
        scan_mode: Union[ScanMode, str] = ScanMode.FULL,
        validation_level: Optional[Union[RuleValidationLevel, str]] = None,
        execution_engine: Union[RuleExecutionEngine, str] = RuleExecutionEngine.SQL,
        condition: str = "",
        parameter_overrides: Optional[Dict[str, Any]] = None,
        responsible_role: str = "",
    ) -> RuleParameterSetting:
        """设定规则参数、阈值、权重、调度和强弱校验策略。"""
        rule = self.rule_library.get_rule(rule_id)
        if not rule:
            raise ValueError(f"规则不存在: {rule_id}")

        setting = RuleParameterSetting(
            setting_id=self._new_id("setting"),
            rule_id=rule_id,
            scope=_to_data_scope(scope),
            target_table=target_table,
            target_column=target_column,
            dimension=rule.dimension,
            threshold=RuleThreshold.from_dict(threshold) if threshold else copy.deepcopy(rule.threshold),
            weight=weight,
            schedule=_coerce_enum(schedule, TaskScheduleType, TaskScheduleType.MANUAL),
            scan_mode=_coerce_enum(scan_mode, ScanMode, ScanMode.FULL),
            validation_level=_coerce_enum(
                validation_level or rule.validation_level,
                RuleValidationLevel,
                rule.validation_level,
            ),
            execution_engine=_coerce_enum(
                execution_engine,
                RuleExecutionEngine,
                RuleExecutionEngine.SQL,
            ),
            condition=condition,
            parameter_overrides=copy.deepcopy(parameter_overrides or {}),
            responsible_role=responsible_role or rule.responsible_role,
        )
        self._settings[setting.setting_id] = setting
        return setting

    def update_rule_parameter_setting(
        self,
        setting_id: str,
        updates: Dict[str, Any],
    ) -> RuleParameterSetting:
        """更新已生成的规则参数配置，供人工确认和阈值调整。"""
        setting = self._require_setting(setting_id)

        if "target_table" in updates:
            setting.target_table = str(updates.get("target_table") or "")
        if "target_column" in updates:
            setting.target_column = str(updates.get("target_column") or "")
        if "threshold" in updates:
            setting.threshold = RuleThreshold.from_dict(updates.get("threshold"))
        if "weight" in updates:
            try:
                setting.weight = max(0.0, float(updates.get("weight")))
            except (TypeError, ValueError):
                raise ValueError("weight必须是数字")
        if "schedule" in updates:
            setting.schedule = _coerce_enum(
                updates.get("schedule"),
                TaskScheduleType,
                setting.schedule,
            )
        if "scan_mode" in updates:
            setting.scan_mode = _coerce_enum(
                updates.get("scan_mode"),
                ScanMode,
                setting.scan_mode,
            )
        if "validation_level" in updates:
            setting.validation_level = _coerce_enum(
                updates.get("validation_level"),
                RuleValidationLevel,
                setting.validation_level,
            )
        if "execution_engine" in updates:
            setting.execution_engine = _coerce_enum(
                updates.get("execution_engine"),
                RuleExecutionEngine,
                setting.execution_engine,
            )
        if "condition" in updates:
            setting.condition = str(updates.get("condition") or "")
        if "parameter_overrides" in updates:
            parameter_overrides = updates.get("parameter_overrides") or {}
            if not isinstance(parameter_overrides, dict):
                raise ValueError("parameter_overrides必须是对象")
            setting.parameter_overrides = copy.deepcopy(parameter_overrides)
        if "responsible_role" in updates:
            setting.responsible_role = str(updates.get("responsible_role") or "数据责任人")
        if "enabled" in updates:
            setting.enabled = bool(updates.get("enabled"))

        setting.updated_at = datetime.now()
        return setting

    def preview_rule_script(
        self,
        setting_or_rule_id: str,
        target_object: Optional[Dict[str, Any]] = None,
        engine: Optional[Union[RuleExecutionEngine, str]] = None,
        parameter_overrides: Optional[Dict[str, Any]] = None,
    ) -> ScriptPreview:
        """按规则参数预览 SQL/GE/ETL 脚本。"""
        setting = self._settings.get(setting_or_rule_id)
        if setting:
            params = copy.deepcopy(setting.parameter_overrides)
            params.update(parameter_overrides or {})
            target = setting.target_object
            if target_object:
                target.update(target_object)
            return self.rule_library.preview_script(
                setting.rule_id,
                engine or setting.execution_engine,
                target,
                params,
            )

        return self.rule_library.preview_script(
            setting_or_rule_id,
            engine or RuleExecutionEngine.SQL,
            target_object,
            parameter_overrides,
        )

    def trial_run(
        self,
        setting_id: str,
        sample_rows: Optional[Sequence[Dict[str, Any]]] = None,
        max_invalid_samples: int = 10,
    ) -> ValidationTrialResult:
        """执行规则样例试跑，返回异常样例和脚本预览。"""
        setting = self._require_setting(setting_id)
        rule = self.rule_library.get_rule(setting.rule_id)
        if not rule:
            raise ValueError(f"规则不存在: {setting.rule_id}")

        rows = list(sample_rows or [])
        total_rows = len(rows)
        invalid_samples, warnings = self._evaluate_samples(setting, rows, max_invalid_samples)
        failure_count = len(invalid_samples)
        if total_rows == 0:
            warnings.append("未提供样例数据，仅完成脚本预览。")
        pass_rate = 1.0 if total_rows == 0 else max(0.0, 1.0 - failure_count / total_rows)
        threshold_rate = setting.threshold.pass_rate
        passed = failure_count == 0 or pass_rate >= threshold_rate

        return ValidationTrialResult(
            setting_id=setting.setting_id,
            rule_id=setting.rule_id,
            passed=passed,
            total_rows=total_rows,
            failure_count=failure_count,
            pass_rate=round(pass_rate, 4),
            script_preview=self.preview_rule_script(setting.setting_id),
            invalid_samples=invalid_samples,
            warnings=warnings,
        )

    def create_task(
        self,
        task_name: str,
        scope: Union[DataScope, Dict[str, Any]],
        rule_setting_ids: Sequence[str],
        task_id: str = "",
        schedule: Union[TaskScheduleType, str] = TaskScheduleType.MANUAL,
        scan_mode: Union[ScanMode, str] = ScanMode.FULL,
        dependency: str = "",
        parallelism: int = 1,
        created_by: str = "system",
    ) -> QualityTaskConfig:
        """创建质量评价任务。"""
        missing = [sid for sid in rule_setting_ids if sid not in self._settings]
        if missing:
            raise ValueError(f"规则参数不存在: {', '.join(missing)}")

        task = QualityTaskConfig(
            task_id=task_id or self._new_id("task"),
            task_name=task_name,
            scope=_to_data_scope(scope),
            rule_setting_ids=list(rule_setting_ids),
            schedule=_coerce_enum(schedule, TaskScheduleType, TaskScheduleType.MANUAL),
            scan_mode=_coerce_enum(scan_mode, ScanMode, ScanMode.FULL),
            dependency=dependency,
            parallelism=max(1, int(parallelism)),
            created_by=created_by,
        )
        self._tasks[task.task_id] = task
        return task

    def execute_task(
        self,
        task_id: str,
        sample_rows: Optional[Sequence[Dict[str, Any]]] = None,
        batch_id: str = "",
    ) -> QualityTaskRunResult:
        """执行质量评价任务并生成问题记录。"""
        task = self._require_task(task_id)
        started_at = datetime.now()
        rule_results: List[RuleExecutionSummary] = []
        issue_distribution: Dict[str, int] = {}
        notifications: List[str] = []
        issue_ids: List[str] = []
        blocked = False
        blocked_reasons: List[str] = []

        for setting_id in task.rule_setting_ids:
            setting = self._require_setting(setting_id)
            if not setting.enabled:
                continue
            trial = self.trial_run(setting_id, sample_rows)
            status = "passed" if trial.passed else "failed"
            preview = trial.script_preview
            rule_results.append(
                RuleExecutionSummary(
                    rule_id=setting.rule_id,
                    setting_id=setting.setting_id,
                    dimension=setting.dimension,
                    validation_level=setting.validation_level,
                    status=status,
                    total_rows=trial.total_rows,
                    failed_rows=trial.failure_count,
                    pass_rate=trial.pass_rate,
                    script=preview.rendered_expression,
                )
            )
            if trial.passed:
                continue

            level = setting.validation_level
            issue_distribution[level.value] = issue_distribution.get(level.value, 0) + 1
            issue = self._create_issue(task, setting, trial, batch_id or task.scope.batch_id)
            issue_ids.append(issue.issue_id)
            if level == RuleValidationLevel.P0_BLOCKING:
                blocked = True
                blocked_reasons.append(f"{setting.rule_id} 强校验失败")
            elif level == RuleValidationLevel.P1_WARNING:
                notifications.append(
                    f"{setting.rule_id} 告警：已通知{setting.responsible_role}处理。"
                )
            else:
                notifications.append(f"{setting.rule_id} 已进入趋势监控。")

        ended_at = datetime.now()
        failed_rules = sum(1 for result in rule_results if result.status == "failed")
        passed_rules = len(rule_results) - failed_rules
        if blocked:
            status = TaskRunStatus.BLOCKED
        elif failed_rules:
            status = TaskRunStatus.WARNING
        else:
            status = TaskRunStatus.SUCCESS

        run = QualityTaskRunResult(
            run_id=self._new_id("run"),
            task_id=task_id,
            status=status,
            started_at=started_at,
            ended_at=ended_at,
            total_rules=len(rule_results),
            passed_rules=passed_rules,
            failed_rules=failed_rules,
            exception_rows=sum(result.failed_rows for result in rule_results),
            issue_distribution=issue_distribution,
            rule_results=rule_results,
            blocked=blocked,
            blocked_reason="; ".join(blocked_reasons),
            notifications=notifications,
            issue_ids=issue_ids,
        )
        self._runs[run.run_id] = run
        return run

    def build_dashboard(
        self,
        scope: Optional[Union[DataScope, Dict[str, Any]]] = None,
        run_ids: Optional[Sequence[str]] = None,
    ) -> QualityDashboard:
        """构建六维质量看板。"""
        runs = self._select_runs(run_ids)
        dim_stats: Dict[QualityDimension, Dict[str, Any]] = {
            dim: {"total": 0, "passed": 0, "failed_rows": 0, "score": 100.0}
            for dim in QualityDimension
        }
        for run in runs:
            for result in run.rule_results:
                stat = dim_stats[result.dimension]
                stat["total"] += 1
                stat["passed"] += 1 if result.status == "passed" else 0
                stat["failed_rows"] += result.failed_rows

        dimension_scores: Dict[str, Dict[str, Any]] = {}
        weighted_total = 0.0
        for dim, stat in dim_stats.items():
            total = stat["total"]
            pass_rate = 1.0 if total == 0 else stat["passed"] / total
            score = round(pass_rate * 100, 2)
            stat["score"] = score
            weight = DEFAULT_DIMENSION_WEIGHTS.get(dim, 0.15)
            weighted_total += score * weight
            dimension_scores[dim.value] = {
                "dimension_zh": DIMENSION_ZH_NAMES.get(dim, dim.value),
                "weight": weight,
                "score": score,
                "rule_pass_rate": round(pass_rate, 4),
                "total_rules": total,
                "passed_rules": stat["passed"],
                "failed_rules": total - stat["passed"],
                "failed_rows": stat["failed_rows"],
            }

        total_rules = sum(run.total_rules for run in runs)
        passed_rules = sum(run.passed_rules for run in runs)
        overall_score = round(weighted_total, 2)
        if run_ids is not None:
            selected_issue_ids = {
                issue_id for run in runs for issue_id in run.issue_ids
            }
            issues = [
                issue
                for issue in self._issues.values()
                if issue.issue_id in selected_issue_ids
            ]
        else:
            issues = list(self._issues.values())
        issue_counts = _count_by((issue.problem_key for issue in _issue_views(issues)))

        dashboard_scope = _to_data_scope(scope) if scope else (runs[-1] and self._tasks[runs[-1].task_id].scope if runs else DataScope(data_source=""))
        return QualityDashboard(
            scope=dashboard_scope,
            generated_at=datetime.now(),
            overall_score=overall_score,
            quality_level=_quality_level(overall_score),
            dimension_scores=dimension_scores,
            rule_pass_rate=round(1.0 if total_rules == 0 else passed_rules / total_rules, 4),
            issue_counts_by_type=issue_counts,
            impact_scope={
                "issue_count": len(issues),
                "affected_rows": sum(issue.affected_rows for issue in issues),
                "downstream_objects": sorted(
                    {item for issue in issues for item in issue.downstream_impacts}
                ),
            },
            trend=[
                {
                    "run_id": run.run_id,
                    "task_id": run.task_id,
                    "time": run.ended_at.isoformat(),
                    "status": run.status.value,
                    "score": round(100 * (run.passed_rules / run.total_rules), 2)
                    if run.total_rules
                    else 100.0,
                }
                for run in runs
            ],
            health_by_level=_count_by(_quality_level(item["score"]) for item in dimension_scores.values()),
        )

    def query_issues(
        self,
        batch_id: str = "",
        resource: str = "",
        status: Optional[Union[IssueStatus, str]] = None,
        data_source: str = "",
        business_domain: str = "",
        dimension: Optional[Union[QualityDimension, str]] = None,
        include_archived: bool = False,
    ) -> List[QualityIssueRecord]:
        """按批次、资源、状态、时间口径等条件查询质量问题。"""
        issues = list(self._issues.values())
        if batch_id:
            issues = [issue for issue in issues if issue.batch_id == batch_id]
        if resource:
            issues = [issue for issue in issues if resource in issue.resource]
        if status:
            st = _coerce_enum(status, IssueStatus, IssueStatus.DISCOVERED)
            issues = [issue for issue in issues if issue.status == st]
        if data_source:
            issues = [issue for issue in issues if issue.source == data_source]
        if business_domain:
            issues = [issue for issue in issues if issue.business_domain == business_domain]
        if dimension:
            dim = _coerce_dimension(dimension)
            issues = [issue for issue in issues if issue.dimension == dim]
        if not include_archived:
            issues = [issue for issue in issues if not issue.archived]
        return sorted(issues, key=lambda item: item.created_at, reverse=True)

    def analyze_issue_lineage(self, issue_id: str) -> Dict[str, Any]:
        """基于问题记录中的资源和影响字段进行轻量血缘分析。"""
        issue = self._require_issue(issue_id)
        return {
            "issue_id": issue.issue_id,
            "resource": issue.resource,
            "root_cause": issue.root_cause or "待定位源表、字段或ETL环节",
            "upstream_trace": issue.upstream_objects
            or [f"{issue.source}.{issue.business_domain}.source"],
            "downstream_impacts": issue.downstream_impacts
            or [f"{issue.resource}.report", f"{issue.resource}.api"],
            "recommendations": [
                "优先核查源系统采集字段和最近一次ETL变更。",
                "对受影响报表/API标记数据质量风险，整改复核后解除提示。",
            ],
        }

    def update_issue_status(
        self,
        issue_id: str,
        status: Union[IssueStatus, str],
        assignee: str = "",
        remediation: str = "",
        review_notes: str = "",
    ) -> QualityIssueRecord:
        """推进问题闭环状态：发现、告警、工单、整改、复核、归档。"""
        issue = self._require_issue(issue_id)
        issue.status = _coerce_enum(status, IssueStatus, IssueStatus.DISCOVERED)
        if assignee:
            issue.assignee = assignee
        if remediation:
            issue.remediation = remediation
        if review_notes:
            issue.review_notes = review_notes
        if issue.status == IssueStatus.ARCHIVED:
            issue.archived = True
        issue.updated_at = datetime.now()
        return issue

    def archive_scoring_rules(
        self,
        weights: Optional[Dict[Union[QualityDimension, str], float]] = None,
        grade_thresholds: Optional[Dict[str, Tuple[float, float]]] = None,
        archived_by: str = "system",
        description: str = "",
    ) -> ScoringArchive:
        """归档计分权重、公式和质量等级阈值。"""
        normalized_weights = {
            _coerce_dimension(dim).value: float(weight)
            for dim, weight in (weights or DEFAULT_DIMENSION_WEIGHTS).items()
        }
        archive = ScoringArchive(
            archive_id=self._new_id("score"),
            weights=normalized_weights,
            scoring_formula="总分 = Σ(维度得分 × 维度权重)，P0失败任务可阻断下游处理。",
            grade_thresholds=grade_thresholds
            or {
                "优秀": (90, 100),
                "良好": (80, 89.99),
                "一般": (70, 79.99),
                "待提升": (60, 69.99),
                "高风险": (0, 59.99),
            },
            archived_by=archived_by,
            description=description,
        )
        self._scoring_archives[archive.archive_id] = archive
        return archive

    def generate_workflow_report(
        self,
        run_id: Optional[str] = None,
        output_format: str = "markdown",
    ) -> Union[str, Dict[str, Any]]:
        """生成流程评价报告，支持 Markdown 或 JSON 字典。"""
        runs = [self._runs[run_id]] if run_id else self._select_runs(None)
        dashboard = self.build_dashboard(run_ids=[run.run_id for run in runs])
        selected_issue_ids = {issue_id for run in runs for issue_id in run.issue_ids}
        issues = [
            issue
            for issue in self._issues.values()
            if issue.issue_id in selected_issue_ids
        ]
        payload = {
            "generated_at": datetime.now().isoformat(),
            "dashboard": dashboard.to_dict(),
            "runs": [run.to_dict() for run in runs],
            "issues": [issue.to_dict() for issue in issues],
            "scoring_archives": [
                archive.to_dict() for archive in self._scoring_archives.values()
            ],
        }
        if output_format.lower() == "json":
            return payload
        return self._render_markdown_report(payload)

    def get_settings(self) -> List[RuleParameterSetting]:
        return list(self._settings.values())

    def get_tasks(self) -> List[QualityTaskConfig]:
        return list(self._tasks.values())

    def get_runs(self) -> List[QualityTaskRunResult]:
        return list(self._runs.values())

    def _evaluate_samples(
        self,
        setting: RuleParameterSetting,
        rows: Sequence[Dict[str, Any]],
        max_invalid_samples: int,
    ) -> Tuple[List[InvalidSample], List[str]]:
        rule = self.rule_library.get_rule(setting.rule_id)
        if not rule:
            return [], [f"规则不存在: {setting.rule_id}"]

        column = setting.target_column
        params = copy.deepcopy(rule.parameters)
        params.update(setting.parameter_overrides)
        invalid: List[InvalidSample] = []
        warnings: List[str] = []
        regex = params.get("regex")
        allowed_values = _parse_allowed_values(params.get("allowed_values"))
        min_value = _to_float(params.get("min_value"))
        max_value = _to_float(params.get("max_value"))
        min_length = _to_int(params.get("min_length"))
        max_length = _to_int(params.get("max_length"))
        decimal_scale = _to_int(params.get("decimal_scale"))

        if not column and rule.applicability.entity_type.value == "COLUMN":
            warnings.append("列级规则未指定 target_column，试跑仅返回脚本预览。")
            return invalid, warnings

        seen_values: Dict[Any, int] = {}
        for idx, row in enumerate(rows):
            if setting.rule_id == "C-F04" and column:
                value = row.get(column)
                if value not in (None, ""):
                    seen_values[value] = seen_values.get(value, 0) + 1
                    if seen_values[value] > 1:
                        invalid.append(
                            InvalidSample(
                                row_index=idx,
                                column_name=column,
                                value=value,
                                reason="主键或唯一键重复",
                            )
                        )
                        if len(invalid) >= max_invalid_samples:
                            break
                        continue
            row_invalid = self._row_invalid_reason(
                setting,
                row,
                column,
                regex,
                allowed_values,
                min_value,
                max_value,
                min_length,
                max_length,
                decimal_scale,
            )
            if row_invalid:
                invalid.append(
                    InvalidSample(
                        row_index=idx,
                        column_name=column,
                        value=row.get(column) if column else copy.deepcopy(row),
                        reason=row_invalid,
                    )
                )
                if len(invalid) >= max_invalid_samples:
                    break
        return invalid, warnings

    def _row_invalid_reason(
        self,
        setting: RuleParameterSetting,
        row: Dict[str, Any],
        column: str,
        regex: Any,
        allowed_values: List[str],
        min_value: Optional[float],
        max_value: Optional[float],
        min_length: Optional[int],
        max_length: Optional[int],
        decimal_scale: Optional[int],
        ) -> str:
        rule_id = setting.rule_id
        value = row.get(column) if column else None
        is_empty_value = value is None or str(value).strip() == ""
        required = _to_bool((setting.parameter_overrides or {}).get("required"), False)
        forced_failures = row.get("__fail_rules", [])
        if isinstance(forced_failures, str):
            forced_failures = [item.strip() for item in forced_failures.split(",") if item.strip()]
        if row.get("__fail_rule_id"):
            forced_failures = [*list(forced_failures or []), str(row.get("__fail_rule_id"))]
        if rule_id in set(forced_failures or []):
            return str(row.get("__fail_reason") or "测试样例标记该规则未通过")

        if required and is_empty_value:
            return "字段为空或仅包含空白字符"

        if rule_id in {"C-F01", "C-F03"} or "not_null" in rule_id.lower():
            if is_empty_value:
                return "字段为空或仅包含空白字符"

        if is_empty_value:
            return ""

        if regex and value not in (None, "") and rule_id != "C-F03":
            try:
                regex_matches = bool(re.match(str(regex), str(value)))
                if "NotMatchRegex" in getattr(
                    self.rule_library.get_rule(rule_id),
                    "test_definition_name",
                    "",
                ):
                    if regex_matches:
                        return "字段值匹配了禁止出现的正则规则"
                elif not regex_matches:
                    return "字段值不匹配正则规则"
            except re.error:
                return "正则表达式不可用"

        if allowed_values and value not in (None, ""):
            if str(value) not in allowed_values:
                return "字段值不在允许枚举集合内"

        if min_value is not None or max_value is not None:
            number = _to_float(value)
            if number is None:
                return "字段值无法转换为数值"
            if min_value is not None and number < min_value:
                return "字段值小于最小阈值"
            if max_value is not None and number > max_value:
                return "字段值大于最大阈值"

        if min_length is not None or max_length is not None:
            length = len(str(value or ""))
            if min_length is not None and length < min_length:
                return "字段长度小于最小阈值"
            if max_length is not None and length > max_length:
                return "字段长度大于最大阈值"

        if rule_id == "C-F04" and column:
            duplicate_count = row.get(f"{column}__duplicate_count")
            if duplicate_count and _to_int(duplicate_count) and int(duplicate_count) > 1:
                return "主键或唯一键重复"

        if rule_id == "A-N03" and decimal_scale is not None and value not in (None, ""):
            text = str(value)
            if "." in text and len(text.split(".", 1)[1]) > decimal_scale:
                return "数值小数位超过允许精度"

        if rule_id in {"A-T02", "T-B01"} and row.get("__future_time") is True:
            return "时间晚于允许窗口"

        if setting.condition and row.get("__condition_failed") is True:
            return "自定义条件不满足"

        return ""

    def _create_issue(
        self,
        task: QualityTaskConfig,
        setting: RuleParameterSetting,
        trial: ValidationTrialResult,
        batch_id: str,
    ) -> QualityIssueRecord:
        rule = self.rule_library.get_rule(setting.rule_id)
        issue = QualityIssueRecord(
            issue_id=self._new_id("issue"),
            batch_id=batch_id or task.scope.batch_id or task.task_id,
            resource=task.scope.table_fqn or setting.target_table or task.scope.target_table,
            status=IssueStatus.DISCOVERED,
            source=task.scope.data_source,
            business_domain=task.scope.business_domain,
            dimension=setting.dimension,
            severity=setting.validation_level.value,
            rule_id=setting.rule_id,
            setting_id=setting.setting_id,
            column_name=setting.target_column,
            affected_rows=trial.failure_count,
            root_cause="待核查源数据、规则参数或ETL加工逻辑。",
            upstream_objects=[],
            downstream_impacts=[],
            assignee=setting.responsible_role,
            remediation=rule.remediation_suggestion if rule else "修复异常数据并重新执行检核。",
        )
        self._issues[issue.issue_id] = issue
        return issue

    def _render_markdown_report(self, payload: Dict[str, Any]) -> str:
        dashboard = payload["dashboard"]
        lines = [
            "# 质量评价流程执行报告",
            "",
            f"- 生成时间：{payload['generated_at']}",
            f"- 总体得分：{dashboard['overall_score']}",
            f"- 质量等级：{dashboard['quality_level']}",
            f"- 规则通过率：{dashboard['rule_pass_rate']}",
            f"- 问题数量：{dashboard['impact_scope']['issue_count']}",
            f"- 影响行数：{dashboard['impact_scope']['affected_rows']}",
            "",
            "## 六维评分",
            "",
            "| 维度 | 得分 | 通过率 | 规则数 | 失败规则 |",
            "|---|---:|---:|---:|---:|",
        ]
        for dim, item in dashboard["dimension_scores"].items():
            lines.append(
                f"| {item['dimension_zh']}({dim}) | {item['score']} | "
                f"{item['rule_pass_rate']} | {item['total_rules']} | {item['failed_rules']} |"
            )
        lines.extend(["", "## 执行批次", ""])
        for run in payload["runs"]:
            lines.append(
                f"- `{run['run_id']}` / `{run['task_id']}`：{run['status']}，"
                f"规则 {run['passed_rules']}/{run['total_rules']} 通过，异常行 {run['exception_rows']}"
            )
        lines.extend(["", "## 问题闭环", ""])
        if payload["issues"]:
            for issue in payload["issues"]:
                lines.append(
                    f"- `{issue['issue_id']}`：{issue['dimension_zh']}，"
                    f"{issue['severity']}，状态 {issue['status']}，责任人 {issue['assignee']}"
                )
        else:
            lines.append("- 暂无质量问题。")
        return "\n".join(lines)

    def _select_runs(self, run_ids: Optional[Sequence[str]]) -> List[QualityTaskRunResult]:
        if not run_ids:
            return sorted(self._runs.values(), key=lambda run: run.started_at)
        return [self._runs[run_id] for run_id in run_ids if run_id in self._runs]

    def _require_setting(self, setting_id: str) -> RuleParameterSetting:
        if setting_id not in self._settings:
            raise ValueError(f"规则参数不存在: {setting_id}")
        return self._settings[setting_id]

    def _require_task(self, task_id: str) -> QualityTaskConfig:
        if task_id not in self._tasks:
            raise ValueError(f"任务不存在: {task_id}")
        return self._tasks[task_id]

    def _require_issue(self, issue_id: str) -> QualityIssueRecord:
        if issue_id not in self._issues:
            raise ValueError(f"质量问题不存在: {issue_id}")
        return self._issues[issue_id]

    def _new_id(self, prefix: str) -> str:
        self._sequence += 1
        return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{self._sequence:04d}"


@dataclass(frozen=True)
class _IssueView:
    problem_key: str


def _issue_views(issues: Iterable[QualityIssueRecord]) -> Iterable[_IssueView]:
    for issue in issues:
        yield _IssueView(problem_key=issue.severity)


def _to_data_scope(scope: Union[DataScope, Dict[str, Any]]) -> DataScope:
    if isinstance(scope, DataScope):
        return scope
    values = dict(scope)
    return DataScope(**{key: value for key, value in values.items() if key in DataScope.__dataclass_fields__})


def _coerce_enum(value: Any, enum_cls: Any, default: Any) -> Any:
    if isinstance(value, enum_cls):
        return value
    if value is None:
        return default
    try:
        return enum_cls(str(value))
    except ValueError:
        try:
            return enum_cls(str(value).upper())
        except ValueError:
            return default


def _coerce_dimension(value: Union[str, QualityDimension]) -> QualityDimension:
    if isinstance(value, QualityDimension):
        return value
    normalized = str(value or "").strip().lower()
    for dim in QualityDimension:
        if normalized in {dim.value, dim.name.lower()}:
            return dim
    zh_lookup = {name: dim for dim, name in DIMENSION_ZH_NAMES.items()}
    return zh_lookup.get(str(value), QualityDimension.NORMATIVITY)


def _parse_allowed_values(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(item).strip("'\" ") for item in raw]
    text = str(raw).strip()
    if text.startswith("${"):
        return []
    return [item.strip().strip("'\"") for item in text.split(",") if item.strip()]


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "是", "必须", "必填"}:
        return True
    if text in {"false", "0", "no", "n", "否", "允许", "非必填"}:
        return False
    return default


def _quality_level(score: float) -> str:
    if score >= 90:
        return "优秀"
    if score >= 80:
        return "良好"
    if score >= 70:
        return "一般"
    if score >= 60:
        return "待提升"
    return "高风险"


def _count_by(items: Iterable[Any]) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for item in items:
        key = str(item)
        result[key] = result.get(key, 0) + 1
    return result


__all__ = [
    "DataScope",
    "RuleParameterSetting",
    "InvalidSample",
    "ValidationTrialResult",
    "QualityTaskConfig",
    "RuleExecutionSummary",
    "QualityIssueRecord",
    "QualityTaskRunResult",
    "QualityDashboard",
    "ScoringArchive",
    "TaskScheduleType",
    "ScanMode",
    "TaskRunStatus",
    "IssueStatus",
    "QualityAssessmentWorkflow",
]
