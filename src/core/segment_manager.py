"""优化的音频片段管理器

基于VAD时间戳进行智能分组和切割：
1. 接收VAD检测的时间戳信息
2. 按<3分钟规则智能分组
3. 只在最终需要时才切割音频文件
4. 避免重复的文件I/O操作
"""

from pathlib import Path
from typing import List, Optional
import os
import subprocess
from ..models.audio_segment import AudioSegment
from ..models.vad_segment import VADResult, VADSegment
from ..utils.logger import logger
from ..utils.audio_utils import calculate_audio_duration_from_file
from ..utils.file_utils import get_file_size


class SegmentManager:
    """优化的音频片段管理器"""
    
    def __init__(self, 
                 max_duration: float = 180.0,  # 3分钟
                 max_size: int = 10 * 1024 * 1024,  # 10MB
                 temp_dir: Optional[str] = None,
                 min_silence_duration: float = 0.5):
        """初始化片段管理器
        
        Args:
            max_duration: 最大片段时长（秒）
            max_size: 最大片段大小（字节）
            temp_dir: 临时目录路径
            min_silence_duration: 最小静音时长（秒）
        """
        self.max_duration = max_duration
        self.max_size = max_size
        self.min_silence_duration = min_silence_duration
        
        # 设置临时目录
        if temp_dir:
            self.temp_dir = Path(temp_dir)
        else:
            from ..config.settings import settings
            self.temp_dir = Path(settings.COMBINED_DIR)
            
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
    def create_segments_from_vad(self, vad_result: VADResult) -> List[AudioSegment]:
        """基于VAD结果创建智能分组的音频片段
        
        Args:
            vad_result: VAD检测结果
            
        Returns:
            组合后的音频片段列表
        """
        if not vad_result.speech_segments:
            logger.warning("未检测到语音片段")
            return []
            
        # 智能分组语音时间段，传递完整的VAD结果用于智能分割
        grouped_segments = self._group_speech_segments(vad_result.speech_segments, vad_result.segments)
        
        # 为每个组创建音频片段
        audio_segments = []
        for i, group in enumerate(grouped_segments):
            segment = self._create_segment_from_group(
                group, vad_result.audio_file, i
            )
            if segment:
                audio_segments.append(segment)
                
        logger.info(f"智能分组完成: {len(vad_result.speech_segments)} 个语音段 -> {len(audio_segments)} 个组合片段")
        return audio_segments
        
    def _group_speech_segments(self, speech_segments: List[VADSegment], all_segments: List[VADSegment] = None) -> List[List[VADSegment]]:
        """智能分组语音片段
        
        Args:
            speech_segments: 语音片段列表
            all_segments: 完整的VAD结果（包括静音段），用于智能分割
            
        Returns:
            分组后的语音片段列表
        """
        if not speech_segments:
            return []
            
        groups = []
        current_group = []
        current_duration = 0.0
        
        # 按时间排序
        sorted_segments = sorted(speech_segments, key=lambda x: x.start_time)
        
        for segment in sorted_segments:
            segment_duration = segment.duration
            
            # 如果单个片段超过最大时长，需要强制分割
            if segment_duration > self.max_duration:
                # 先保存当前组
                if current_group:
                    groups.append(current_group)
                    current_group = []
                
                # 将长片段分割成多个子片段，传递完整的VAD结果用于智能分割
                sub_segments = self._split_long_segment(segment, all_segments)
                for sub_segment in sub_segments:
                    groups.append([sub_segment])
                continue
            
            # 检查是否可以添加到当前组
            if current_group:
                # 计算如果添加这个片段，总时长是多少
                group_start = current_group[0].start_time
                group_end = segment.end_time
                total_duration = group_end - group_start
                
                if total_duration <= self.max_duration:
                    # 可以添加到当前组
                    current_group.append(segment)
                    current_duration = total_duration
                else:
                    # 需要开始新组
                    if current_group:
                        groups.append(current_group)
                    current_group = [segment]
                    current_duration = segment_duration
            else:
                # 第一个片段
                current_group = [segment]
                current_duration = segment_duration
                
        # 添加最后一组
        if current_group:
            groups.append(current_group)
            
        logger.debug(f"语音片段分组: {len(sorted_segments)} -> {len(groups)} 组")
        return groups
        
    def _split_long_segment(self, segment: VADSegment, all_segments: List[VADSegment] = None) -> List[VADSegment]:
        """将超长的语音片段分割成多个子片段
        
        Args:
            segment: 需要分割的语音片段
            all_segments: 所有VAD段（包括静音段），用于寻找合适的分割点
            
        Returns:
            分割后的子片段列表
        """
        from ..models.vad_segment import VADSegment
        
        # 如果没有提供完整的VAD结果，使用简单的时间分割
        if not all_segments:
            return self._simple_time_split(segment)
            
        # 寻找合适的静音点进行分割
        return self._smart_split_at_silence(segment, all_segments)
        
    def _simple_time_split(self, segment: VADSegment) -> List[VADSegment]:
        """简单的时间分割（备用方案）"""
        from ..models.vad_segment import VADSegment
        
        sub_segments = []
        current_start = segment.start_time
        
        while current_start < segment.end_time:
            current_end = min(current_start + self.max_duration, segment.end_time)
            
            sub_segment = VADSegment(
                start_time=current_start,
                end_time=current_end,
                is_speech=segment.is_speech,
                confidence=segment.confidence
            )
            
            sub_segments.append(sub_segment)
            current_start = current_end
            
        logger.debug(f"简单时间分割: {segment.duration:.2f}s -> {len(sub_segments)} 个子片段")
        return sub_segments
        
    def _smart_split_at_silence(self, segment: VADSegment, all_segments: List[VADSegment]) -> List[VADSegment]:
        """在静音处智能分割"""
        from ..models.vad_segment import VADSegment
        
        # 找到segment时间范围内的所有静音段
        silence_segments = [
            s for s in all_segments 
            if not s.is_speech and 
            s.start_time >= segment.start_time and 
            s.end_time <= segment.end_time and
            s.duration >= self.min_silence_duration  # 只考虑足够长的静音
        ]
        
        if not silence_segments:
            logger.debug(f"未找到合适的静音点，使用简单分割")
            return self._simple_time_split(segment)
            
        # 寻找最佳分割点
        sub_segments = []
        current_start = segment.start_time
        
        for silence in silence_segments:
            # 检查到这个静音点的时长是否接近max_duration
            potential_duration = silence.start_time - current_start
            
            if potential_duration >= self.max_duration * 0.8:  # 达到80%就考虑分割
                # 在静音的中点分割
                split_point = (silence.start_time + silence.end_time) / 2
                
                sub_segment = VADSegment(
                    start_time=current_start,
                    end_time=split_point,
                    is_speech=segment.is_speech,
                    confidence=segment.confidence
                )
                
                sub_segments.append(sub_segment)
                current_start = split_point
                
                # 如果剩余部分不长，直接结束
                if segment.end_time - current_start <= self.max_duration:
                    break
                    
        # 添加最后一段
        if current_start < segment.end_time:
            sub_segment = VADSegment(
                start_time=current_start,
                end_time=segment.end_time,
                is_speech=segment.is_speech,
                confidence=segment.confidence
            )
            sub_segments.append(sub_segment)
            
        logger.debug(f"智能静音分割: {segment.duration:.2f}s -> {len(sub_segments)} 个子片段")
        return sub_segments
        
    def _create_segment_from_group(self, 
                                  group: List[VADSegment], 
                                  original_audio_path: str, 
                                  group_index: int) -> Optional[AudioSegment]:
        """从分组创建音频片段
        
        Args:
            group: 语音片段组
            original_audio_path: 原始音频文件路径
            group_index: 组索引
            
        Returns:
            创建的音频片段，失败时返回None
        """
        if not group:
            return None
            
        # 计算组的时间范围
        start_time = group[0].start_time
        end_time = group[-1].end_time
        duration = end_time - start_time
        
        # 生成输出文件名
        original_path = Path(original_audio_path)
        output_filename = f"{original_path.stem}_segment_{group_index:03d}.opus"
        output_path = self.temp_dir / output_filename
        
        # 使用ffmpeg切割音频
        success = self._extract_audio_segment(
            original_audio_path, str(output_path), start_time, duration
        )
        
        if not success:
            logger.error(f"切割音频片段失败: {output_filename}")
            return None
            
        # 获取文件信息
        try:
            actual_duration = calculate_audio_duration_from_file(str(output_path))
            file_size = get_file_size(str(output_path))
            
            segment = AudioSegment(
                id=f"segment_{group_index:03d}",
                file_path=str(output_path),
                start_time=start_time,
                end_time=end_time,
                duration=actual_duration,
                file_size=file_size,
                is_speech=True,
                combined_group_id=f"group_{group_index}"
            )
            
            logger.debug(f"创建音频片段: {output_filename} ({duration:.2f}s, {file_size} bytes)")
            return segment
            
        except Exception as e:
            logger.error(f"获取片段信息失败: {e}")
            return None
            
    def _extract_audio_segment(self, 
                              input_path: str, 
                              output_path: str, 
                              start_time: float, 
                              duration: float) -> bool:
        """使用ffmpeg提取音频片段
        
        Args:
            input_path: 输入音频文件路径
            output_path: 输出音频文件路径
            start_time: 开始时间（秒）
            duration: 持续时间（秒）
            
        Returns:
            是否成功
        """
        try:
            # 优先使用检测到的 FFmpeg 路径（settings 覆盖 -> external/ffmpeg -> PATH）
            from ..utils.audio_utils import detect_ffmpeg, FFmpegError
            try:
                ffmpeg_path = detect_ffmpeg()
            except FFmpegError:
                # 兜底使用 settings（若设置了）或系统 PATH
                from ..config.settings import settings
                ffmpeg_path = settings.FFMPEG_PATH or "ffmpeg"

            cmd = [
                ffmpeg_path,
                '-i', input_path,
                '-ss', str(start_time),
                '-t', str(duration),
                '-c', 'copy',  # 复制编码，避免重新编码
                '-y',  # 覆盖输出文件
                output_path
            ]

            # 执行命令
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=300  # 5分钟超时
            )
            
            if result.returncode == 0:
                logger.debug(f"音频片段提取成功: {output_path}")
                return True
            else:
                logger.error(f"ffmpeg提取失败: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"提取音频片段异常: {e}")
            return False
            
    def validate_segment(self, segment: AudioSegment) -> bool:
        """验证片段是否符合要求
        
        Args:
            segment: 音频片段
            
        Returns:
            是否符合要求
        """
        # 检查文件是否存在
        if not os.path.exists(segment.file_path):
            logger.warning(f"片段文件不存在: {segment.file_path}")
            return False
            
        # 检查时长
        if segment.duration > self.max_duration:
            logger.warning(f"片段时长超限: {segment.duration}s > {self.max_duration}s")
            return False
            
        # 检查文件大小
        if segment.file_size > self.max_size:
            logger.warning(f"片段大小超限: {segment.file_size} > {self.max_size}")
            return False
            
        return True
        
    def cleanup_temp_files(self) -> int:
        """清理临时文件
        
        Returns:
            清理的文件数量
        """
        count = 0
        try:
            for file_path in self.temp_dir.glob("*"):
                if file_path.is_file():
                    file_path.unlink()
                    count += 1
                    
            logger.info(f"清理临时文件: {count} 个")
            return count
            
        except Exception as e:
            logger.error(f"清理临时文件失败: {e}")
            return count
            
    def get_stats(self) -> dict:
        """获取统计信息
        
        Returns:
            统计信息字典
        """
        temp_files = list(self.temp_dir.glob("*"))
        total_size = sum(f.stat().st_size for f in temp_files if f.is_file())
        
        return {
            'max_duration': self.max_duration,
            'max_size': self.max_size,
            'temp_dir': str(self.temp_dir),
            'temp_files_count': len(temp_files),
            'temp_files_size': total_size
        }