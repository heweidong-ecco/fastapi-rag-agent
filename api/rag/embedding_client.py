import os
import core.config as config
from dotenv import load_dotenv
from openai import OpenAI
from core.cache import get_cached_embedding, set_cached_embedding
from billing.token_tracker import record_usage  # 新增导入

load_dotenv()

# 🔴 批 6（`T1` · `DEC-082`）：客户端**惰性构造**，⛔ 不许在模块级建。
#   改前是模块级 `OpenAI(api_key=DASHSCOPE_API_KEY, ...)` —— 缺 key（`os.getenv` 无默认 ⇒ `None`）
#   时在 **import 期**就抛 SDK 那句通用 `OpenAIError`，**炸掉整条 import 链**
#   （`rag_pipeline` / `api_v1` / `hybrid_search` 全都起不来），
#   而那句话提的是 `OPENAI_API_KEY` —— 本仓根本不用那个名字。
#   ⚠️ CI 一直没照出来：`ci.yml` 塞了 dummy key（= 门挂在别处）。
_client = None


def _get_client() -> OpenAI:
    """惰性单例。缺 key ⇒ 抛**点名 `DASHSCOPE_API_KEY`** 的错（与 `config.validate_config` 同族）。

    ⚠️ `os.getenv(...) or config.…` 这个写法与 `llm_factory._resolve` **同源**：
    先看 env（调用时读得到，测试改得动），回落 `config`（默认值只有一处）。
    """
    global _client
    if _client is None:
        api_key = os.getenv("DASHSCOPE_API_KEY") or config.DASHSCOPE_API_KEY
        if not api_key:
            raise EnvironmentError(
                "DASHSCOPE_API_KEY 未设置 —— embedding 固定走阿里云百炼，缺它取不到向量。"
                "检查 .env 或环境变量（见 docs/契约/环境变量.md §4）。"
            )
        _client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    return _client


def get_embedding(text: str, model="text-embedding-v2") -> list:
    """带缓存的Embedding调用"""
    # 0. 🔴 先把客户端取到手（`DEC-082`）—— 缺 key 在这里就**响亮地断**，
    #    ⛔ 不要等拼到 API 调用那一步。⚠️ 这比改前多管一件事：**缓存命中时也要 key**
    #    （否则「同一句有时报错、有时不报」取决于缓存状态，比一律报错更难查）。
    client = _get_client()

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