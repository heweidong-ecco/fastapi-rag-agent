"""
搜索工具：基于阿里百炼搜索引擎
"""
import os
import json
from openai import OpenAI
from langchain_core.tools import tool
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_CHAT

# 初始化阿里百炼客户端
client = OpenAI(
    api_key=LLM_API_KEY,
    base_url=LLM_BASE_URL,
)


@tool
def web_search(query: str) -> str:
    """
    使用阿里百炼搜索引擎搜索互联网信息。
    适用于需要获取实时信息、新闻、资料等场景。
    输入是搜索关键词或问题。
    """
    try:
        # 调用阿里百炼的搜索API
        response = client.chat.completions.create(
            model=LLM_MODEL_CHAT,  # 使用支持的模型
            messages=[
                {
                    "role": "system",
                    "content": "你是一个搜索助手，请使用搜索功能获取实时信息。"
                },
                {
                    "role": "user",
                    "content": f"请搜索以下内容并给出详细结果：{query}"
                }
            ],
            # 注:enable_search 为阿里百炼私有扩展;切到 DeepSeek 等其它端点会被忽略,通常走下方兜底。
            extra_body={
                "enable_search": True,
                "search_options": {
                    "forced_search": True  # 强制进行搜索
                }
            },
            temperature=0.1,
        )

        # 提取搜索结果
        result = response.choices[0].message.content
        return result

    except Exception as e:
        # 如果搜索API失败，回退到简单的LLM回答
        try:
            fallback_response = client.chat.completions.create(
                model=LLM_MODEL_CHAT,
                messages=[
                    {"role": "user", "content": f"请根据你的知识回答以下问题：{query}"}
                ],
                temperature=0.1,
            )
            return f"（注：实时搜索不可用，以下为基于模型知识的回答）\n{fallback_response.choices[0].message.content}"
        except:
            return f"搜索失败: {str(e)}"