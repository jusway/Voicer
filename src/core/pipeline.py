"""简化的主流程编排类

实现完整的ASR处理流水线：
1. 音频文件转换
2. VAD语音活动检测和分割
3. 音频片段组合
4. ASR识别调用
5. 结果收集和输出
"""

import os
from pathlib import Path
from typing import List, Optional
from ..utils.logger import logger
from ..config.settings import settings
from .audio_converter import AudioConverter
from .vad_processor import VADProcessor
from .segment_manager import SegmentManager
from .asr_client import ASRClient
from .context_manager import ContextManager


class PipelineError(Exception):
    """Pipeline处理错误"""
    pass


class Pipeline:
    """简化的主流程编排类"""

    def __init__(self,
                 output_dir: Optional[str] = None,
                 context_prompt: Optional[str] = None):
        """初始化Pipeline

        Args:
            output_dir: 输出目录
            context_prompt: 上下文提示词
        """
        self.output_dir = Path(output_dir) if output_dir else None
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)

        # 初始化核心组件
        self.audio_converter = AudioConverter()
        self.vad_processor = VADProcessor()
        self.segment_manager = SegmentManager()
        self.asr_client = ASRClient()
        self.context_manager = ContextManager()

        # 设置上下文
        if context_prompt:
            self.context_manager.set_scenario(context_prompt)

        logger.info("Pipeline初始化完成")

    def process_audio_file(self, input_path: str, output_name: Optional[str] = None,
                          progress_callback: Optional[callable] = None,
                          stop_event: Optional[object] = None) -> dict:
        """处理单个音频文件

        Args:
            input_path: 输入音频文件路径
            output_name: 输出文件名（不含扩展名）
            progress_callback: 进度回调函数
            stop_event: 停止事件对象

        Returns:
            处理结果字典

        Raises:
            PipelineError: 处理失败时抛出
        """
        def report_progress(step: str, current: int = 0, total: int = 100, percentage: float = None):
            """报告进度"""
            if progress_callback:
                if percentage is None:
                    percentage = (current / total * 100) if total > 0 else 0
                progress_callback(step, current, total, percentage)

        def check_stop():
            """检查是否需要停止"""
            if stop_event and hasattr(stop_event, 'is_set') and stop_event.is_set():
                raise PipelineError("用户取消处理")

        try:
            input_path = Path(input_path)
            if not input_path.exists():
                raise PipelineError(f"输入文件不存在: {input_path}")

            if not output_name:
                output_name = input_path.stem
            # 确定输出目录：未显式传入时，默认写到输入文件所在目录
            if self.output_dir is None:
                self.output_dir = input_path.parent
            self.output_dir.mkdir(parents=True, exist_ok=True)


            logger.info(f"开始处理音频文件: {input_path}")
            report_progress("开始处理音频文件...", 0, 100, 0)

            # 步骤1: 音频转换
            check_stop()
            logger.info("步骤1: 音频格式转换")
            report_progress("音频格式转换中...", 10, 100, 10)
            converted_path, remove_after = self._convert_audio(input_path)

            # 步骤2: VAD检测时间戳
            check_stop()
            logger.info("步骤2: VAD语音活动检测")
            report_progress("语音活动检测中...", 20, 100, 20)
            vad_result = self._detect_vad_timestamps(converted_path)

            if not vad_result.speech_segments:
                raise PipelineError("未检测到语音片段。请检查音频音量/静音，或在设置中调整VAD阈值。")

            logger.info(f"检测到 {len(vad_result.speech_segments)} 个语音时间段")

            # 步骤3: 智能分组和切割
            check_stop()
            logger.info("步骤3: 智能分组和音频切割")
            report_progress("智能分组和音频切割中...", 30, 100, 30)
            combined_segments = self.segment_manager.create_segments_from_vad(vad_result)

            logger.info(f"智能分组后共 {len(combined_segments)} 个片段")

            # 步骤4: ASR识别
            check_stop()
            logger.info("步骤4: 语音识别")
            report_progress("开始语音识别...", 40, 100, 40)
            recognition_results = self._recognize_segments(combined_segments, progress_callback=report_progress, stop_event=stop_event)

            # 步骤5: 结果输出
            check_stop()
            logger.info("步骤5: 结果输出")
            report_progress("保存识别结果...", 90, 100, 90)
            output_files = self._save_results(recognition_results, output_name)

            # 清理临时文件
            self._cleanup_temp_files(converted_path, combined_segments, remove_after)

            # 完成处理
            report_progress("处理完成", 100, 100, 100)

            # 合并成功识别的文本
            text_content = " ".join(r['text'] for r in recognition_results if r['success'])

            result = {
                'success': True,
                'input_file': str(input_path),
                'output_files': output_files,
                'text_content': text_content,
                'speech_segments_count': len(vad_result.speech_segments),
                'combined_segments_count': len(combined_segments),
                'total_text_length': sum(len(r['text']) for r in recognition_results if r['success']),
                'recognition_success_rate': sum(1 for r in recognition_results if r['success']) / len(recognition_results) if recognition_results else 0
            }

            logger.info(f"音频文件处理完成: {input_path}")
            return result

        except Exception as e:
            error_msg = f"处理音频文件失败: {str(e)}"
            logger.error(error_msg)
            raise PipelineError(error_msg)

    def _convert_audio(self, input_path: Path) -> tuple[str, bool]:
        """转换音频格式

        Args:
            input_path: 输入文件路径

        Returns:
            (转换后的文件路径, 是否为临时转换文件)
        """
        try:
            # 如果已经是opus格式，直接返回且不删除原文件
            if input_path.suffix.lower() == '.opus':
                return str(input_path), False

            # 转换为opus格式
            output_path = Path(settings.CONVERTED_DIR) / f"{input_path.stem}.opus"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            conversion_result = self.audio_converter.convert_to_opus(
                str(input_path),
                output_path=str(output_path)
            )

            # 从转换结果中提取输出路径
            if isinstance(conversion_result, dict) and conversion_result.get('success'):
                converted_path = conversion_result['output_path']
            else:
                raise PipelineError(f"音频转换失败: {conversion_result}")

            logger.debug(f"音频转换完成: {input_path} -> {converted_path}")
            return converted_path, True

        except Exception as e:
            raise PipelineError(f"音频转换失败: {str(e)}")

    def _detect_vad_timestamps(self, audio_path: str):
        """VAD时间戳检测

        Args:
            audio_path: 音频文件路径

        Returns:
            VAD检测结果
        """
        try:
            vad_result = self.vad_processor.detect_speech_timestamps(audio_path)

            logger.debug(f"VAD检测完成: {len(vad_result.speech_segments)} 个语音时间段, "
                        f"总语音时长: {vad_result.speech_duration:.1f}s")
            return vad_result

        except Exception as e:
            raise PipelineError(f"VAD检测失败: {str(e)}")

    def _recognize_segments(self, segments: List, progress_callback: Optional[callable] = None, stop_event: Optional[object] = None) -> List[dict]:
        """识别音频片段

        Args:
            segments: 音频片段列表
            progress_callback: 进度回调函数
            stop_event: 停止事件对象

        Returns:
            识别结果列表
        """
        results = []
        total_segments = len(segments)

        for i, segment in enumerate(segments, 1):
            # 检查停止事件
            if stop_event and hasattr(stop_event, 'is_set') and stop_event.is_set():
                raise PipelineError("用户取消处理")

            try:
                logger.debug(f"识别片段 {i}/{len(segments)}: {segment.id}")

                # 报告进度
                if progress_callback:
                    progress_percentage = 40 + (i / total_segments) * 50  # 40-90%的进度范围
                    progress_callback(f"识别片段 {i}/{total_segments}", i, total_segments, progress_percentage)

                # 构建上下文提示词
                context_prompt = self.context_manager.build_prompt()

                # 调用ASR识别
                result = self.asr_client.recognize(
                    audio_path=segment.file_path,
                    context_prompt=context_prompt
                )

                if result['success']:
                    # 添加识别结果到上下文历史
                    self.context_manager.add_context(result['text'])

                    logger.debug(f"片段 {i} 识别成功: {result['text'][:50]}...")
                else:
                    logger.warning(f"片段 {i} 识别失败: {result['error_message']}")

                # 添加片段信息
                result.update({
                    'segment_id': segment.id,
                    'segment_start_time': segment.start_time,
                    'segment_end_time': segment.end_time,
                    'segment_duration': segment.duration
                })

                results.append(result)

            except Exception as e:
                error_result = {
                    'success': False,
                    'error_message': f"处理片段异常: {str(e)}",
                    'segment_id': segment.id,
                    'segment_start_time': segment.start_time,
                    'segment_end_time': segment.end_time,
                    'segment_duration': segment.duration
                }
                results.append(error_result)
                logger.error(f"片段 {i} 处理异常: {str(e)}")

        return results

    def _save_results(self, results: List[dict], output_name: str) -> dict:
        """保存识别结果

        Args:
            results: 识别结果列表
            output_name: 输出文件名

        Returns:
            输出文件路径字典
        """
        output_files = {}

        try:
            # 合并所有成功的识别文本
            successful_results = [r for r in results if r['success']]
            full_text = " ".join(r['text'] for r in successful_results)

            # 保存纯文本文件
            txt_path = self.output_dir / f"{output_name}.txt"
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(full_text)
            output_files['text'] = str(txt_path)

            logger.info(f"结果保存完成: {len(output_files)} 个文件")
            return output_files

        except Exception as e:
            raise PipelineError(f"保存结果失败: {str(e)}")



    def _cleanup_temp_files(self, converted_path: str, combined_segments: List, remove_converted: bool) -> None:
        """清理临时文件

        Args:
            converted_path: 转换后的音频文件路径
            combined_segments: 组合后的片段列表
            remove_converted: 是否删除转换后的音频（仅当由本流程临时生成时为 True）
        """
        try:
            # 删除转换后的文件（仅当是临时文件时）
            if remove_converted and converted_path and os.path.exists(converted_path):
                os.remove(converted_path)

            # 删除组合后的片段文件
            for segment in combined_segments:
                if os.path.exists(segment.file_path):
                    os.remove(segment.file_path)

            logger.debug("临时文件清理完成")

        except Exception as e:
            logger.warning(f"清理临时文件失败: {str(e)}")

    def get_stats(self) -> dict:
        """获取Pipeline统计信息

        Returns:
            统计信息字典
        """
        return {
            'output_dir': str(self.output_dir),
            'audio_converter': self.audio_converter.get_stats() if hasattr(self.audio_converter, 'get_stats') else {},
            'vad_processor': self.vad_processor.get_stats() if hasattr(self.vad_processor, 'get_stats') else {},
            'segment_manager': self.segment_manager.get_stats(),
            'asr_client': self.asr_client.get_stats(),
            'context_manager': self.context_manager.get_stats()
        }


def create_pipeline(output_dir: Optional[str] = None,
                   context_prompt: Optional[str] = None) -> Pipeline:
    """创建Pipeline实例的便捷函数

    Args:
        output_dir: 输出目录
        context_prompt: 上下文提示词

    Returns:
        Pipeline实例
    """
    return Pipeline(
        output_dir=output_dir,
        context_prompt=context_prompt
    )


def process_audio_file(input_path: str,
                      output_dir: Optional[str] = None,
                      context_prompt: Optional[str] = None,
                      progress_callback: Optional[callable] = None,
                      stop_event: Optional[object] = None) -> dict:
    """处理单个音频文件的便捷函数

    Args:
        input_path: 输入音频文件路径
        output_dir: 输出目录
        context_prompt: 上下文提示词
        progress_callback: 进度回调函数
        stop_event: 停止事件对象

    Returns:
        处理结果字典
    """
    pipeline = create_pipeline(output_dir, context_prompt)
    return pipeline.process_audio_file(input_path, progress_callback=progress_callback, stop_event=stop_event)