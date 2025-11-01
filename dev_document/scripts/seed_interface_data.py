#!/usr/bin/env python3
"""
Seed interface demo data for the multi-store project on Odoo 16.0.

Usage:
    python dev_document/scripts/seed_interface_data.py --config odoo.conf.local --db brand_multistore_dev
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from contextlib import contextmanager
from pathlib import Path

import psycopg2

# Ensure the repository root is importable before loading `odoo`
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import odoo  # type: ignore  # noqa: E402
from odoo import SUPERUSER_ID, api  # noqa: E402
from odoo.modules.registry import Registry  # noqa: E402
from odoo.tools import config as odoo_config  # noqa: E402

LOGGER = logging.getLogger("seed_interface_data")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

DEFAULT_DB = "brand_multistore_dev"
DEFAULT_CONFIG = "odoo.conf.local"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed baseline demo data for API testing.")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Path to odoo.conf (default: odoo.conf.local)")
    parser.add_argument("--db", default=os.environ.get("ODOO_DB", DEFAULT_DB), help="Database name")
    parser.add_argument(
        "--skip-users",
        action="store_true",
        help="Skip creating demo users (useful when credentials already exist).",
    )
    return parser.parse_args()


def load_config(config_path: str) -> None:
    path = Path(config_path)
    if not path.exists():
        fallback = Path("odoo.conf")
        LOGGER.warning("Config %s not found, falling back to %s", config_path, fallback)
        config_path = str(fallback)
    odoo_config.parse_config(["-c", config_path])


@contextmanager
def get_env(db_name: str):
    registry = Registry(db_name)
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {"lang": "zh_CN"})
        yield env
        cr.commit()


def ensure_company(env, name: str, parent=None, city=None, phone=None):
    Company = env["res.company"].sudo()
    company = Company.search([("name", "=", name)], limit=1)
    if company:
        updates = {}
        if parent and company.parent_id != parent:
            updates["parent_id"] = parent.id
        if updates:
            company.write(updates)
        partner_values = {k: v for k, v in {"city": city, "phone": phone} if v}
        if partner_values:
            company.partner_id.sudo().write(partner_values)
        LOGGER.info("Company ensured: %s (id=%s)", company.name, company.id)
        return company

    currency = (
        env.ref("base.CNY", raise_if_not_found=False)
        or env.ref("base.USD", raise_if_not_found=False)
        or env.company.currency_id
    )
    vals = {
        "name": name,
        "parent_id": parent.id if parent else False,
        "currency_id": currency.id,
    }
    company = Company.create(vals)
    company.partner_id.sudo().write(
        {k: v for k, v in {"city": city, "phone": phone, "lang": "zh_CN"} if v}
    )
    LOGGER.info("Company created: %s (id=%s)", company.name, company.id)
    return company


def ensure_partner(env, name: str, phone: str, email: str, company=None, is_company=False):
    Partner = env["res.partner"].sudo()
    partner = Partner.search([("email", "=", email)], limit=1)
    vals = {
        "name": name,
        "phone": phone,
        "email": email,
        "lang": "zh_CN",
        "company_id": company.id if company else False,
        "is_company": is_company,
    }
    if partner:
        partner.write({k: v for k, v in vals.items() if v})
        LOGGER.info("Partner ensured: %s (id=%s)", partner.name, partner.id)
        return partner
    partner = Partner.create(vals)
    LOGGER.info("Partner created: %s (id=%s)", partner.name, partner.id)
    return partner


def ensure_user(env, name: str, login: str, password: str, groups, company):
    Users = env["res.users"].sudo().with_context(no_reset_password=True)
    user = Users.search([("login", "=", login)], limit=1)
    group_ids = [env.ref(xmlid).id for xmlid in groups]
    vals = {
        "name": name,
        "login": login,
        "password": password,
        "company_id": company.id,
        "company_ids": [(6, 0, [company.id])],
        "groups_id": [(6, 0, group_ids)],
        "lang": "zh_CN",
        "tz": "Asia/Shanghai",
    }
    if user:
        user.write({k: v for k, v in vals.items() if k != "password"})
        LOGGER.info("User ensured: %s (id=%s)", user.name, user.id)
        return user
    user = Users.create(vals)
    LOGGER.info("User created: %s (login=%s)", user.name, login)
    user._set_password(password)
    return user


def seed_data(env, skip_users: bool):
    brand_company = env.ref("base.main_company")
    brand_company.write({"name": "雪茄威士忌品牌总部"})
    brand_company.partner_id.write(
        {
            "name": "雪茄威士忌品牌总部",
            "phone": "+86 10 1234 5678",
            "city": "北京",
            "lang": "zh_CN",
        }
    )

    sh_store = ensure_company(
        env,
        "上海静安旗舰店",
        parent=brand_company,
        city="上海",
        phone="+86 21 9876 5432",
    )
    sz_store = ensure_company(
        env,
        "深圳欢乐海岸店",
        parent=brand_company,
        city="深圳",
        phone="+86 755 1234 5678",
    )

    investor = ensure_partner(
        env,
        name="王启明",
        phone="+86 139 0000 0001",
        email="investor01@example.com",
        company=brand_company,
    )
    vip_member = ensure_partner(
        env,
        name="陈雅婷",
        phone="+86 138 1111 2222",
        email="member01@example.com",
        company=sh_store,
    )

    bind_phone = "+86 139 3333 4444"
    bind_partner = env["res.partner"].sudo().search([("phone", "=", bind_phone)], limit=1)
    bind_vals = {
        "name": "接口会员",
        "email": "api.member@example.com",
        "mobile": bind_phone,
        "company_id": sh_store.id,
        "lang": "zh_CN",
        "is_store_member": False,
        "member_origin_company_id": False,
        "member_code": False,
    }
    if bind_partner:
        bind_partner.write({k: v for k, v in bind_vals.items() if v is not None})
        bind_partner.write({"phone": bind_phone})
    else:
        bind_vals["phone"] = bind_phone
        bind_partner = env["res.partner"].sudo().create(bind_vals)


    if not skip_users:
        ensure_user(
            env,
            name="品牌平台管理员",
            login="brand.admin@example.com",
            password="Admin@2024",
            groups=["base.group_system"],
            company=brand_company,
        )
        ensure_user(
            env,
            name="上海门店店长",
            login="store.manager.sh@example.com",
            password="Store@2024",
            groups=["base.group_user"],
            company=sh_store,
        )
        ensure_user(
            env,
            name="深圳门店店长",
            login="store.manager.sz@example.com",
            password="Store@2024",
            groups=["base.group_user"],
            company=sz_store,
        )

    summary = {
        "store_company_id": sh_store.id,
        "member_id": vip_member.id,
        "member_bind_phone": bind_phone,
        "member_bind_name": bind_partner.name,
        "member_bind_email": bind_partner.email,
        "member_list_keyword": "陈",
    }

    LOGGER.info(
        "Demo partners: brand=%s member=%s investor=%s bind_candidate=%s",
        brand_company.id,
        vip_member.id,
        investor.id,
        bind_partner.id,
    )
    print(json.dumps({"postman": summary}, ensure_ascii=False, indent=2))


def main():
    args = parse_args()
    load_config(args.config)
    try:
        with get_env(args.db) as env:
            seed_data(env, skip_users=args.skip_users)
    except psycopg2.OperationalError as exc:
        LOGGER.error("Database connection failed: %s", exc)
        sys.exit(1)
    except Exception:  # noqa: BLE001
        LOGGER.exception("Unexpected error while seeding data")
        sys.exit(1)


if __name__ == "__main__":
    main()
