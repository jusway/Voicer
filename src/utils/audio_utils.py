"""
音频处理工具模块

提供音频处理相关的工具函数，包括FFmpeg检测、音频格式验证、片段大小计算等功能。
"""

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Tuple, Callable, Union, List, Dict, Deque
import struct
from collections import deque
from datetime import datetime, timedelta
from enum import Enum
import uuid
import json
import re

# 延迟导入防止循环导入
def get_settings():
    from ..config.settings import settings
    return settings

def get_logger():
    from .logger import logger
    return logger


class AudioSizeCalculationError(Exception):
    """音频大小计算错误"""
    pass


def calculate_audio_file_size(file_path: Union[str, Path]) -> int:
    """计算音频文件大小
    
    Args:
        file_path: 音频文件路径
        
    Returns:
        int: 文件大小（字节）
        
    Raises:
        AudioSizeCalculationError: 文件不存在或无法访问时抛出
    """
    try:
        file_path = Path(file_path)
        if not file_path.exists():
            raise AudioSizeCalculationError(f"文件不存在: {file_path}")
        
        file_size = file_path.stat().st_size
        return file_size
        
    except OSError as e:
        raise AudioSizeCalculationError(f"无法获取文件大小: {e}")


def calculate_audio_segment_size(segment_info: dict) -> int:
    """根据音频片段信息计算预期文件大小
    
    Args:
        segment_info: 包含音频参数的字典
            - duration: 时长（秒）
            - sample_rate: 采样率（Hz）
            - channels: 声道数
            - bit_depth: 位深度（位）
            - format: 音频格式
            
    Returns:
        int: 预期文件大小（字节）
    """
    duration = segment_info.get('duration', 0.0)
    sample_rate = segment_info.get('sample_rate', 16000)
    channels = segment_info.get('channels', 1)
    bit_depth = segment_info.get('bit_depth', 16)
    audio_format = segment_info.get('format', 'wav').lower()
    
    # 计算原始PCM数据大小
    bytes_per_sample = bit_depth // 8
    raw_size = int(duration * sample_rate * channels * bytes_per_sample)
    
    # 根据格式估算压缩后大小
    format_multipliers = {
        'wav': 1.0,      # 无压缩
        'opus': 0.1,     # 高压缩比
        'mp3': 0.125,    # 中等压缩比
        'aac': 0.1,      # 高压缩比
        'm4a': 0.1,      # 高压缩比
        'flac': 0.6,     # 无损压缩
    }
    
    multiplier = format_multipliers.get(audio_format, 1.0)
    estimated_size = int(raw_size * multiplier)
    
    # 添加文件头和元数据的估算大小
    header_size = {
        'wav': 44,       # WAV文件头
        'opus': 1000,    # Opus容器开销
        'mp3': 128,      # ID3标签等
        'aac': 200,      # AAC容器
        'm4a': 500,      # M4A容器
        'flac': 1000,    # FLAC元数据
    }
    
    estimated_size += header_size.get(audio_format, 100)
    
    return estimated_size


def get_audio_file_info(file_path: Union[str, Path]) -> dict:
    """获取音频文件的详细信息
    
    Args:
        file_path: 音频文件路径
        
    Returns:
        dict: 音频文件信息，包含文件大小、格式等
    """
    file_path = Path(file_path)
    
    info = {
        'file_path': str(file_path),
        'file_name': file_path.name,
        'file_size': 0,
        'exists': file_path.exists(),
        'format': file_path.suffix.lower().lstrip('.'),
        'readable': False
    }
    
    if info['exists']:
        try:
            info['file_size'] = calculate_audio_file_size(file_path)
            info['readable'] = os.access(file_path, os.R_OK)
        except AudioSizeCalculationError:
            pass
    
    return info


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小显示
    
    Args:
        size_bytes: 文件大小（字节）
        
    Returns:
        str: 格式化的文件大小字符串
    """
    if size_bytes <= 0:
        return "0 B"
    
    size = float(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def validate_segment_size(file_path: Union[str, Path], max_size: int = 10 * 1024 * 1024) -> Tuple[bool, str]:
    """验证音频片段大小是否符合要求
    
    Args:
        file_path: 音频文件路径
        max_size: 最大允许大小（字节），默认10MB
        
    Returns:
        Tuple[bool, str]: (是否符合要求, 详细信息)
    """
    try:
        file_size = calculate_audio_file_size(file_path)
        
        if file_size <= max_size:
            return True, f"文件大小 {format_file_size(file_size)} 符合要求（< {format_file_size(max_size)}）"
        else:
            return False, f"文件大小 {format_file_size(file_size)} 超出限制（> {format_file_size(max_size)}）"
            
    except AudioSizeCalculationError as e:
        return False, f"无法验证文件大小: {e}"


def batch_calculate_sizes(file_paths: List[Union[str, Path]]) -> List[dict]:
    """批量计算多个音频文件的大小
    
    Args:
        file_paths: 音频文件路径列表
        
    Returns:
        List[dict]: 每个文件的大小信息列表
    """
    results = []
    
    for file_path in file_paths:
        try:
            file_info = get_audio_file_info(file_path)
            results.append(file_info)
        except Exception as e:
            results.append({
                'file_path': str(file_path),
                'file_name': Path(file_path).name,
                'file_size': 0,
                'exists': False,
                'format': '',
                'readable': False,
                'error': str(e)
            })
    
    return results


class AudioDurationCalculationError(Exception):
    """音频时长计算错误"""
    pass


def calculate_audio_duration_from_file(file_path: Union[str, Path]) -> float:
    """从音频文件计算时长。优先使用FFmpeg，备用soundfile
    
    Args:
        file_path: 音频文件路径
        
    Returns:
        float: 音频时长（秒）
        
    Raises:
        AudioDurationCalculationError: 无法计算时长时抛出
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise AudioDurationCalculationError(f"文件不存在: {file_path}")
    
    logger = get_logger()
    
    # 方法 1: 使用 FFmpeg 获取时长
    try:
        duration = _get_duration_with_ffprobe(file_path)
        if duration > 0:
            logger.debug(f"使用FFprobe获取时长: {duration:.3f}s")
            return duration
    except Exception as e:
        logger.debug(f"FFprobe获取时长失败: {e}")
    
    # 方法 2: 使用 soundfile 获取时长
    try:
        duration = _get_duration_with_soundfile(file_path)
        if duration > 0:
            logger.debug(f"使用soundfile获取时长: {duration:.3f}s")
            return duration
    except Exception as e:
        logger.debug(f"soundfile获取时长失败: {e}")
    
    # 方法 3: 根据文件大小估算时长（对WAV文件）
    try:
        if file_path.suffix.lower() == '.wav':
            duration = _estimate_wav_duration(file_path)
            if duration > 0:
                logger.warning(f"使用估算方法获取WAV时长: {duration:.3f}s")
                return duration
    except Exception as e:
        logger.debug(f"估算WAV时长失败: {e}")
    
    raise AudioDurationCalculationError(f"无法计算音频文件时长: {file_path}")


def _get_duration_with_ffprobe(file_path: Path) -> float:
    """使用FFprobe获取音频时长"""
    try:
        ffmpeg_path = detect_ffmpeg()
        ffprobe_path = ffmpeg_path.replace('ffmpeg', 'ffprobe')
        
        # 构建ffprobe命令
        cmd = [
            ffprobe_path,
            '-v', 'quiet',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(file_path)
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=30
        )
        
        if result.returncode == 0 and result.stdout.strip():
            duration = float(result.stdout.strip())
            return duration
        
        return 0.0
        
    except Exception:
        return 0.0


def _get_duration_with_soundfile(file_path: Path) -> float:
    """使用soundfile获取音频时长"""
    try:
        import soundfile as sf
        
        with sf.SoundFile(str(file_path)) as f:
            duration = len(f) / f.samplerate
            return duration
            
    except ImportError:
        raise AudioDurationCalculationError("soundfile库未安装")
    except Exception as e:
        raise AudioDurationCalculationError(f"soundfile读取失败: {e}")


def _estimate_wav_duration(file_path: Path) -> float:
    """估算WAV文件时长（通过文件头信息）"""
    try:
        with open(file_path, 'rb') as f:
            # 读取WAV文件头
            f.seek(0)
            if f.read(4) != b'RIFF':
                return 0.0
            
            f.seek(8)
            if f.read(4) != b'WAVE':
                return 0.0
            
            # 查找fmt块
            f.seek(12)
            while True:
                chunk_id = f.read(4)
                if not chunk_id:
                    break
                    
                chunk_size = struct.unpack('<I', f.read(4))[0]
                
                if chunk_id == b'fmt ':
                    # 读取音频格式信息
                    audio_format = struct.unpack('<H', f.read(2))[0]
                    num_channels = struct.unpack('<H', f.read(2))[0]
                    sample_rate = struct.unpack('<I', f.read(4))[0]
                    byte_rate = struct.unpack('<I', f.read(4))[0]
                    block_align = struct.unpack('<H', f.read(2))[0]
                    bits_per_sample = struct.unpack('<H', f.read(2))[0]
                    
                    # 计算数据大小（文件大小 - 文件头大小）
                    data_size = file_path.stat().st_size - 44  # 传统 WAV 文件头 44 字节
                    
                    # 计算时长
                    duration = data_size / byte_rate
                    return duration
                    
                else:
                    # 跳过其他块
                    f.seek(f.tell() + chunk_size)
        
        return 0.0
        
    except Exception:
        return 0.0


