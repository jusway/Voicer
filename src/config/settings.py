"""简化的系统配置模块

提供系统运行所需的核心配置参数。
"""

import os
import json
import tempfile
from pathlib import Path
from typing import Optional


class Settings:
    """简化的系统配置类"""

    def __init__(self):
        # API配置
        self.DASHSCOPE_API_KEY = ""
        self.ASR_MODEL = "qwen3-asr-flash"

        # ASR provider routing
        self.ASR_PROVIDER = "dashscope"  # or "siliconflow"
        self.SILICONFLOW_API_KEY = ""
        self.SILICONFLOW_BASE_URL = "https://api.siliconflow.cn"

        # 处理参数
        self.MAX_SEGMENT_DURATION = 180  # 3分钟
        self.MAX_SEGMENT_SIZE = 10 * 1024 * 1024  # 10MB
        self.MAX_CONTEXT_TOKENS = 9000

        # VAD参数
        self.VAD_THRESHOLD = 0.5
        self.MIN_SILENCE_DURATION = 0.5

        # ASR配置
        self.LANGUAGE = "zh"
        self.ENABLE_LID = False
        self.ENABLE_ITN = False

        # 路径配置
        self.PROJECT_ROOT = Path(__file__).parent.parent.parent
        self.DATA_DIR = self.PROJECT_ROOT / "data"
        self.INPUT_DIR = self.DATA_DIR / "input"
        self.OUTPUT_DIR = self.DATA_DIR / "output"
        # 使用系统临时目录作为运行期临时路径根
        self.TEMP_DIR = Path(tempfile.gettempdir()) / "qwen3_asr_api"
        self.CONVERTED_DIR = self.TEMP_DIR / "converted"
        self.COMBINED_DIR = self.TEMP_DIR / "combined"
        self.EXTERNAL_DIR = self.PROJECT_ROOT / "external"

        # 外部工具路径
        self.FFMPEG_PATH = ""
        self.SILERO_VAD_MODEL_PATH = ""

        # 设置默认路径
        self._set_default_paths()

        # 从环境变量和配置文件加载
        self._load_from_env()
        self._load_from_config()

    def _set_default_paths(self):
        """设置默认路径"""
        # FFmpeg路径
        if os.name == 'nt':  # Windows
            self.FFMPEG_PATH = str(self.EXTERNAL_DIR / "ffmpeg" / "ffmpeg.exe")
        else:  # Linux/Mac
            self.FFMPEG_PATH = "ffmpeg"

        # Silero VAD模型路径
        self.SILERO_VAD_MODEL_PATH = str(self.EXTERNAL_DIR / "silero_vad" / "silero_vad.onnx")

    def _load_from_env(self):
        """从环境变量加载配置"""
        # API Key优先从环境变量读取
        env_api_key = os.getenv("DASHSCOPE_API_KEY")
        if env_api_key:
            self.DASHSCOPE_API_KEY = env_api_key

        # 读取可选路径环境变量（如设置则覆盖默认值）
        env_ffmpeg = os.getenv("FFMPEG_PATH")
        if env_ffmpeg:
            self.FFMPEG_PATH = env_ffmpeg
        env_vad = os.getenv("VAD_MODEL_PATH")
        if env_vad:
            self.SILERO_VAD_MODEL_PATH = env_vad

    def _load_from_config(self):
        """从配置文件加载配置"""
        config_file = self.PROJECT_ROOT / "config.json"
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)

                # 更新配置
                for key, value in config_data.items():
                    if hasattr(self, key):
                        # 对于路径配置，保持Path对象类型
                        if key.endswith('_DIR') or key.endswith('_PATH'):
                            if isinstance(getattr(self, key), Path):
                                setattr(self, key, Path(value))
                            else:
                                setattr(self, key, value)
                        elif key == 'PROJECT_ROOT':
                            # PROJECT_ROOT必须保持为Path对象
                            setattr(self, key, Path(value))
                        else:
                            setattr(self, key, value)

            except (json.JSONDecodeError, FileNotFoundError) as e:
                print(f"加载配置文件失败: {e}")

    def ensure_directories(self):
        """确保必要的目录存在"""
        directories = [
            self.DATA_DIR,
            self.INPUT_DIR,
            self.OUTPUT_DIR,
            self.TEMP_DIR,
            self.CONVERTED_DIR,
            self.COMBINED_DIR
        ]

        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)

    def validate(self) -> bool:
        """验证配置是否有效

        Returns:
            配置是否有效
        """
        # 检查API Key
        if not self.DASHSCOPE_API_KEY:
            print("错误: DASHSCOPE_API_KEY 未配置")
            return False

        # 检查Silero VAD模型文件
        if not Path(self.SILERO_VAD_MODEL_PATH).exists():
            print(f"警告: Silero VAD模型文件不存在: {self.SILERO_VAD_MODEL_PATH}")

        return True

    def to_dict(self) -> dict:
        """转换为字典

        Returns:
            配置字典
        """
        return {
            'DASHSCOPE_API_KEY': self.DASHSCOPE_API_KEY,
            'SILICONFLOW_API_KEY': self.SILICONFLOW_API_KEY,
            'SILICONFLOW_BASE_URL': self.SILICONFLOW_BASE_URL,
            'ASR_PROVIDER': self.ASR_PROVIDER,
            'ASR_MODEL': self.ASR_MODEL,
            'MAX_SEGMENT_DURATION': self.MAX_SEGMENT_DURATION,
            'MAX_SEGMENT_SIZE': self.MAX_SEGMENT_SIZE,
            'MAX_CONTEXT_TOKENS': self.MAX_CONTEXT_TOKENS,
            'VAD_THRESHOLD': self.VAD_THRESHOLD,
            'MIN_SILENCE_DURATION': self.MIN_SILENCE_DURATION,
            'LANGUAGE': self.LANGUAGE,
            'ENABLE_LID': self.ENABLE_LID,
            'ENABLE_ITN': self.ENABLE_ITN,
            'PROJECT_ROOT': str(self.PROJECT_ROOT),
            'DATA_DIR': str(self.DATA_DIR),
            'OUTPUT_DIR': str(self.OUTPUT_DIR),
            'FFMPEG_PATH': self.FFMPEG_PATH,
            'SILERO_VAD_MODEL_PATH': self.SILERO_VAD_MODEL_PATH
        }

    def reload_from_file(self):
        """从配置文件重新加载配置"""
        self._load_from_config()


