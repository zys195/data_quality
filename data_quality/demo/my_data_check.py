"""
自定义数据质量校验脚本。

使用方式：
    1. 修改下方「===== 1. 配置你的表信息 =====」中的表名和字段
    2. 修改下方「===== 2. 输入你的数据 =====」中的数据行
    3. 修改下方「===== 3. 选择要校验的规则 =====」中的规则
    4. 运行: python data_quality/demo/my_data_check.py
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


# ============================================================
# ===== 1. 配置你的表信息 (修改这里) =====
# ============================================================
MY_TABLE_FQN = "mysql.default.db.employee"   # 表的全限定名
MY_TABLE_NAME = "employee"                    # 表名
MY_FIELDS = ["id", "name", "phone", "email", "age", "salary", "status"]  # 所有字段
MY_BUSINESS_DOMAIN = "人力资源"                # 业务域

# ============================================================
# ===== 2. 输入你的数据 (修改这里) =====
# ============================================================
MY_DATA = [
    {"id": "1", "name": "张三", "phone": "13800138000", "email": "zhangsan@example.com", "age": "28", "salary": "15000", "status": "在职"},
    {"id": "1", "name": "李四", "phone": "12345678901", "email": "bad-email", "age": "35", "salary": "25000", "status": "在职"},
    {"id": "3", "name": "王五", "phone": "13900139000", "email": "wangwu@example.com", "age": "200", "salary": "-5000", "status": "离职"},
    {"id": "4", "name": "", "phone": "", "email": "", "age": "N/A", "salary": "abc", "status": "未知状态"},
]

# ============================================================
# ===== 3. 选择要校验的规则 (修改这里) =====
# ============================================================
# 可用规则ID列表（共95条，下面列出常用规则；其余为白皮书六维扩展规则）：
#   规范性: N-F01(身份证), N-F02(手机号), N-F03(固话), N-F04(IP地址), N-F05(日期),
#           N-F06(金额格式), N-F07(编码规则), N-F08(邮箱), N-C01(编码规范), N-C02(命名规范), N-V01(枚举值域), N-V02(值域范围)
#   完整性: C-F01(非空), C-F02(填充率), C-F03(脏数据), C-F04(唯一性), C-F05(记录完整性), C-L01(关联完整性)
#   准确性: A-N01(数值格式), A-N02(数值范围), A-N03(数值精度), A-R01(计算逻辑), A-B01(业务逻辑), A-T01(时间先后), A-T02(时间范围)
#   一致性: CS-S01(跨系统一致性), C-C01(跨表一致性), CS-T01(主从一致性)
#   时效性: T-F01(数据新鲜度), T-T01(响应时效), T-B01(时间窗口)
#   可访问性: AC-C01(连接可达), AC-S01(查询可达), AC-S02(元数据可达), AC-A01(权限检查)

MY_RULES = [
    {
        "rule_id": "C-F01",       # 非空校验
        "target_column": "name",
        "validation_level": "P0_BLOCKING",
    },
    {
        "rule_id": "N-F02",       # 手机号格式
        "target_column": "phone",
        "validation_level": "P1_WARNING",
    },
    {
        "rule_id": "N-F08",       # 邮箱格式
        "target_column": "email",
        "validation_level": "P1_WARNING",
    },
    {
        "rule_id": "C-F04",       # 唯一性校验
        "target_column": "id",
        "validation_level": "P0_BLOCKING",
    },
    {
        "rule_id": "A-N02",       # 数值范围
        "target_column": "age",
        "validation_level": "P1_WARNING",
        "parameter_overrides": {"min_value": "0", "max_value": "120"},
    },
    {
        "rule_id": "A-N02",       # 数值范围（薪资）
        "target_column": "salary",
        "validation_level": "P1_WARNING",
        "parameter_overrides": {"min_value": "0", "max_value": "500000"},
    },
    {
        "rule_id": "N-V01",       # 枚举值域
        "target_column": "status",
        "validation_level": "P1_WARNING",
        "parameter_overrides": {"allowed_values": "在职,离职,休假"},
    },
]


def install_runtime_stubs():
    if "pydantic" not in sys.modules:
        pydantic = types.ModuleType("pydantic")
        class BaseModel:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)
            def model_dump(self):
                return dict(self.__dict__)
        pydantic.BaseModel = BaseModel
        pydantic.Field = lambda default=None, **kw: None if default is Ellipsis else default
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
        CRITICAL = "CRITICAL"; HIGH = "HIGH"; MEDIUM = "MEDIUM"; LOW = "LOW"

    class QualityDimension(str, Enum):
        NORMATIVITY = "normativity"; COMPLETENESS = "completeness"
        ACCURACY = "accuracy"; CONSISTENCY = "consistency"
        TIMELINESS = "timeliness"; ACCESSIBILITY = "accessibility"

    class QualityRuleCategory(str, Enum):
        FORMAT_CHECK="format_check"; ENUM_CHECK="enum_check"; REGEX_CHECK="regex_check"
        NULL_CHECK="null_check"; FILL_RATE_CHECK="fill_rate_check"; REFERENCE_CHECK="reference_check"
        RANGE_CHECK="range_check"; PRECISION_CHECK="precision_check"; DUPLICATE_CHECK="duplicate_check"
        DIRTY_DATA_CHECK="dirty_data_check"; CROSS_TABLE_CHECK="cross_table_check"
        CROSS_SYSTEM_CHECK="cross_system_check"; CALCULATION_CHECK="calculation_check"
        UPDATE_LATENCY_CHECK="update_latency_check"; TIME_SEQUENCE_CHECK="time_sequence_check"
        HISTORY_VALIDITY_CHECK="history_validity_check"; ACCESSIBLE_CHECK="accessible_check"
        PERFORMANCE_CHECK="performance_check"; UNIQUENESS_CHECK="uniqueness_check"

    evaluator.RuleSeverity = RuleSeverity
    models.QualityDimension = QualityDimension
    models.QualityRuleCategory = QualityRuleCategory
    models.get_dimension_by_test_definition = lambda _name: QualityDimension.NORMATIVITY

    sys.modules.update({
        "metadata": metadata, "metadata.data_quality": dq,
        "metadata.data_quality.dimension": dim_pkg,
        "metadata.data_quality.dimension.evaluator": evaluator,
        "metadata.data_quality.dimension.models": models,
        "metadata.data_quality.rules": rules_pkg,
        "metadata.data_quality.workflow": workflow_pkg,
        "metadata.data_quality.api": api_pkg,
    })


def load_module(name, rel_path):
    path = DATA_QUALITY / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    install_runtime_stubs()

    rule_library_mod = load_module("metadata.data_quality.rules.rule_library", "rules/rule_library.py")
    workflow_mod = load_module("metadata.data_quality.workflow.quality_assessment_workflow", "workflow/quality_assessment_workflow.py")

    library = rule_library_mod.RuleLibrary(load_builtin=True)
    workflow = workflow_mod.QualityAssessmentWorkflow(rule_library=library)

    # 1. 定义数据范围
    scope = workflow_mod.DataScope(
        data_source="mysql",
        database="default",
        schema="db",
        table_fqn=MY_TABLE_FQN,
        table_name=MY_TABLE_NAME,
        fields=MY_FIELDS,
        business_domain=MY_BUSINESS_DOMAIN,
        batch_id="manual_batch",
        row_count=len(MY_DATA),
    )

    # 2. 配置规则参数
    setting_ids = []
    for rule_cfg in MY_RULES:
        setting = workflow.configure_rule_parameters(
            rule_id=rule_cfg["rule_id"],
            scope=scope,
            target_column=rule_cfg["target_column"],
            validation_level=rule_cfg.get("validation_level", "P1_WARNING"),
            parameter_overrides=rule_cfg.get("parameter_overrides", {}),
        )
        setting_ids.append(setting.setting_id)

    print(f"\n{'='*60}")
    print(f"  数据质量校验报告")
    print(f"  表名: {MY_TABLE_FQN}")
    print(f"  数据行数: {len(MY_DATA)}")
    print(f"  校验规则数: {len(MY_RULES)}")
    print(f"{'='*60}\n")

    # 3. 逐条规则试跑，显示详情
    print("--- 规则校验明细 ---\n")
    for rule_cfg in MY_RULES:
        setting = next(s for s in workflow.get_settings() if s.rule_id == rule_cfg["rule_id"] and s.target_column == rule_cfg["target_column"])
        trial = workflow.trial_run(setting.setting_id, MY_DATA)
        rule_info = library.get_rule(rule_cfg["rule_id"])

        status_icon = "[PASS]" if trial.passed else "[FAIL]"
        print(f"  {status_icon} {rule_info.display_name} ({rule_cfg['rule_id']})")
        print(f"      字段: {rule_cfg['target_column']}  |  通过率: {trial.pass_rate:.0%}  |  异常行数: {trial.failure_count}/{trial.total_rows}")
        if trial.invalid_samples:
            for sample in trial.invalid_samples:
                print(f"        -> 第{sample.row_index+1}行: 值={sample.value}  原因: {sample.reason}")
        print()

    # 4. 创建任务并执行
    task = workflow.create_task(
        task_name=f"{MY_TABLE_NAME} 质量评价",
        scope=scope,
        rule_setting_ids=setting_ids,
        schedule="manual",
        scan_mode="full",
    )
    run = workflow.execute_task(task.task_id, sample_rows=MY_DATA, batch_id="manual_batch")

    # 5. 构建看板
    dashboard = workflow.build_dashboard(run_ids=[run.run_id])

    # 6. 输出六维评分
    print("--- 六维质量评分 ---\n")
    print(f"  {'维度':<10} {'得分':>6} {'权重':>6} {'规则通过':>10}")
    print(f"  {'-'*35}")
    for dim_key, dim_data in dashboard.dimension_scores.items():
        print(f"  {dim_data['dimension_zh']:<10} {dim_data['score']:>5.1f}  {dim_data['weight']:>4.0%}  {dim_data['passed_rules']:>3}/{dim_data['total_rules']:>3}")

    print(f"\n  {'='*35}")
    print(f"  总体得分: {dashboard.overall_score:.1f} / 100")
    print(f"  质量等级: {dashboard.quality_level}")
    print(f"  任务状态: {run.status.value}")
    if run.blocked:
        print(f"  阻断原因: {run.blocked_reason}")

    # 7. 输出完整 JSON
    print(f"\n{'='*60}")
    print(f"  完整 JSON 结果")
    print(f"{'='*60}\n")
    result = {
        "table": MY_TABLE_FQN,
        "data_rows": len(MY_DATA),
        "rules_count": len(MY_RULES),
        "task_status": run.status.value,
        "overall_score": dashboard.overall_score,
        "quality_level": dashboard.quality_level,
        "rule_pass_rate": dashboard.rule_pass_rate,
        "dimension_scores": dashboard.dimension_scores,
        "rule_results": [r.to_dict() for r in run.rule_results],
        "issues": [{"issue_id": iid, "rule_id": workflow._issues[iid].rule_id, "status": workflow._issues[iid].status.value} for iid in run.issue_ids],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 8. 输出 Markdown 报告
    report = workflow.generate_workflow_report(run_id=run.run_id)
    print(f"\n{'='*60}")
    print(f"  Markdown 报告")
    print(f"{'='*60}\n")
    print(report)


if __name__ == "__main__":
    main()