def calculate_segment_duration_from_times(start_time: float, end_time: float) -> float:
    """根据开始和结束时间计算片段时长
    
    Args:
        start_time: 开始时间（秒）
        end_time: 结束时间（秒）
        
    Returns:
        float: 片段时长（秒）
        
    Raises:
        AudioDurationCalculationError: 时间参数无效时抛出
    """
    if start_time < 0 or end_time < 0:
        raise AudioDurationCalculationError("开始和结束时间不能为负")
    
    if end_time <= start_time:
        raise AudioDurationCalculationError("结束时间必须大于开始时间")
    
    return end_time - start_time


def format_duration(duration_seconds: float) -> str:
    """格式化时长显示
    
    Args:
        duration_seconds: 时长（秒）
        
    Returns:
        str: 格式化的时长字符串 (HH:MM:SS.mmm)
    """
    if duration_seconds < 0:
        return "00:00:00.000"
    
    hours = int(duration_seconds // 3600)
    minutes = int((duration_seconds % 3600) // 60)
    seconds = duration_seconds % 60
    
    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"


def validate_segment_duration(duration: float, max_duration: float = 180.0) -> Tuple[bool, str]:
    """验证音频片段时长是否符合要求
    
    Args:
        duration: 片段时长（秒）
        max_duration: 最大允许时长（秒），默认180秒（3分钟）
        
    Returns:
        Tuple[bool, str]: (是否符合要求, 详细信息)
    """
    if duration <= 0:
        return False, f"无效的时长: {duration:.3f}秒"
    
    if duration <= max_duration:
        return True, f"时长 {format_duration(duration)} 符合要求（≤ {format_duration(max_duration)}）"
    else:
        return False, f"时长 {format_duration(duration)} 超出限制（> {format_duration(max_duration)}）"


def get_audio_file_duration_info(file_path: Union[str, Path]) -> dict:
    """获取音频文件的时长信息
    
    Args:
        file_path: 音频文件路径
        
    Returns:
        dict: 包含时长信息的字典
    """
    file_path = Path(file_path)
    
    info = {
        'file_path': str(file_path),
        'file_name': file_path.name,
        'exists': file_path.exists(),
        'duration_seconds': 0.0,
        'formatted_duration': '00:00:00.000',
        'is_valid': False,
        'error': None
    }
    
    if info['exists']:
        try:
            duration = calculate_audio_duration_from_file(file_path)
            info['duration_seconds'] = duration
            info['formatted_duration'] = format_duration(duration)
            info['is_valid'] = duration > 0
        except AudioDurationCalculationError as e:
            info['error'] = str(e)
    else:
        info['error'] = '文件不存在'
    
    return info


class AudioCombinationError(Exception):
    """音频组合错误"""
    pass


def combine_audio_segments(segments: List[dict], 
                          output_path: Union[str, Path],
                          max_duration: float = 180.0,
                          max_size: int = 10 * 1024 * 1024,
                          format: str = 'opus') -> dict:
    """组合多个音频片段为一个大片段
    
    Args:
        segments: 音频片段信息列表，每个元素包含 file_path 和 duration
        output_path: 输出文件路径
        max_duration: 最大允许时长（秒）
        max_size: 最大允许文件大小（字节）
        format: 输出音频格式
        
    Returns:
        dict: 组合结果信息
        
    Raises:
        AudioCombinationError: 组合失败时抛出
    """
    if not segments:
        raise AudioCombinationError("没有提供要组合的片段")
    
    logger = get_logger()
    
    # 验证片段有效性
    valid_segments = []
    total_duration = 0.0
    
    for segment in segments:
        file_path = segment.get('file_path')
        duration = segment.get('duration', 0.0)
        
        if not file_path or not Path(file_path).exists():
            logger.warning(f"跳过不存在的片段: {file_path}")
            continue
        
        if duration <= 0:
            logger.warning(f"跳过无效时长的片段: {file_path}")
            continue
        
        # 检查是否超出时长限制
        if total_duration + duration > max_duration:
            logger.info(f"达到时长限制，停止添加片段")
            break
        
        valid_segments.append(segment)
        total_duration += duration
    
    if not valid_segments:
        raise AudioCombinationError("没有找到有效的片段")
    
    logger.info(f"将组合 {len(valid_segments)} 个片段，总时长: {total_duration:.2f}秒")
    
    # 使用FFmpeg进行组合
    try:
        result = _combine_with_ffmpeg(valid_segments, output_path, format)
        
        # 验证输出文件
        output_path = Path(output_path)
        if not output_path.exists():
            raise AudioCombinationError("组合后的文件不存在")
        
        output_size = output_path.stat().st_size
        if output_size > max_size:
            logger.warning(f"组合后文件大小超限: {format_file_size(output_size)} > {format_file_size(max_size)}")
        
        result.update({
            'output_path': str(output_path),
            'output_size': output_size,
            'total_duration': total_duration,
            'segment_count': len(valid_segments),
            'size_check_passed': output_size <= max_size,
            'duration_check_passed': total_duration <= max_duration
        })
        
        return result
        
    except Exception as e:
        raise AudioCombinationError(f"组合音频片段失败: {e}")


def _combine_with_ffmpeg(segments: List[dict], output_path: Union[str, Path], format: str) -> dict:
    """使用FFmpeg组合音频片段"""
    try:
        ffmpeg_path = detect_ffmpeg()
    except FFmpegError:
        raise AudioCombinationError("FFmpeg不可用，无法组合音频片段")
    
    logger = get_logger()
    output_path = Path(output_path)
    
    # 创建临时文件列表
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        file_list_path = f.name
        for segment in segments:
            # FFmpeg concat 格式: file 'path'
            f.write(f"file '{segment['file_path']}'\n")
    
    try:
        # 构建 FFmpeg 命令
        cmd = [
            ffmpeg_path,
            '-f', 'concat',
            '-safe', '0',
            '-i', file_list_path,
            '-c', 'copy',  # 复制流，不重新编码
            '-y',  # 覆盖输出文件
            str(output_path)
        ]
        
        # 如果需要重新编码为不同格式
        if format.lower() == 'opus':
            cmd[-3:-1] = ['-c:a', 'libopus', '-b:a', '64k']
        elif format.lower() == 'mp3':
            cmd[-3:-1] = ['-c:a', 'libmp3lame', '-b:a', '128k']
        
        logger.debug(f"FFmpeg组合命令: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=300  # 5分钟超时
        )
        
        if result.returncode != 0:
            error_msg = f"FFmpeg组合失败: {result.stderr}"
            logger.error(error_msg)
            raise AudioCombinationError(error_msg)
        
        logger.info(f"成功组合音频片段: {output_path}")
        
        return {
            'success': True,
            'method': 'ffmpeg',
            'command': ' '.join(cmd),
            'stderr': result.stderr,
            'stdout': result.stdout
        }
        
    finally:
        # 清理临时文件
        try:
            os.unlink(file_list_path)
        except Exception:
            pass


def plan_segment_combinations(segments: List[dict], 
                            max_duration: float = 180.0,
                            max_size: int = 10 * 1024 * 1024) -> List[List[dict]]:
    """规划片段组合方案
    
    Args:
        segments: 音频片段列表
        max_duration: 最大时长（秒）
        max_size: 最大文件大小（字节）
        
    Returns:
        List[List[dict]]: 组合方案列表，每个元素是一个组合
    """
    if not segments:
        return []
    
    combinations = []
    current_combination = []
    current_duration = 0.0
    current_size = 0
    
    for segment in segments:
        duration = segment.get('duration', 0.0)
        file_path = segment.get('file_path', '')
        
        # 获取文件大小
        try:
            size = calculate_audio_file_size(file_path) if file_path else 0
        except AudioSizeCalculationError:
            size = 0
        
        # 检查是否可以添加到当前组合
        if (current_duration + duration <= max_duration and 
            current_size + size <= max_size and
            current_combination):
            # 添加到当前组合
            current_combination.append(segment)
            current_duration += duration
            current_size += size
        else:
            # 开始新的组合
            if current_combination:
                combinations.append(current_combination)
            
            current_combination = [segment]
            current_duration = duration
            current_size = size
    
    # 添加最后一个组合
    if current_combination:
        combinations.append(current_combination)
    
    return combinations


def optimize_segment_combinations(segments: List[dict],
                                max_duration: float = 180.0,
                                max_size: int = 10 * 1024 * 1024,
                                target_duration: float = 150.0) -> List[List[dict]]:
    """优化片段组合方案，尽量接近目标时长
    
    Args:
        segments: 音频片段列表
        max_duration: 最大时长（秒）
        max_size: 最大文件大小（字节）
        target_duration: 目标时长（秒）
        
    Returns:
        List[List[dict]]: 优化后的组合方案
    """
    if not segments:
        return []
    
    # 按时间顺序排列
    sorted_segments = sorted(segments, key=lambda x: x.get('start_time', 0))
    
    combinations = []
    i = 0
    
    while i < len(sorted_segments):
        current_combination = []
        current_duration = 0.0
        current_size = 0
        
        # 尽量填满目标时长
        while i < len(sorted_segments):
            segment = sorted_segments[i]
            duration = segment.get('duration', 0.0)
            
            # 获取文件大小
            try:
                size = calculate_audio_file_size(segment.get('file_path', '')) 
            except AudioSizeCalculationError:
                size = 0
            
            # 检查是否可以添加
            new_duration = current_duration + duration
            new_size = current_size + size
            
            if new_duration <= max_duration and new_size <= max_size:
                current_combination.append(segment)
                current_duration = new_duration
                current_size = new_size
                i += 1
                
                # 如果达到目标时长，考虑结束当前组合
                if current_duration >= target_duration:
                    break
            else:
                break
        
        if current_combination:
            combinations.append(current_combination)
        
        # 如果没有添加任何片段，跳过当前片段
        if not current_combination and i < len(sorted_segments):
            i += 1
    
    return combinations


def get_combination_info(combination: List[dict]) -> dict:
    """获取组合的统计信息
    
    Args:
        combination: 片段组合
        
    Returns:
        dict: 组合的统计信息
    """
    if not combination:
        return {
            'segment_count': 0,
            'total_duration': 0.0,
            'total_size': 0,
            'formatted_duration': '00:00:00.000',
            'formatted_size': '0 B',
            'start_time': 0.0,
            'end_time': 0.0,
            'is_valid': False
        }
    
    total_duration = sum(seg.get('duration', 0.0) for seg in combination)
    total_size = 0
    
    for segment in combination:
        try:
            size = calculate_audio_file_size(segment.get('file_path', ''))
            total_size += size
        except AudioSizeCalculationError:
            pass
    
    start_time = min(seg.get('start_time', 0.0) for seg in combination)
    end_time = max(seg.get('end_time', seg.get('start_time', 0.0) + seg.get('duration', 0.0)) 
                  for seg in combination)
    
    return {
        'segment_count': len(combination),
        'total_duration': total_duration,
        'total_size': total_size,
        'formatted_duration': format_duration(total_duration),
        'formatted_size': format_file_size(total_size),
        'start_time': start_time,
        'end_time': end_time,
        'is_valid': total_duration > 0
    }


class AudioConversionError(Exception):
    """音频转换错误"""
    
    def __init__(self, message: str, error_code: str = None, 
                 suggestions: list = None, ffmpeg_output: str = None):
        super().__init__(message)
        self.error_code = error_code
        self.suggestions = suggestions or []
        self.ffmpeg_output = ffmpeg_output


def analyze_conversion_error(stderr_output: str, returncode: int) -> dict:
    """分析转换错误并提供建议
    
    Args:
        stderr_output: FFmpeg错误输出
        returncode: 返回码
        
    Returns:
        dict: 错误分析结果
    """
    error_info = {
        'error_type': 'unknown',
        'error_message': 'Unknown conversion error',
        'suggestions': [],
        'is_recoverable': False,
        'retry_recommended': False
    }
    
    stderr_lower = stderr_output.lower()
    
    # 分析常见错误类型
    if 'no such file or directory' in stderr_lower or 'cannot find' in stderr_lower:
        error_info.update({
            'error_type': 'file_not_found',
            'error_message': '输入文件不存在或无法访问',
            'suggestions': [
                '检查输入文件路径是否正确',
                '确认文件存在且有读取权限',
                '检查文件名是否包含特殊字符'
            ],
            'is_recoverable': True
        })
    
    elif 'permission denied' in stderr_lower or 'access denied' in stderr_lower:
        error_info.update({
            'error_type': 'permission_error',
            'error_message': '文件权限不足',
            'suggestions': [
                '检查文件读写权限',
                '确认输出目录有写入权限',
                '尝试使用管理员权限运行'
            ],
            'is_recoverable': True
        })
    
    elif 'invalid data found' in stderr_lower or 'not supported' in stderr_lower:
        error_info.update({
            'error_type': 'format_error',
            'error_message': '不支持的音频格式或文件损坏',
            'suggestions': [
                '检查输入文件是否为有效的音频文件',
                '尝试使用其他音频格式',
                '检查文件是否损坏或不完整'
            ],
            'is_recoverable': False
        })
    
    elif 'disk full' in stderr_lower or 'no space left' in stderr_lower:
        error_info.update({
            'error_type': 'disk_space_error',
            'error_message': '磁盘空间不足',
            'suggestions': [
                '清理磁盘空间',
                '选择其他输出目录',
                '降低音频质量以减少文件大小'
            ],
            'is_recoverable': True
        })
    
    elif 'timeout' in stderr_lower or returncode == 124:
        error_info.update({
            'error_type': 'timeout_error',
            'error_message': '转换超时',
            'suggestions': [
                '增加超时时间',
                '检查输入文件大小和复杂度',
                '尝试使用更快的编码参数'
            ],
            'is_recoverable': True,
            'retry_recommended': True
        })
    
    elif 'codec not found' in stderr_lower or 'unknown encoder' in stderr_lower:
        error_info.update({
            'error_type': 'codec_error',
            'error_message': '找不到所需的编解码器',
            'suggestions': [
                '检查FFmpeg版本是否支持所需的编解码器',
                '尝试使用其他输出格式',
                '更新或重新编译FFmpeg'
            ],
            'is_recoverable': True
        })
    
    elif returncode == 1 and 'error' not in stderr_lower:
        error_info.update({
            'error_type': 'parameter_error',
            'error_message': '无效的命令行参数',
            'suggestions': [
                '检查转换参数是否正确',
                '尝试使用默认参数',
                '检查FFmpeg版本兼容性'
            ],
            'is_recoverable': True
        })
    
    return error_info


# =============================================================================
# 片段队列管理功能 (Task 29)
# =============================================================================

from collections import deque
from datetime import datetime
from enum import Enum
from typing import Deque, Optional
import threading


class SegmentStatus(Enum):
    """片段处理状态枚举"""
    PENDING = "pending"      # 待处理
    PROCESSING = "processing" # 处理中
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"        # 处理失败
    CANCELLED = "cancelled"   # 已取消


class SegmentQueueItem:
    """队列中的片段项"""
    
    def __init__(self, segment: dict, priority: int = 0, metadata: dict = None):
        """
        Args:
            segment: 音频片段信息
            priority: 优先级（数值越大优先级越高）
            metadata: 额外的元数据
        """
        self.segment = segment
        self.priority = priority
        self.metadata = metadata or {}
        self.status = SegmentStatus.PENDING
        self.created_at = datetime.now()
        self.updated_at = self.created_at
        self.retry_count = 0
        self.error_message = None
        self.processing_start_time = None
        self.processing_end_time = None
        
        # 生成唯一ID
        import uuid
        self.id = str(uuid.uuid4())
    
    def update_status(self, new_status: SegmentStatus, error_message: str = None):
        """更新状态"""
        self.status = new_status
        self.updated_at = datetime.now()
        
        if new_status == SegmentStatus.PROCESSING:
            self.processing_start_time = self.updated_at
        elif new_status in [SegmentStatus.COMPLETED, SegmentStatus.FAILED, SegmentStatus.CANCELLED]:
            self.processing_end_time = self.updated_at
        
        if error_message:
            self.error_message = error_message
        
        if new_status == SegmentStatus.FAILED:
            self.retry_count += 1
    
    @property
    def processing_duration(self) -> float:
        """获取处理时长（秒）"""
        if self.processing_start_time:
            end_time = self.processing_end_time or datetime.now()
            return (end_time - self.processing_start_time).total_seconds()
        return 0.0
    
    def __lt__(self, other):
        """支持优先级排序（优先级高的在前）"""
        return self.priority > other.priority
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'id': self.id,
            'segment': self.segment,
            'priority': self.priority,
            'metadata': self.metadata,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'retry_count': self.retry_count,
            'error_message': self.error_message,
            'processing_duration': self.processing_duration
        }


class SegmentQueueError(Exception):
    """片段队列错误"""
    pass


class SegmentQueue:
    """音频片段处理队列管理器"""
    
    def __init__(self, max_size: int = 1000, max_retry_count: int = 3):
        """
        Args:
            max_size: 队列最大大小
            max_retry_count: 最大重试次数
        """
        self.max_size = max_size
        self.max_retry_count = max_retry_count
        self._queue: Deque[SegmentQueueItem] = deque()
        self._processing_items: Dict[str, SegmentQueueItem] = {}
        self._completed_items: Deque[SegmentQueueItem] = deque(maxlen=100)  # 保留最近100个完成的项目
        self._lock = threading.RLock()
        self._stats = {
            'total_added': 0,
            'total_processed': 0,
            'total_failed': 0,
            'total_cancelled': 0
        }
    
    def add_segment(self, segment: dict, priority: int = 0, metadata: dict = None) -> str:
        """添加片段到队列
        
        Args:
            segment: 音频片段信息
            priority: 优先级
            metadata: 元数据
            
        Returns:
            str: 队列项ID
            
        Raises:
            SegmentQueueError: 队列已满时抛出
        """
        with self._lock:
            if len(self._queue) >= self.max_size:
                raise SegmentQueueError(f"队列已满，当前大小: {len(self._queue)}")
            
            item = SegmentQueueItem(segment, priority, metadata)
            
            # 按优先级插入（维持优先级顺序）
            inserted = False
            for i, existing_item in enumerate(self._queue):
                if item.priority > existing_item.priority:
                    self._queue.insert(i, item)
                    inserted = True
                    break
            
            if not inserted:
                self._queue.append(item)
            
            self._stats['total_added'] += 1
            return item.id
    
    def add_segments_batch(self, segments: List[dict], priority: int = 0, metadata: dict = None) -> List[str]:
        """批量添加片段
        
        Args:
            segments: 音频片段列表
            priority: 优先级
            metadata: 元数据
            
        Returns:
            List[str]: 队列项ID列表
        """
        item_ids = []
        for segment in segments:
            try:
                item_id = self.add_segment(segment, priority, metadata)
                item_ids.append(item_id)
            except SegmentQueueError as e:
                logger = get_logger()
                logger.warning(f"添加片段失败: {e}")
                break
        return item_ids
    
    def get_next_segment(self) -> Optional[SegmentQueueItem]:
        """获取下一个待处理的片段
        
        Returns:
            Optional[SegmentQueueItem]: 下一个片段项，如果队列为空则返回None
        """
        with self._lock:
            if not self._queue:
                return None
            
            item = self._queue.popleft()
            item.update_status(SegmentStatus.PROCESSING)
            self._processing_items[item.id] = item
            return item
    
    def complete_segment(self, item_id: str, success: bool = True, error_message: str = None):
        """标记片段处理完成
        
        Args:
            item_id: 队列项ID
            success: 是否成功
            error_message: 错误信息（如果失败）
        """
        with self._lock:
            if item_id not in self._processing_items:
                raise SegmentQueueError(f"未找到处理中的片段: {item_id}")
            
            item = self._processing_items.pop(item_id)
            
            if success:
                item.update_status(SegmentStatus.COMPLETED)
                self._completed_items.append(item)
                self._stats['total_processed'] += 1
            else:
                # 检查是否需要重试
                if item.retry_count < self.max_retry_count:
                    item.update_status(SegmentStatus.PENDING, error_message)
                    # 重新加入队列，降低优先级
                    item.priority = max(0, item.priority - 1)
                    self._queue.append(item)
                else:
                    item.update_status(SegmentStatus.FAILED, error_message)
                    self._completed_items.append(item)
                    self._stats['total_failed'] += 1
    
    def cancel_segment(self, item_id: str):
        """取消片段处理
        
        Args:
            item_id: 队列项ID
        """
        with self._lock:
            # 在待处理队列中查找
            for i, item in enumerate(self._queue):
                if item.id == item_id:
                    item.update_status(SegmentStatus.CANCELLED)
                    self._queue.remove(item)
                    self._completed_items.append(item)
                    self._stats['total_cancelled'] += 1
                    return
            
            # 在处理中查找
            if item_id in self._processing_items:
                item = self._processing_items.pop(item_id)
                item.update_status(SegmentStatus.CANCELLED)
                self._completed_items.append(item)
                self._stats['total_cancelled'] += 1
                return
            
            raise SegmentQueueError(f"未找到片段: {item_id}")
    
    def get_queue_status(self) -> dict:
        """获取队列状态
        
        Returns:
            dict: 队列状态信息
        """
        with self._lock:
            return {
                'pending_count': len(self._queue),
                'processing_count': len(self._processing_items),
                'completed_count': len(self._completed_items),
                'max_size': self.max_size,
                'is_full': len(self._queue) >= self.max_size,
                'is_empty': len(self._queue) == 0,
                'stats': self._stats.copy()
            }
    
    def get_pending_segments(self) -> List[dict]:
        """获取待处理片段列表
        
        Returns:
            List[dict]: 待处理片段信息列表
        """
        with self._lock:
            return [item.to_dict() for item in self._queue]
    
    def get_processing_segments(self) -> List[dict]:
        """获取处理中片段列表
        
        Returns:
            List[dict]: 处理中片段信息列表
        """
        with self._lock:
            return [item.to_dict() for item in self._processing_items.values()]
    
    def get_completed_segments(self, limit: int = 50) -> List[dict]:
        """获取已完成片段列表
        
        Args:
            limit: 返回数量限制
            
        Returns:
            List[dict]: 已完成片段信息列表
        """
        with self._lock:
            completed_list = list(self._completed_items)
            # 按完成时间倒序排列
            completed_list.sort(key=lambda x: x.updated_at, reverse=True)
            return [item.to_dict() for item in completed_list[:limit]]
    
    def clear_completed(self):
        """清空已完成的片段记录"""
        with self._lock:
            self._completed_items.clear()
    
    def reset_queue(self):
        """重置队列（清空所有内容）"""
        with self._lock:
            self._queue.clear()
            self._processing_items.clear()
            self._completed_items.clear()
            self._stats = {
                'total_added': 0,
                'total_processed': 0,
                'total_failed': 0,
                'total_cancelled': 0
            }
    
    def get_segment_by_id(self, item_id: str) -> Optional[dict]:
        """根据ID获取片段信息
        
        Args:
            item_id: 队列项ID
            
        Returns:
            Optional[dict]: 片段信息，未找到时返回None
        """
        with self._lock:
            # 在待处理队列中查找
            for item in self._queue:
                if item.id == item_id:
                    return item.to_dict()
            
            # 在处理中查找
            if item_id in self._processing_items:
                return self._processing_items[item_id].to_dict()
            
            # 在已完成中查找
            for item in self._completed_items:
                if item.id == item_id:
                    return item.to_dict()
            
            return None
    
    def update_segment_priority(self, item_id: str, new_priority: int):
        """更新片段优先级
        
        Args:
            item_id: 队列项ID
            new_priority: 新的优先级
        """
        with self._lock:
            # 只能更新待处理队列中的片段
            for i, item in enumerate(self._queue):
                if item.id == item_id:
                    # 移除并重新插入以保持优先级顺序
                    self._queue.remove(item)
                    item.priority = new_priority
                    
                    # 按优先级重新插入
                    inserted = False
                    for j, existing_item in enumerate(self._queue):
                        if item.priority > existing_item.priority:
                            self._queue.insert(j, item)
                            inserted = True
                            break
                    
                    if not inserted:
                        self._queue.append(item)
                    return
            
            raise SegmentQueueError(f"未找到待处理片段: {item_id}")
    
    def get_statistics(self) -> dict:
        """获取详细统计信息
        
        Returns:
            dict: 统计信息
        """
        with self._lock:
            status = self.get_queue_status()
            
            # 计算平均处理时间
            processing_times = []
            for item in self._completed_items:
                if item.status == SegmentStatus.COMPLETED and item.processing_duration > 0:
                    processing_times.append(item.processing_duration)
            
            avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0
            
            # 计算成功率
            total_finished = self._stats['total_processed'] + self._stats['total_failed']
            success_rate = (self._stats['total_processed'] / total_finished * 100) if total_finished > 0 else 0
            
            status.update({
                'average_processing_time': avg_processing_time,
                'success_rate': success_rate,
                'total_finished': total_finished,
                'queue_utilization': len(self._queue) / self.max_size * 100
            })
            
            return status


# =============================================================================
# 片段状态跟踪功能 (Task 30)
# =============================================================================

class SegmentStatusTracker:
    """音频片段状态跟踪器"""
    
    def __init__(self):
        self._segments: Dict[str, Dict] = {}  # segment_id -> segment_info
        self._status_history: Dict[str, List[Dict]] = {}  # segment_id -> history_list
        self._lock = threading.RLock()
        self._listeners: List[callable] = []  # 状态变化监听器
    
    def register_segment(self, segment_id: str, segment_info: dict) -> bool:
        """注册一个新的片段进行跟踪
        
        Args:
            segment_id: 片段唯一标识
            segment_info: 片段信息
            
        Returns:
            bool: 注册是否成功
        """
        with self._lock:
            if segment_id in self._segments:
                return False  # 已存在
            
            self._segments[segment_id] = {
                'id': segment_id,
                'info': segment_info.copy(),
                'status': SegmentStatus.PENDING,
                'created_at': datetime.now(),
                'updated_at': datetime.now(),
                'error_message': None,
                'retry_count': 0,
                'processing_start_time': None,
                'processing_end_time': None,
                'metadata': {}
            }
            
            self._status_history[segment_id] = []
            self._add_status_entry(segment_id, SegmentStatus.PENDING, "片段已注册")
            
            return True
    
    def update_status(self, segment_id: str, new_status: SegmentStatus, 
                     message: str = None, metadata: dict = None) -> bool:
        """更新片段状态
        
        Args:
            segment_id: 片段ID
            new_status: 新状态
            message: 状态变化消息
            metadata: 额外的元数据
            
        Returns:
            bool: 更新是否成功
        """
        with self._lock:
            if segment_id not in self._segments:
                return False
            
            segment = self._segments[segment_id]
            old_status = segment['status']
            
            # 验证状态转换是否合法
            if not self._is_valid_status_transition(old_status, new_status):
                logger = get_logger()
                logger.warning(f"无效的状态转换: {old_status.value} -> {new_status.value}")
                return False
            
            # 更新状态
            segment['status'] = new_status
            segment['updated_at'] = datetime.now()
            
            if message:
                segment['error_message'] = message if new_status == SegmentStatus.FAILED else None
            
            if metadata:
                segment['metadata'].update(metadata)
            
            # 特殊状态处理
            if new_status == SegmentStatus.PROCESSING:
                segment['processing_start_time'] = segment['updated_at']
            elif new_status in [SegmentStatus.COMPLETED, SegmentStatus.FAILED, SegmentStatus.CANCELLED]:
                segment['processing_end_time'] = segment['updated_at']
            
            if new_status == SegmentStatus.FAILED:
                segment['retry_count'] += 1
            
            # 记录状态历史
            self._add_status_entry(segment_id, new_status, message, metadata)
            
            # 通知监听器
            self._notify_listeners(segment_id, old_status, new_status, message)
            
            return True
    
    def _is_valid_status_transition(self, old_status: SegmentStatus, new_status: SegmentStatus) -> bool:
        """验证状态转换是否合法"""
        # 定义合法的状态转换
        valid_transitions = {
            SegmentStatus.PENDING: [SegmentStatus.PROCESSING, SegmentStatus.CANCELLED],
            SegmentStatus.PROCESSING: [SegmentStatus.COMPLETED, SegmentStatus.FAILED, SegmentStatus.CANCELLED],
            SegmentStatus.FAILED: [SegmentStatus.PENDING, SegmentStatus.CANCELLED],  # 可以重试
            SegmentStatus.COMPLETED: [SegmentStatus.CANCELLED],  # 完成后只能取消
            SegmentStatus.CANCELLED: []  # 取消后不能再变更
        }
        
        return new_status in valid_transitions.get(old_status, [])
    
    def _add_status_entry(self, segment_id: str, status: SegmentStatus, 
                         message: str = None, metadata: dict = None):
        """添加状态历史记录"""
        entry = {
            'status': status,
            'timestamp': datetime.now(),
            'message': message,
            'metadata': metadata or {}
        }
        
        self._status_history[segment_id].append(entry)
        
        # 限制历史记录数量
        if len(self._status_history[segment_id]) > 50:
            self._status_history[segment_id] = self._status_history[segment_id][-50:]
    
    def get_segment_status(self, segment_id: str) -> Optional[dict]:
        """获取片段状态信息
        
        Args:
            segment_id: 片段ID
            
        Returns:
            Optional[dict]: 片段状态信息，未找到时返回None
        """
        with self._lock:
            if segment_id not in self._segments:
                return None
            
            segment = self._segments[segment_id]
            
            # 计算处理时长
            processing_duration = 0.0
            if segment['processing_start_time']:
                end_time = segment['processing_end_time'] or datetime.now()
                processing_duration = (end_time - segment['processing_start_time']).total_seconds()
            
            return {
                'id': segment['id'],
                'info': segment['info'].copy(),
                'status': segment['status'].value,
                'created_at': segment['created_at'].isoformat(),
                'updated_at': segment['updated_at'].isoformat(),
                'error_message': segment['error_message'],
                'retry_count': segment['retry_count'],
                'processing_duration': processing_duration,
                'metadata': segment['metadata'].copy()
            }
    
    def get_segment_history(self, segment_id: str) -> List[dict]:
        """获取片段状态历史
        
        Args:
            segment_id: 片段ID
            
        Returns:
            List[dict]: 状态历史列表
        """
        with self._lock:
            if segment_id not in self._status_history:
                return []
            
            return [
                {
                    'status': entry['status'].value,
                    'timestamp': entry['timestamp'].isoformat(),
                    'message': entry['message'],
                    'metadata': entry['metadata']
                }
                for entry in self._status_history[segment_id]
            ]
    
    def get_segments_by_status(self, status: SegmentStatus) -> List[dict]:
        """获取指定状态的所有片段
        
        Args:
            status: 片段状态
            
        Returns:
            List[dict]: 片段列表
        """
        with self._lock:
            result = []
            for segment_id, segment in self._segments.items():
                if segment['status'] == status:
                    status_info = self.get_segment_status(segment_id)
                    if status_info:
                        result.append(status_info)
            return result
    
    def get_all_segments(self) -> List[dict]:
        """获取所有片段的状态信息
        
        Returns:
            List[dict]: 所有片段的状态信息
        """
        with self._lock:
            result = []
            for segment_id in self._segments:
                status_info = self.get_segment_status(segment_id)
                if status_info:
                    result.append(status_info)
            return result
    
    def get_statistics(self) -> dict:
        """获取状态统计信息
        
        Returns:
            dict: 统计信息
        """
        with self._lock:
            stats = {
                'total_segments': len(self._segments),
                'by_status': {}
            }
            
            # 按状态统计
            for status in SegmentStatus:
                count = sum(1 for seg in self._segments.values() if seg['status'] == status)
                stats['by_status'][status.value] = count
            
            # 计算平均处理时间
            processing_times = []
            for segment in self._segments.values():
                if (segment['status'] == SegmentStatus.COMPLETED and 
                    segment['processing_start_time'] and segment['processing_end_time']):
                    duration = (segment['processing_end_time'] - segment['processing_start_time']).total_seconds()
                    processing_times.append(duration)
            
            stats['average_processing_time'] = sum(processing_times) / len(processing_times) if processing_times else 0
            
            # 计算成功率
            completed = stats['by_status'].get('completed', 0)
            failed = stats['by_status'].get('failed', 0)
            total_finished = completed + failed
            stats['success_rate'] = (completed / total_finished * 100) if total_finished > 0 else 0
            
            # 计算重试率
            total_retries = sum(seg['retry_count'] for seg in self._segments.values())
            stats['retry_rate'] = (total_retries / len(self._segments) * 100) if self._segments else 0
            
            return stats
    
    def add_status_listener(self, listener: callable):
        """添加状态变化监听器
        
        Args:
            listener: 监听器函数，签名为 listener(segment_id, old_status, new_status, message)
        """
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)
    
    def remove_status_listener(self, listener: callable):
        """移除状态变化监听器
        
        Args:
            listener: 要移除的监听器函数
        """
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)
    
    def _notify_listeners(self, segment_id: str, old_status: SegmentStatus, 
                         new_status: SegmentStatus, message: str = None):
        """通知状态变化监听器"""
        for listener in self._listeners:
            try:
                listener(segment_id, old_status, new_status, message)
            except Exception as e:
                logger = get_logger()
                logger.error(f"状态监听器执行失败: {e}")
    
    def cleanup_completed(self, older_than_hours: int = 24):
        """清理已完成的片段记录
        
        Args:
            older_than_hours: 清理多少小时前完成的记录
        """
        with self._lock:
            cutoff_time = datetime.now() - timedelta(hours=older_than_hours)
            
            segments_to_remove = []
            for segment_id, segment in self._segments.items():
                if (segment['status'] in [SegmentStatus.COMPLETED, SegmentStatus.CANCELLED] and
                    segment['updated_at'] < cutoff_time):
                    segments_to_remove.append(segment_id)
            
            for segment_id in segments_to_remove:
                del self._segments[segment_id]
                del self._status_history[segment_id]
    
    def reset_tracker(self):
        """重置跟踪器（清空所有数据）"""
        with self._lock:
            self._segments.clear()
            self._status_history.clear()
            self._listeners.clear()
    
    def export_data(self) -> dict:
        """导出所有跟踪数据
        
        Returns:
            dict: 包含所有片段和历史的数据
        """
        with self._lock:
            return {
                'segments': {
                    segment_id: {
                        **segment,
                        'status': segment['status'].value,
                        'created_at': segment['created_at'].isoformat(),
                        'updated_at': segment['updated_at'].isoformat(),
                        'processing_start_time': segment['processing_start_time'].isoformat() if segment['processing_start_time'] else None,
                        'processing_end_time': segment['processing_end_time'].isoformat() if segment['processing_end_time'] else None
                    }
                    for segment_id, segment in self._segments.items()
                },
                'history': {
                    segment_id: [
                        {
                            'status': entry['status'].value,
                            'timestamp': entry['timestamp'].isoformat(),
                            'message': entry['message'],
                            'metadata': entry['metadata']
                        }
                        for entry in history
                    ]
                    for segment_id, history in self._status_history.items()
                },
                'export_time': datetime.now().isoformat()
            }


