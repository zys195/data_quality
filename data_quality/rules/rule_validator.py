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
规则校验器模块

支持规则的人工校验流程：
1. 规则启用/禁用
2. 参数调整确认
3. 审批状态追踪
4. 规则版本管理
"""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from metadata.data_quality.dimension.models import QualityDimension
from metadata.data_quality.rules.rule_recommender import RuleRecommendation


class ValidationStatus(str, Enum):
    """规则校验状态"""
    PENDING = "PENDING"       # 待校验
    APPROVED = "APPROVED"    # 已批准
    REJECTED = "REJECTED"    # 已拒绝
    MODIFIED = "MODIFIED"    # 已修改
    DEPRECATED = "DEPRECATED"  # 已废弃


class ValidationPriority(str, Enum):
    """校验优先级"""
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


@dataclass
class ParameterChange:
    """参数变更记录"""
    parameter_name: str
    original_value: Any
    new_value: Any
    change_reason: str = ""


@dataclass
class ValidationRecord:
    """规则校验记录"""
    validation_id: str
    rule_id: str
    rule_name: str
    status: ValidationStatus
    created_at: datetime
    created_by: str
    validated_by: Optional[str] = None
    validated_at: Optional[datetime] = None
    validation_comment: str = ""
    
    # 参数变更
    original_parameters: Dict[str, Any] = field(default_factory=dict)
    modified_parameters: Dict[str, Any] = field(default_factory=dict)
    parameter_changes: List[ParameterChange] = field(default_factory=list)
    
    # 启用/禁用
    enabled: bool = True
    disable_reason: str = ""
    
    # 优先级和截止日期
    priority: ValidationPriority = ValidationPriority.NORMAL
    due_date: Optional[datetime] = None
    
    # 版本信息
    version: int = 1
    previous_version: Optional[int] = None
    
    # 标签和分类
    tags: Set[str] = field(default_factory=set)
    business_owner: str = ""
    
    # 统计信息
    apply_count: int = 0  # 应用次数
    failure_count: int = 0  # 失败次数
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = asdict(self)
        result['status'] = self.status.value
        result['priority'] = self.priority.value
        result['created_at'] = self.created_at.isoformat()
        if self.validated_at:
            result['validated_at'] = self.validated_at.isoformat()
        if self.due_date:
            result['due_date'] = self.due_date.isoformat()
        result['tags'] = list(self.tags)
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ValidationRecord':
        """从字典创建"""
        if isinstance(data.get('status'), str):
            data['status'] = ValidationStatus(data['status'])
        if isinstance(data.get('priority'), str):
            data['priority'] = ValidationPriority(data['priority'])
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if isinstance(data.get('validated_at'), str):
            data['validated_at'] = datetime.fromisoformat(data['validated_at'])
        if isinstance(data.get('due_date'), str):
            data['due_date'] = datetime.fromisoformat(data['due_date'])
        if isinstance(data.get('tags'), list):
            data['tags'] = set(data['tags'])
        if data.get('parameter_changes'):
            data['parameter_changes'] = [
                ParameterChange(**pc) for pc in data['parameter_changes']
            ]
        return cls(**data)


@dataclass
class ValidationSummary:
    """校验汇总信息"""
    total_rules: int = 0
    pending_count: int = 0
    approved_count: int = 0
    rejected_count: int = 0
    modified_count: int = 0
    deprecated_count: int = 0
    
    enabled_count: int = 0
    disabled_count: int = 0
    
    by_dimension: Dict[QualityDimension, Dict[str, int]] = field(default_factory=dict)
    by_severity: Dict[str, int] = field(default_factory=dict)
    
    overdue_count: int = 0
    urgent_count: int = 0


class RuleValidator:
    """规则校验器
    
    提供规则的人工校验能力，包括：
    - 规则审批流程
    - 参数调整确认
    - 规则启用/禁用
    - 版本管理
    """
    
    def __init__(self, storage_path: Optional[Path] = None):
        """
        初始化规则校验器
        
        Args:
            storage_path: 校验记录存储路径，默认使用内存存储
        """
        self.storage_path = storage_path
        self._validations: Dict[str, ValidationRecord] = {}
        self._rule_validations: Dict[str, str] = {}  # rule_id -> validation_id
        
        if storage_path and storage_path.exists():
            self._load_validations()
    
    def _load_validations(self):
        """从文件加载校验记录"""
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for record in data.get('validations', []):
                    vr = ValidationRecord.from_dict(record)
                    self._validations[vr.validation_id] = vr
                    self._rule_validations[vr.rule_id] = vr.validation_id
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    
    def _save_validations(self):
        """保存校验记录到文件"""
        if not self.storage_path:
            return
        
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump({
                'validations': [v.to_dict() for v in self._validations.values()]
            }, f, ensure_ascii=False, indent=2)
    
    def create_validation(
        self,
        rule_id: str,
        rule_name: str,
        created_by: str,
        parameters: Optional[Dict[str, Any]] = None,
        priority: ValidationPriority = ValidationPriority.NORMAL,
        due_date: Optional[datetime] = None,
        tags: Optional[Set[str]] = None,
        business_owner: str = "",
    ) -> ValidationRecord:
        """创建规则校验记录
        
        Args:
            rule_id: 规则ID
            rule_name: 规则名称
            created_by: 创建人
            parameters: 规则参数
            priority: 优先级
            due_date: 截止日期
            tags: 标签集合
            business_owner: 业务负责人
            
        Returns:
            创建的校验记录
        """
        validation_id = str(uuid.uuid4())
        
        record = ValidationRecord(
            validation_id=validation_id,
            rule_id=rule_id,
            rule_name=rule_name,
            status=ValidationStatus.PENDING,
            created_at=datetime.now(),
            created_by=created_by,
            original_parameters=parameters or {},
            modified_parameters=parameters.copy() if parameters else {},
            priority=priority,
            due_date=due_date,
            tags=tags or set(),
            business_owner=business_owner,
        )
        
        self._validations[validation_id] = record
        self._rule_validations[rule_id] = validation_id
        self._save_validations()
        
        return record
    
    def approve_validation(
        self,
        validation_id: str,
        validated_by: str,
        comment: str = "",
    ) -> ValidationRecord:
        """批准规则校验
        
        Args:
            validation_id: 校验记录ID
            validated_by: 审批人
            comment: 审批意见
            
        Returns:
            更新后的校验记录
        """
        record = self._validations.get(validation_id)
        if not record:
            raise ValueError(f"校验记录不存在: {validation_id}")
        
        if record.status == ValidationStatus.REJECTED:
            raise ValueError("已被拒绝的记录不能直接批准")
        
        record.status = ValidationStatus.APPROVED
        record.validated_by = validated_by
        record.validated_at = datetime.now()
        record.validation_comment = comment
        
        self._save_validations()
        return record
    
    def reject_validation(
        self,
        validation_id: str,
        validated_by: str,
        reason: str,
    ) -> ValidationRecord:
        """拒绝规则校验
        
        Args:
            validation_id: 校验记录ID
            validated_by: 审批人
            reason: 拒绝原因
            
        Returns:
            更新后的校验记录
        """
        record = self._validations.get(validation_id)
        if not record:
            raise ValueError(f"校验记录不存在: {validation_id}")
        
        record.status = ValidationStatus.REJECTED
        record.validated_by = validated_by
        record.validated_at = datetime.now()
        record.validation_comment = reason
        record.enabled = False
        record.disable_reason = reason
        
        self._save_validations()
        return record
    
    def modify_parameters(
        self,
        validation_id: str,
        modified_by: str,
        new_parameters: Dict[str, Any],
        change_reason: str = "",
    ) -> ValidationRecord:
        """修改规则参数
        
        Args:
            validation_id: 校验记录ID
            modified_by: 修改人
            new_parameters: 新参数
            change_reason: 修改原因
            
        Returns:
            更新后的校验记录
        """
        record = self._validations.get(validation_id)
        if not record:
            raise ValueError(f"校验记录不存在: {validation_id}")
        
        # 记录参数变更
        for key, new_value in new_parameters.items():
            original_value = record.original_parameters.get(key)
            if original_value != new_value:
                change = ParameterChange(
                    parameter_name=key,
                    original_value=original_value,
                    new_value=new_value,
                    change_reason=change_reason,
                )
                record.parameter_changes.append(change)
        
        record.modified_parameters = new_parameters
        record.previous_version = record.version
        record.version += 1
        record.status = ValidationStatus.MODIFIED
        
        self._save_validations()
        return record
    
    def enable_rule(
        self,
        rule_id: str,
        enabled: bool = True,
        reason: str = "",
    ) -> ValidationRecord:
        """启用/禁用规则
        
        Args:
            rule_id: 规则ID
            enabled: 是否启用
            reason: 原因
            
        Returns:
            更新后的校验记录
        """
        validation_id = self._rule_validations.get(rule_id)
        if not validation_id:
            raise ValueError(f"规则校验记录不存在: {rule_id}")
        
        record = self._validations.get(validation_id)
        record.enabled = enabled
        record.disable_reason = reason
        
        self._save_validations()
        return record
    
    def get_validation(self, validation_id: str) -> Optional[ValidationRecord]:
        """获取校验记录"""
        return self._validations.get(validation_id)
    
    def get_validation_by_rule(self, rule_id: str) -> Optional[ValidationRecord]:
        """根据规则ID获取校验记录"""
        validation_id = self._rule_validations.get(rule_id)
        if validation_id:
            return self._validations.get(validation_id)
        return None
    
    def get_pending_validations(
        self,
        dimension: Optional[QualityDimension] = None,
        priority: Optional[ValidationPriority] = None,
    ) -> List[ValidationRecord]:
        """获取待校验的规则列表
        
        Args:
            dimension: 按维度筛选
            priority: 按优先级筛选
            
        Returns:
            待校验记录列表
        """
        pending = [
            v for v in self._validations.values()
            if v.status == ValidationStatus.PENDING and v.enabled
        ]
        
        if priority:
            pending = [v for v in pending if v.priority == priority]
        
        # 按优先级和创建时间排序
        pending.sort(key=lambda x: (x.priority.value, x.created_at))
        
        return pending
    
    def get_overdue_validations(self) -> List[ValidationRecord]:
        """获取已超期的校验记录"""
        now = datetime.now()
        return [
            v for v in self._validations.values()
            if v.status == ValidationStatus.PENDING
            and v.due_date
            and v.due_date < now
        ]
    
    def get_summary(self) -> ValidationSummary:
        """获取校验汇总信息"""
        summary = ValidationSummary()
        
        for record in self._validations.values():
            summary.total_rules += 1
            
            # 按状态统计
            if record.status == ValidationStatus.PENDING:
                summary.pending_count += 1
            elif record.status == ValidationStatus.APPROVED:
                summary.approved_count += 1
            elif record.status == ValidationStatus.REJECTED:
                summary.rejected_count += 1
            elif record.status == ValidationStatus.MODIFIED:
                summary.modified_count += 1
            elif record.status == ValidationStatus.DEPRECATED:
                summary.deprecated_count += 1
            
            # 启用/禁用统计
            if record.enabled:
                summary.enabled_count += 1
            else:
                summary.disabled_count += 1
            
            # 超期检测
            if record.due_date and record.due_date < datetime.now():
                summary.overdue_count += 1
            
            # 紧急检测
            if record.priority == ValidationPriority.URGENT:
                summary.urgent_count += 1
        
        return summary
    
    def from_recommendation(
        self,
        recommendation: RuleRecommendation,
        created_by: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> ValidationRecord:
        """从规则推荐创建校验记录
        
        Args:
            recommendation: 规则推荐
            created_by: 创建人
            parameters: 规则参数
            
        Returns:
            创建的校验记录
        """
        rule_id = f"{recommendation.test_definition_name}_{recommendation.column_name or 'table'}"
        
        return self.create_validation(
            rule_id=rule_id,
            rule_name=recommendation.test_definition_name,
            created_by=created_by,
            parameters=parameters or recommendation.parameters,
            tags={recommendation.dimension.value} if recommendation.dimension else set(),
        )
    
    def bulk_approve(
        self,
        validation_ids: List[str],
        validated_by: str,
        comment: str = "",
    ) -> List[ValidationRecord]:
        """批量批准规则
        
        Args:
            validation_ids: 校验记录ID列表
            validated_by: 审批人
            comment: 审批意见
            
        Returns:
            批准后的记录列表
        """
        results = []
        for vid in validation_ids:
            try:
                result = self.approve_validation(vid, validated_by, comment)
                results.append(result)
            except ValueError:
                continue
        return results
    
    def deprecate_rule(self, rule_id: str, reason: str) -> ValidationRecord:
        """废弃规则
        
        Args:
            rule_id: 规则ID
            reason: 废弃原因
            
        Returns:
            更新后的校验记录
        """
        validation_id = self._rule_validations.get(rule_id)
        if not validation_id:
            raise ValueError(f"规则校验记录不存在: {rule_id}")
        
        record = self._validations.get(validation_id)
        record.status = ValidationStatus.DEPRECATED
        record.enabled = False
        record.disable_reason = reason
        
        self._save_validations()
        return record
    
    def get_validations_by_status(
        self,
        status: ValidationStatus,
    ) -> List[ValidationRecord]:
        """按状态获取校验记录"""
        return [v for v in self._validations.values() if v.status == status]
    
    def get_enabled_rules(self) -> List[ValidationRecord]:
        """获取所有启用的规则"""
        return [v for v in self._validations.values() if v.enabled]
    
    def record_usage(
        self,
        rule_id: str,
        success: bool = True,
    ) -> ValidationRecord:
        """记录规则使用情况
        
        Args:
            rule_id: 规则ID
            success: 是否成功
            
        Returns:
            更新后的校验记录
        """
        validation_id = self._rule_validations.get(rule_id)
        if not validation_id:
            raise ValueError(f"规则校验记录不存在: {rule_id}")
        
        record = self._validations.get(validation_id)
        record.apply_count += 1
        if not success:
            record.failure_count += 1
        
        self._save_validations()
        return record
    
    def get_statistics(self, rule_id: str) -> Dict[str, Any]:
        """获取规则统计信息
        
        Args:
            rule_id: 规则ID
            
        Returns:
            统计信息字典
        """
        record = self.get_validation_by_rule(rule_id)
        if not record:
            return {}
        
        success_rate = 0.0
        if record.apply_count > 0:
            success_rate = (record.apply_count - record.failure_count) / record.apply_count * 100
        
        return {
            "rule_id": rule_id,
            "rule_name": record.rule_name,
            "status": record.status.value,
            "enabled": record.enabled,
            "apply_count": record.apply_count,
            "failure_count": record.failure_count,
            "success_rate": success_rate,
            "version": record.version,
            "last_validated": record.validated_at.isoformat() if record.validated_at else None,
        }
