"""
文件操作工具模块

提供文件和目录操作的通用函数，包括创建、删除、移动、复制等功能。
"""

import os
import shutil
from pathlib import Path
from typing import List, Optional, Union, Tuple
from .logger import logger


def ensure_dir(path: Union[str, Path]) -> Path:
    """确保目录存在，如果不存在则创建
    
    Args:
        path: 目录路径
        
    Returns:
        Path: 创建或已存在的目录路径对象
    """
    path_obj = Path(path)
    path_obj.mkdir(parents=True, exist_ok=True)
    logger.debug(f"确保目录存在: {path_obj}")
    return path_obj


def ensure_parent_dir(file_path: Union[str, Path]) -> Path:
    """确保文件的父目录存在
    
    Args:
        file_path: 文件路径
        
    Returns:
        Path: 文件路径对象
    """
    file_path_obj = Path(file_path)
    if file_path_obj.parent != file_path_obj:
        ensure_dir(file_path_obj.parent)
    return file_path_obj


def safe_remove_file(file_path: Union[str, Path]) -> bool:
    """安全删除文件
    
    Args:
        file_path: 要删除的文件路径
        
    Returns:
        bool: 删除成功返回True，文件不存在或删除失败返回False
    """
    try:
        path_obj = Path(file_path)
        if path_obj.exists() and path_obj.is_file():
            path_obj.unlink()
            logger.debug(f"删除文件: {path_obj}")
            return True
        else:
            logger.debug(f"文件不存在，无需删除: {path_obj}")
            return False
    except Exception as e:
        logger.error(f"删除文件失败 {file_path}: {e}")
        return False


def safe_remove_dir(dir_path: Union[str, Path], recursive: bool = False) -> bool:
    """安全删除目录
    
    Args:
        dir_path: 要删除的目录路径
        recursive: 是否递归删除目录及其内容
        
    Returns:
        bool: 删除成功返回True，目录不存在或删除失败返回False
    """
    try:
        path_obj = Path(dir_path)
        if path_obj.exists() and path_obj.is_dir():
            if recursive:
                shutil.rmtree(path_obj)
                logger.debug(f"递归删除目录: {path_obj}")
            else:
                path_obj.rmdir()
                logger.debug(f"删除空目录: {path_obj}")
            return True
        else:
            logger.debug(f"目录不存在，无需删除: {path_obj}")
            return False
    except Exception as e:
        logger.error(f"删除目录失败 {dir_path}: {e}")
        return False


def copy_file(src: Union[str, Path], dst: Union[str, Path], overwrite: bool = False) -> bool:
    """复制文件
    
    Args:
        src: 源文件路径
        dst: 目标文件路径
        overwrite: 是否覆盖已存在的目标文件
        
    Returns:
        bool: 复制成功返回True，失败返回False
    """
    try:
        src_path = Path(src)
        dst_path = Path(dst)
        
        if not src_path.exists():
            logger.error(f"源文件不存在: {src_path}")
            return False
        
        if dst_path.exists() and not overwrite:
            logger.warning(f"目标文件已存在且不允许覆盖: {dst_path}")
            return False
        
        # 确保目标目录存在
        ensure_parent_dir(dst_path)
        
        shutil.copy2(src_path, dst_path)
        logger.debug(f"复制文件: {src_path} -> {dst_path}")
        return True
        
    except Exception as e:
        logger.error(f"复制文件失败 {src} -> {dst}: {e}")
        return False


def move_file(src: Union[str, Path], dst: Union[str, Path], overwrite: bool = False) -> bool:
    """移动文件
    
    Args:
        src: 源文件路径
        dst: 目标文件路径
        overwrite: 是否覆盖已存在的目标文件
        
    Returns:
        bool: 移动成功返回True，失败返回False
    """
    try:
        src_path = Path(src)
        dst_path = Path(dst)
        
        if not src_path.exists():
            logger.error(f"源文件不存在: {src_path}")
            return False
        
        if dst_path.exists() and not overwrite:
            logger.warning(f"目标文件已存在且不允许覆盖: {dst_path}")
            return False
        
        # 确保目标目录存在
        ensure_parent_dir(dst_path)
        
        shutil.move(str(src_path), str(dst_path))
        logger.debug(f"移动文件: {src_path} -> {dst_path}")
        return True
        
    except Exception as e:
        logger.error(f"移动文件失败 {src} -> {dst}: {e}")
        return False