def create_recovery_suggestion(error_info: dict, input_path: str, output_path: str) -> str:
    """创建恢复建议文本
    
    Args:
        error_info: 错误分析信息
        input_path: 输入文件路径
        output_path: 输出文件路径
        
    Returns:
        str: 恢复建议文本
    """
    suggestions = []
    
    if error_info['is_recoverable']:
        suggestions.append("✨ 这个错误可能可以修复！")
    else:
        suggestions.append("⚠️ 这个错误可能需要手动干预")
    
    suggestions.append(f"📝 错误类型: {error_info['error_type']}")
    suggestions.append(f"💡 建议解决方案:")
    
    for i, suggestion in enumerate(error_info['suggestions'], 1):
        suggestions.append(f"   {i}. {suggestion}")
    
    if error_info['retry_recommended']:
        suggestions.append("🔄 建议稍后重试")
    
    return "\n".join(suggestions)


class FFmpegError(Exception):
    """FFmpeg相关错误"""
    pass


def detect_ffmpeg() -> str:
    """检测系统中FFmpeg是否可用
    
    Returns:
        str: FFmpeg可执行文件路径
        
    Raises:
        FFmpegError: 当FFmpeg不可用时抛出异常
    """
    settings = get_settings()
    logger = get_logger()
    
    logger.debug("开始检测FFmpeg可用性")
    
    # 检查顺序：
    # 1. 配置文件中指定的路径
    # 2. external/ffmpeg/ffmpeg.exe (Windows)
    # 3. 系统PATH中的ffmpeg
    
    candidates = []
    
    # 1. 检查配置文件中的路径
    if settings.FFMPEG_PATH and settings.FFMPEG_PATH.strip():
        candidates.append(settings.FFMPEG_PATH.strip())
        logger.debug(f"从配置文件添加FFmpeg路径: {settings.FFMPEG_PATH}")
    
    # 2. 检查项目external目录
    external_ffmpeg = settings.EXTERNAL_DIR / "ffmpeg" / ("ffmpeg.exe" if os.name == 'nt' else "ffmpeg")
    candidates.append(str(external_ffmpeg))
    logger.debug(f"添加项目external目录FFmpeg路径: {external_ffmpeg}")
    
    # 3. 检查系统PATH
    if os.name == 'nt':
        # Windows
        candidates.extend(["ffmpeg.exe", "ffmpeg"])
    else:
        # Linux/Mac
        candidates.extend(["ffmpeg"])
    
    logger.debug(f"FFmpeg候选路径: {candidates}")
    
    # 逐一测试候选路径
    for candidate in candidates:
        try:
            ffmpeg_path = _test_ffmpeg_path(candidate)
            if ffmpeg_path:
                logger.debug(f"检测到可用的FFmpeg: {ffmpeg_path}")
                return ffmpeg_path
        except Exception as e:
            logger.debug(f"测试FFmpeg路径失败 {candidate}: {e}")
            continue
    
    # 所有候选路径都失败
    error_msg = "未找到可用的FFmpeg。请确保FFmpeg已安装并在PATH中，或在配置文件中指定正确路径"
    logger.error(error_msg)
    raise FFmpegError(error_msg)


