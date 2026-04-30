# customers 模块

## 职责

- 客户档案 CRUD：display_name、legal_name、contact_*、region、notes。
- 软删除 + 审计写入。
- 与 License 一对多。

## 不做

- 不做客户自助（客户不直接登录 Console）。
- 不做合同 / 订阅 / 计费。

## 上下游

- 上游：accounts（仅超级管理员可写）。
- 下游：licenses 引用 customer_id；notifications 用 customer 的联系信息。
