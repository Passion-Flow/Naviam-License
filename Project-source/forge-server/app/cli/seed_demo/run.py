"""seed_demo —— 一键写入示例 customer / product / api-key 数据。

只做创建；幂等（slug 冲突 → 跳过该条不报错）。**不**创建 license（避免误用
demo 私钥；客户自己在 admin UI 走完整 issue 流程）。

调用：
  python -m app.cli.seed_demo            # 写默认两套示例
  python -m app.cli.seed_demo --json     # 机器可读输出
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from typing import Any

from app.adapters.database import get_database
from app.adapters.database.interface.protocol import Database
from app.repositories.api_keys import ApiKeyRepository
from app.repositories.customers import CustomerRepository, CustomerSlugConflict
from app.repositories.products import ProductRepository, ProductSlugConflict

DEMO_CUSTOMERS = [
    {
        "slug": "acme-corp",
        "name": "Acme Corporation",
        "contact_email": "ops@acme.example",
        "contact_name": "Wile E. Coyote",
        "region": "us-east-1",
        "notes": "demo customer; replace before going to production",
    },
    {
        "slug": "globex-cn",
        "name": "Globex 中国",
        "contact_email": "support@globex.example.cn",
        "contact_name": "张三",
        "region": "cn-shanghai",
        "notes": "demo customer",
    },
]

DEMO_PRODUCTS = [
    {
        "slug": "myapp-pro",
        "name": "MyApp Pro",
        "description": "Pro tier with SSO + audit",
        "version": "2.x",
        "features_schema": {"sso": "bool", "audit": "bool", "seats": "int"},
        "default_limits": {"seats": 50},
    },
    {
        "slug": "myapp-enterprise",
        "name": "MyApp Enterprise",
        "description": "Enterprise tier with full SLA",
        "version": "2.x",
        "features_schema": {"sso": "bool", "audit": "bool", "ha": "bool", "seats": "int"},
        "default_limits": {"seats": 5000},
    },
]


@dataclass
class SeedResult:
    customers_created: list[str] = field(default_factory=list)
    customers_existed: list[str] = field(default_factory=list)
    products_created: list[str] = field(default_factory=list)
    products_existed: list[str] = field(default_factory=list)
    api_keys_issued: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "customers_created": self.customers_created,
            "customers_existed": self.customers_existed,
            "products_created": self.products_created,
            "products_existed": self.products_existed,
            "api_keys_issued": self.api_keys_issued,
        }


async def seed_demo(*, db: Database | None = None) -> SeedResult:
    owns_db = db is None
    if db is None:
        db = get_database()
        await db.connect()

    result = SeedResult()
    customers = CustomerRepository(db)
    products = ProductRepository(db)
    api_keys = ApiKeyRepository(db)

    try:
        for c in DEMO_CUSTOMERS:
            try:
                await customers.create(**c)
                result.customers_created.append(c["slug"])
            except CustomerSlugConflict:
                result.customers_existed.append(c["slug"])

        for p in DEMO_PRODUCTS:
            try:
                await products.create(**p)
                result.products_created.append(p["slug"])
            except ProductSlugConflict:
                result.products_existed.append(p["slug"])

        # 每个新建客户配 1 把 API key（明文只在这次输出，不存）
        for slug in result.customers_created:
            customer = await customers.get_by_slug(slug)
            if customer is None:
                continue
            _, plaintext = await api_keys.issue(
                customer_id=customer.id, project_label="demo"
            )
            result.api_keys_issued.append(
                {"customer_slug": slug, "plaintext": plaintext}
            )

        return result
    finally:
        if owns_db:
            await db.disconnect()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forge.cli.seed_demo")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(seed_demo())
    except Exception as exc:  # noqa: BLE001
        print(f"seed_demo failed: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        d = result.to_dict()
        print(f"customers created: {d['customers_created']}")
        print(f"customers existed: {d['customers_existed']}")
        print(f"products  created: {d['products_created']}")
        print(f"products  existed: {d['products_existed']}")
        for k in d["api_keys_issued"]:
            print(f"  api-key for {k['customer_slug']}: {k['plaintext']}  (save it — shown once)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