def _test_ffmpeg_path(ffmpeg_path: str) -> Optional[str]:
    """测试指定路径的FFmpeg是否可用
    
    Args:
        ffmpeg_path: FFmpeg可执行文件路径
        
    Returns:
        Optional[str]: 如果可用返回规范化路径，否则返回None
    """
    logger = get_logger()
    try:
        # 尝试运行ffmpeg -version命令
        result = subprocess.run(
            [ffmpeg_path, "-version"],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=10,
            check=False
        )
        
        if result.returncode == 0 and "ffmpeg version" in result.stdout.lower():
            # FFmpeg可用，返回绝对路径
            path_obj = Path(ffmpeg_path)
            if path_obj.is_absolute():
                return str(path_obj)
            else:
                # 相对路径或命令名，尝试找到完整路径
                import shutil
                full_path = shutil.which(ffmpeg_path)
                return full_path if full_path else str(path_obj.resolve())
        else:
            logger.debug(f"FFmpeg版本检查失败 {ffmpeg_path}: returncode={result.returncode}")
            return None
            
    except subprocess.TimeoutExpired:
        logger.debug(f"FFmpeg版本检查超时 {ffmpeg_path}")
        return None
    except FileNotFoundError:
        logger.debug(f"FFmpeg文件不存在 {ffmpeg_path}")
        return None
    except Exception as e:
        logger.debug(f"FFmpeg测试异常 {ffmpeg_path}: {e}")
        return None


