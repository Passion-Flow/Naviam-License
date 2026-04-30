# accounts 模块

## 职责

- 默认管理员（`Admin / admin@workerspace.ai / admin@workerspace.ai`）创建与首次登录强制改密。
- 用户名 / 邮箱 / Argon2id 密码、最小长度 12 位、CommonPassword 黑名单。
- TOTP 2FA + 备用恢复码。
- 登录限速（`django-ratelimit`）+ 登录锁定（`django-axes`）。
- 会话：服务端 Redis 后端、SameSite=Strict、HttpOnly、Secure。
- 强制改密：`must_change_pw` 为 true 时，所有非「auth.*」端点跳转改密。

## 不做

- 不做注册（厂商内部使用）。
- 第一版不做多角色 / SSO / SCIM。

## 上下游

- 上游：`security`（限速 / 头部 / 审计）。
- 下游：所有写操作要求登录 + 强制改密通过。

## 关键文件（阶段 2 实现）

- `models.py`：`User`（继承 AbstractBaseUser + PermissionsMixin），`LoginAttempt`。
- `serializers.py`：`LoginSerializer`、`TotpSerializer`、`ChangePasswordSerializer`、`MeSerializer`。
- `services.py`：`login`、`logout`、`change_password`、`setup_totp`、`confirm_totp`、`force_lockout`。
- `views.py`：基于 `APIView`，显式 `permission_classes`、`throttle_classes`。
- `permissions.py`：`MustHaveChangedPassword`。
- `middleware.py`：未改密强制跳转。

## 安全要求

- 不在响应里暴露用户是否存在；登录失败统一 `auth.invalid_credentials`。
- 锁定后不暴露剩余次数；显示「请稍后再试」。
- 所有登录与改密事件写入审计哈希链。
