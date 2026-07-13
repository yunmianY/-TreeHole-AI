"""用户认证业务逻辑。"""

from sqlalchemy.orm import Session

from app.models.user import User
from app.core.security import hash_password, verify_password, create_access_token


class AuthService:
    """用户注册与登录服务。"""

    @staticmethod
    def register(db: Session, username: str, password: str) -> tuple[User | None, str | None]:
        """注册新用户。

        Returns:
            (user, error_message): 成功时 (user, None)，失败时 (None, error)。
        """
        # 检查用户名唯一性
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            return None, f"用户名 '{username}' 已被注册"

        # 创建用户
        user = User(
            username=username,
            hashed_password=hash_password(password),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user, None

    @staticmethod
    def login(db: Session, username: str, password: str) -> tuple[str | None, str | None]:
        """用户登录，验证凭据并返回 JWT token。

        Returns:
            (token, error_message): 成功时 (token, None)，失败时 (None, error)。
        """
        user = db.query(User).filter(User.username == username).first()
        if not user:
            return None, "用户名或密码错误"

        if not verify_password(password, user.hashed_password):
            return None, "用户名或密码错误"

        token = create_access_token(data={"sub": user.id})
        return token, None

    @staticmethod
    def get_user_by_id(db: Session, user_id: str) -> User | None:
        """通过 ID 获取用户。"""
        return db.query(User).filter(User.id == user_id).first()
