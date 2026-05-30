"""无权限检查实现

此实现不做任何权限检查，全部允许访问。
适用于：
- 开发环境
- 内部信任环境
- 企业在网关层做权限控制
"""
from __future__ import annotations

from typing import Any


class NoOpPermissionChecker:
    """无权限检查，全部允许
    
    这是默认的权限检查器，不进行任何权限判断。
    所有文档对所有用户可访问。
    """
    
    def can_access_document(
        self,
        document: dict[str, Any],
        user_context: dict[str, Any] | None,
    ) -> bool:
        """始终返回 True，允许访问所有文档"""
        return True
    
    def filter_documents(
        self,
        documents: list[dict[str, Any]],
        user_context: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """返回所有文档，不做过滤"""
        return documents