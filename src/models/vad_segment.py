"""VAD时间段数据模型

定义VAD检测结果的时间段信息，不包含实际的音频文件。
"""

from dataclasses import dataclass
from typing import List


@dataclass
class VADSegment:
    """VAD检测的时间段
    
    只包含时间信息，不涉及实际的音频文件切割。
    """
    start_time: float  # 开始时间（秒）
    end_time: float    # 结束时间（秒）
    is_speech: bool    # 是否为语音段
    confidence: float = 1.0  # 置信度
    
    @property
    def duration(self) -> float:
        """时间段长度"""
        return self.end_time - self.start_time
    
    def __str__(self) -> str:
        segment_type = "语音" if self.is_speech else "静音"
        return f"VADSegment({self.start_time:.2f}s-{self.end_time:.2f}s, {segment_type}, {self.duration:.2f}s)"


@dataclass 
class VADResult:
    """VAD检测结果
    
    包含原始音频文件路径和所有检测到的时间段。
    """
    audio_file: str  # 原始音频文件路径
    segments: List[VADSegment]  # 检测到的时间段列表
    total_duration: float  # 音频总时长
    
    @property
    def speech_segments(self) -> List[VADSegment]:
        """获取所有语音段"""
        return [seg for seg in self.segments if seg.is_speech]
    
    @property
    def silence_segments(self) -> List[VADSegment]:
        """获取所有静音段"""
        return [seg for seg in self.segments if not seg.is_speech]
    
    @property
    def speech_duration(self) -> float:
        """总语音时长"""
        return sum(seg.duration for seg in self.speech_segments)
    
    @property
    def silence_duration(self) -> float:
        """总静音时长"""
        return sum(seg.duration for seg in self.silence_segments)
    
    def __str__(self) -> str:
        return f"VADResult({len(self.segments)} segments, {self.speech_duration:.1f}s speech, {self.silence_duration:.1f}s silence)"