# 全局配置实例
settings = Settings()


def load_settings(config_file: Optional[str] = None) -> Settings:
    """加载配置的便捷函数

    Args:
        config_file: 配置文件路径

    Returns:
        配置实例
    """
    global settings

    if config_file:
        # 如果指定了配置文件，重新加载
        settings = Settings()
        if Path(config_file).exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)

                for key, value in config_data.items():
                    if hasattr(settings, key):
                        setattr(settings, key, value)

            except (json.JSONDecodeError, FileNotFoundError) as e:
                print(f"加载配置文件失败: {e}")

    return settings


def create_default_config(config_file: str) -> bool:
    """创建默认配置文件

    Args:
        config_file: 配置文件路径

    Returns:
        是否创建成功
    """
    try:
        default_config = {
            "DASHSCOPE_API_KEY": "",
            "ASR_MODEL": "qwen3-asr-flash",
            "MAX_SEGMENT_DURATION": 180,
            "MAX_SEGMENT_SIZE": 10485760,
            "MAX_CONTEXT_TOKENS": 9000,
            "VAD_THRESHOLD": 0.5,
            "MIN_SILENCE_DURATION": 0.5,
            "LANGUAGE": "zh",
            "ENABLE_LID": False,
            "ENABLE_ITN": False
        }

        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)

        print(f"默认配置文件已创建: {config_file}")
        return True

    except Exception as e:
        print(f"创建配置文件失败: {e}")
        return False