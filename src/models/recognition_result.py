"""
识别结果数据模型

定义语音识别结果的数据结构，用于存储ASR API返回的识别结果。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
import uuid


@dataclass
class RecognitionResult:
    """语音识别结果数据类
    
    表示一个音频片段的语音识别结果，包括识别文本、置信度、
    token使用情况等信息。
    """
    
    # 基本标识信息
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    segment_id: str = ""  # 对应的音频片段ID
    
    # 识别结果
    text: str = ""  # 识别出的文本内容
    confidence: float = 0.0  # 置信度 (0.0-1.0)
    
    # API相关信息
    tokens_used: int = 0  # 使用的token数量
    request_id: str = ""  # API请求ID
    
    # 时间信息
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 扩展信息
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """初始化后处理"""
        # 确保置信度在有效范围内
        if self.confidence < 0.0:
            self.confidence = 0.0
        elif self.confidence > 1.0:
            self.confidence = 1.0
        
        # 确保token数量为非负数
        if self.tokens_used < 0:
            self.tokens_used = 0
    
    @property
    def is_empty(self) -> bool:
        """检查识别结果是否为空
        
        Returns:
            bool: 如果没有识别出文本内容返回True
        """
        return not self.text or self.text.strip() == ""
    
    @property
    def text_length(self) -> int:
        """获取文本长度
        
        Returns:
            int: 文本字符数
        """
        return len(self.text) if self.text else 0
    
    @property
    def text_word_count(self) -> int:
        """获取文本词数（简单按空格分割）
        
        Returns:
            int: 词数
        """
        return len(self.text.split()) if self.text else 0
    
    @property
    def confidence_level(self) -> str:
        """获取置信度等级描述
        
        Returns:
            str: 置信度等级 (高/中/低)
        """
        if self.confidence >= 0.8:
            return "高"
        elif self.confidence >= 0.6:
            return "中"
        else:
            return "低"
    
    @property
    def formatted_timestamp(self) -> str:
        """格式化时间戳
        
        Returns:
            str: 格式化的时间字符串
        """
        return self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    
    @property
    def formatted_confidence(self) -> str:
        """格式化置信度
        
        Returns:
            str: 格式化的置信度字符串 (百分比)
        """
        return f"{self.confidence * 100:.1f}%"
    
    def clean_text(self) -> str:
        """清理文本内容
        
        Returns:
            str: 清理后的文本
        """
        if not self.text:
            return ""
        
        # 去除首尾空白字符
        cleaned = self.text.strip()
        
        # 去除多余的空格
        cleaned = " ".join(cleaned.split())
        
        return cleaned
    
    def get_text_preview(self, max_length: int = 50) -> str:
        """获取文本预览
        
        Args:
            max_length: 最大预览长度
            
        Returns:
            str: 文本预览（超长时截断并添加省略号）
        """
        cleaned_text = self.clean_text()
        if len(cleaned_text) <= max_length:
            return cleaned_text
        else:
            return cleaned_text[:max_length] + "..."
    
    def is_valid(self) -> bool:
        """检查识别结果是否有效
        
        Returns:
            bool: 结果有效返回True，无效返回False
        """
        # 检查基本字段
        if not self.id or not self.segment_id:
            return False
        
        # 检查置信度范围
        if self.confidence < 0.0 or self.confidence > 1.0:
            return False
        
        # 检查token数量
        if self.tokens_used < 0:
            return False
        
        # 如果有文本内容，不能为空字符串
        if self.text is not None and self.text == "":
            # 允许None，但不允许空字符串
            pass
        
        return True
    
    def add_metadata(self, key: str, value: Any) -> None:
        """添加元数据
        
        Args:
            key: 元数据键
            value: 元数据值
        """
        self.metadata[key] = value
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """获取元数据
        
        Args:
            key: 元数据键
            default: 默认值
            
        Returns:
            Any: 元数据值
        """
        return self.metadata.get(key, default)
    
    def to_dict(self) -> dict:
        """转换为字典格式
        
        Returns:
            dict: 识别结果信息字典
        """
        return {
            'id': self.id,
            'segment_id': self.segment_id,
            'text': self.text,
            'confidence': self.confidence,
            'tokens_used': self.tokens_used,
            'request_id': self.request_id,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'RecognitionResult':
        """从字典创建识别结果实例
        
        Args:
            data: 包含识别结果信息的字典
            
        Returns:
            RecognitionResult: 识别结果实例
        """
        # 处理时间戳
        timestamp_str = data.get('timestamp')
        if isinstance(timestamp_str, str):
            try:
                timestamp = datetime.fromisoformat(timestamp_str)
            except ValueError:
                timestamp = datetime.now()
        else:
            timestamp = timestamp_str if timestamp_str else datetime.now()
        
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            segment_id=data.get('segment_id', ''),
            text=data.get('text', ''),
            confidence=data.get('confidence', 0.0),
            tokens_used=data.get('tokens_used', 0),
            request_id=data.get('request_id', ''),
            timestamp=timestamp,
            metadata=data.get('metadata', {}),
        )
    
    @classmethod
    def from_api_response(cls, segment_id: str, api_response: dict) -> 'RecognitionResult':
        """从API响应创建识别结果实例
        
        Args:
            segment_id: 音频片段ID
            api_response: API响应数据
            
        Returns:
            RecognitionResult: 识别结果实例
        """
        # 解析API响应结构
        text = ""
        confidence = 0.0
        tokens_used = 0
        request_id = api_response.get('request_id', '')
        
        # 提取文本内容
        output = api_response.get('output', {})
        choices = output.get('choices', [])
        if choices:
            message = choices[0].get('message', {})
            content = message.get('content', [])
            if content:
                text = content[0].get('text', '')
        
        # 提取token使用信息
        usage = api_response.get('usage', {})
        if 'input_tokens_details' in usage:
            tokens_used = usage['input_tokens_details'].get('text_tokens', 0)
        
        # 创建实例
        result = cls(
            segment_id=segment_id,
            text=text,
            confidence=confidence,  # API通常不返回置信度，保持默认值
            tokens_used=tokens_used,
            request_id=request_id,
        )
        
        # 添加原始API响应到元数据
        result.add_metadata('api_response', api_response)
        
        return result
    
    def __str__(self) -> str:
        """字符串表示
        
        Returns:
            str: 识别结果的字符串描述
        """
        preview = self.get_text_preview(30)
        return (f"RecognitionResult(id={self.id[:8]}..., "
                f"segment={self.segment_id[:8]}..., "
                f"text='{preview}', "
                f"confidence={self.formatted_confidence}, "
                f"tokens={self.tokens_used})")
    
    def __repr__(self) -> str:
        """详细字符串表示
        
        Returns:
            str: 识别结果的详细字符串描述
        """
        return (f"RecognitionResult(id='{self.id}', "
                f"segment_id='{self.segment_id}', "
                f"text='{self.text}', "
                f"confidence={self.confidence}, "
                f"tokens_used={self.tokens_used}, "
                f"request_id='{self.request_id}', "
                f"timestamp={self.formatted_timestamp})")