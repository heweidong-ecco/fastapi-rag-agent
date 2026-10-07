"""
手动脚本：跑一遍 `DocumentPreprocessor` 的清洗效果，肉眼比对输入输出。

⚠️ 2026-10-07：本文件原名 `test_preprocess.py`，但它 **不是 pytest 用例**
  （零个 `test_` 函数）—— 顶着 `test_` 前缀只会被 pytest 在收集阶段整个 import 执行一遍，
   把这几行 `print` 混进 pytest 输出。⇒ 去掉前缀。
   运行方式：`cd api && python preprocess.py`。
"""
from document_preprocessor import DocumentPreprocessor

preprocessor = DocumentPreprocessor()

# 包含噪声的测试文本
raw_text = """
联系我们：support@example.com 或者访问我们的官网 https://www.example.com/docs。
你也可以发送邮件到 admin@company.org。
这是正常的中文文本，需要保留。
"""

cleaned_text = preprocessor.process(raw_text)

print("=== 原始文本 ===")
print(raw_text)
print("\n=== 处理后文本 ===")
print(cleaned_text)