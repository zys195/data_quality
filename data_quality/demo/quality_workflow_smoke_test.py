"""
质量评价流程冒烟测试。

运行方式：
    python data_quality/demo/quality_workflow_smoke_test.py

该脚本通过最小依赖桩加载新增模块，不要求安装完整 OpenMetadata / pydantic
环境，适合本地汇报前快速验证规则库和质量评价流程能力。
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[2]
DATA_QUALITY = ROOT / "data_quality"


def install_runtime_stubs() -> None:
    """Install minimal modules required by standalone smoke tests."""
    if "pydantic" not in sys.modules:
        pydantic = types.ModuleType("pydantic")

        class BaseModel:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

            def model_dump(self):
                return dict(self.__dict__)

        def Field(default=None, **kwargs):
            if "default_factory" in kwargs:
                return kwargs["default_factory"]()
            return None if default is Ellipsis else default

        pydantic.BaseModel = BaseModel
        pydantic.Field = Field
        sys.modules["pydantic"] = pydantic

    metadata = types.ModuleType("metadata")
    dq = types.ModuleType("metadata.data_quality")
    dim_pkg = types.ModuleType("metadata.data_quality.dimension")
    evaluator = types.ModuleType("metadata.data_quality.dimension.evaluator")
    models = types.ModuleType("metadata.data_quality.dimension.models")
    rules_pkg = types.ModuleType("metadata.data_quality.rules")
    workflow_pkg = types.ModuleType("metadata.data_quality.workflow")
    api_pkg = types.ModuleType("metadata.data_quality.api")

    class RuleSeverity(str, Enum):
        CRITICAL = "CRITICAL"
        HIGH = "HIGH"
        MEDIUM = "MEDIUM"
        LOW = "LOW"

    class QualityDimension(str, Enum):
        NORMATIVITY = "normativity"
        COMPLETENESS = "completeness"
        ACCURACY = "accuracy"
        CONSISTENCY = "consistency"
        TIMELINESS = "timeliness"
        ACCESSIBILITY = "accessibility"

    class QualityRuleCategory(str, Enum):
        FORMAT_CHECK = "format_check"
        ENUM_CHECK = "enum_check"
        REGEX_CHECK = "regex_check"
        NULL_CHECK = "null_check"
        FILL_RATE_CHECK = "fill_rate_check"
        REFERENCE_CHECK = "reference_check"
        RANGE_CHECK = "range_check"
        PRECISION_CHECK = "precision_check"
        DUPLICATE_CHECK = "duplicate_check"
        DIRTY_DATA_CHECK = "dirty_data_check"
        CROSS_TABLE_CHECK = "cross_table_check"
        CROSS_SYSTEM_CHECK = "cross_system_check"
        CALCULATION_CHECK = "calculation_check"
        UPDATE_LATENCY_CHECK = "update_latency_check"
        TIME_SEQUENCE_CHECK = "time_sequence_check"
        HISTORY_VALIDITY_CHECK = "history_validity_check"
        ACCESSIBLE_CHECK = "accessible_check"
        PERFORMANCE_CHECK = "performance_check"
        UNIQUENESS_CHECK = "uniqueness_check"

    evaluator.RuleSeverity = RuleSeverity
    models.QualityDimension = QualityDimension
    models.QualityRuleCategory = QualityRuleCategory
    models.get_dimension_by_test_definition = lambda _name: QualityDimension.NORMATIVITY

    sys.modules.update(
        {
            "metadata": metadata,
            "metadata.data_quality": dq,
            "metadata.data_quality.dimension": dim_pkg,
            "metadata.data_quality.dimension.evaluator": evaluator,
            "metadata.data_quality.dimension.models": models,
            "metadata.data_quality.rules": rules_pkg,
            "metadata.data_quality.workflow": workflow_pkg,
            "metadata.data_quality.api": api_pkg,
        }
    )


def load_module(name: str, relative_path: str):
    path = DATA_QUALITY / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module: {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_test_modules() -> Dict[str, Any]:
    install_runtime_stubs()
    return {
        "rule_library": load_module(
            "metadata.data_quality.rules.rule_library",
            "rules/rule_library.py",
        ),
        "workflow": load_module(
            "metadata.data_quality.workflow.quality_assessment_workflow",
            "workflow/quality_assessment_workflow.py",
        ),
        "workflow_api": load_module(
            "metadata.data_quality.api.quality_workflow_api",
            "api/quality_workflow_api.py",
        ),
    }


def main() -> int:
    checks: List[Dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = "") -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
        if not passed:
            raise AssertionError(f"{name}: {detail}")

    try:
        modules = load_test_modules()
        rule_library_mod = modules["rule_library"]
        workflow_mod = modules["workflow"]
        api_mod = modules["workflow_api"]

        library = rule_library_mod.RuleLibrary(load_builtin=True)
        summary = library.get_summary().to_dict()
        previous_added_rule_ids = {
            "N-F07",
            "N-F08",
            "N-C02",
            "C-F03",
            "C-F04",
            "A-N03",
            "A-T02",
            "CS-T01",
            "T-B01",
            "AC-S02",
        }
        whitepaper_extended_rule_ids = set()
        for prefix in ["N", "C", "A", "CS", "T", "AC"]:
            whitepaper_extended_rule_ids.update(
                f"{prefix}-W{i:02d}" for i in range(1, 11)
            )
        all_rule_ids = {rule.rule_id for rule in library.list_rules()}

        check("内置规则总数", summary["total_rules"] >= 95, summary)
        check(
            "原基础扩展十条规则存在",
            previous_added_rule_ids.issubset(all_rule_ids),
            sorted(previous_added_rule_ids),
        )
        check(
            "白皮书扩展六十条规则存在",
            whitepaper_extended_rule_ids.issubset(all_rule_ids),
            sorted(whitepaper_extended_rule_ids),
        )
        check(
            "六维评价覆盖",
            set(summary["by_dimension"])
            == {
                "normativity",
                "completeness",
                "accuracy",
                "consistency",
                "timeliness",
                "accessibility",
            },
            summary["by_dimension"],
        )
        check(
            "内置规则均支持SQL/GE/ETL",
            all(
                {"SQL", "GE", "ETL"}.issubset({engine.value for engine in rule.scripts})
                for rule in library.list_rules()
            ),
            summary["by_engine"],
        )

        email_preview = library.preview_script(
            "N-F08",
            "SQL",
            {"table_name": "customer", "column_name": "email"},
        ).to_dict()
        precision_preview = library.preview_script(
            "A-N03",
            "SQL",
            {"table_name": "order_fact", "column_name": "amount"},
        ).to_dict()
        master_detail_preview = library.preview_script(
            "CS-T01",
            "SQL",
            {
                "master_table": "customer",
                "detail_table": "order_fact",
                "master_key": "customer_id",
                "master_compare_column": "currency",
                "detail_compare_column": "currency",
            },
        ).to_dict()
        check("新增规则脚本预览", "email" in email_preview["rendered_expression"], email_preview)
        check("金额精度脚本预览", "ROUND(amount, 2)" in precision_preview["rendered_expression"], precision_preview)
        check("主从一致性脚本预览", "order_fact" in master_detail_preview["rendered_expression"], master_detail_preview)

        workflow = workflow_mod.QualityAssessmentWorkflow(rule_library=library)
        scope = workflow_mod.DataScope(
            data_source="mysql",
            database="dw",
            schema="public",
            table_fqn="mysql.dw.public.customer_order",
            table_name="customer_order",
            fields=["id", "mobile_phone", "amount", "email"],
            business_domain="客户订单",
            batch_id="batch_20260531",
            row_count=3,
        )
        phone_setting = workflow.configure_rule_parameters(
            "N-F02",
            scope,
            target_column="mobile_phone",
            validation_level="P1_WARNING",
        )
        id_setting = workflow.configure_rule_parameters(
            "C-F04",
            scope,
            target_column="id",
            validation_level="P0_BLOCKING",
        )
        amount_setting = workflow.configure_rule_parameters(
            "A-N03",
            scope,
            target_column="amount",
            validation_level="P1_WARNING",
            parameter_overrides={"decimal_scale": "2"},
        )
        email_setting = workflow.configure_rule_parameters(
            "N-F08",
            scope,
            target_column="email",
            validation_level="P1_WARNING",
        )

        sample_rows = [
            {"id": "1", "mobile_phone": "13800138000000000", "amount": "10.00", "email": "ok@example.com"},
            {"id": "1", "mobile_phone": "12345", "amount": "10.123", "email": "bad-email"},
            {"id": "3", "mobile_phone": "13900139000000000", "amount": "20.10", "email": "user@example.com"},
        ]

        phone_trial = workflow.trial_run(phone_setting.setting_id, sample_rows)
        id_trial = workflow.trial_run(id_setting.setting_id, sample_rows)
        check("规则参数设定", len(workflow.get_settings()) == 4, [s.rule_id for s in workflow.get_settings()])
        check("样例试跑识别手机号异常", phone_trial.failure_count == 1, phone_trial.to_dict())
        check("样例试跑识别主键重复", id_trial.failure_count == 1, id_trial.to_dict())

        task = workflow.create_task(
            task_name="客户订单质量评价任务",
            scope=scope,
            rule_setting_ids=[
                phone_setting.setting_id,
                id_setting.setting_id,
                amount_setting.setting_id,
                email_setting.setting_id,
            ],
            schedule="manual",
            scan_mode="full",
            parallelism=2,
        )
        run = workflow.execute_task(task.task_id, sample_rows=sample_rows, batch_id="batch_20260531")
        check("任务执行生成结果", run.total_rules == 4 and run.failed_rules == 4, run.to_dict())
        check("P0失败阻断下游", run.blocked and run.status.value == "blocked", run.to_dict())
        check("质量问题自动生成", len(run.issue_ids) == 4, run.issue_ids)

        dashboard = workflow.build_dashboard(run_ids=[run.run_id]).to_dict()
        check("六维看板输出", len(dashboard["dimension_scores"]) == 6, dashboard["dimension_scores"])
        check("看板包含问题影响范围", dashboard["impact_scope"]["issue_count"] == 4, dashboard["impact_scope"])

        first_issue = run.issue_ids[0]
        lineage = workflow.analyze_issue_lineage(first_issue)
        workflow.update_issue_status(first_issue, "ticketed", assignee="数据责任人")
        workflow.update_issue_status(first_issue, "archived", review_notes="复核通过")
        archived_issue = next(
            issue
            for issue in workflow.query_issues(include_archived=True)
            if issue.issue_id == first_issue
        )
        check("问题血缘分析", lineage["issue_id"] == first_issue and lineage["downstream_impacts"], lineage)
        check("问题闭环归档", archived_issue.archived is True, archived_issue.to_dict())

        archive = workflow.archive_scoring_rules(archived_by="tester")
        report_md = workflow.generate_workflow_report(run_id=run.run_id)
        report_json = workflow.generate_workflow_report(run_id=run.run_id, output_format="json")
        check("计分规则归档", archive.archive_id in report_json["scoring_archives"][0]["archive_id"], archive.to_dict())
        check("报告输出", "质量评价流程执行报告" in report_md and report_json["runs"], report_md[:120])

        api = api_mod.QualityWorkflowAPI(workflow=workflow)
        api_dashboard = api.get_dashboard(api_mod.DashboardQueryRequest(run_ids=[run.run_id]))
        check("流程API门面可调用", api_dashboard["overall_score"] >= 0, api_dashboard)

        result = {
            "test_result": "PASS",
            "total_checks": len(checks),
            "passed_checks": sum(1 for item in checks if item["passed"]),
            "failed_checks": 0,
            "checks": checks,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001 - smoke test should report all failures as JSON
        result = {
            "test_result": "FAIL",
            "total_checks": len(checks),
            "passed_checks": sum(1 for item in checks if item["passed"]),
            "failed_checks": sum(1 for item in checks if not item["passed"]) or 1,
            "checks": checks,
            "error": str(exc),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
