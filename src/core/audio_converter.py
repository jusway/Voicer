"""
音频转换器模块

实现完整的AudioConverter类，封装音频转换功能。
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Callable
import threading
import time

# 延迟导入防止循环导入
def get_settings():
    from ..config.settings import settings
    return settings

def get_logger():
    from src.utils.logger import logger
    return logger


class AudioConverter:
    """音频转换器类
    
    封装音频转换功能，提供简单易用的接口。
    """
    
    def __init__(self, ffmpeg_path: Optional[str] = None):
        """初始化音频转换器
        
        Args:
            ffmpeg_path: FFmpeg可执行文件路径，如果为None则自动检测
        """
        self.ffmpeg_path = ffmpeg_path
        self.logger = get_logger()
        self._conversion_history = []
        self._is_converting = False
        self._current_conversion = None
        
    def _ensure_ffmpeg(self):
        """确保FFmpeg可用"""
        if self.ffmpeg_path is None:
            from src.utils.audio_utils import detect_ffmpeg
            self.ffmpeg_path = detect_ffmpeg()
        return self.ffmpeg_path
    
    def convert_file(self, input_path: str, output_path: str,
                    conversion_params: Optional['AudioConversionParams'] = None,
                    show_progress: bool = False,
                    progress_callback: Optional[Callable[[dict], None]] = None) -> dict:
        """转换单个音频文件
        
        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径
            conversion_params: 转换参数
            show_progress: 是否显示进度
            progress_callback: 进度回调函数
            
        Returns:
            dict: 转换结果
        """
        from src.utils.audio_utils import convert_audio_file, AudioConversionParams
        
        if conversion_params is None:
            conversion_params = AudioConversionParams()
        
        self._is_converting = True
        self._current_conversion = {
            'input_path': input_path,
            'output_path': output_path,
            'start_time': time.time()
        }
        
        try:
            result = convert_audio_file(
                input_path=input_path,
                output_path=output_path,
                conversion_params=conversion_params,
                ffmpeg_path=self._ensure_ffmpeg(),
                show_progress=show_progress,
                progress_callback=progress_callback
            )
            
            # 记录转换历史
            self._conversion_history.append({
                'input_path': input_path,
                'output_path': output_path,
                'success': result['success'],
                'duration': result.get('duration', 0),
                'timestamp': time.time(),
                'error': result.get('error')
            })
            
            return result
            
        finally:
            self._is_converting = False
            self._current_conversion = None
    
    def convert_to_opus(self, input_path: str, output_path: Optional[str] = None,
                       sample_rate: int = 16000, channels: int = 1,
                       bitrate: str = '64k', show_progress: bool = False) -> dict:
        """转换音频文件为Opus格式（快捷方法）
        
        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径，如果为None则自动生成
            sample_rate: 采样率
            channels: 声道数
            bitrate: 比特率
            show_progress: 是否显示进度
            
        Returns:
            dict: 转换结果
        """
        from src.utils.audio_utils import AudioConversionParams
        
        if output_path is None:
            input_path_obj = Path(input_path)
            output_path = str(input_path_obj.with_suffix('.opus'))
        
        params = AudioConversionParams(
            output_format='.opus',
            sample_rate=sample_rate,
            channels=channels,
            bitrate=bitrate
        )
        
        return self.convert_file(input_path, output_path, params, show_progress)
    
    def batch_convert(self, input_files: List[str], output_dir: str,
                     conversion_params: Optional['AudioConversionParams'] = None,
                     show_progress: bool = False,
                     progress_callback: Optional[Callable[[dict], None]] = None) -> dict:
        """批量转换音频文件
        
        Args:
            input_files: 输入文件列表
            output_dir: 输出目录
            conversion_params: 转换参数
            show_progress: 是否显示进度
            progress_callback: 进度回调函数
            
        Returns:
            dict: 批量转换结果
        """
        from src.utils.audio_utils import AudioConversionParams
        from src.utils.file_utils import ensure_dir
        
        if conversion_params is None:
            conversion_params = AudioConversionParams()
        
        output_dir_obj = Path(output_dir)
        ensure_dir(output_dir_obj)
        
        results = {
            'total': len(input_files),
            'success': 0,
            'failed': 0,
            'results': [],
            'errors': [],
            'start_time': time.time()
        }
        
        self.logger.info(f"开始批量转换 {len(input_files)} 个文件")
        
        for i, input_file in enumerate(input_files, 1):
            input_path_obj = Path(input_file)
            
            # 生成输出文件名
            output_filename = input_path_obj.stem + conversion_params.output_format
            output_path = output_dir_obj / output_filename
            
            self.logger.info(f"正在转换 ({i}/{len(input_files)}): {input_path_obj.name}")
            
            # 创建批量进度回调
            def batch_progress_callback(progress_info):
                batch_progress = {
                    'current_file': i,
                    'total_files': len(input_files),
                    'file_progress': progress_info,
                    'overall_progress': ((i - 1) + progress_info['progress_percent'] / 100) / len(input_files) * 100
                }
                if progress_callback:
                    progress_callback(batch_progress)
            
            # 转换单个文件
            result = self.convert_file(
                str(input_path_obj), 
                str(output_path),
                conversion_params,
                show_progress,
                batch_progress_callback if progress_callback else None
            )
            
            results['results'].append({
                'input': str(input_path_obj),
                'output': str(output_path),
                'result': result
            })
            
            if result['success']:
                results['success'] += 1
                self.logger.info(f"转换成功: {input_path_obj.name}")
            else:
                results['failed'] += 1
                results['errors'].append({
                    'file': input_file,
                    'error': result['error']
                })
                self.logger.error(f"转换失败: {input_path_obj.name} - {result['error']}")
        
        results['duration'] = time.time() - results['start_time']
        self.logger.info(f"批量转换完成: 成功 {results['success']}/失败 {results['failed']}/总计 {results['total']}, 耗时: {results['duration']:.2f}秒")
        
        return results
    
    def get_conversion_history(self) -> List[dict]:
        """获取转换历史记录
        
        Returns:
            List[dict]: 转换历史记录列表
        """
        return self._conversion_history.copy()
    
    def clear_history(self):
        """清空转换历史记录"""
        self._conversion_history.clear()
        self.logger.debug("转换历史记录已清空")
    
    def is_converting(self) -> bool:
        """检查是否正在转换
        
        Returns:
            bool: 是否正在转换
        """
        return self._is_converting
    
    def get_current_conversion(self) -> Optional[dict]:
        """获取当前转换信息
        
        Returns:
            Optional[dict]: 当前转换信息，如果没有正在进行的转换则返回None
        """
        if self._current_conversion:
            current = self._current_conversion.copy()
            current['elapsed_time'] = time.time() - current['start_time']
            return current
        return None
    
    def get_supported_formats(self) -> dict:
        """获取支持的音频格式
        
        Returns:
            dict: 支持的格式信息
        """
        from src.utils.audio_utils import SUPPORTED_INPUT_FORMATS, SUPPORTED_OUTPUT_FORMATS
        
        return {
            'input_formats': sorted(list(SUPPORTED_INPUT_FORMATS)),
            'output_formats': sorted(list(SUPPORTED_OUTPUT_FORMATS))
        }
    
    def validate_input_file(self, file_path: str) -> dict:
        """验证输入文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            dict: 验证结果
        """
        from src.utils.audio_utils import detect_audio_format, get_audio_info
        
        format_info = detect_audio_format(file_path, self.ffmpeg_path)
        
        if format_info['is_audio'] and not format_info.get('error'):
            audio_info = get_audio_info(file_path, self.ffmpeg_path)
            return {
                'valid': True,
                'format_info': format_info,
                'audio_info': audio_info,
                'recommendations': self._get_conversion_recommendations(audio_info)
            }
        else:
            return {
                'valid': False,
                'format_info': format_info,
                'audio_info': None,
                'recommendations': []
            }
    
    def _get_conversion_recommendations(self, audio_info: dict) -> List[str]:
        """根据音频信息提供转换建议
        
        Args:
            audio_info: 音频信息
            
        Returns:
            List[str]: 转换建议列表
        """
        recommendations = []
        
        if isinstance(audio_info, dict) and 'error' not in audio_info:
            # 根据文件大小建议
            size = audio_info.get('size', 0)
            if size > 50 * 1024 * 1024:  # 50MB
                recommendations.append("文件较大，建议使用较低的比特率以减少输出文件大小")
            
            # 根据采样率建议
            sample_rate = audio_info.get('sample_rate', 0)
            if sample_rate > 48000:
                recommendations.append("采样率较高，可以考虑降低到48kHz以减少文件大小")
            elif sample_rate < 16000:
                recommendations.append("采样率较低，可能影响音质")
            
            # 根据声道数建议
            channels = audio_info.get('channels', 0)
            if channels > 2:
                recommendations.append("多声道音频，考虑转换为立体声或单声道以减少文件大小")
            
            # 根据时长建议
            duration = audio_info.get('duration', 0)
            if duration > 3600:  # 1小时
                recommendations.append("音频时长较长，转换可能需要较长时间")
        
        return recommendations
    
    def get_conversion_stats(self) -> dict:
        """获取转换统计信息
        
        Returns:
            dict: 统计信息
        """
        if not self._conversion_history:
            return {
                'total_conversions': 0,
                'successful_conversions': 0,
                'failed_conversions': 0,
                'success_rate': 0.0,
                'total_duration': 0.0,
                'average_duration': 0.0
            }
        
        successful = sum(1 for h in self._conversion_history if h['success'])
        total_duration = sum(h['duration'] for h in self._conversion_history)
        
        return {
            'total_conversions': len(self._conversion_history),
            'successful_conversions': successful,
            'failed_conversions': len(self._conversion_history) - successful,
            'success_rate': successful / len(self._conversion_history) * 100,
            'total_duration': total_duration,
            'average_duration': total_duration / len(self._conversion_history)
        }
    
    def __str__(self) -> str:
        return f"AudioConverter(ffmpeg_path={self.ffmpeg_path}, history_count={len(self._conversion_history)})"
    
    def __repr__(self) -> str:
        return self.__str__()