def get_ffmpeg_version(ffmpeg_path: Optional[str] = None) -> Tuple[bool, str]:
    """获取FFmpeg版本信息
    
    Args:
        ffmpeg_path: FFmpeg路径，如果为None则自动检测
        
    Returns:
        Tuple[bool, str]: (是否成功, 版本信息或错误信息)
    """
    try:
        if ffmpeg_path is None:
            ffmpeg_path = detect_ffmpeg()
        
        result = subprocess.run(
            [ffmpeg_path, "-version"],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=10,
            check=False
        )
        
        if result.returncode == 0:
            # 提取版本信息的第一行
            lines = result.stdout.strip().split('\n')
            version_line = lines[0] if lines else "Unknown version"
            return True, version_line
        else:
            return False, f"FFmpeg返回错误代码: {result.returncode}"
            
    except FFmpegError as e:
        return False, str(e)
    except subprocess.TimeoutExpired:
        return False, "FFmpeg版本检查超时"
    except Exception as e:
        return False, f"获取FFmpeg版本时发生错误: {e}"


def validate_ffmpeg() -> bool:
    """验证FFmpeg是否可用
    
    Returns:
        bool: FFmpeg是否可用
    """
    try:
        detect_ffmpeg()
        return True
    except FFmpegError:
        return False


