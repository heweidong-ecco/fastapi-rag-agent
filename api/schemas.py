"""
Pydantic 数据模型集中定义
所有请求体、响应体、路径参数、查询参数的模型在此管理。
"""
from typing import List, Optional
from pydantic import BaseModel, Field
# ==================== Pydantic模型 ====================
# ==================== 检索相关 ====================
class QuestionRequest(BaseModel):
    """RAG 检索请求，包含用户问题、检索模式、是否生成答案等参数，以及当前输入的这条的对话历史用于真停止按钮的调用使它（支持历史补偿）"""
    question: str = Field(..., description="用户问题")
    top_k: int = Field(3, ge=1, le=20)
    mode: str = Field("accurate", description="检索模式: fast, accurate, full")
    generate_answer: bool = Field(False, description="是否直接生成答案")
    strict_mode: bool = Field(False, description="严格模式（仅 generate_answer=True 时有效）")
    citations: bool = Field(False, description="是否在答案中标注引用来源")
    conversation_history: list[dict] = Field(
        default=[],
        description="之前的对话历史，格式为 [{'role': 'user'/'assistant', 'content': '...'}]"
    )
# ==================== 文档管理相关 ====================
class DocumentInsert(BaseModel):
    """单条文档插入请求"""
    content: str = Field(
        ...,
        description="要入库的文档文本内容",
        example="Python是一种广泛使用的编程语言，常用于数据分析和AI开发。"
    )
    source: str = Field(
        "manual",
        description="文档来源标识，用于分类筛选。例如 tech_docs, life_docs, culture_docs",
        example="tech_docs"
    )

class BatchDocumentInsert(BaseModel):
    """批量文档插入请求"""
    documents: List[DocumentInsert] = Field(
        description="要批量插入的文档列表",
        examples=[
            [
                {"content": "Python是一种广泛使用的编程语言，常用于数据分析和AI开发。", "source": "tech_docs"},
                {"content": "今天中午吃什么呢？这是一个让人纠结的哲学问题。", "source": "life_docs"},
                {"content": "FastAPI是一个高性能的Python Web框架，支持异步处理。", "source": "tech_docs"},
            ]
        ]
    )

    # 也可以在模型级别添加多个完整示例（会覆盖字段级示例）
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "documents": [
                        {"content": "Python是一种广泛使用的编程语言，常用于数据分析和AI开发。", "source": "tech_docs"},
                        {"content": "今天中午吃什么呢？这是一个让人纠结的哲学问题。", "source": "life_docs"},
                        {"content": "FastAPI是一个高性能的Python Web框架，支持异步处理。", "source": "tech_docs"},
                    ]
                }
            ]
        }
    }
# ==================== 认证与用户管理相关 ====================
#  access_token 和 refresh_token 登录和刷新接口
class LoginRequest(BaseModel):
    """JWT 登录请求"""
    user_name: str = Field(..., description="用户名", example="admin")
    password: str = Field(..., description="密码", example="admin123")

class RefreshRequest(BaseModel):
    """JWT Token 刷新请求"""
    refresh_token: str = Field(
        description="用于获取新访问令牌的刷新令牌,之前登录获取的 refresh_token",
        examples=["eyJhbGciOiJIUzI1NiIs..."]  # 示例令牌片段
    )
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
                }
            ]
        }
    }   

# 管理接口（仅供管理员使用，暂不加权限控制）：
class UserCreate(BaseModel):
    """管理员创建用户请求"""
    user_name: str = Field(
        ...,
        description="用户名，用于标识调用者，创建后不可修改",
        example="test_user",
        min_length=3,
        max_length=50
    )
    expire_days: int = Field(
        30,
        description="API Key 的有效天数，从创建时刻开始计算",
        ge=1,
        le=365,
        example=90
    )
