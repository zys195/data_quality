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
质量评价规则库 API 服务。

该模块提供后端调用门面，方便 REST 层或服务层直接接入规则导入、CRUD、
复用、脚本预览和统计能力。
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from metadata.data_quality.rules.rule_library import (
    RuleImportResult,
    RuleLibrary,
    RuleLibrarySummary,
    RuleReusePlan,
    RuleTemplate,
)


class RuleImportRequest(BaseModel):
    """规则导入请求。"""

    rules: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="待导入规则列表；与 file_path 二选一",
    )
    file_path: Optional[str] = Field(None, description="JSON/YAML规则文件路径")
    overwrite: bool = Field(False, description="规则编号冲突时是否覆盖")


class RuleCreateRequest(BaseModel):
    """规则新增请求。"""

    rule: Dict[str, Any] = Field(..., description="规则模板内容")
    overwrite: bool = Field(False, description="规则编号冲突时是否覆盖")


class RuleUpdateRequest(BaseModel):
    """规则修改请求。"""

    rule_id: str = Field(..., description="规则编号")
    updates: Dict[str, Any] = Field(..., description="待更新字段")


class RuleDeleteRequest(BaseModel):
    """规则删除请求。"""

    rule_id: str = Field(..., description="规则编号")
    soft_delete: bool = Field(False, description="是否软删除为废弃状态")


class RuleQueryRequest(BaseModel):
    """规则查询请求。"""

    dimension: Optional[str] = Field(None, description="评价维度")
    entity_type: Optional[str] = Field(None, description="适用对象")
    engine: Optional[str] = Field(None, description="执行引擎：GE/SQL/ETL")
    problem_category: Optional[str] = Field(None, description="问题归类")
    source_type: Optional[str] = Field(None, description="规则来源")
    status: Optional[str] = Field(None, description="规则状态")
    keyword: Optional[str] = Field(None, description="关键词")
    include_disabled: bool = Field(True, description="是否包含停用/废弃规则")


class RuleScriptPreviewRequest(BaseModel):
    """规则脚本预览请求。"""

    rule_id: str = Field(..., description="规则编号")
    engine: str = Field("SQL", description="执行引擎：GE/SQL/ETL")
    target_object: Optional[Dict[str, Any]] = Field(
        None,
        description="目标对象，如 table_name、column_name、foreign_key 等",
    )
    parameter_overrides: Dict[str, Any] = Field(
        default_factory=dict,
        description="规则参数覆盖",
    )


class RuleReuseRequest(BaseModel):
    """规则复用请求。"""

    rule_id: str = Field(..., description="规则编号")
    target_object: Dict[str, Any] = Field(
        ...,
        description="目标对象，如 table_name、column_name、关联表等",
    )
    engine: str = Field("SQL", description="执行引擎：GE/SQL/ETL")
    parameter_overrides: Dict[str, Any] = Field(default_factory=dict)
    test_case_name: Optional[str] = Field(None, description="生成的测试用例名称")


class RuleTemplateResponse(BaseModel):
    """规则模板响应。"""

    rule_id: str
    name: str
    display_name: str
    dimension: str
    dimension_zh: str
    source_type: str
    problem_category: str
    core_definition: str
    applicable_object: Dict[str, Any]
    test_definition_name: str
    parameters: Dict[str, Any]
    threshold: Dict[str, Any]
    validation_level: str
    severity: str
    responsible_role: str
    remediation_suggestion: str
    issue_strategy: str
    scripts: Dict[str, Dict[str, Any]]
    tags: List[str]
    status: str
    version: int
    created_at: datetime
    updated_at: datetime
    reuse_count: int = 0


class RuleImportResponse(BaseModel):
    """规则导入响应。"""

    imported_count: int
    updated_count: int
    skipped_count: int
    errors: List[str]


class RuleListResponse(BaseModel):
    """规则列表响应。"""

    total: int
    rules: List[RuleTemplateResponse]


class RuleScriptPreviewResponse(BaseModel):
    """脚本预览响应。"""

    rule_id: str
    engine: str
    expression: str
    rendered_expression: str
    parameters: Dict[str, Any]
    unresolved_placeholders: List[str]


class RuleReuseResponse(BaseModel):
    """规则复用响应。"""

    rule_id: str
    rule_name: str
    target_object: Dict[str, Any]
    engine: str
    test_case_config: Dict[str, Any]
    script_preview: RuleScriptPreviewResponse
    threshold: Dict[str, Any]
    responsible_role: str
    remediation_suggestion: str


class RuleLibrarySummaryResponse(BaseModel):
    """规则库统计响应。"""

    total_rules: int
    active_rules: int
    disabled_rules: int
    deprecated_rules: int
    builtin_rules: int
    custom_rules: int
    by_dimension: Dict[str, int]
    by_problem_category: Dict[str, int]
    by_validation_level: Dict[str, int]
    by_engine: Dict[str, int]
    by_source_type: Dict[str, int]


