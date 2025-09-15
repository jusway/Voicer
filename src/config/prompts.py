"""
提示词模板模块

提供可配置的提示词模板，支持场景描述和前文的组装。
按照用户记忆中的规范：动态维护提示词内容，确保介绍情景+前文两部分总token数不超过9000。
"""

from typing import Dict, List, Optional, Union, Any
from dataclasses import dataclass, field
from datetime import datetime
import re

# 延迟导入防止循环导入
def get_logger():
    from ..utils.logger import logger
    return logger


@dataclass
class PromptTemplate:
    """提示词模板数据类"""
    name: str
    scenario: str
    keywords_prefix: str = "热词："
    context_prefix: str = "前文："
    separator: str = "\n\n"
    max_tokens: int = 9000
    priority_order: List[str] = field(default_factory=lambda: ["scenario", "keywords", "context"])
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'name': self.name,
            'scenario': self.scenario,
            'keywords_prefix': self.keywords_prefix,
            'context_prefix': self.context_prefix,
            'separator': self.separator,
            'max_tokens': self.max_tokens,
            'priority_order': self.priority_order.copy(),
            'metadata': self.metadata.copy(),
            'created_at': self.created_at.isoformat()
        }


class PromptTemplateError(Exception):
    """提示词模板错误"""
    pass


