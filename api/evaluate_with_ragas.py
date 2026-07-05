"""
RAGAS 自动化评估脚本（基于 FastAPI 接口），含 context_precision）
"""
import json
import time
import httpx
import os
from dotenv import load_dotenv
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_recall,
    context_precision  # 新增：上下文精确率
)
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

load_dotenv()

# ==================== 配置 ====================
EVAL_DATASET_PATH = "eval_dataset.json"
API_BASE_URL = "http://localhost:8000/api/v1"
API_USERNAME = "admin"
API_PASSWORD = "admin123"
TOP_K = 3

# 用于生成答案和 RAGAS 评估的 LLM
eval_llm = ChatOpenAI(
    model="qwen-plus",
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    temperature=0
)

eval_embeddings = OpenAIEmbeddings(
    model="text-embedding-v2",
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

# 生成最终答案的简单链
answer_prompt = ChatPromptTemplate.from_messages([
    ("system", 
     "你是一个严格基于事实的问答助手。\n\n"
     "请按照以下规则回答：\n"
     "1. 首先判断提供的上下文是否与用户问题相关。\n"
     "2. 如果上下文完全不相关，直接回答：\"根据现有资料，无法回答此问题。\"\n"
     "3. 如果上下文部分相关，只基于相关部分回答，并忽略无关内容。\n"
     "4. 不要编造任何信息，不要引入你自己的知识。\n\n"
     "上下文：\n{context}"
    ),
    ("user", "{question}")
])
answer_chain = answer_prompt | eval_llm | StrOutputParser()


def get_auth_token():
    resp = httpx.post(f"{API_BASE_URL}/auth/login", json={
        "user_name": API_USERNAME,
        "password": API_PASSWORD
    })
    resp.raise_for_status()
    return resp.json()["access_token"]


def call_rag_api(question: str, token: str,max_retries: int = 3) -> dict:
    """调用 /rag/search 接口，获取检索文档，并自动生成答案，带重试、并返回检索结果、生成答案以及改写后的查询（如有）"""
    last_exception = None
    for attempt in range(max_retries):
        try:
            resp = httpx.post(
                f"{API_BASE_URL}/rag/search",
                headers={"Authorization": f"Bearer {token}"},
                json={"question": question, "top_k": TOP_K, "mode": "accurate"},
                timeout=120.0  # 增加到 2 分钟
            )
            resp.raise_for_status()
            data = resp.json()
            docs = data.get("docs", [])
            # 从检索结果中提取文本上下文
            contexts = [doc["content"] for doc in docs]

            # 使用 LLM 基于检索到的上下文生成答案
            answer = answer_chain.invoke({
                "context": "\n\n".join(contexts),
                "question": question
            })
            # 提取改写后的查询（如果存在）
            pipeline_info = data.get("pipeline", {})
            rewritten_query = pipeline_info.get("rewritten_query", question)
                        # --- 关键修改：如果检索不到任何文档，直接返回拒答，不调用 LLM ---
            if not contexts:
                return {
                    "answer": "根据现有资料，无法回答此问题。",
                    "contexts": [],
                    "rewritten_query": rewritten_query
                }

            # 生成答案（只在有文档时才调用 LLM）
            answer = answer_chain.invoke({
                "context": "\n\n".join(contexts),
                "question": question
            })

            # 成功返回后，主动休息一下，避免连续冲击
            time.sleep(1.5)
            return {
                "answer": answer,
                "contexts": contexts,
                "rewritten_query": rewritten_query
            }
        except (httpx.ReadError, httpx.RemoteProtocolError, httpx.ConnectError) as e:
            last_exception = e
            print(f"    ⚠️ 请求失败 (尝试 {attempt+1}/{max_retries}): {e}")
            time.sleep(2)  # 等待 2 秒后重试
        except Exception as e:
            # 其他异常直接抛出
            raise e

    # 所有重试都失败
    raise last_exception


def load_eval_dataset(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def prepare_ragas_dataset(eval_data, token):
    questions = []
    answers = []
    contexts_list = []
    ground_truths = []
    detailed_results = []  # 新增：存储每个问题的详细信息

    print(f"正在处理 {len(eval_data)} 个问题...")
    for i, item in enumerate(eval_data):
        question = item["question"]
        result = call_rag_api(question, token)
        questions.append(question)
        answers.append(result["answer"])
        contexts_list.append(result["contexts"])
        # 直接传入字符串，不再是列表
        ground_truths.append(item["answer"])

        # 保存详细结果，包含改写后的查询
        detailed_results.append({
            "question": question,
            "rewritten_query": result.get("rewritten_query", question),
            "expected_answer": item["answer"],  # 标准答案
            "actual_answer": result["answer"],  # 系统生成的答案
            "retrieved_docs": result["contexts"] # 检索到的文档列表
        })
        if (i + 1) % 10 == 0:
            print(f"  已完成 {i+1}/{len(eval_data)}")

    ragas_dataset = Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts_list,
        "ground_truth": ground_truths
    })
    return ragas_dataset, detailed_results  # 修改返回值

def main():
    print("=" * 60)
    print("RAGAS 自动化评估（基于 FastAPI）")
    print("=" * 60)

    # 1. 登录
    print("\n1. 登录获取 Token...")
    token = get_auth_token()
    print("   ✅ 登录成功")

    # 2. 加载数据
    print(f"\n2. 加载评估数据集: {EVAL_DATASET_PATH}")
    eval_data = load_eval_dataset(EVAL_DATASET_PATH)
    print(f"   共 {len(eval_data)} 个问答对")

    # 3. 运行 RAG 并构建数据集
    print("\n3. 通过 API 运行 RAG 并生成答案...")
    start = time.time()
    ragas_dataset, detailed_results = prepare_ragas_dataset(eval_data, token)
    elapsed = time.time() - start
    print(f"   完成，耗时 {elapsed:.1f}s")

    # 4. RAGAS 评估
    print("\n4. 运行 RAGAS 评估...")
    result = evaluate(
        ragas_dataset,
        metrics=[faithfulness, answer_relevancy, context_recall, context_precision],  # 新增 context_precision
        llm=eval_llm,
        embeddings=eval_embeddings,
    )

    # 5. 输出报告 
    print("\n" + "=" * 60)
    print("📊 评估报告")
    print("=" * 60)
    report = {"eval_size": len(eval_data)}
    for metric in ["faithfulness", "answer_relevancy", "context_recall", "context_precision"]:
        if metric in result:
            score = round(float(result[metric]), 4)
            report[metric] = score
            print(f"  • {metric}: {score:.4f}")

    report["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open("ragas_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 报告已保存至 ragas_report.json")
    # ===== 新增：保存详细对比数据 =====
    with open("ragas_detailed_report.json", "w", encoding="utf-8") as f:
        json.dump(detailed_results, f, ensure_ascii=False, indent=2)
    print("📋 详细对比报告已保存至 ragas_detailed_report.json")
if __name__ == "__main__":
    main()