# products 模块

## 职责

- 产品定义：code、display_name、schema_version。
- 第一版仅一条 fixtures `code='default'`。
- 提供 schema_version 给 activations 用于 Cloud ID 协议版本协商。

## 不做

- 不做产品市场化 / 多版本管理 / 价目。

## 扩展

- 后续接入第二个产品：通过 `python manage.py loaddata` 或 Admin 添加；License 模块按 product_code 路由签发模板。
- 第二个产品的 Cloud ID 协议升级时，新增 schema_version 与 SDK 协商。
