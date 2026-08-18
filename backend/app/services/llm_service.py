"""LLM服务模块 (LangChain)"""

from langchain_openai import ChatOpenAI

from ..config import get_settings

# 全局LLM实例
_llm_instance = None


def get_llm() -> ChatOpenAI:
    """获取 LLM 实例(单例)。"""
    global _llm_instance

    if _llm_instance is None:
        settings = get_settings()
        _llm_instance = ChatOpenAI(
            model=settings.llm_model_id,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=settings.llm_temperature,
            timeout=60,
            max_retries=2,
        )
        print("✅ LLM服务初始化成功")
        print(f"   Base URL: {settings.llm_base_url}")
        print(f"   模型: {settings.llm_model_id}")

    return _llm_instance


def reset_llm():
    """重置LLM实例(用于测试或重新配置)"""
    global _llm_instance
    _llm_instance = None
