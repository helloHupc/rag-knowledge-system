"""权限检查器加载器

根据配置动态加载权限检查器实例。
"""
from __future__ import annotations

import importlib
import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# 全局单例
_checker_instance: Any = None


def load_permission_checker() -> Any:
    """加载权限检查器实例
    
    根据配置 PERMISSION_MODE 加载对应的权限检查器：
    - none: 使用 NoOpPermissionChecker（无权限检查）
    - plugin: 使用配置的插件类
    
    Returns:
        权限检查器实例
    """
    global _checker_instance
    
    if _checker_instance is not None:
        return _checker_instance
    
    settings = get_settings()
    
    if settings.permission_mode == "none":
        from app.permissions.noop import NoOpPermissionChecker
        _checker_instance = NoOpPermissionChecker()
        logger.info("Loaded NoOpPermissionChecker (permission_mode=none)")
    elif settings.permission_mode == "plugin":
        plugin_path = settings.permission_plugin
        try:
            module_path, class_name = plugin_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            checker_class = getattr(module, class_name)
            _checker_instance = checker_class()
            logger.info(f"Loaded permission checker: {plugin_path}")
        except Exception as e:
            logger.error(f"Failed to load permission checker {plugin_path}: {e}")
            raise ValueError(f"Failed to load permission checker: {plugin_path}") from e
    else:
        raise ValueError(f"Unknown permission_mode: {settings.permission_mode}")
    
    return _checker_instance


def reset_permission_checker() -> None:
    """重置权限检查器实例
    
    用于测试或重新加载配置时调用。
    """
    global _checker_instance
    _checker_instance = None