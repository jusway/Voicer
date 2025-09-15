"""简化的ASR API客户端

提供对Qwen3-ASR-Flash API的调用封装：
1. 单次音频识别
2. 简单的重试机制
3. 基本的错误处理
"""

import os
import time
from typing import Optional, Dict, Any
import dashscope
from ..config.settings import settings
from ..utils.logger import logger


class ASRClientError(Exception):
    """ASR客户端异常"""
    pass


class ASRClient:
    """简化的ASR API客户端"""
    
    def __init__(self, 
                 api_key: Optional[str] = None,
                 model: str = "qwen3-asr-flash",
                 max_retries: int = 3,
                 retry_delay: float = 1.0):
        """初始化ASR客户端
        
        Args:
            api_key: DashScope API密钥
            model: ASR模型名称
            max_retries: 最大重试次数
            retry_delay: 重试间隔（秒）
        """
        self.api_key = api_key or settings.DASHSCOPE_API_KEY
        self.model = model
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        if not self.api_key:
            raise ASRClientError("API密钥未配置")
            
        # 设置DashScope API密钥
        dashscope.api_key = self.api_key
        
        logger.info(f"ASR客户端初始化完成，模型: {self.model}")
        
    def recognize(self, 
                 audio_path: str, 
                 context_prompt: Optional[str] = None,
                 language: str = "zh") -> Dict[str, Any]:
        """识别音频文件
        
        Args:
            audio_path: 音频文件路径
            context_prompt: 上下文提示词
            language: 语言代码
            
        Returns:
            识别结果字典
            
        Raises:
            ASRClientError: 识别失败时抛出
        """
        # 验证音频文件
        self._validate_audio_file(audio_path)
        
        # 构建消息
        messages = self._build_messages(audio_path, context_prompt)
        
        # 仅在调试模式下打印API调用输入数据，避免终端过于啰嗦
        logger.debug("=== ASR API 调用输入数据 ===")
        logger.debug(f"模型: {self.model}")
        logger.debug(f"语言: {language}")
        logger.debug(f"音频文件: {audio_path}")
        try:
            import os
            logger.debug(f"文件大小: {os.path.getsize(audio_path)} 字节")
        except Exception:
            pass
        logger.debug(f"上下文提示: {context_prompt if context_prompt else '无'}")
        logger.debug(f"消息结构: {len(messages)} 条消息")
        for i, msg in enumerate(messages):
            logger.debug(f"  消息 {i+1}: role={msg['role']}, content_items={len(msg['content'])}")
            for j, content_item in enumerate(msg['content']):
                if 'text' in content_item:
                    t = content_item['text']
                    logger.debug(f"    内容 {j+1}: text='{t[:100]}{'...' if len(t) > 100 else ''}'")
                elif 'audio' in content_item:
                    logger.debug(f"    内容 {j+1}: audio='{content_item['audio']}'")
        logger.debug("=== 输入数据结束 ===")
        
        # 执行识别（带重试）
        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(f"开始识别音频: {audio_path} (尝试 {attempt + 1}/{self.max_retries + 1})")
                
                response = dashscope.MultiModalConversation.call(
                    model=self.model,
                    messages=messages,
                    language=language
                )
                
                # 解析响应
                result = self._parse_response(response)
                
                if result['success']:
                    logger.info(f"音频识别成功: {audio_path}")
                    return result
                else:
                    logger.warning(f"识别失败: {result['error_message']}")
                    if attempt < self.max_retries:
                        time.sleep(self.retry_delay)
                        continue
                    else:
                        raise ASRClientError(result['error_message'])
                        
            except Exception as e:
                error_msg = f"API调用失败: {str(e)}"
                logger.error(error_msg)
                
                if attempt < self.max_retries:
                    logger.info(f"等待 {self.retry_delay} 秒后重试...")
                    time.sleep(self.retry_delay)
                    continue
                else:
                    raise ASRClientError(error_msg)
                    
        raise ASRClientError("识别失败，已达到最大重试次数")
        
    def _validate_audio_file(self, audio_path: str) -> None:
        """验证音频文件
        
        Args:
            audio_path: 音频文件路径
            
        Raises:
            ASRClientError: 文件无效时抛出
        """
        if not os.path.exists(audio_path):
            raise ASRClientError(f"音频文件不存在: {audio_path}")
            
        if not os.path.isfile(audio_path):
            raise ASRClientError(f"路径不是文件: {audio_path}")
            
        # 检查文件大小（10MB限制）
        file_size = os.path.getsize(audio_path)
        max_size = 10 * 1024 * 1024  # 10MB
        if file_size > max_size:
            raise ASRClientError(f"文件大小超限: {file_size} > {max_size}")
            
    def _build_messages(self, audio_path: str, context_prompt: Optional[str] = None) -> list:
        """构建API请求消息
        
        Args:
            audio_path: 音频文件路径
            context_prompt: 上下文提示词
            
        Returns:
            消息列表
        """
        messages = []
        
        # 添加系统消息（上下文提示）
        if context_prompt:
            messages.append({
                "role": "system",
                "content": [{"text": context_prompt}]
            })
            
        # 添加用户消息（音频文件）
        messages.append({
            "role": "user",
            "content": [
                {"audio": f"file://{audio_path}"}
            ]
        })
        
        return messages
        
    def _parse_response(self, response) -> Dict[str, Any]:
        """解析API响应
        
        Args:
            response: API响应对象
            
        Returns:
            解析后的结果字典
        """
        try:
            # 检查响应状态
            if response.status_code != 200:
                return {
                    'success': False,
                    'error_message': f"API返回错误状态: {response.status_code}",
                    'raw_response': response
                }
                
            # 提取识别文本
            output = response.output
            if not output or 'choices' not in output:
                return {
                    'success': False,
                    'error_message': "响应格式错误：缺少choices字段",
                    'raw_response': response
                }
                
            choices = output['choices']
            if not choices:
                return {
                    'success': False,
                    'error_message': "响应格式错误：choices为空",
                    'raw_response': response
                }
                
            # 获取第一个选择的内容
            first_choice = choices[0]
            message = first_choice.get('message', {})
            content = message.get('content', [])
            
            if not content:
                return {
                    'success': False,
                    'error_message': "响应格式错误：content为空",
                    'raw_response': response
                }
                
            # 提取文本内容
            text_content = ""
            for item in content:
                if isinstance(item, dict) and 'text' in item:
                    text_content += item['text']
                    
            if not text_content.strip():
                return {
                    'success': False,
                    'error_message': "识别结果为空",
                    'raw_response': response
                }
                
            # 提取使用统计
            usage = response.usage or {}
            tokens_used = usage.get('output_tokens', 0)
            
            return {
                'success': True,
                'text': text_content.strip(),
                'request_id': response.request_id,
                'tokens_used': tokens_used,
                'raw_response': response
            }
            
        except Exception as e:
            return {
                'success': False,
                'error_message': f"解析响应失败: {str(e)}",
                'raw_response': response
            }
            
    def get_stats(self) -> dict:
        """获取客户端统计信息
        
        Returns:
            统计信息字典
        """
        return {
            'model': self.model,
            'max_retries': self.max_retries,
            'retry_delay': self.retry_delay,
            'api_key_configured': bool(self.api_key)
        }