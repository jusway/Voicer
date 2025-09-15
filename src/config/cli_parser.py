"""命令行参数解析模块

提供命令行参数解析功能，支持所有系统配置参数的命令行输入。
"""

import argparse
from pathlib import Path
from typing import Optional, Dict, Any
from .settings import Settings


def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器
    
    Returns:
        argparse.ArgumentParser: 配置好的参数解析器
    """
    parser = argparse.ArgumentParser(
        description="Qwen3 ASR API - 语音识别系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python main.py input.wav                           # 基本用法
  python main.py input.wav -o output.txt            # 指定输出文件
  python main.py input.wav --language en            # 指定语言
  python main.py input.wav --config config.json     # 使用配置文件
        """
    )
    
    # 必需参数
    parser.add_argument(
        "input_file",
        type=str,
        help="输入音频文件路径"
    )
    
    # 输出配置
    parser.add_argument(
        "-o", "--output",
        type=str,
        help="输出文件路径（默认：与输入文件同目录、同名.txt）"
    )

    # API配置
    parser.add_argument(
        "--api-key",
        type=str,
        help="DashScope API密钥"
    )
    
    parser.add_argument(
        "--model",
        type=str,
        default="qwen3-asr-flash",
        help="ASR模型名称（默认：qwen3-asr-flash）"
    )
    
    # 语言和处理配置
    parser.add_argument(
        "--language",
        type=str,
        default="zh",
        choices=["zh", "en", "auto"],
        help="识别语言（默认：zh）"
    )
    
    parser.add_argument(
        "--enable-lid",
        action="store_true",
        help="启用自动语言检测"
    )
    
    parser.add_argument(
        "--enable-itn",
        action="store_true",
        help="启用逆文本规范化"
    )
    
    # 处理参数
    parser.add_argument(
        "--max-segment-duration",
        type=int,
        default=180,
        help="最大分段时长（秒，默认：180）"
    )
    
    parser.add_argument(
        "--max-segment-size",
        type=int,
        default=10485760,  # 10MB
        help="最大分段大小（字节，默认：10MB）"
    )
    
    parser.add_argument(
        "--max-context-tokens",
        type=int,
        default=9000,
        help="最大上下文token数（默认：9000）"
    )
    
    # VAD参数
    parser.add_argument(
        "--vad-threshold",
        type=float,
        default=0.5,
        help="VAD阈值（默认：0.5）"
    )
    
    parser.add_argument(
        "--min-silence-duration",
        type=float,
        default=0.5,
        help="最小静音时长（秒，默认：0.5）"
    )
    
    parser.add_argument(
        "--min-speech-duration",
        type=float,
        default=0.3,
        help="最小语音时长（秒，默认：0.3）"
    )
    
    # 路径配置
    parser.add_argument(
        "--ffmpeg-path",
        type=str,
        help="FFmpeg可执行文件路径"
    )
    
    parser.add_argument(
        "--silero-vad-path",
        type=str,
        help="Silero VAD模型文件路径"
    )
    
    # 配置文件
    parser.add_argument(
        "--config",
        type=str,
        help="配置文件路径"
    )
    
    # 调试选项
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="启用详细输出"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用调试模式"
    )
    
    return parser


def parse_args(args: Optional[list] = None) -> argparse.Namespace:
    """解析命令行参数
    
    Args:
        args: 命令行参数列表（用于测试，默认使用sys.argv）
        
    Returns:
        argparse.Namespace: 解析后的参数
    """
    parser = create_parser()
    return parser.parse_args(args)


def args_to_settings(args: argparse.Namespace) -> Settings:
    """将命令行参数转换为Settings对象
    
    Args:
        args: 解析后的命令行参数
        
    Returns:
        Settings: 配置对象
    """
    # 创建配置字典
    config_dict = {}
    
    # API配置
    if args.api_key:
        config_dict["DASHSCOPE_API_KEY"] = args.api_key
    if args.model:
        config_dict["ASR_MODEL"] = args.model
    
    # 路径配置
    if args.ffmpeg_path:
        config_dict["FFMPEG_PATH"] = args.ffmpeg_path
    if args.silero_vad_path:
        config_dict["SILERO_VAD_MODEL_PATH"] = args.silero_vad_path
    
    # 处理参数
    if args.max_segment_duration:
        config_dict["MAX_SEGMENT_DURATION"] = args.max_segment_duration
    if args.max_segment_size:
        config_dict["MAX_SEGMENT_SIZE"] = args.max_segment_size
    if args.max_context_tokens:
        config_dict["MAX_CONTEXT_TOKENS"] = args.max_context_tokens
    
    # VAD参数
    if args.vad_threshold is not None:
        config_dict["VAD_THRESHOLD"] = args.vad_threshold
    if args.min_silence_duration is not None:
        config_dict["MIN_SILENCE_DURATION"] = args.min_silence_duration
    if args.min_speech_duration is not None:
        config_dict["MIN_SPEECH_DURATION"] = args.min_speech_duration
    
    # ASR配置
    if args.language:
        config_dict["LANGUAGE"] = args.language
    if args.enable_lid:
        config_dict["ENABLE_LID"] = True
    if args.enable_itn:
        config_dict["ENABLE_ITN"] = True
    
    # 创建Settings对象
    settings = Settings()
    
    # 更新配置
    for key, value in config_dict.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
    
    return settings


def get_input_output_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    """获取输入和输出文件路径
    
    Args:
        args: 解析后的命令行参数
        
    Returns:
        tuple[Path, Path]: (输入文件路径, 输出文件路径)
    """
    input_path = Path(args.input_file)
    
    if args.output:
        output_path = Path(args.output)
    else:
        # 使用默认输出路径：与输入文件同目录、同名.txt
        output_path = input_path.with_suffix(".txt")

    return input_path, output_path