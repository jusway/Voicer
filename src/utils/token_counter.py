"""
Token计数器模块

提供准确的Token计数功能，确保与API实际消耗一致。
支持多种计数方式和中文文本优化处理。
"""

import re
import unicodedata
from typing import Union, Dict, Optional, List
from pathlib import Path

# 延迟导入防止循环导入
def get_logger():
    from .logger import logger
    return logger


class TokenCountError(Exception):
    """Token计数错误"""
    pass


class TokenCounter:
    """Token计数器
    
    提供准确的Token计数功能，特别针对中文文本进行优化。
    支持多种计数策略以适应不同的API需求。
    """
    
    def __init__(self, method: str = 'qwen', debug: bool = False):
        """初始化Token计数器
        
        Args:
            method: 计数方法 ('qwen', 'openai', 'claude', 'simple')
            debug: 是否启用调试模式
        """
        self.method = method
        self.debug = debug
        self.logger = get_logger()
        
        # 初始化计数方法
        self._init_counting_method()
        
        # 缓存统计
        self._cache = {}
        self._stats = {
            'total_counts': 0,
            'cache_hits': 0,
            'method_used': method
        }
        
        if self.debug:
            self.logger.debug(f"初始化Token计数器: method={method}")
    
    def _init_counting_method(self):
        """初始化计数方法"""
        self.counting_methods = {
            'qwen': self._count_qwen_tokens,
            'openai': self._count_openai_tokens,
            'claude': self._count_claude_tokens,
            'simple': self._count_simple_tokens
        }
        
        if self.method not in self.counting_methods:
            raise TokenCountError(f"不支持的计数方法: {self.method}")
    
    def count_tokens(self, text: Union[str, List[str]], use_cache: bool = True) -> int:
        """计算文本的Token数量
        
        Args:
            text: 输入文本或文本列表
            use_cache: 是否使用缓存
            
        Returns:
            int: Token数量
            
        Raises:
            TokenCountError: 计数失败时抛出
        """
        try:
            # 处理输入
            if isinstance(text, list):
                text = '\n'.join(text)
            
            if not isinstance(text, str):
                raise TokenCountError(f"输入必须是字符串或字符串列表，得到: {type(text)}")
            
            # 检查缓存
            if use_cache and text in self._cache:
                self._stats['cache_hits'] += 1
                return self._cache[text]
            
            # 执行计数
            count_func = self.counting_methods[self.method]
            token_count = count_func(text)
            
            # 更新缓存和统计
            if use_cache:
                self._cache[text] = token_count
            self._stats['total_counts'] += 1
            
            if self.debug:
                self.logger.debug(f"Token计数: {len(text)} 字符 -> {token_count} tokens")
            
            return token_count
            
        except Exception as e:
            self.logger.error(f"Token计数失败: {e}")
            raise TokenCountError(f"Token计数失败: {e}")
    
    def _count_qwen_tokens(self, text: str) -> int:
        """千问模型的Token计数方法
        
        根据千问API的实际Token消耗规律进行计数。
        中文字符通常按1-2个token计算，英文按标准分词计算。
        """
        if not text:
            return 0
        
        # 统计不同类型的字符
        chinese_chars = 0
        english_words = 0
        numbers = 0
        punctuation = 0
        whitespace = 0
        other_chars = 0
        
        # 预处理：分离中英文和其他字符
        # 使用正则表达式分析文本
        chinese_pattern = re.compile(r'[\u4e00-\u9fff]')
        english_pattern = re.compile(r'[a-zA-Z]+')
        number_pattern = re.compile(r'\d+')
        punctuation_pattern = re.compile(r'[^\w\s\u4e00-\u9fff]')
        
        # 统计中文字符
        chinese_chars = len(chinese_pattern.findall(text))
        
        # 统计英文单词
        english_words = len(english_pattern.findall(text))
        
        # 统计数字序列
        numbers = len(number_pattern.findall(text))
        
        # 统计标点符号
        punctuation = len(punctuation_pattern.findall(text))
        
        # 统计空白字符
        whitespace = len(re.findall(r'\s', text))
        
        # 计算Token数量
        token_count = 0
        
        # 中文字符：平均1.3个token per字符
        token_count += int(chinese_chars * 1.3)
        
        # 英文单词：平均1.2个token per单词
        token_count += int(english_words * 1.2)
        
        # 数字：较短的数字序列约1个token，长数字可能更多
        token_count += max(numbers, int(sum(len(match.group()) for match in number_pattern.finditer(text)) * 0.7))
        
        # 标点符号：大部分是1个token
        token_count += punctuation
        
        # 空白字符通常不单独计算token，但会影响分词
        # 这里不额外计算
        
        # 添加基础token开销（特殊token等）
        if token_count > 0:
            token_count += 2  # 开始和结束token
        
        return max(1, token_count)  # 至少1个token
    
    def _count_openai_tokens(self, text: str) -> int:
        """OpenAI模型的Token计数方法"""
        if not text:
            return 0
        
        # OpenAI的近似计算：英文约4字符=1token，中文约1.5字符=1token
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        other_chars = len(text) - chinese_chars
        
        # 中文按1.5字符=1token计算
        chinese_tokens = int(chinese_chars / 1.5)
        
        # 其他字符按4字符=1token计算
        other_tokens = int(other_chars / 4)
        
        return max(1, chinese_tokens + other_tokens)
    
    def _count_claude_tokens(self, text: str) -> int:
        """Claude模型的Token计数方法"""
        if not text:
            return 0
        
        # Claude对中文的处理与OpenAI类似，但稍有不同
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        other_chars = len(text) - chinese_chars
        
        # 中文按1.2字符=1token计算
        chinese_tokens = int(chinese_chars / 1.2)
        
        # 其他字符按3.8字符=1token计算
        other_tokens = int(other_chars / 3.8)
        
        return max(1, chinese_tokens + other_tokens)
    
    def _count_simple_tokens(self, text: str) -> int:
        """简单的Token计数方法
        
        基于空格和标点符号的简单分词计数。
        """
        if not text:
            return 0
        
        # 简单分词：按空格和标点分割
        words = re.findall(r'\w+|[\u4e00-\u9fff]', text)
        return max(1, len(words))
    
    def count_multiple_texts(self, texts: List[str], use_cache: bool = True) -> List[int]:
        """批量计算多个文本的Token数量
        
        Args:
            texts: 文本列表
            use_cache: 是否使用缓存
            
        Returns:
            List[int]: 每个文本的Token数量列表
        """
        results = []
        for text in texts:
            count = self.count_tokens(text, use_cache)
            results.append(count)
        return results
    
    def estimate_cost(self, text: str, input_price_per_1k: float = 0.001, 
                     output_price_per_1k: float = 0.002) -> Dict[str, float]:
        """估算API调用成本
        
        Args:
            text: 输入文本
            input_price_per_1k: 每1000个输入token的价格
            output_price_per_1k: 每1000个输出token的价格（假设输出是输入的1/3）
            
        Returns:
            Dict[str, float]: 成本估算信息
        """
        input_tokens = self.count_tokens(text)
        estimated_output_tokens = int(input_tokens * 0.3)  # 假设输出是输入的30%
        
        input_cost = (input_tokens / 1000) * input_price_per_1k
        output_cost = (estimated_output_tokens / 1000) * output_price_per_1k
        total_cost = input_cost + output_cost
        
        return {
            'input_tokens': input_tokens,
            'estimated_output_tokens': estimated_output_tokens,
            'total_tokens': input_tokens + estimated_output_tokens,
            'input_cost': input_cost,
            'output_cost': output_cost,
            'total_cost': total_cost,
            'currency': 'USD'
        }
    
    def validate_length(self, text: str, max_tokens: int = 9000) -> Dict[str, Union[bool, int]]:
        """验证文本长度是否符合要求
        
        Args:
            text: 输入文本
            max_tokens: 最大允许的token数量
            
        Returns:
            Dict: 验证结果
        """
        token_count = self.count_tokens(text)
        is_valid = token_count <= max_tokens
        
        return {
            'is_valid': is_valid,
            'token_count': token_count,
            'max_tokens': max_tokens,
            'excess_tokens': max(0, token_count - max_tokens),
            'utilization_rate': (token_count / max_tokens * 100) if max_tokens > 0 else 0
        }
    
    def analyze_text_composition(self, text: str) -> Dict[str, int]:
        """分析文本组成
        
        Args:
            text: 输入文本
            
        Returns:
            Dict[str, int]: 文本组成分析
        """
        if not text:
            return {
                'total_chars': 0, 'chinese_chars': 0, 'english_chars': 0,
                'numbers': 0, 'punctuation': 0, 'whitespace': 0,
                'english_words': 0, 'estimated_tokens': 0
            }
        
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_chars = len(re.findall(r'[a-zA-Z]', text))
        numbers = len(re.findall(r'\d', text))
        punctuation = len(re.findall(r'[^\w\s\u4e00-\u9fff]', text))
        whitespace = len(re.findall(r'\s', text))
        english_words = len(re.findall(r'[a-zA-Z]+', text))
        
        estimated_tokens = self.count_tokens(text)
        
        return {
            'total_chars': len(text),
            'chinese_chars': chinese_chars,
            'english_chars': english_chars,
            'numbers': numbers,
            'punctuation': punctuation,
            'whitespace': whitespace,
            'english_words': english_words,
            'estimated_tokens': estimated_tokens
        }
    
    def get_statistics(self) -> Dict[str, Union[int, str, float]]:
        """获取计数器统计信息
        
        Returns:
            Dict: 统计信息
        """
        cache_hit_rate = (self._stats['cache_hits'] / self._stats['total_counts'] * 100) if self._stats['total_counts'] > 0 else 0
        
        return {
            'method_used': self._stats['method_used'],
            'total_counts': self._stats['total_counts'],
            'cache_hits': self._stats['cache_hits'],
            'cache_hit_rate': cache_hit_rate,
            'cache_size': len(self._cache),
            'debug_mode': self.debug
        }
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        self.logger.debug("Token计数器缓存已清空")
    
    def set_method(self, method: str):
        """更改计数方法
        
        Args:
            method: 新的计数方法
            
        Raises:
            TokenCountError: 不支持的方法时抛出
        """
        if method not in self.counting_methods:
            raise TokenCountError(f"不支持的计数方法: {method}")
        
        self.method = method
        self._stats['method_used'] = method
        self.clear_cache()  # 更改方法后清空缓存
        
        self.logger.debug(f"Token计数方法已更改为: {method}")


