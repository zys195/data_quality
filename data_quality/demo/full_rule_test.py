"""
数据质量规则全量测试脚本。

逐条测试规则库中全部 95 条内置规则，每条规则使用模拟数据
（包含一条通过数据和一条失败数据），记录试跑结果并生成 Markdown 测试报告。

运行方式：
    python data_quality/demo/full_rule_test.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
DATA_QUALITY = ROOT / "data_quality"


# ===================================================================
# 运行时桩模块
# ===================================================================
def install_runtime_stubs() -> None:
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
        FORMAT_CHECK = "format_check"; ENUM_CHECK = "enum_check"
        REGEX_CHECK = "regex_check"; NULL_CHECK = "null_check"
        FILL_RATE_CHECK = "fill_rate_check"; REFERENCE_CHECK = "reference_check"
        RANGE_CHECK = "range_check"; PRECISION_CHECK = "precision_check"
        DUPLICATE_CHECK = "duplicate_check"; DIRTY_DATA_CHECK = "dirty_data_check"
        CROSS_TABLE_CHECK = "cross_table_check"; CROSS_SYSTEM_CHECK = "cross_system_check"
        CALCULATION_CHECK = "calculation_check"; UPDATE_LATENCY_CHECK = "update_latency_check"
        TIME_SEQUENCE_CHECK = "time_sequence_check"; HISTORY_VALIDITY_CHECK = "history_validity_check"
        ACCESSIBLE_CHECK = "accessible_check"; PERFORMANCE_CHECK = "performance_check"
        UNIQUENESS_CHECK = "uniqueness_check"

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


def load_module(name: str, rel_path: str):
    path = DATA_QUALITY / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ===================================================================
# 每条规则的模拟数据与参数
# ===================================================================

# 通用字段模板
PASS_ROW = {
    "id": "PASS-001",
    "id_card": "110101199003077738",
    "phone": "13800138000000000",
    "email": "user@example.com",
    "code": "STD001",
    "region_code": "110101",
    "name": "张三",
    "value": "valid_value",
    "amount": "100.00",
    "age": "28",
    "salary": "15000.50",
    "score": "95.5",
    "status": "有效",
    "flag": "Y",
    "event_time": "2026-06-19 10:00:00",
    "create_time": "2026-06-19 08:00:00",
    "update_time": "2026-06-19 09:00:00",
    "start_time": "2026-06-19 08:00:00",
    "end_time": "2026-06-19 18:00:00",
    "plate": "京A12345",
    "imei": "123456789012345",
    "mac_addr": "00:1A:2B:3C:4D:5E",
    "ip_addr": "192.168.1.100",
    "url": "https://www.example.com/path",
    "credit_code": "91110108MA01K1B123",
    "bank_card": "6222021234567890123",
    "post_code": "100000",
    "currency": "CNY",
    "country_code": "CN",
    "date_val": "2026-06-19",
    "datetime_val": "2026-06-19 10:00:00",
    "longitude": "116.404",
    "latitude": "39.915",
    "desc": "正常描述",
    "batch_status": "FINISHED",
    "batch_start_time": "2026-06-19T06:00:00",
    "batch_end_time": "2026-06-19T06:30:00",
    "load_time": "2026-06-19T06:00:00",
    "process_time": "2026-06-19T06:10:00",
    "grantee": "dq_reader",
    "api_name": "query_orders",
    "mobile_phone": "13800138000000000",
    "tel": "01012345678",
    "need_attachment_flag": "N",
    "attachment_id": "",
    "biz_date": "2026-06-19",
    "business_id": "BIZ001",
    "source_system": "ERP",
    "price": "10.00",
    "quantity": "10",
    "total_amount": "100.00",
}

FAIL_ROW = {
    "id": "FAIL-001",
    "id_card": "12345",
    "phone": "abc",
    "email": "bad-email",
    "code": "bad code!",
    "region_code": "0X0000",
    "name": "张@#三\n",
    "value": "",
    "amount": "abc",
    "age": "200",
    "salary": "-5000",
    "score": "999",
    "status": "未知状态",
    "flag": "maybe",
    "event_time": "2099-01-01 00:00:00",
    "create_time": "2099-01-01 00:00:00",
    "update_time": "2020-01-01 00:00:00",
    "start_time": "2026-06-19 18:00:00",
    "end_time": "2026-06-19 08:00:00",
    "plate": "无效车牌",
    "imei": "ABC",
    "mac_addr": "ZZ:ZZ:ZZ",
    "ip_addr": "999.999.999.999",
    "url": "not a url",
    "credit_code": "XYZ",
    "bank_card": "1234",
    "post_code": "ABC",
    "currency": "人民币",
    "country_code": "China",
    "date_val": "19/06/2026",
    "datetime_val": "2026/06/19 10时",
    "longitude": "",
    "latitude": "39.915",
    "desc": "   ",
    "batch_status": "RUNNING",
    "batch_start_time": "2026-06-19T06:00:00",
    "batch_end_time": "2026-06-19T08:00:00",
    "load_time": "2026-06-19T06:00:00",
    "process_time": "2026-06-19T09:00:00",
    "grantee": "unknown_user",
    "api_name": "query_orders",
    "mobile_phone": "",
    "tel": "",
    "need_attachment_flag": "Y",
    "attachment_id": "",
    "biz_date": "2026-06-19",
    "business_id": "",
    "source_system": "",
    "price": "10.00",
    "quantity": "10",
    "total_amount": "999.00",
}

# 规则测试配置：(rule_id, target_column, parameter_overrides, special_data_flag)
# special_data_flag 用于一些需要特殊处理的规则
RULE_TEST_CONFIG = {
    # ---- 规范性 ----
    "N-F01": ("id_card", {}, "regex"),
    "N-F02": ("phone", {}, "regex"),
    "N-F03": ("plate", {}, "regex"),
    "N-F04": ("imei", {}, "regex"),
    "N-F05": ("mac_addr", {}, "regex"),
    "N-F06": ("ip_addr", {}, "regex"),
    "N-F07": ("url", {}, "regex"),
    "N-F08": ("email", {}, "regex"),
    "N-C01": ("code", {}, "regex"),
    "N-C02": ("region_code", {}, "regex"),
    "N-N01": ("name", {}, "regex"),
    "N-V01": ("status", {"allowed_values": "'有效','无效','待审'"}, "enum"),
    # ---- 完整性 ----
    "C-F01": ("name", {}, "not_null"),
    "C-F02": ("desc", {"min_fill_rate": "0.5"}, "fill_rate"),
    "C-F03": ("desc", {}, "blank_string"),
    "C-F04": ("id", {}, "unique"),
    "C-R01": ("", {"record_complete_condition": "1 = 1"}, "table"),
    "C-L01": ("", {"referenced_table": "master_table", "foreign_key": "id", "referenced_key": "id"}, "table"),
    # ---- 准确性 ----
    "A-N01": ("amount", {}, "numeric"),
    "A-N02": ("age", {"min_value": "0", "max_value": "120"}, "range"),
    "A-N03": ("amount", {"decimal_scale": "2"}, "precision"),
    "A-L01": ("name", {"min_length": "1", "max_length": "50"}, "length"),
    "A-B01": ("", {"invalid_condition": "1 = 1"}, "table"),
    "A-T01": ("", {"start_time_column": "start_time", "end_time_column": "end_time"}, "table"),
    "A-T02": ("event_time", {"tolerance_minutes": "5"}, "future_time"),
    # ---- 一致性 ----
    "CS-S01": ("", {"source_table": "src", "target_table": "tgt", "source_key": "id", "target_key": "id", "compare_column": "amount"}, "table"),
    "CS-C01": ("", {"calculation_expression": "price * quantity", "result_column": "total_amount"}, "table"),
    "CS-T01": ("", {"master_table": "customer", "detail_table": "order_fact", "master_key": "id", "master_compare_column": "status", "detail_compare_column": "status"}, "table"),
    # ---- 时效性 ----
    "T-F01": ("", {"update_time_column": "update_time", "max_delay_hours": "24"}, "table"),
    "T-D01": ("", {"load_time_column": "load_time", "process_time_column": "process_time", "max_delay_minutes": "120"}, "table"),
    "T-B01": ("", {"batch_status_column": "batch_status", "expected_status": "FINISHED", "batch_start_time_column": "batch_start_time", "batch_end_time_column": "batch_end_time", "max_finish_minutes": "60"}, "table"),
    # ---- 可访问性 ----
    "AC-C01": ("", {}, "table"),
    "AC-P01": ("", {"grantee": "dq_reader", "privilege_type": "SELECT"}, "table"),
    "AC-S01": ("", {"max_response_ms": "1000"}, "table"),
    "AC-S02": ("", {"api_monitor_table": "api_monitor_log", "api_name": "query_orders", "max_response_ms": "1000"}, "table"),

    # ---- 规范性扩展 ----
    "N-W01": ("date_val", {}, "regex"),
    "N-W02": ("datetime_val", {}, "regex"),
    "N-W03": ("credit_code", {}, "regex"),
    "N-W04": ("bank_card", {}, "regex"),
    "N-W05": ("post_code", {}, "regex"),
    "N-W06": ("currency", {}, "regex"),
    "N-W07": ("country_code", {}, "regex"),
    "N-W08": ("flag", {"allowed_values": "'Y','N','1','0'"}, "enum"),
    "N-W09": ("", {}, "table"),
    "N-W10": ("", {}, "table"),

    # ---- 完整性扩展 ----
    "C-W01": ("", {"mobile_column": "mobile_phone", "email_column": "email", "tel_column": "tel"}, "table"),
    "C-W02": ("", {"key_column_a": "business_id", "key_column_b": "source_system"}, "table"),
    "C-W03": ("", {"min_row_count": "1"}, "table"),
    "C-W04": ("", {"partition_column": "biz_date", "partition_value": "2026-06-19", "min_row_count": "1"}, "table"),
    "C-W05": ("", {"required_flag_column": "need_attachment_flag", "required_flag_value": "Y", "attachment_column": "attachment_id"}, "table"),
    "C-W06": ("", {"longitude_column": "longitude", "latitude_column": "latitude"}, "table"),
    "C-W07": ("", {"invalid_condition": "1 = 1"}, "table"),
    "C-W08": ("", {"invalid_condition": "1 = 1"}, "table"),
    "C-W09": ("", {"max_duplicate_rate": "0.1"}, "table"),
    "C-W10": ("", {"total_min_fill_rate": "0.6"}, "table"),

    # ---- 准确性扩展 ----
    "A-W01": ("amount", {"min_value": "0", "max_value": "1000000"}, "range"),
    "A-W02": ("salary", {"min_value": "0", "max_value": "500000"}, "range"),
    "A-W03": ("amount", {"decimal_scale": "2"}, "precision"),
    "A-W04": ("amount", {}, "table"),
    "A-W05": ("", {"calculation_expression": "price * quantity", "result_column": "total_amount"}, "table"),
    "A-W06": ("", {"invalid_condition": "1 = 1"}, "table"),
    "A-W07": ("", {"start_time_column": "start_time", "end_time_column": "end_time"}, "table"),
    "A-W08": ("event_time", {"tolerance_minutes": "5"}, "future_time"),
    "A-W09": ("event_time", {}, "table"),
    "A-W10": ("", {"invalid_condition": "1 = 1"}, "table"),

    # ---- 一致性扩展 ----
    "CS-W01": ("", {"source_table": "src", "target_table": "tgt", "source_key": "id", "target_key": "id", "compare_column": "amount"}, "table"),
    "CS-W02": ("", {"calculation_expression": "price * quantity", "result_column": "total_amount"}, "table"),
    "CS-W03": ("", {"master_table": "customer", "detail_table": "order_fact", "master_key": "id", "master_compare_column": "status", "detail_compare_column": "status"}, "table"),
    "CS-W04": ("", {"reference_table": "dim_product", "foreign_key": "product_id", "referenced_key": "id"}, "table"),
    "CS-W05": ("", {"invalid_condition": "1 = 1"}, "table"),
    "CS-W06": ("", {"source_table": "src", "target_table": "tgt", "source_key": "id", "target_key": "id", "compare_column": "amount"}, "table"),
    "CS-W07": ("", {"invalid_condition": "1 = 1"}, "table"),
    "CS-W08": ("", {"invalid_condition": "1 = 1"}, "table"),
    "CS-W09": ("", {"source_table": "src", "target_table": "tgt", "compare_column": "amount"}, "table"),
    "CS-W10": ("", {"invalid_condition": "1 = 1"}, "table"),

    # ---- 时效性扩展 ----
    "T-W01": ("", {"update_time_column": "update_time", "max_delay_hours": "24"}, "table"),
    "T-W02": ("", {"update_time_column": "update_time", "max_delay_hours": "1"}, "table"),
    "T-W03": ("", {"load_time_column": "load_time", "process_time_column": "process_time", "max_delay_minutes": "120"}, "table"),
    "T-W04": ("", {"batch_status_column": "batch_status", "expected_status": "FINISHED", "batch_start_time_column": "batch_start_time", "batch_end_time_column": "batch_end_time", "max_finish_minutes": "60"}, "table"),
    "T-W05": ("", {"invalid_condition": "1 = 1"}, "table"),
    "T-W06": ("event_time", {"tolerance_minutes": "5"}, "future_time"),
    "T-W07": ("", {"update_time_column": "update_time", "max_delay_hours": "24"}, "table"),
    "T-W08": ("", {"invalid_condition": "1 = 1"}, "table"),
    "T-W09": ("", {"invalid_condition": "1 = 1"}, "table"),
    "T-W10": ("", {"invalid_condition": "1 = 1"}, "table"),

    # ---- 可访问性扩展 ----
    "AC-W01": ("", {}, "table"),
    "AC-W02": ("", {"grantee": "dq_reader", "privilege_type": "SELECT"}, "table"),
    "AC-W03": ("", {"max_response_ms": "1000"}, "table"),
    "AC-W04": ("", {"api_monitor_table": "api_monitor_log", "api_name": "query_orders", "max_response_ms": "1000"}, "table"),
    "AC-W05": ("", {"invalid_condition": "1 = 1"}, "table"),
    "AC-W06": ("", {"invalid_condition": "1 = 1"}, "table"),
    "AC-W07": ("", {"max_response_ms": "1000"}, "table"),
    "AC-W08": ("", {"api_monitor_table": "api_monitor_log", "api_name": "query_orders", "max_response_ms": "1000"}, "table"),
    "AC-W09": ("", {"invalid_condition": "1 = 1"}, "table"),
    "AC-W10": ("", {"invalid_condition": "1 = 1"}, "table"),
}


def _build_sample_rows(rule_id: str, target_column: str, data_flag: str) -> List[Dict[str, Any]]:
    """为每条规则构建包含一条通过、一条失败的模拟数据。"""
    pass_row = dict(PASS_ROW)
    fail_row = dict(FAIL_ROW)

    # 对于表级规则使用 __fail_rules 标记来强制触发
    if data_flag == "table":
        fail_row["__fail_rules"] = [rule_id]
        fail_row["__fail_reason"] = f"规则{rule_id}测试样例标记未通过"
    elif data_flag == "future_time":
        fail_row["__fail_rules"] = [rule_id]
        fail_row["__fail_reason"] = "时间晚于允许窗口"
        fail_row["__future_time"] = True
    elif data_flag == "unique":
        # C-F04: id 重复
        fail_row["id"] = "PASS-001"  # 与 pass_row 相同的 id
    elif data_flag == "not_null":
        # C-F01: 空值
        fail_row[target_column] = ""
    elif data_flag == "blank_string":
        # C-F03: 空白字符串
        fail_row[target_column] = "   "
    elif data_flag == "fill_rate":
        # C-F02: 填充率不足
        fail_row[target_column] = ""
    elif data_flag == "numeric":
        # A-N01: 非数值
        fail_row[target_column] = "not_a_number"
    elif data_flag == "range":
        # A-N02: 超出范围
        pass  # FAIL_ROW 已经有超范围的值
    elif data_flag == "precision":
        # A-N03: 精度超限
        fail_row[target_column] = "100.123"
    elif data_flag == "length":
        # A-L01: 长度超限
        fail_row[target_column] = ""  # 空字符串长度为0, 小于 min_length=1
    elif data_flag == "enum":
        pass  # FAIL_ROW 的 status 已经是 "未知状态"
    elif data_flag == "regex":
        pass  # FAIL_ROW 的字段值已经是不匹配的

    return [pass_row, fail_row]


def main() -> int:
    install_runtime_stubs()
    rule_library_mod = load_module(
        "metadata.data_quality.rules.rule_library", "rules/rule_library.py"
    )
    workflow_mod = load_module(
        "metadata.data_quality.workflow.quality_assessment_workflow",
        "workflow/quality_assessment_workflow.py",
    )

    library = rule_library_mod.RuleLibrary(load_builtin=True)
    all_rules = library.list_rules()
    rule_map = {r.rule_id: r for r in all_rules}

    workflow = workflow_mod.QualityAssessmentWorkflow(rule_library=library)

    scope = workflow_mod.DataScope(
        data_source="test_fixture",
        database="dq",
        schema="test",
        table_fqn="test_fixture.dq.test.full_rule_test",
        table_name="full_rule_test",
        fields=list(PASS_ROW.keys()),
        business_domain="全量规则测试",
        batch_id="full_rule_test_batch",
        row_count=2,
    )

    results: List[Dict[str, Any]] = []
    test_passed = 0
    test_failed = 0
    test_errors = 0

    print(f"{'='*70}")
    print(f"  数据质量规则全量测试")
    print(f"  规则总数: {len(all_rules)}")
    print(f"  测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    for idx, rule in enumerate(all_rules, 1):
        rule_id = rule.rule_id
        config = RULE_TEST_CONFIG.get(rule_id)
        if not config:
            # 未配置测试数据的规则，使用通用 table 级测试
            target_column, param_overrides, data_flag = "", {}, "table"
        else:
            target_column, param_overrides, data_flag = config

        try:
            # 1. 配置规则参数
            setting = workflow.configure_rule_parameters(
                rule_id=rule_id,
                scope=scope,
                target_column=target_column,
                validation_level="P1_WARNING",
                parameter_overrides=param_overrides,
            )

            # 2. 构建模拟数据
            sample_rows = _build_sample_rows(rule_id, target_column, data_flag)

            # 3. 试跑
            trial = workflow.trial_run(setting.setting_id, sample_rows)

            # 4. 判断试跑结果
            # 期望: 总行数=2, 至少1条失败 (因为第二条是故意构造的失败数据)
            trial_ok = trial.total_rows == 2
            has_failure = trial.failure_count >= 1

            result_status = "PASS" if (trial_ok and has_failure) else "WARN"
            if result_status == "PASS":
                test_passed += 1
            else:
                test_failed += 1

            invalid_details = []
            for s in trial.invalid_samples:
                invalid_details.append({
                    "row_index": s.row_index,
                    "value": str(s.value)[:80],
                    "reason": s.reason,
                })

            results.append({
                "seq": idx,
                "rule_id": rule_id,
                "display_name": rule.display_name,
                "dimension": rule.dimension.value,
                "severity": rule.severity.value if hasattr(rule.severity, 'value') else str(rule.severity),
                "entity_type": rule.applicability.entity_type.value,
                "target_column": target_column,
                "data_flag": data_flag,
                "trial_passed": trial.passed,
                "total_rows": trial.total_rows,
                "failure_count": trial.failure_count,
                "pass_rate": trial.pass_rate,
                "result": result_status,
                "invalid_samples": invalid_details,
                "error": None,
            })

            status_icon = "[OK]" if result_status == "PASS" else "[!!]"
            print(f"  {status_icon} [{idx:>3}/{len(all_rules)}] {rule_id:<8} {rule.display_name:<30} "
                  f"fail={trial.failure_count}/{trial.total_rows}  pass_rate={trial.pass_rate:.0%}")

        except Exception as exc:
            test_errors += 1
            results.append({
                "seq": idx,
                "rule_id": rule_id,
                "display_name": rule.display_name,
                "dimension": rule.dimension.value,
                "severity": rule.severity.value if hasattr(rule.severity, 'value') else str(rule.severity),
                "entity_type": rule.applicability.entity_type.value,
                "target_column": target_column,
                "data_flag": data_flag,
                "trial_passed": False,
                "total_rows": 0,
                "failure_count": 0,
                "pass_rate": 0.0,
                "result": "ERROR",
                "invalid_samples": [],
                "error": str(exc),
            })
            print(f"  [ERR] [{idx:>3}/{len(all_rules)}] {rule_id:<8} {rule.display_name:<30} ERROR: {exc}")

    # ---- 汇总 ----
    total = len(all_rules)
    print(f"\n{'='*70}")
    print(f"  测试汇总")
    print(f"{'='*70}")
    print(f"  规则总数: {total}")
    print(f"  通过: {test_passed}  警告: {test_failed}  错误: {test_errors}")
    print(f"  通过率: {test_passed/total:.1%}")

    # ---- 生成 Markdown 报告 ----
    md_lines = _render_markdown_report(results, total, test_passed, test_failed, test_errors)
    md_path = DATA_QUALITY / "docs" / "full_rule_test_report.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    # ---- 生成 JSON 报告 ----
    json_path = DATA_QUALITY / "docs" / "full_rule_test_report.json"
    json_data = {
        "test_title": "数据质量规则全量测试报告",
        "tested_at": datetime.now().replace(microsecond=0).isoformat(),
        "total_rules": total,
        "passed": test_passed,
        "warnings": test_failed,
        "errors": test_errors,
        "pass_rate": round(test_passed / total, 4) if total else 0,
        "results": results,
    }
    json_path.write_text(
        json.dumps(json_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"\n  Markdown 报告: {md_path}")
    print(f"  JSON 报告: {json_path}")
    return 0 if test_errors == 0 else 1


def _render_markdown_report(
    results: List[Dict[str, Any]],
    total: int,
    passed: int,
    warnings: int,
    errors: int,
) -> List[str]:
    dimension_zh = {
        "normativity": "规范性",
        "completeness": "完整性",
        "accuracy": "准确性",
        "consistency": "一致性",
        "timeliness": "时效性",
        "accessibility": "可访问性",
    }
    lines = [
        "# 数据质量规则全量测试报告",
        "",
        f"- 测试时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 规则总数：{total}",
        f"- 通过数：{passed}",
        f"- 警告数：{warnings}",
        f"- 错误数：{errors}",
        f"- 通过率：{passed/total:.1%}" if total else "- 通过率：N/A",
        "",
        "## 测试方法",
        "",
        "每条规则使用两条模拟数据进行试跑：",
        "- **通过数据**：构造符合规则约束的合法值",
        "- **失败数据**：构造违反规则约束的非法值（列级规则使用非法值，表级规则使用 `__fail_rules` 标记）",
        "",
        "判定标准：试跑总行数为 2 且至少检测到 1 条异常记录即为 PASS；否则为 WARN。",
        "",
        "## 按维度统计",
        "",
    ]

    # 按维度统计
    dim_stats: Dict[str, Dict[str, int]] = {}
    for r in results:
        dim = r["dimension"]
        if dim not in dim_stats:
            dim_stats[dim] = {"total": 0, "passed": 0, "warn": 0, "error": 0}
        dim_stats[dim]["total"] += 1
        if r["result"] == "PASS":
            dim_stats[dim]["passed"] += 1
        elif r["result"] == "WARN":
            dim_stats[dim]["warn"] += 1
        else:
            dim_stats[dim]["error"] += 1

    lines.append("| 维度 | 规则数 | 通过 | 警告 | 错误 | 通过率 |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for dim in ["normativity", "completeness", "accuracy", "consistency", "timeliness", "accessibility"]:
        s = dim_stats.get(dim, {"total": 0, "passed": 0, "warn": 0, "error": 0})
        rate = f"{s['passed']/s['total']:.0%}" if s["total"] else "N/A"
        lines.append(f"| {dimension_zh.get(dim, dim)} | {s['total']} | {s['passed']} | {s['warn']} | {s['error']} | {rate} |")
    lines.append("")

    # 测试明细
    lines.append("## 规则测试明细")
    lines.append("")
    lines.append("| 序号 | 规则ID | 规则名称 | 维度 | 严重度 | 目标列 | 总行数 | 异常数 | 通过率 | 结果 |")
    lines.append("| ---:| --- | --- | --- | --- | --- | ---:| ---:| ---:| --- |")

    for r in results:
        dim_label = dimension_zh.get(r["dimension"], r["dimension"])
        rate_str = f"{r['pass_rate']:.0%}" if r["total_rows"] else "N/A"
        lines.append(
            f"| {r['seq']} | {r['rule_id']} | {r['display_name']} | {dim_label} | {r['severity']} | "
            f"{r['target_column'] or '(表级)'} | {r['total_rows']} | {r['failure_count']} | {rate_str} | {r['result']} |"
        )
    lines.append("")

    # 异常样例详情
    sample_details = [r for r in results if r["invalid_samples"]]
    if sample_details:
        lines.append("## 异常样例详情")
        lines.append("")
        for r in sample_details:
            lines.append(f"### {r['rule_id']} - {r['display_name']}")
            lines.append("")
            for s in r["invalid_samples"]:
                lines.append(f"- 第{s['row_index']+1}行：值=`{s['value']}`，原因：{s['reason']}")
            lines.append("")

    # 错误详情
    error_details = [r for r in results if r["error"]]
    if error_details:
        lines.append("## 错误详情")
        lines.append("")
        for r in error_details:
            lines.append(f"### {r['rule_id']} - {r['display_name']}")
            lines.append(f"- 错误信息：{r['error']}")
            lines.append("")

    return lines


if __name__ == "__main__":
    raise SystemExit(main())
