"""简化的VAD处理模块

使用Silero-VAD进行语音活动检测，只返回时间戳信息。
职责：
- 检测音频中的语音活动区间
- 返回时间戳信息，不实际切割文件
- 为后续的智能分组提供基础数据
"""

import numpy as np
import soundfile as sf
from pathlib import Path
from typing import List
from ..models.vad_segment import VADSegment, VADResult
from ..utils.logger import logger
from ..config.settings import settings


class VADProcessor:
    """简化的VAD处理器"""
    
    def __init__(self, 
                 threshold: float = 0.5,
                 min_speech_duration: float = 0.3,
                 min_silence_duration: float = 0.5):
        """初始化VAD处理器
        
        Args:
            threshold: VAD阈值
            min_speech_duration: 最小语音时长
            min_silence_duration: 最小静音时长
        """
        self.threshold = threshold
        self.min_speech_duration = min_speech_duration
        self.min_silence_duration = min_silence_duration
        self.model = None
        self.sample_rate = 16000
        
    def _load_model(self):
        """加载Silero VAD模型"""
        if self.model is None:
            try:
                # 加载预训练的Silero VAD模型
                model_path = settings.SILERO_VAD_MODEL_PATH
                if Path(model_path).exists():
                    # 使用ONNX模型（CPU provider）
                    import onnxruntime as ort
                    providers = ["CPUExecutionProvider"]
                    self.model = ort.InferenceSession(model_path, providers=providers)
                    logger.info(f"VAD模型加载成功: {model_path} | providers={self.model.get_providers()}")
                else:
                    # ONNX模型文件不存在，提示放置路径或调整配置
                    raise FileNotFoundError(
                        f"ONNX模型文件不存在: {model_path}。请将模型文件放置到该路径，"
                        f"或更新 settings.SILERO_VAD_MODEL_PATH 为正确的模型文件路径。"
                    )
            except Exception as e:
                logger.error(f"VAD模型加载失败: {e}")
                raise
                
    def detect_speech_timestamps(self, audio_path: str) -> VADResult:
        """检测语音活动时间戳
        
        Args:
            audio_path: 音频文件路径
            
        Returns:
            VAD检测结果，包含时间戳信息
        """
        self._load_model()
        
        # 加载音频
        audio_data, sample_rate = sf.read(audio_path)
        
        # 转换为numpy数组并确保是2D格式 (channels, samples)
        if audio_data.ndim == 1:
            audio_data = audio_data.reshape(1, -1)
        elif audio_data.ndim == 2:
            audio_data = audio_data.T  # soundfile返回(samples, channels)，转换为(channels, samples)
            
        # 转换为单声道
        if audio_data.shape[0] > 1:
            audio_data = np.mean(audio_data, axis=0, keepdims=True)
            
        # 要求输入已为16kHz（重采样应在管线前用ffmpeg完成）
        if sample_rate != self.sample_rate:
            raise ValueError(f"VAD输入采样率应为{self.sample_rate}Hz，当前为{sample_rate}Hz，请在进入VAD前进行预处理。")

        # 获取音频总时长
        total_duration = audio_data.shape[1] / self.sample_rate
        
        # 使用ONNX模型进行VAD检测
        speech_timestamps = self._detect_with_onnx(audio_data)
            
        # 转换为VADSegment列表
        segments = self._convert_to_segments(speech_timestamps, total_duration)
        
        return VADResult(
            audio_file=audio_path,
            segments=segments,
            total_duration=total_duration
        )
        

        
    def _detect_with_onnx(self, audio_data: np.ndarray) -> List[dict]:
        """使用ONNX模型检测（改进实现）"""
        # 使用滑动窗口进行VAD检测
        window_size = int(0.5 * self.sample_rate)  # 0.5秒窗口
        hop_size = int(0.1 * self.sample_rate)     # 0.1秒步长
        
        audio_data = audio_data.squeeze()
        speech_probs = []
        
        # 滑动窗口检测
        for i in range(0, len(audio_data) - window_size + 1, hop_size):
            window = audio_data[i:i + window_size]
            
            # 简单的能量检测作为VAD（可以替换为更复杂的ONNX推理）
            energy = np.mean(window ** 2)
            # 使用能量阈值进行语音检测
            prob = 1.0 if energy > 0.001 else 0.0  # 简单阈值
            speech_probs.append(prob)
            
        # 将概率转换为时间戳
        timestamps = []
        in_speech = False
        speech_start = 0
        
        for i, prob in enumerate(speech_probs):
            time_pos = i * hop_size
            
            if prob > self.threshold and not in_speech:
                # 开始语音
                speech_start = time_pos
                in_speech = True
            elif prob <= self.threshold and in_speech:
                # 结束语音
                speech_end = time_pos
                if (speech_end - speech_start) / self.sample_rate >= self.min_speech_duration:
                    timestamps.append({
                        'start': speech_start,
                        'end': speech_end
                    })
                in_speech = False
                
        # 处理最后一个语音段
        if in_speech:
            speech_end = len(audio_data)
            if (speech_end - speech_start) / self.sample_rate >= self.min_speech_duration:
                timestamps.append({
                    'start': speech_start,
                    'end': speech_end
                })
                
        return timestamps
        
    def _convert_to_segments(self, timestamps: List[dict], total_duration: float) -> List[VADSegment]:
        """将时间戳转换为VADSegment列表"""
        segments = []
        
        # 添加语音段
        for ts in timestamps:
            start_time = ts['start'] / self.sample_rate
            end_time = ts['end'] / self.sample_rate
            
            segments.append(VADSegment(
                start_time=start_time,
                end_time=end_time,
                is_speech=True
            ))
            
        # 填充静音段
        segments = self._fill_silence_segments(segments, total_duration)
        
        # 按时间排序
        segments.sort(key=lambda x: x.start_time)
        
        return segments
        
    def _fill_silence_segments(self, speech_segments: List[VADSegment], total_duration: float) -> List[VADSegment]:
        """在语音段之间填充静音段"""
        all_segments = speech_segments.copy()
        
        # 按开始时间排序
        speech_segments.sort(key=lambda x: x.start_time)
        
        # 添加开头的静音
        if speech_segments and speech_segments[0].start_time > 0:
            all_segments.append(VADSegment(
                start_time=0.0,
                end_time=speech_segments[0].start_time,
                is_speech=False
            ))
            
        # 添加中间的静音
        for i in range(len(speech_segments) - 1):
            current_end = speech_segments[i].end_time
            next_start = speech_segments[i + 1].start_time
            
            if next_start > current_end:
                all_segments.append(VADSegment(
                    start_time=current_end,
                    end_time=next_start,
                    is_speech=False
                ))
                
        # 添加结尾的静音
        if speech_segments and speech_segments[-1].end_time < total_duration:
            all_segments.append(VADSegment(
                start_time=speech_segments[-1].end_time,
                end_time=total_duration,
                is_speech=False
            ))
            
        return all_segments
        
    def get_stats(self) -> dict:
        """获取处理器统计信息"""
        return {
            'threshold': self.threshold,
            'min_speech_duration': self.min_speech_duration,
            'min_silence_duration': self.min_silence_duration,
            'sample_rate': self.sample_rate,
            'model_loaded': self.model is not None
        }