# 便捷函数
def count_tokens(text: Union[str, List[str]], method: str = 'qwen') -> int:
    """便捷的Token计数函数
    
    Args:
        text: 输入文本或文本列表
        method: 计数方法
        
    Returns:
        int: Token数量
    """
    counter = TokenCounter(method=method)
    return counter.count_tokens(text)


def estimate_tokens_needed(scenario: str, context: str,
                          method: str = 'qwen') -> Dict[str, int]:
    """估算组装提示词所需的Token数量

    Args:
        scenario: 场景描述
        context: 上下文
        method: 计数方法

    Returns:
        Dict[str, int]: 各部分的Token数量
    """
    counter = TokenCounter(method=method)

    scenario_tokens = counter.count_tokens(scenario)
    context_tokens = counter.count_tokens(context)
    total_tokens = scenario_tokens + context_tokens

    return {
        'scenario_tokens': scenario_tokens,
        'context_tokens': context_tokens,
        'total_tokens': total_tokens
    }


def validate_context_length(scenario: str, keywords: List[str], context: str,
                           max_tokens: int = 9000, method: str = 'qwen') -> Dict[str, Union[bool, int]]:
    """验证上下文总长度是否符合要求
    
    Args:
        scenario: 场景描述
        keywords: 热词列表
        context: 上下文
        max_tokens: 最大允许token数
        method: 计数方法
        
    Returns:
        Dict: 验证结果
    """
    token_info = estimate_tokens_needed(scenario, keywords, context, method)
    total_tokens = token_info['total_tokens']
    
    return {
        'is_valid': total_tokens <= max_tokens,
        'total_tokens': total_tokens,
        'max_tokens': max_tokens,
        'excess_tokens': max(0, total_tokens - max_tokens),
        'breakdown': token_info
    }