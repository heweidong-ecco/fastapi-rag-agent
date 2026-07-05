"""
带引用溯源的答案生成模块
"""
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

CITATION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一个严谨的问答助手。请严格根据以下上下文回答用户的问题。

**引用规则（必须遵守）：**
1. 当你使用上下文中的某条信息时，必须在句末标注来源编号，格式为 `[来源:X]`，其中 X 是文档编号。
2. 如果一句话使用了多个来源，标注为 `[来源:X, Y]`。
3. 不要编造任何上下文以外的信息。如果上下文不足以回答问题，请直接说“根据现有资料，无法回答”。

**上下文文档：**
{context}

**用户问题：**
{question}

**回答（请严格遵循引用规则）：**
"""),
    ("user", "{question}")
])

def generate_answer_with_citations(contexts: list[dict], question: str, llm) -> tuple[str, list[dict]]:
    """
    生成带引用标注的答案，并返回来源信息列表。
    
    参数:
        contexts: 检索到的文档块列表，每个包含 id, content, source 等字段
        question: 用户问题
        llm: 语言模型实例
    
    返回:
        (带引用标注的答案文本, 来源信息列表)
    """
    # 构建带编号的上下文
    context_text_parts = []
    sources = []
    for i, doc in enumerate(contexts, start=1):
        context_text_parts.append(f"[文档{i}来源：{doc.get('source', '未知')}]\n{doc['content']}")
        sources.append({
            "id": doc.get("id"),
            "source": doc.get("source", "未知"),
            "content_preview": doc["content"][:100]
        })
    
    context_text = "\n\n".join(context_text_parts)
    
    # 调用 LLM 生成
    chain = CITATION_PROMPT | llm | StrOutputParser()
    answer = chain.invoke({
        "context": context_text,
        "question": question
    })
    
    return answer, sources