class PromptTemplateManager:
    """提示词模板管理器
    
    管理多个提示词模板，支持动态加载和切换。
    确保组装的提示词符合token限制要求。
    """
    
    def __init__(self):
        """初始化模板管理器"""
        self.logger = get_logger()
        self.templates: Dict[str, PromptTemplate] = {}
        self.current_template: Optional[str] = None
        
        # 初始化默认模板
        self._init_default_templates()
        
        self.logger.debug("提示词模板管理器已初始化")
    
    def _init_default_templates(self):
        """初始化默认模板"""
        # 通用语音识别模板
        general_template = PromptTemplate(
            name="general_asr",
            scenario="""你是一个专业的语音识别助手，需要将音频转换为准确的文字。
请注意以下要求：
1. 保持原始语义和语调
2. 正确识别专业术语和人名
3. 适当添加标点符号
4. 保持语言的自然流畅性""",
            keywords_prefix="重要词汇：",
            context_prefix="上下文参考：",
            separator="\n\n",
            max_tokens=9000,
            metadata={
                "description": "通用语音识别模板",
                "use_cases": ["会议记录", "访谈转录", "讲座记录"]
            }
        )
        
        # 会议记录专用模板
        meeting_template = PromptTemplate(
            name="meeting_asr",
            scenario="""你是一个专业的会议记录助手，需要将会议音频转换为准确的文字记录。
请特别注意：
1. 准确识别发言人的专业术语
2. 保持商务用语的正式性
3. 正确识别公司名称、产品名称等专有名词
4. 合理分段，便于阅读理解""",
            keywords_prefix="会议关键词：",
            context_prefix="会议背景：",
            separator="\n\n",
            max_tokens=9000,
            metadata={
                "description": "会议记录专用模板",
                "use_cases": ["商务会议", "技术讨论", "项目评审"]
            }
        )
        
        # 教育培训模板
        education_template = PromptTemplate(
            name="education_asr",
            scenario="""你是一个教育内容转录助手，需要将教学音频转换为学习材料。
请重点关注：
1. 准确识别学科专业术语
2. 保持教学内容的逻辑性
3. 正确识别重点强调的内容
4. 适当标注停顿和语气变化""",
            keywords_prefix="学科术语：",
            context_prefix="课程内容：",
            separator="\n\n",
            max_tokens=9000,
            metadata={
                "description": "教育培训专用模板",
                "use_cases": ["在线课程", "培训讲座", "学术演讲"]
            }
        )
        
        # 客服对话模板
        customer_service_template = PromptTemplate(
            name="customer_service_asr",
            scenario="""你是一个客服对话记录助手，需要准确转录客户服务对话。
请注意：
1. 区分客服和客户的对话
2. 准确识别产品名称和服务术语
3. 保持对话的完整性和连贯性
4. 注意情感色彩的表达""",
            keywords_prefix="服务关键词：",
            context_prefix="对话背景：",
            separator="\n\n",
            max_tokens=9000,
            metadata={
                "description": "客服对话专用模板", 
                "use_cases": ["电话客服", "在线咨询", "投诉处理"]
            }
        )
        
        # 注册默认模板
        self.templates = {
            "general_asr": general_template,
            "meeting_asr": meeting_template,
            "education_asr": education_template,
            "customer_service_asr": customer_service_template
        }
        
        # 设置默认模板
        self.current_template = "general_asr"
    
    def add_template(self, template: PromptTemplate) -> bool:
        """添加新模板
        
        Args:
            template: 提示词模板
            
        Returns:
            bool: 是否添加成功
        """
        try:
            if template.name in self.templates:
                self.logger.warning(f"模板 {template.name} 已存在，将被覆盖")
            
            self.templates[template.name] = template
            self.logger.info(f"添加模板: {template.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"添加模板失败: {e}")
            return False
    
    def get_template(self, name: str) -> Optional[PromptTemplate]:
        """获取指定模板
        
        Args:
            name: 模板名称
            
        Returns:
            Optional[PromptTemplate]: 模板对象，不存在时返回None
        """
        return self.templates.get(name)
    
    def list_templates(self) -> List[str]:
        """列出所有模板名称
        
        Returns:
            List[str]: 模板名称列表
        """
        return list(self.templates.keys())
    
    def set_current_template(self, name: str) -> bool:
        """设置当前使用的模板
        
        Args:
            name: 模板名称
            
        Returns:
            bool: 设置是否成功
        """
        if name not in self.templates:
            self.logger.error(f"模板 {name} 不存在")
            return False
        
        self.current_template = name
        self.logger.info(f"当前模板设置为: {name}")
        return True
    
    def get_current_template(self) -> Optional[PromptTemplate]:
        """获取当前模板
        
        Returns:
            Optional[PromptTemplate]: 当前模板对象
        """
        if self.current_template:
            return self.templates.get(self.current_template)
        return None
    
    def remove_template(self, name: str) -> bool:
        """删除指定模板
        
        Args:
            name: 模板名称
            
        Returns:
            bool: 删除是否成功
        """
        if name not in self.templates:
            return False
        
        # 不能删除当前正在使用的模板
        if name == self.current_template:
            self.logger.warning(f"不能删除当前使用的模板: {name}")
            return False
        
        del self.templates[name]
        self.logger.info(f"删除模板: {name}")
        return True
    
    def create_template_from_dict(self, data: Dict[str, Any]) -> PromptTemplate:
        """从字典创建模板
        
        Args:
            data: 模板数据字典
            
        Returns:
            PromptTemplate: 创建的模板对象
            
        Raises:
            PromptTemplateError: 创建失败时抛出
        """
        try:
            # 必需字段检查
            required_fields = ['name', 'scenario']
            for field in required_fields:
                if field not in data:
                    raise PromptTemplateError(f"缺少必需字段: {field}")
            
            # 创建模板
            template = PromptTemplate(
                name=data['name'],
                scenario=data['scenario'],
                keywords_prefix=data.get('keywords_prefix', '热词：'),
                context_prefix=data.get('context_prefix', '前文：'),
                separator=data.get('separator', '\n\n'),
                max_tokens=data.get('max_tokens', 9000),
                priority_order=data.get('priority_order', ['scenario', 'keywords', 'context']),
                metadata=data.get('metadata', {})
            )
            
            return template
            
        except Exception as e:
            raise PromptTemplateError(f"创建模板失败: {e}")
    
    def export_templates(self) -> Dict[str, Dict]:
        """导出所有模板
        
        Returns:
            Dict[str, Dict]: 模板数据字典
        """
        return {name: template.to_dict() for name, template in self.templates.items()}
    
    def import_templates(self, templates_data: Dict[str, Dict]) -> int:
        """导入模板数据
        
        Args:
            templates_data: 模板数据字典
            
        Returns:
            int: 成功导入的模板数量
        """
        success_count = 0
        
        for name, data in templates_data.items():
            try:
                template = self.create_template_from_dict(data)
                self.add_template(template)
                success_count += 1
            except Exception as e:
                self.logger.error(f"导入模板 {name} 失败: {e}")
        
        self.logger.info(f"成功导入 {success_count}/{len(templates_data)} 个模板")
        return success_count


class PromptBuilder:
    """提示词构建器
    
    根据模板和输入内容构建完整的提示词。
    """
    
    def __init__(self, template_manager: Optional[PromptTemplateManager] = None):
        """初始化构建器
        
        Args:
            template_manager: 模板管理器，如果为None则创建新的
        """
        self.template_manager = template_manager or PromptTemplateManager()
        self.logger = get_logger()
    
    def build_prompt(self, 
                    keywords: List[str] = None,
                    context: str = "",
                    template_name: Optional[str] = None,
                    custom_scenario: Optional[str] = None) -> str:
        """构建完整的提示词
        
        Args:
            keywords: 热词列表
            context: 上下文内容
            template_name: 指定使用的模板名称
            custom_scenario: 自定义场景描述（覆盖模板中的场景）
            
        Returns:
            str: 构建的完整提示词
            
        Raises:
            PromptTemplateError: 构建失败时抛出
        """
        try:
            # 获取模板
            if template_name:
                template = self.template_manager.get_template(template_name)
                if not template:
                    raise PromptTemplateError(f"模板 {template_name} 不存在")
            else:
                template = self.template_manager.get_current_template()
                if not template:
                    raise PromptTemplateError("没有可用的模板")
            
            # 准备各部分内容
            scenario = custom_scenario or template.scenario
            keywords = keywords or []
            context = context or ""
            
            # 构建各部分
            parts = []
            
            # 按优先级顺序组装
            for part_type in template.priority_order:
                if part_type == "scenario" and scenario:
                    parts.append(scenario.strip())
                elif part_type == "keywords" and keywords:
                    keywords_text = template.keywords_prefix + " " + ", ".join(keywords)
                    parts.append(keywords_text)
                elif part_type == "context" and context:
                    context_text = template.context_prefix + " " + context.strip()
                    parts.append(context_text)
            
            # 组装完整提示词
            full_prompt = template.separator.join(parts)
            
            self.logger.debug(f"构建提示词完成，长度: {len(full_prompt)} 字符")
            
            return full_prompt
            
        except Exception as e:
            self.logger.error(f"构建提示词失败: {e}")
            raise PromptTemplateError(f"构建提示词失败: {e}")
    
    def build_with_validation(self,
                             keywords: List[str] = None,
                             context: str = "",
                             template_name: Optional[str] = None,
                             custom_scenario: Optional[str] = None,
                             token_counter=None) -> Dict[str, Union[str, bool, int]]:
        """构建提示词并验证token长度
        
        Args:
            keywords: 热词列表
            context: 上下文内容
            template_name: 指定使用的模板名称
            custom_scenario: 自定义场景描述
            token_counter: Token计数器实例
            
        Returns:
            Dict: 构建结果和验证信息
        """
        try:
            # 构建提示词
            prompt = self.build_prompt(keywords, context, template_name, custom_scenario)
            
            # 获取模板进行验证
            if template_name:
                template = self.template_manager.get_template(template_name)
            else:
                template = self.template_manager.get_current_template()
            
            max_tokens = template.max_tokens if template else 9000
            
            # Token计数和验证
            if token_counter:
                token_count = token_counter.count_tokens(prompt)
                is_valid = token_count <= max_tokens
                excess_tokens = max(0, token_count - max_tokens)
            else:
                # 简单估算
                token_count = len(prompt) // 2  # 粗略估算
                is_valid = token_count <= max_tokens
                excess_tokens = max(0, token_count - max_tokens)
            
            return {
                'prompt': prompt,
                'is_valid': is_valid,
                'token_count': token_count,
                'max_tokens': max_tokens,
                'excess_tokens': excess_tokens,
                'template_used': template.name if template else None
            }
            
        except Exception as e:
            self.logger.error(f"构建和验证提示词失败: {e}")
            raise PromptTemplateError(f"构建和验证提示词失败: {e}")
    
    def preview_prompt_parts(self,
                            keywords: List[str] = None,
                            context: str = "",
                            template_name: Optional[str] = None,
                            custom_scenario: Optional[str] = None) -> Dict[str, str]:
        """预览提示词各部分内容
        
        Args:
            keywords: 热词列表
            context: 上下文内容
            template_name: 指定使用的模板名称
            custom_scenario: 自定义场景描述
            
        Returns:
            Dict[str, str]: 各部分内容预览
        """
        try:
            # 获取模板
            if template_name:
                template = self.template_manager.get_template(template_name)
                if not template:
                    raise PromptTemplateError(f"模板 {template_name} 不存在")
            else:
                template = self.template_manager.get_current_template()
                if not template:
                    raise PromptTemplateError("没有可用的模板")
            
            # 准备各部分内容
            scenario = custom_scenario or template.scenario
            context = context or ""

            # 构建预览
            preview = {
                'scenario': scenario,
                'context_raw': context,
                'context_formatted': template.context_prefix + " " + context if context else "",
                'separator': repr(template.separator),
                'template_name': template.name
            }
            
            return preview
            
        except Exception as e:
            self.logger.error(f"预览提示词失败: {e}")
            raise PromptTemplateError(f"预览提示词失败: {e}")


# 全局模板管理器实例
_global_template_manager = None

def get_template_manager() -> PromptTemplateManager:
    """获取全局模板管理器实例"""
    global _global_template_manager
    if _global_template_manager is None:
        _global_template_manager = PromptTemplateManager()
    return _global_template_manager


def get_prompt_builder() -> PromptBuilder:
    """获取提示词构建器实例"""
    return PromptBuilder(get_template_manager())


# 便捷函数
def build_asr_prompt(context: str = "", template_name: str = "general_asr") -> str:
    """便捷的ASR提示词构建函数

    Args:
        context: 上下文内容
        template_name: 模板名称

    Returns:
        str: 构建的提示词
    """
    builder = get_prompt_builder()
    return builder.build_prompt(context=context, template_name=template_name)