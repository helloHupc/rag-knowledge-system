"""Permissions package.

本包提供权限检查功能，支持插件化扩展。

使用方式：
1. 默认模式（无权限检查）：
   - 配置 PERMISSION_MODE=none
   - 系统使用 NoOpPermissionChecker，不做权限检查

2. 插件模式（企业自定义权限）：
   - 配置 PERMISSION_MODE=plugin
   - 配置 PERMISSION_PLUGIN=your.module.YourChecker
   - 企业实现 PermissionChecker 接口

接口：
- PermissionChecker: 权限检查器接口（定义在 app.core.permission）
- NoOpPermissionChecker: 无权限检查实现
- load_permission_checker: 加载权限检查器实例
"""

from app.core.permission import PermissionChecker
from app.permissions.noop import NoOpPermissionChecker
from app.permissions.loader import load_permission_checker, reset_permission_checker

__all__ = [
    "PermissionChecker",
    "NoOpPermissionChecker",
    "load_permission_checker",
    "reset_permission_checker",
]