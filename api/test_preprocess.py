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