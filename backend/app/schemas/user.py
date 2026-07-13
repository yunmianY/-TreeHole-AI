"""用户相关请求/响应 schema。"""

from pydantic import BaseModel, Field


class UserRegisterRequest(BaseModel):
    """注册请求。"""
    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=128, description="密码")


class UserLoginRequest(BaseModel):
    """登录请求。"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class TokenResponse(BaseModel):
    """登录成功返回的 token。"""
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """用户信息响应。"""
    id: str
    username: str
    created_at: str

    class Config:
        from_attributes = True
