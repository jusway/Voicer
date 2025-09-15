"""
日志工具模块

提供统一的日志记录功能，支持控制台输出和文件记录。
"""

import logging
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime


class Logger:
    """日志器类
    
    提供统一的日志记录功能，支持多种日志级别和输出方式。
    """
    
    def __init__(self, name: str = "qwen3_asr", log_file: Optional[str] = None, level: str = "INFO"):
        """初始化日志器
        
        Args:
            name: 日志器名称
            log_file: 日志文件路径，如果为None则不写入文件
            level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))
        
        # 清除已有的处理器，避免重复
        self.logger.handlers.clear()
        
        # 创建格式器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, level.upper()))
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # 文件处理器
        if log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(getattr(logging, level.upper()))
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
    
    def debug(self, message: str, *args, **kwargs):
        """记录DEBUG级别日志"""
        self.logger.debug(message, *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs):
        """记录INFO级别日志"""
        self.logger.info(message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        """记录WARNING级别日志"""
        self.logger.warning(message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        """记录ERROR级别日志"""
        self.logger.error(message, *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs):
        """记录CRITICAL级别日志"""
        self.logger.critical(message, *args, **kwargs)
    
    def exception(self, message: str, *args, **kwargs):
        """记录异常信息"""
        self.logger.exception(message, *args, **kwargs)


def setup_logger(name: str = "qwen3_asr", 
                log_file: Optional[str] = None, 
                level: str = "INFO") -> Logger:
    """设置日志器
    
    Args:
        name: 日志器名称
        log_file: 日志文件路径
        level: 日志级别
        
    Returns:
        Logger: 配置好的日志器实例
    """
    return Logger(name, log_file, level)


def get_default_logger() -> Logger:
    """获取默认日志器
    
    Returns:
        Logger: 默认配置的日志器
    """
    # 导入配置（避免循环导入）
    try:
        from ..config.settings import settings
        
        # 生成带时间戳的日志文件名，日志写到项目根目录下的 ./log
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"process_{timestamp}.log"
        log_dir = Path(settings.PROJECT_ROOT) / "log"
        log_file = str(log_dir / log_filename)
    except ImportError:
        log_file = None
    
    return setup_logger(log_file=log_file)


# 创建全局默认日志器实例
logger = get_default_logger()