def get_ffmpeg_path() -> str:
    """获取FFmpeg路径（缓存版本）
    
    Returns:
        str: FFmpeg可执行文件路径
        
    Raises:
        FFmpegError: 当FFmpeg不可用时抛出异常
    """
    # 可以在这里添加缓存逻辑以提高性能
    return detect_ffmpeg()


def check_ffmpeg_features(ffmpeg_path: Optional[str] = None) -> dict:
    """检查FFmpeg支持的功能
    
    Args:
        ffmpeg_path: FFmpeg路径，如果为None则自动检测
        
    Returns:
        dict: 支持的编解码器和格式信息
    """
    try:
        if ffmpeg_path is None:
            ffmpeg_path = detect_ffmpeg()
        
        features = {
            'codecs': [],
            'formats': [],
            'available': True,
            'version': ''
        }
        
        # 获取版本信息
        success, version = get_ffmpeg_version(ffmpeg_path)
        if success:
            features['version'] = version
        
        # 获取编解码器信息
        try:
            result = subprocess.run(
                [ffmpeg_path, "-codecs"],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=15,
                check=False
            )
            
            if result.returncode == 0:
                # 简单提取常用编解码器
                common_codecs = ['opus', 'mp3', 'aac', 'wav', 'flac', 'ogg']
                for codec in common_codecs:
                    if codec in result.stdout.lower():
                        features['codecs'].append(codec)
                        
        except Exception as e:
            logger.debug(f"获取FFmpeg编解码器信息失败: {e}")
        
        # 获取格式信息
        try:
            result = subprocess.run(
                [ffmpeg_path, "-formats"],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=15,
                check=False
            )
            
            if result.returncode == 0:
                # 简单提取常用格式
                common_formats = ['mp4', 'avi', 'mov', 'wav', 'mp3', 'opus', 'webm']
                for fmt in common_formats:
                    if fmt in result.stdout.lower():
                        features['formats'].append(fmt)
                        
        except Exception as e:
            logger.debug(f"获取FFmpeg格式信息失败: {e}")
        
        return features
        
    except FFmpegError:
        return {
            'codecs': [],
            'formats': [],
            'available': False,
            'version': 'FFmpeg not available'
        }


# 音频格式支持常量
SUPPORTED_INPUT_FORMATS = {
    # 视频格式（提取音频）
    '.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v',
    # 音频格式
    '.mp3', '.wav', '.opus', '.ogg', '.aac', '.flac', '.m4a', '.wma'
}

SUPPORTED_OUTPUT_FORMATS = {
    '.opus', '.wav', '.mp3', '.aac', '.ogg', '.flac'
}

# 默认转换格式
DEFAULT_OUTPUT_FORMAT = '.opus'
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_CHANNELS = 1  # 单声道


def is_supported_audio_format(file_path: str) -> bool:
    """检查文件格式是否支持
    
    Args:
        file_path: 音频文件路径
        
    Returns:
        bool: 是否支持该格式
    """
    file_ext = Path(file_path).suffix.lower()
    return file_ext in SUPPORTED_INPUT_FORMATS


def is_audio_file(file_path: str) -> bool:
    """检查文件是否为音频文件
    
    Args:
        file_path: 文件路径
        
    Returns:
        bool: 是否为音频文件
    """
    if not Path(file_path).exists():
        return False
    
    return is_supported_audio_format(file_path)


def format_duration(seconds: float) -> str:
    """格式化时长为可读字符串
    
    Args:
        seconds: 秒数
        
    Returns:
        str: 格式化的时长字符串
    """
    if seconds < 0:
        return "00:00:00"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def parse_duration(duration_str: str) -> float:
    """解析时长字符串为秒数
    
    Args:
        duration_str: 时长字符串，格式如"HH:MM:SS"或"MM:SS"或"SS"
        
    Returns:
        float: 秒数
    """
    try:
        parts = duration_str.strip().split(':')
        parts = [float(p) for p in parts]
        
        if len(parts) == 1:
            # 只有秒数
            return parts[0]
        elif len(parts) == 2:
            # MM:SS
            return parts[0] * 60 + parts[1]
        elif len(parts) == 3:
            # HH:MM:SS
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        else:
            return 0.0
    except (ValueError, IndexError):
        return 0.0


def detect_audio_format(file_path: str, ffmpeg_path: Optional[str] = None) -> dict:
    """检测音频文件格式信息
    
    Args:
        file_path: 音频文件路径
        ffmpeg_path: FFmpeg路径，如果为None则自动检测
        
    Returns:
        dict: 音频格式信息，包含：
            - format: 文件格式（如'mp3', 'opus', 'wav'等）
            - codec: 音频编解码器
            - container: 容器格式
            - mime_type: MIME类型
            - extension: 文件扩展名
            - is_audio: 是否为音频文件
            - supported: 是否为支持的格式
            - error: 错误信息（如果有）
    """
    logger = get_logger()
    
    try:
        file_path_obj = Path(file_path)
        
        # 检查文件是否存在
        if not file_path_obj.exists():
            return {
                'format': 'unknown',
                'codec': 'unknown', 
                'container': 'unknown',
                'mime_type': 'unknown',
                'extension': file_path_obj.suffix.lower(),
                'is_audio': False,
                'supported': False,
                'error': 'File not found'
            }
        
        extension = file_path_obj.suffix.lower()
        
        # 基于扩展名的初步判断
        result = {
            'extension': extension,
            'is_audio': extension in SUPPORTED_INPUT_FORMATS,
            'supported': extension in SUPPORTED_INPUT_FORMATS,
            'error': None
        }
        
        # 使用mimetypes模块进行MIME类型检测
        import mimetypes
        mime_type, _ = mimetypes.guess_type(file_path)
        result['mime_type'] = mime_type or 'unknown'
        
        # 使用FFmpeg/ffprobe进行详细检测
        if ffmpeg_path is None:
            try:
                ffmpeg_path = detect_ffmpeg()
            except FFmpegError:
                # FFmpeg不可用，仅返回基于扩展名的结果
                logger.warning("FFmpeg不可用，仅基于文件扩展名检测格式")
                result.update({
                    'format': extension.lstrip('.') if extension else 'unknown',
                    'codec': 'unknown',
                    'container': 'unknown'
                })
                return result
        
        # 使用ffprobe获取详细格式信息
        # 智能构造ffprobe路径
        ffmpeg_path_obj = Path(ffmpeg_path)
        if ffmpeg_path_obj.name.startswith('ffmpeg'):
            ffprobe_name = ffmpeg_path_obj.name.replace('ffmpeg', 'ffprobe', 1)
            ffprobe_path = str(ffmpeg_path_obj.parent / ffprobe_name)
        else:
            # 如果不是标准的ffmpeg命名，尝试在同一目录下查找ffprobe
            ffprobe_path = str(ffmpeg_path_obj.parent / 'ffprobe.exe' if os.name == 'nt' else 'ffprobe')
        
        cmd = [
            ffprobe_path,
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            file_path
        ]
        
        probe_result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            encoding='utf-8',
            errors='ignore'
        )
        
        if probe_result.returncode != 0 or not probe_result.stdout.strip():
            logger.debug(f"ffprobe检测失败: {probe_result.stderr}")
            # 回退到基于扩展名的检测
            result.update({
                'format': extension.lstrip('.') if extension else 'unknown',
                'codec': 'unknown',
                'container': 'unknown'
            })
            return result
        
        import json
        try:
            probe_data = json.loads(probe_result.stdout)
        except (json.JSONDecodeError, TypeError) as e:
            logger.debug(f"JSON解析失败: {e}")
            result.update({
                'format': extension.lstrip('.') if extension else 'unknown',
                'codec': 'unknown',
                'container': 'unknown',
                'error': f'JSON parsing failed: {e}'
            })
            return result
        
        # 解析格式信息
        format_info = probe_data.get('format', {})
        streams = probe_data.get('streams', [])
        
        # 获取音频流
        audio_streams = [s for s in streams if s.get('codec_type') == 'audio']
        
        if not audio_streams:
            result.update({
                'format': format_info.get('format_name', 'unknown').split(',')[0],
                'codec': 'no_audio',
                'container': format_info.get('format_name', 'unknown'),
                'is_audio': False,
                'supported': False
            })
            return result
        
        # 使用第一个音频流的信息
        audio_stream = audio_streams[0]
        
        format_name = format_info.get('format_name', 'unknown')
        if ',' in format_name:
            # 取第一个格式名
            format_name = format_name.split(',')[0]
        
        result.update({
            'format': format_name,
            'codec': audio_stream.get('codec_name', 'unknown'),
            'container': format_info.get('format_name', 'unknown'),
            'is_audio': True
        })
        
        logger.debug(f"检测到音频格式: {result['format']}, 编解码器: {result['codec']}")
        return result
        
    except subprocess.TimeoutExpired:
        logger.error(f"音频格式检测超时: {file_path}")
        return {
            'format': 'unknown',
            'codec': 'unknown',
            'container': 'unknown', 
            'mime_type': 'unknown',
            'extension': Path(file_path).suffix.lower(),
            'is_audio': False,
            'supported': False,
            'error': 'Detection timeout'
        }
    except Exception as e:
        logger.error(f"音频格式检测失败: {e}")
        return {
            'format': 'unknown',
            'codec': 'unknown',
            'container': 'unknown',
            'mime_type': 'unknown', 
            'extension': Path(file_path).suffix.lower(),
            'is_audio': False,
            'supported': False,
            'error': str(e)
        }


