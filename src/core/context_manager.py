"""简化的上下文管理器

负责管理语音识别的上下文信息：
1. 场景描述管理
2. 前文上下文维护
3. Token计数和长度控制（确保<9000 tokens）
4. 提示词组装
"""

from typing import List, Optional
from ..utils.token_counter import count_tokens
from ..utils.logger import logger


class ContextManager:
    """简化的上下文管理器"""
    
    def __init__(self, max_tokens: int = 9000):
        """初始化上下文管理器
        
        Args:
            max_tokens: 最大token数限制
        """
        self.max_tokens = max_tokens
        self.scenario = ""
        self.context_history: List[str] = []
        
    def set_scenario(self, scenario: str) -> None:
        """设置场景描述
        
        Args:
            scenario: 场景描述文本
        """
        self.scenario = scenario.strip()
        logger.debug(f"设置场景描述: {self.scenario}")
        

        
    def add_context(self, text: str) -> None:
        """添加上下文历史
        
        Args:
            text: 识别结果文本
        """
        if text.strip():
            self.context_history.append(text.strip())
            # 保持合理的历史长度
            if len(self.context_history) > 10:
                self.context_history = self.context_history[-10:]
            logger.debug(f"添加上下文: {text[:50]}...")
            
    def build_prompt(self) -> str:
        """构建完整的提示词
        
        Returns:
            组装好的提示词字符串
        """
        parts = []
        
        # 添加用户提供的场景文本（不拼接固定前缀）
        if self.scenario:
            parts.append(self.scenario)

        # 添加前文上下文（不拼接固定前缀）
        if self.context_history:
            context_str = " ".join(self.context_history)
            parts.append(context_str)

        prompt = "\n".join(parts)

        # 检查并控制长度
        prompt = self._control_length(prompt)

        return prompt
        
    def _control_length(self, prompt: str) -> str:
        """控制提示词长度在限制范围内
        
        Args:
            prompt: 原始提示词
            
        Returns:
            长度控制后的提示词
        """
        token_count = count_tokens(prompt)
        
        if token_count <= self.max_tokens:
            return prompt
            
        logger.warning(f"提示词超长 ({token_count} > {self.max_tokens})，进行截断")
        
        # 简单的截断策略：优先保留场景和热词，截断上下文历史
        parts = []
        
        # 保留用户输入的场景文本
        if self.scenario:
            scenario_part = self.scenario
            parts.append(scenario_part)

        # 计算已用token数
        base_prompt = "\n".join(parts)
        base_tokens = count_tokens(base_prompt)

        # 为上下文历史分配剩余token
        remaining_tokens = self.max_tokens - base_tokens - 100  # 预留100个token

        if remaining_tokens > 0 and self.context_history:
            # 从最新的历史开始添加
            context_parts = []
            current_tokens = 0

            for text in reversed(self.context_history):
                text_tokens = count_tokens(text)
                if current_tokens + text_tokens <= remaining_tokens:
                    context_parts.insert(0, text)
                    current_tokens += text_tokens
                else:
                    break

            if context_parts:
                context_str = " ".join(context_parts)
                parts.append(context_str)

        return "\n".join(parts)
        
    def clear_context(self) -> None:
        """清空上下文历史"""
        self.context_history.clear()
        logger.debug("清空上下文历史")
        
    def get_stats(self) -> dict:
        """获取统计信息
        
        Returns:
            统计信息字典
        """
        prompt = self.build_prompt()
        return {
            'scenario_length': len(self.scenario),
            'context_history_count': len(self.context_history),
            'total_prompt_tokens': count_tokens(prompt),
            'max_tokens': self.max_tokens
        }