class RuleLibraryAPI:
    """规则库 API 服务。"""

    def __init__(
        self,
        library: Optional[RuleLibrary] = None,
        storage_path: Optional[Path] = None,
    ):
        self.library = library or RuleLibrary(storage_path=storage_path)

    def import_rules(self, request: RuleImportRequest) -> RuleImportResponse:
        """导入规则。"""
        if request.file_path:
            result = self.library.import_rules_from_file(
                request.file_path,
                overwrite=request.overwrite,
            )
        elif request.rules is not None:
            result = self.library.import_rules(
                request.rules,
                overwrite=request.overwrite,
            )
        else:
            raise ValueError("导入规则时 rules 与 file_path 至少提供一个")

        return self._build_import_response(result)

    def create_rule(self, request: RuleCreateRequest) -> RuleTemplateResponse:
        """新增规则。"""
        rule = self.library.create_rule(request.rule, overwrite=request.overwrite)
        return self._build_rule_response(rule)

    def update_rule(self, request: RuleUpdateRequest) -> RuleTemplateResponse:
        """修改规则。"""
        rule = self.library.update_rule(request.rule_id, request.updates)
        return self._build_rule_response(rule)

    def delete_rule(self, request: RuleDeleteRequest) -> bool:
        """删除规则。"""
        return self.library.delete_rule(request.rule_id, soft_delete=request.soft_delete)

    def get_rule(self, rule_id: str) -> Optional[RuleTemplateResponse]:
        """获取规则详情。"""
        rule = self.library.get_rule(rule_id)
        if not rule:
            return None
        return self._build_rule_response(rule)

    def query_rules(self, request: RuleQueryRequest) -> RuleListResponse:
        """查询规则列表。"""
        rules = self.library.list_rules(
            dimension=request.dimension,
            entity_type=request.entity_type,
            engine=request.engine,
            problem_category=request.problem_category,
            source_type=request.source_type,
            status=request.status,
            keyword=request.keyword,
            include_disabled=request.include_disabled,
        )
        return RuleListResponse(
            total=len(rules),
            rules=[self._build_rule_response(rule) for rule in rules],
        )

    def preview_rule_script(
        self,
        request: RuleScriptPreviewRequest,
    ) -> RuleScriptPreviewResponse:
        """预览规则脚本。"""
        preview = self.library.preview_script(
            rule_id=request.rule_id,
            engine=request.engine,
            target_object=request.target_object,
            parameter_overrides=request.parameter_overrides,
        )
        return RuleScriptPreviewResponse(**preview.to_dict())

    def reuse_rule(self, request: RuleReuseRequest) -> RuleReuseResponse:
        """复用规则并生成测试用例配置。"""
        plan = self.library.reuse_rule(
            rule_id=request.rule_id,
            target_object=request.target_object,
            engine=request.engine,
            parameter_overrides=request.parameter_overrides,
            test_case_name=request.test_case_name,
        )
        return self._build_reuse_response(plan)

    def get_summary(self) -> RuleLibrarySummaryResponse:
        """获取规则库统计。"""
        return self._build_summary_response(self.library.get_summary())

    def get_builtin_dimension_rules(self) -> RuleListResponse:
        """获取内置六维评价规则。"""
        rules = self.library.list_rules(include_disabled=False)
        return RuleListResponse(
            total=len(rules),
            rules=[self._build_rule_response(rule) for rule in rules],
        )

    def _build_rule_response(self, rule: RuleTemplate) -> RuleTemplateResponse:
        data = rule.to_dict()
        return RuleTemplateResponse(
            rule_id=rule.rule_id,
            name=rule.name,
            display_name=rule.display_name,
            dimension=rule.dimension.value,
            dimension_zh=rule.dimension_zh,
            source_type=rule.source_type.value,
            problem_category=rule.problem_category,
            core_definition=rule.core_definition,
            applicable_object=data["applicability"],
            test_definition_name=rule.test_definition_name,
            parameters=data["parameters"],
            threshold=data["threshold"],
            validation_level=rule.validation_level.value,
            severity=rule.severity.value,
            responsible_role=rule.responsible_role,
            remediation_suggestion=rule.remediation_suggestion,
            issue_strategy=rule.issue_strategy,
            scripts=data["scripts"],
            tags=rule.tags,
            status=rule.status.value,
            version=rule.version,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
            reuse_count=self.library.get_reuse_count(rule.rule_id),
        )

    @staticmethod
    def _build_import_response(result: RuleImportResult) -> RuleImportResponse:
        return RuleImportResponse(**result.to_dict())

    @staticmethod
    def _build_reuse_response(plan: RuleReusePlan) -> RuleReuseResponse:
        return RuleReuseResponse(
            rule_id=plan.rule_id,
            rule_name=plan.rule_name,
            target_object=plan.target_object,
            engine=plan.engine.value,
            test_case_config=plan.test_case_config,
            script_preview=RuleScriptPreviewResponse(**plan.script_preview.to_dict()),
            threshold=plan.threshold.to_dict(),
            responsible_role=plan.responsible_role,
            remediation_suggestion=plan.remediation_suggestion,
        )

    @staticmethod
    def _build_summary_response(summary: RuleLibrarySummary) -> RuleLibrarySummaryResponse:
        return RuleLibrarySummaryResponse(**summary.to_dict())


__all__ = [
    "RuleLibraryAPI",
    "RuleImportRequest",
    "RuleCreateRequest",
    "RuleUpdateRequest",
    "RuleDeleteRequest",
    "RuleQueryRequest",
    "RuleScriptPreviewRequest",
    "RuleReuseRequest",
    "RuleTemplateResponse",
    "RuleImportResponse",
    "RuleListResponse",
    "RuleScriptPreviewResponse",
    "RuleReuseResponse",
    "RuleLibrarySummaryResponse",
]