def get_audio_info(file_path: str, ffmpeg_path: Optional[str] = None) -> dict:
    """获取音频文件信息
    
    Args:
        file_path: 音频文件路径
        ffmpeg_path: FFmpeg路径，如果为None则自动检测
        
    Returns:
        dict: 音频文件信息
    """
    logger = get_logger()
    
    try:
        if ffmpeg_path is None:
            ffmpeg_path = detect_ffmpeg()
        
        if not Path(file_path).exists():
            return {'error': 'File not found'}
        
        # 使用ffprobe获取音频信息
        # 智能构造ffprobe路径
        ffmpeg_path_obj = Path(ffmpeg_path)
        if ffmpeg_path_obj.name.startswith('ffmpeg'):
            ffprobe_name = ffmpeg_path_obj.name.replace('ffmpeg', 'ffprobe', 1)
            ffprobe_path = str(ffmpeg_path_obj.parent / ffprobe_name)
        else:
            # 如果不是标准的ffmpeg命名，尝试在同一目录下查找ffprobe
            ffprobe_path = str(ffmpeg_path_obj.parent / 'ffprobe.exe' if os.name == 'nt' else 'ffprobe')
        
        result = subprocess.run([
            ffprobe_path,
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            file_path
        ], capture_output=True, text=True, timeout=30, encoding='utf-8', errors='ignore')
        
        if result.returncode != 0 or not result.stdout.strip():
            return {'error': f'ffprobe failed: {result.stderr}'}
        
        import json
        try:
            info = json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError) as e:
            return {'error': f'JSON parsing failed: {e}'}
        
        # 提取音频流信息
        audio_streams = [s for s in info.get('streams', []) if s.get('codec_type') == 'audio']
        
        if not audio_streams:
            return {'error': 'No audio streams found'}
        
        stream = audio_streams[0]  # 使用第一个音频流
        format_info = info.get('format', {})
        
        return {
            'duration': float(format_info.get('duration', 0)),
            'size': int(format_info.get('size', 0)),
            'bitrate': int(format_info.get('bit_rate', 0)),
            'sample_rate': int(stream.get('sample_rate', 0)),
            'channels': int(stream.get('channels', 0)),
            'codec': stream.get('codec_name', 'unknown'),
            'format': format_info.get('format_name', 'unknown').split(',')[0]
        }
        
    except subprocess.TimeoutExpired:
        logger.error(f"获取音频信息超时: {file_path}")
        return {'error': 'Timeout while getting audio info'}
    except Exception as e:
        logger.error(f"获取音频信息失败: {e}")
        return {'error': str(e)}


class AudioConversionParams:
    """音频转换参数类"""
    
    def __init__(self,
                 output_format: str = DEFAULT_OUTPUT_FORMAT,
                 sample_rate: int = DEFAULT_SAMPLE_RATE,
                 channels: int = DEFAULT_CHANNELS,
                 bitrate: Optional[str] = None,
                 quality: Optional[str] = None):
        """
        Args:
            output_format: 输出格式（如'.opus'）
            sample_rate: 采样率
            channels: 声道数
            bitrate: 比特率（如'64k'）
            quality: 质量设置（如'medium'）
        """
        self.output_format = output_format
        self.sample_rate = sample_rate
        self.channels = channels
        self.bitrate = bitrate
        self.quality = quality
    
    def to_ffmpeg_args(self) -> list:
        """转换为FFmpeg参数
        
        Returns:
            list: FFmpeg命令行参数
        """
        args = []
        
        # 采样率
        args.extend(['-ar', str(self.sample_rate)])
        
        # 声道数
        args.extend(['-ac', str(self.channels)])
        
        # 比特率
        if self.bitrate:
            args.extend(['-b:a', self.bitrate])
        
        # 质量设置（针对不同格式）
        if self.quality:
            if self.output_format == '.opus':
                # Opus质量映射
                quality_map = {
                    'low': '32k',
                    'medium': '64k', 
                    'high': '128k'
                }
                if self.quality in quality_map:
                    args.extend(['-b:a', quality_map[self.quality]])
        
        return args
    
    def __str__(self) -> str:
        return f"AudioConversionParams(format={self.output_format}, sr={self.sample_rate}, ch={self.channels})"
    
class ConversionProgressMonitor:
    """音频转换进度监控器"""
    
    def __init__(self, total_duration: float = 0):
        self.total_duration = total_duration
        self.current_time = 0.0
        self.progress_percent = 0.0
        self.is_running = False
        self.start_time = 0
        self.callbacks = []
    
    def add_callback(self, callback: Callable[[dict], None]):
        """添加进度回调函数"""
        self.callbacks.append(callback)
    
    def update_progress(self, current_time: float):
        """更新进度"""
        self.current_time = current_time
        if self.total_duration > 0:
            self.progress_percent = min(100.0, (current_time / self.total_duration) * 100)
        
        # 调用所有回调函数
        progress_info = {
            'current_time': self.current_time,
            'total_duration': self.total_duration,
            'progress_percent': self.progress_percent,
            'elapsed_time': time.time() - self.start_time if self.start_time else 0
        }
        
        for callback in self.callbacks:
            try:
                callback(progress_info)
            except Exception as e:
                logger = get_logger()
                logger.debug(f"进度回调函数异常: {e}")
    
    def start(self):
        """开始监控"""
        self.is_running = True
        self.start_time = time.time()
    
    def stop(self):
        """停止监控"""
        self.is_running = False


def parse_ffmpeg_progress(line: str) -> Optional[float]:
    """解析FFmpeg进度输出
    
    Args:
        line: FFmpeg输出行
        
    Returns:
        Optional[float]: 当前处理时间（秒），如果解析失败返回none
    """
    try:
        # 查找 time= 字段
        if 'time=' in line:
            time_part = line.split('time=')[1].split()[0]
            # 解析时间格式 HH:MM:SS.ss
            time_parts = time_part.split(':')
            if len(time_parts) == 3:
                hours = float(time_parts[0])
                minutes = float(time_parts[1])
                seconds = float(time_parts[2])
                return hours * 3600 + minutes * 60 + seconds
    except (IndexError, ValueError, AttributeError):
        pass
    return None


def default_progress_callback(progress_info: dict):
    """默认进度显示回调函数"""
    percent = progress_info['progress_percent']
    current = progress_info['current_time']
    total = progress_info['total_duration']
    elapsed = progress_info['elapsed_time']
    
    # 简单的进度条
    bar_length = 30
    filled_length = int(bar_length * percent / 100)
    bar = '█' * filled_length + '-' * (bar_length - filled_length)
    
    print(f'\r转换进度: |{bar}| {percent:.1f}% ({current:.1f}s/{total:.1f}s) 耗时: {elapsed:.1f}s', end='', flush=True)


def _run_ffmpeg_with_progress(cmd: list, progress_monitor: ConversionProgressMonitor):
    """带进度监控的FFmpeg执行函数"""
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
            encoding='utf-8',
            errors='ignore'
        )
        
        # 读取stderr以获取进度信息
        stderr_output = []
        while True:
            line = process.stderr.readline()
            if not line and process.poll() is not None:
                break
            if line:
                stderr_output.append(line)
                # 解析进度信息
                current_time = parse_ffmpeg_progress(line)
                if current_time is not None:
                    progress_monitor.update_progress(current_time)
        
        # 等待进程结束
        stdout, _ = process.communicate()
        
        progress_monitor.stop()
        
        # 清理进度显示
        if progress_monitor.callbacks:
            print()  # 换行
        
        # 构造返回结果
        class MockResult:
            def __init__(self, returncode, stdout, stderr):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = ''.join(stderr)
        
        return MockResult(process.returncode, stdout, stderr_output)
        
    except Exception as e:
        progress_monitor.stop()
        raise e


