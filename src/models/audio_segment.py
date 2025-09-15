"""
音频片段数据模型

定义音频片段的数据结构，用于管理VAD分割后的音频片段信息。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import uuid


@dataclass
class AudioSegment:
    """音频片段数据类
    
    表示一个音频片段的完整信息，包括文件路径、时间信息、
    大小信息和处理状态等。
    """
    
    # 基本标识信息
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    file_path: str = ""
    
    # 时间信息（以秒为单位）
    start_time: float = 0.0
    end_time: float = 0.0
    duration: float = 0.0
    
    # 文件信息
    file_size: int = 0  # 字节
    
    # 语音活动信息
    is_speech: bool = True
    
    # 组合信息
    combined_group_id: Optional[str] = None
    
    def __post_init__(self):
        """初始化后处理，计算派生属性"""
        # 如果duration为0，尝试从start_time和end_time计算
        if self.duration == 0.0 and self.end_time > self.start_time:
            self.duration = self.end_time - self.start_time
        
        # 如果end_time为0，尝试从start_time和duration计算
        if self.end_time == 0.0 and self.duration > 0.0:
            self.end_time = self.start_time + self.duration
    
    @property
    def file_path_obj(self) -> Path:
        """获取文件路径对象
        
        Returns:
            Path: 文件路径对象
        """
        return Path(self.file_path) if self.file_path else Path()
    
    @property
    def exists(self) -> bool:
        """检查文件是否存在
        
        Returns:
            bool: 文件是否存在
        """
        return self.file_path_obj.exists() if self.file_path else False
    
    @property
    def file_name(self) -> str:
        """获取文件名
        
        Returns:
            str: 文件名（不包含路径）
        """
        return self.file_path_obj.name if self.file_path else ""
    
    @property
    def file_stem(self) -> str:
        """获取文件名（不包含扩展名）
        
        Returns:
            str: 文件名（不包含扩展名）
        """
        return self.file_path_obj.stem if self.file_path else ""
    
    @property
    def file_suffix(self) -> str:
        """获取文件扩展名
        
        Returns:
            str: 文件扩展名
        """
        return self.file_path_obj.suffix if self.file_path else ""
    
    @property
    def formatted_duration(self) -> str:
        """格式化显示时长
        
        Returns:
            str: 格式化的时长字符串 (MM:SS.SSS)
        """
        if self.duration <= 0:
            return "00:00.000"
        
        minutes = int(self.duration // 60)
        seconds = self.duration % 60
        return f"{minutes:02d}:{seconds:06.3f}"
    
    @property
    def formatted_time_range(self) -> str:
        """格式化显示时间范围
        
        Returns:
            str: 格式化的时间范围字符串
        """
        start_min = int(self.start_time // 60)
        start_sec = self.start_time % 60
        end_min = int(self.end_time // 60)
        end_sec = self.end_time % 60
        
        return f"{start_min:02d}:{start_sec:06.3f} - {end_min:02d}:{end_sec:06.3f}"
    
    @property
    def formatted_file_size(self) -> str:
        """格式化显示文件大小
        
        Returns:
            str: 格式化的文件大小字符串
        """
        if self.file_size <= 0:
            return "0 B"
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if self.file_size < 1024.0:
                return f"{self.file_size:.1f} {unit}"
            self.file_size /= 1024.0
        return f"{self.file_size:.1f} TB"
    
    def update_file_info(self) -> bool:
        """更新文件信息（大小等）
        
        Returns:
            bool: 更新成功返回True，失败返回False
        """
        try:
            if self.exists:
                self.file_size = self.file_path_obj.stat().st_size
                return True
            else:
                self.file_size = 0
                return False
        except Exception:
            self.file_size = 0
            return False
    
    def is_valid(self) -> bool:
        """检查音频片段是否有效
        
        Returns:
            bool: 片段有效返回True，无效返回False
        """
        # 检查基本属性
        if not self.id or not self.file_path:
            return False
        
        # 检查时间信息
        if self.start_time < 0 or self.end_time < 0 or self.duration < 0:
            return False
        
        if self.end_time > 0 and self.start_time >= self.end_time:
            return False
        
        # 检查文件大小
        if self.file_size < 0:
            return False
        
        return True
    
    def to_dict(self) -> dict:
        """转换为字典格式
        
        Returns:
            dict: 音频片段信息字典
        """
        return {
            'id': self.id,
            'file_path': self.file_path,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'duration': self.duration,
            'file_size': self.file_size,
            'is_speech': self.is_speech,
            'combined_group_id': self.combined_group_id,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'AudioSegment':
        """从字典创建音频片段实例
        
        Args:
            data: 包含音频片段信息的字典
            
        Returns:
            AudioSegment: 音频片段实例
        """
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            file_path=data.get('file_path', ''),
            start_time=data.get('start_time', 0.0),
            end_time=data.get('end_time', 0.0),
            duration=data.get('duration', 0.0),
            file_size=data.get('file_size', 0),
            is_speech=data.get('is_speech', True),
            combined_group_id=data.get('combined_group_id'),
        )
    
    def __str__(self) -> str:
        """字符串表示
        
        Returns:
            str: 音频片段的字符串描述
        """
        speech_type = "语音" if self.is_speech else "静音"
        return (f"AudioSegment(id={self.id[:8]}..., "
                f"file={self.file_name}, "
                f"duration={self.formatted_duration}, "
                f"size={self.formatted_file_size}, "
                f"type={speech_type})")
    
    def __repr__(self) -> str:
        """详细字符串表示
        
        Returns:
            str: 音频片段的详细字符串描述
        """
        return (f"AudioSegment(id='{self.id}', "
                f"file_path='{self.file_path}', "
                f"start_time={self.start_time}, "
                f"end_time={self.end_time}, "
                f"duration={self.duration}, "
                f"file_size={self.file_size}, "
                f"is_speech={self.is_speech}, "
                f"combined_group_id='{self.combined_group_id}')")