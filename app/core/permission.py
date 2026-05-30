"""权限检查器接口定义

本模块定义了权限检查器的标准接口，企业可以实现自己的权限逻辑。
"""
from __future__ import annotations

from typing import Any, Protocol


class PermissionChecker(Protocol):
    """权限检查器接口
    
    企业可以实现此接口，定义自己的权限检查逻辑。
    系统会在检索流程中调用这些方法进行权限过滤。
    
    使用方式：
    1. 实现 PermissionChecker 接口
    2. 配置 PERMISSION_MODE=plugin
    3. 配置 PERMISSION_PLUGIN=your.module.YourChecker
    """
    
    def can_access_document(
        self,
        document: dict[str, Any],
        user_context: dict[str, Any] | None,
    ) -> bool:
        """判断用户是否能访问单个文档
        
        Args:
            document: 文档信息字典，包含以下字段：
                - doc_uuid: 文档唯一标识
                - source_module: 知识库标识（如 oa, hr, crm）
                - source_type: 文档类型（如 policy, faq, manual）
                - access_level: 访问级别（如 public, internal, private）
                - tags: 标签列表
                - owner_dept: 所属部门
                - created_by: 创建者
            user_context: 用户上下文，可能为 None，包含以下字段：
                - user_id: 用户ID
                - roles: 角色列表
                - departments: 部门列表
                - is_authenticated: 是否已认证
                
        Returns:
            True 表示允许访问，False 表示拒绝
        """
        ...
    
    def filter_documents(
        self,
        documents: list[dict[str, Any]],
        user_context: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """过滤用户可访问的文档列表
        
        默认实现会调用 can_access_document 逐个判断。
        企业可以重写此方法实现批量权限检查（如调用外部权限服务）。
        
        Args:
            documents: 文档列表
            user_context: 用户上下文，可能为 None
            
        Returns:
            过滤后的文档列表
        """
        ...