def convert_audio_file(input_path: str, output_path: str, 
                       conversion_params: Optional[AudioConversionParams] = None,
                       ffmpeg_path: Optional[str] = None,
                       show_progress: bool = False,
                       progress_callback: Optional[Callable[[dict], None]] = None) -> dict:
    """转换单个音频文件
    
    Args:
        input_path: 输入音频文件路径
        output_path: 输出音频文件路径
        conversion_params: 转换参数，如果为None则使用默认参数
        ffmpeg_path: FFmpeg路径，如果为None则自动检测
        show_progress: 是否显示进度
        progress_callback: 进度回调函数
        
    Returns:
        dict: 转换结果，包含：
            - success: 是否成功
            - output_path: 输出文件路径
            - input_info: 输入文件信息
            - output_info: 输出文件信息
            - duration: 转换耗时（秒）
            - error: 错误信息（如果有）
    """
    logger = get_logger()
    
    try:
        from pathlib import Path
        import time
        
        input_path_obj = Path(input_path)
        output_path_obj = Path(output_path)
        
        # 检查输入文件是否存在
        if not input_path_obj.exists():
            error_analysis = {
                'error_type': 'file_not_found',
                'error_message': '输入文件不存在',
                'suggestions': ['检查文件路径是否正确'],
                'is_recoverable': True,
                'retry_recommended': False
            }
            return {
                'success': False,
                'output_path': str(output_path_obj),
                'input_info': None,
                'output_info': None,
                'duration': 0,
                'error': 'Input file not found',
                'error_analysis': error_analysis,
                'recovery_suggestion': create_recovery_suggestion(error_analysis, input_path, output_path)
            }
        
        # 检测输入文件格式
        input_format = detect_audio_format(input_path, ffmpeg_path)
        if not input_format['is_audio']:
            error_analysis = {
                'error_type': 'format_error',
                'error_message': '输入文件不是有效的音频文件',
                'suggestions': ['检查文件格式是否正确', '尝试使用其他音频文件'],
                'is_recoverable': True,
                'retry_recommended': False
            }
            return {
                'success': False,
                'output_path': str(output_path_obj),
                'input_info': input_format,
                'output_info': None,
                'duration': 0,
                'error': 'Input file is not a valid audio file',
                'error_analysis': error_analysis,
                'recovery_suggestion': create_recovery_suggestion(error_analysis, input_path, output_path)
            }
        
        # 获取输入文件信息
        input_info = get_audio_info(input_path, ffmpeg_path)
        
        # 检测FFmpeg
        if ffmpeg_path is None:
            ffmpeg_path = detect_ffmpeg()
        
        # 使用默认转换参数
        if conversion_params is None:
            conversion_params = AudioConversionParams()
        
        # 确保输出目录存在
        from ..utils.file_utils import ensure_parent_dir
        ensure_parent_dir(output_path_obj)
        
        # 创建进度监控器
        total_duration = input_info.get('duration', 0) if isinstance(input_info, dict) and 'duration' in input_info else 0
        progress_monitor = None
        
        if show_progress or progress_callback:
            progress_monitor = ConversionProgressMonitor(total_duration)
            
            if progress_callback:
                progress_monitor.add_callback(progress_callback)
            elif show_progress:
                progress_monitor.add_callback(default_progress_callback)
        
        # 构建转换命令
        start_time = time.time()
        
        cmd = [
            ffmpeg_path,
            '-i', str(input_path_obj),  # 输入文件
            '-y',  # 覆盖输出文件
        ]
        
        # 如果需要显示进度，添加进度输出参数
        if progress_monitor:
            cmd.extend(['-progress', 'pipe:2', '-v', 'info'])
        else:
            cmd.extend(['-v', 'warning'])  # 减少输出信息
        
        # 添加转换参数
        cmd.extend(conversion_params.to_ffmpeg_args())
        
        # 输出文件
        cmd.append(str(output_path_obj))
        
        logger.info(f"开始转换音频: {input_path} -> {output_path}")
        logger.debug(f"转换命令: {' '.join(cmd)}")
        
        # 执行转换
        if progress_monitor:
            progress_monitor.start()
            # 使用实时进度监控
            result = _run_ffmpeg_with_progress(cmd, progress_monitor)
        else:
            # 正常执行，不显示进度
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=300  # 5分钟超时
            )
        
        duration = time.time() - start_time
        
        if result.returncode != 0:
            # 分析错误并提供建议
            error_analysis = analyze_conversion_error(result.stderr, result.returncode)
            recovery_suggestion = create_recovery_suggestion(error_analysis, input_path, output_path)
            
            error_msg = f"FFmpeg conversion failed: {error_analysis['error_message']}\n{recovery_suggestion}"
            logger.error(error_msg)
            
            return {
                'success': False,
                'output_path': str(output_path_obj),
                'input_info': input_info,
                'output_info': None,
                'duration': duration,
                'error': error_msg,
                'error_analysis': error_analysis,
                'recovery_suggestion': recovery_suggestion
            }
        
        # 检查输出文件是否存在
        if not output_path_obj.exists():
            return {
                'success': False,
                'output_path': str(output_path_obj),
                'input_info': input_info,
                'output_info': None,
                'duration': duration,
                'error': 'Output file was not created'
            }
        
        # 获取输出文件信息
        output_info = get_audio_info(str(output_path_obj), ffmpeg_path)
        
        logger.info(f"音频转换成功，耗时: {duration:.2f}秒")
        
        return {
            'success': True,
            'output_path': str(output_path_obj),
            'input_info': input_info,
            'output_info': output_info,
            'duration': duration,
            'error': None,
            'error_analysis': None,
            'recovery_suggestion': None
        }
        
    except subprocess.TimeoutExpired:
        error_analysis = {
            'error_type': 'timeout_error',
            'error_message': '音频转换超时',
            'suggestions': ['增加超时时间', '检查输入文件大小'],
            'is_recoverable': True,
            'retry_recommended': True
        }
        error_msg = "Audio conversion timeout"
        logger.error(error_msg)
        return {
            'success': False,
            'output_path': output_path,
            'input_info': None,
            'output_info': None,
            'duration': 0,
            'error': error_msg,
            'error_analysis': error_analysis,
            'recovery_suggestion': create_recovery_suggestion(error_analysis, input_path, output_path)
        }
    except Exception as e:
        error_analysis = {
            'error_type': 'unknown',
            'error_message': f'音频转换失败: {str(e)}',
            'suggestions': ['检查输入文件和参数', '查看详细错误日志'],
            'is_recoverable': False,
            'retry_recommended': False
        }
        error_msg = f"Audio conversion failed: {e}"
        logger.error(error_msg)
        return {
            'success': False,
            'output_path': output_path,
            'input_info': None,
            'output_info': None,
            'duration': 0,
            'error': error_msg,
            'error_analysis': error_analysis,
            'recovery_suggestion': create_recovery_suggestion(error_analysis, input_path, output_path)
        }


def convert_to_opus(input_path: str, output_path: Optional[str] = None,
                    sample_rate: int = DEFAULT_SAMPLE_RATE,
                    channels: int = DEFAULT_CHANNELS,
                    bitrate: str = '64k',
                    ffmpeg_path: Optional[str] = None) -> dict:
    """转换音频文件为Opus格式（快捷函数）
    
    Args:
        input_path: 输入音频文件路径
        output_path: 输出文件路径，如果为None则自动生成
        sample_rate: 采样率
        channels: 声道数
        bitrate: 比特率
        ffmpeg_path: FFmpeg路径
        
    Returns:
        dict: 转换结果
    """
    from pathlib import Path
    
    if output_path is None:
        input_path_obj = Path(input_path)
        output_path = str(input_path_obj.with_suffix('.opus'))
    
    params = AudioConversionParams(
        output_format='.opus',
        sample_rate=sample_rate,
        channels=channels,
        bitrate=bitrate
    )
    
    return convert_audio_file(input_path, output_path, params, ffmpeg_path)


def batch_convert_audio(input_files: list, output_dir: str,
                       conversion_params: Optional[AudioConversionParams] = None,
                       ffmpeg_path: Optional[str] = None) -> dict:
    """批量转换音频文件
    
    Args:
        input_files: 输入文件列表
        output_dir: 输出目录
        conversion_params: 转换参数
        ffmpeg_path: FFmpeg路径
        
    Returns:
        dict: 批量转换结果
    """
    logger = get_logger()
    from pathlib import Path
    
    output_dir_obj = Path(output_dir)
    from ..utils.file_utils import ensure_dir
    ensure_dir(output_dir_obj)
    
    results = {
        'total': len(input_files),
        'success': 0,
        'failed': 0,
        'results': [],
        'errors': []
    }
    
    for input_file in input_files:
        input_path_obj = Path(input_file)
        
        # 生成输出文件名
        if conversion_params and conversion_params.output_format:
            output_filename = input_path_obj.stem + conversion_params.output_format
        else:
            output_filename = input_path_obj.stem + DEFAULT_OUTPUT_FORMAT
            
        output_path = output_dir_obj / output_filename
        
        # 转换单个文件
        result = convert_audio_file(str(input_path_obj), str(output_path), 
                                  conversion_params, ffmpeg_path)
        
        results['results'].append({
            'input': str(input_path_obj),
            'output': str(output_path),
            'result': result
        })
        
        if result['success']:
            results['success'] += 1
            logger.info(f"批量转换成功: {input_file}")
        else:
            results['failed'] += 1
            results['errors'].append({
                'file': input_file,
                'error': result['error']
            })
            logger.error(f"批量转换失败: {input_file} - {result['error']}")
    
    logger.info(f"批量转换完成: 成功 {results['success']}/失败 {results['failed']}/总计 {results['total']}")
    return results
