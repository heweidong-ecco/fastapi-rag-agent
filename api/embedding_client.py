import os
from dotenv import load_dotenv
from openai import OpenAI
from cache import get_cached_embedding, set_cached_embedding
from config import DASHSCOPE_API_KEY
from token_tracker import record_usage  # 新增导入

load_dotenv()

client = OpenAI(
    api_key=DASHSCOPE_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

def get_embedding(text: str, model="text-embedding-v2") -> list:
    """带缓存的Embedding调用"""
    # 1. 先查缓存
    cached = get_cached_embedding(text)
    if cached:
        return cached
    
    # 2. 缓存未命中，调用API
    text = text.replace("\n", " ")
    response = client.embeddings.create(input=[text], model=model)
    embedding = response.data[0].embedding
    
    # 3. 记录Token消耗和成本
    if hasattr(response, 'usage'):
        usage = response.usage
        # Embedding 调用没有 completion tokens，全部是 prompt tokens
        record_usage(
            model=model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=0,
            purpose="embedding",
            user_name="system",   # 系统级调用，可后续改为动态获取当前用户
            thread_id="system"
        )

    # 4. 存入缓存
    set_cached_embedding(text, embedding)
    
    return embedding

if __name__ == "__main__":
    vec = get_embedding("人工智能正在改变世界")
    print(f"向量维度: {len(vec)}")
    print(f"前10个值: {vec[:10]}")