def get_file_size(file_path: Union[str, Path]) -> int:
    """获取文件大小
    
    Args:
        file_path: 文件路径
        
    Returns:
        int: 文件大小（字节），文件不存在返回-1
    """
    try:
        path_obj = Path(file_path)
        if path_obj.exists() and path_obj.is_file():
            return path_obj.stat().st_size
        else:
            logger.warning(f"文件不存在: {path_obj}")
            return -1
    except Exception as e:
        logger.error(f"获取文件大小失败 {file_path}: {e}")
        return -1


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小为人类可读格式
    
    Args:
        size_bytes: 文件大小（字节）
        
    Returns:
        str: 格式化后的文件大小字符串
    """
    if size_bytes < 0:
        return "未知"
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def list_files(directory: Union[str, Path], 
               pattern: str = "*", 
               recursive: bool = False) -> List[Path]:
    """列出目录中的文件
    
    Args:
        directory: 目录路径
        pattern: 文件匹配模式（如 "*.txt", "*.mp3"）
        recursive: 是否递归搜索子目录
        
    Returns:
        List[Path]: 匹配的文件路径列表
    """
    try:
        path_obj = Path(directory)
        if not path_obj.exists() or not path_obj.is_dir():
            logger.warning(f"目录不存在: {path_obj}")
            return []
        
        if recursive:
            files = list(path_obj.rglob(pattern))
        else:
            files = list(path_obj.glob(pattern))
        
        # 只返回文件，不包括目录
        files = [f for f in files if f.is_file()]
        logger.debug(f"找到 {len(files)} 个文件，模式: {pattern}, 递归: {recursive}")
        return files
        
    except Exception as e:
        logger.error(f"列出文件失败 {directory}: {e}")
        return []


def get_unique_filename(file_path: Union[str, Path]) -> Path:
    """获取唯一的文件名（如果文件已存在，自动添加数字后缀）
    
    Args:
        file_path: 原始文件路径
        
    Returns:
        Path: 唯一的文件路径
    """
    path_obj = Path(file_path)
    
    if not path_obj.exists():
        return path_obj
    
    # 分离文件名和扩展名
    stem = path_obj.stem
    suffix = path_obj.suffix
    parent = path_obj.parent
    
    counter = 1
    while True:
        new_name = f"{stem}_{counter}{suffix}"
        new_path = parent / new_name
        if not new_path.exists():
            logger.debug(f"生成唯一文件名: {path_obj} -> {new_path}")
            return new_path
        counter += 1


def clean_temp_files(temp_dir: Union[str, Path], 
                    pattern: str = "*", 
                    max_age_hours: Optional[int] = None) -> int:
    """清理临时文件
    
    Args:
        temp_dir: 临时文件目录
        pattern: 要清理的文件模式
        max_age_hours: 最大文件年龄（小时），超过此时间的文件将被删除
        
    Returns:
        int: 删除的文件数量
    """
    try:
        import time
        
        temp_path = Path(temp_dir)
        if not temp_path.exists():
            logger.debug(f"临时目录不存在: {temp_path}")
            return 0
        
        files = list_files(temp_path, pattern, recursive=True)
        deleted_count = 0
        current_time = time.time()
        
        for file_path in files:
            try:
                should_delete = True
                
                # 检查文件年龄
                if max_age_hours is not None:
                    file_mtime = file_path.stat().st_mtime
                    file_age_hours = (current_time - file_mtime) / 3600
                    should_delete = file_age_hours > max_age_hours
                
                if should_delete and safe_remove_file(file_path):
                    deleted_count += 1
                    
            except Exception as e:
                logger.warning(f"清理文件失败 {file_path}: {e}")
        
        logger.info(f"清理临时文件完成，删除 {deleted_count} 个文件")
        return deleted_count
        
    except Exception as e:
        logger.error(f"清理临时文件失败 {temp_dir}: {e}")
        return 0


def validate_path(path: Union[str, Path], 
                 must_exist: bool = False, 
                 must_be_file: bool = False, 
                 must_be_dir: bool = False) -> Tuple[bool, str]:
    """验证路径
    
    Args:
        path: 要验证的路径
        must_exist: 路径必须存在
        must_be_file: 路径必须是文件
        must_be_dir: 路径必须是目录
        
    Returns:
        Tuple[bool, str]: (验证结果, 错误信息)
    """
    try:
        path_obj = Path(path)
        
        if must_exist and not path_obj.exists():
            return False, f"路径不存在: {path_obj}"
        
        if path_obj.exists():
            if must_be_file and not path_obj.is_file():
                return False, f"路径不是文件: {path_obj}"
            
            if must_be_dir and not path_obj.is_dir():
                return False, f"路径不是目录: {path_obj}"
        
        return True, ""
        
    except Exception as e:
        return False, f"路径验证失败: {e}"
