"""
分块策略对比实验
比较不同 chunk_size 和 chunk_overlap 下的检索效果。
"""
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyMuPDFLoader
from db import search_similar
from embedding_client import get_embedding
import time

# 准备一份测试文档（用你的 test.pdf 或任意中文 PDF）
PDF_PATH = "test.pdf"

# 待对比的分块参数组合
CONFIGS = [
    {"chunk_size": 200, "chunk_overlap": 0},
    {"chunk_size": 200, "chunk_overlap": 50},
    {"chunk_size": 500, "chunk_overlap": 50},
    {"chunk_size": 500, "chunk_overlap": 100},
    {"chunk_size": 1000, "chunk_overlap": 100},
    {"chunk_size": 1000, "chunk_overlap": 200},
]

TEST_QUERIES = [
    "Python编程语言的特点",
    "FastAPI 的性能优势",
    "数据库连接池配置",
]

def run_experiment():
    # 加载文档
    loader = PyMuPDFLoader(PDF_PATH)
    pages = loader.load()
    full_text = "\n\n".join([p.page_content for p in pages])
    print(f"文档总长度: {len(full_text)} 字符\n")

    for config in CONFIGS:
        chunk_size = config["chunk_size"]
        chunk_overlap = config["chunk_overlap"]

        # 分割
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "，", " ", ""]
        )
        chunks = splitter.split_text(full_text)

        print(f"{'='*60}")
        print(f"chunk_size={chunk_size}, chunk_overlap={chunk_overlap}")
        print(f"生成块数: {len(chunks)}")
        print(f"平均块长度: {sum(len(c) for c in chunks) / len(chunks):.0f} 字符")



if __name__ == "__main__":
    run_experiment()