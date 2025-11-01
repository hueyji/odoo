#!/usr/bin/env python3
"""
Invoke the brand_core multi-company initialization wizard from command line.

Usage example:
    python dev_document/scripts/init_brand_companies.py --config odoo.conf --db odoo16 \\
        --brand "雪茄威士忌品牌总部" \\
        --store "上海外滩旗舰门店" --store "上海新天地体验店"
"""

from __future__ import annotations

import argparse
import logging
import sys
from contextlib import contextmanager
from pathlib import Path

LOGGER = logging.getLogger("init_brand_companies")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import odoo  # type: ignore  # noqa: E402
from odoo import SUPERUSER_ID, api  # noqa: E402
from odoo.modules.registry import Registry  # noqa: E402
from odoo.tools import config as odoo_config  # noqa: E402

DEFAULT_DB = "odoo16"
DEFAULT_CONFIG = "odoo.conf"
DEFAULT_STORES = ["上海外滩旗舰门店", "上海新天地体验店"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create brand headquarters, stores and investor company.")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Config file path (default: odoo.conf)")
    parser.add_argument("--db", default=DEFAULT_DB, help="Database name (default: odoo16)")
    parser.add_argument("--brand", default="雪茄威士忌品牌总部", help="Brand headquarters company name.")
    parser.add_argument(
        "--store",
        action="append",
        dest="stores",
        help="Store company name (can be specified multiple times).",
    )
    parser.add_argument(
        "--investor-name",
        default="品牌投资人虚拟公司",
        help="Investor virtual company name (ignored when --no-investor is used).",
    )
    parser.add_argument(
        "--no-investor",
        action="store_true",
        help="Do not create investor virtual company.",
    )
    parser.add_argument(
        "--skip-assign-user",
        action="store_true",
        help="Do not update the current user access to include the new companies.",
    )
    return parser.parse_args()


def load_config(config_path: str) -> None:
    odoo_config.parse_config(["-c", config_path])


@contextmanager
def get_env(db_name: str):
    registry = Registry(db_name)
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {"lang": "zh_CN"})
        yield env
        cr.commit()


def run_wizard(env, brand: str, stores: list[str], investor_name: str, create_investor: bool, assign_user: bool):
    Wizard = env["brand.core.company.init.wizard"].sudo()
    store_lines = "\n".join(stores)
    wizard = Wizard.create(
        {
            "brand_name": brand,
            "store_names": store_lines,
            "create_investor_company": create_investor,
            "investor_company_name": investor_name,
            "assign_current_user": assign_user,
        }
    )
    wizard.action_initialize()
    LOGGER.info(
        "Initialized companies - brand: %s, stores: %s, investor: %s",
        brand,
        ", ".join(stores),
        investor_name if create_investor else "skipped",
    )


def main():
    args = parse_args()
    stores = args.stores or DEFAULT_STORES
    if not stores:
        parser_error = "至少需要指定一个门店名称 (--store)。"
        raise SystemExit(parser_error)

    load_config(args.config)

    with get_env(args.db) as env:
        run_wizard(
            env=env,
            brand=args.brand,
            stores=stores,
            investor_name=args.investor_name,
            create_investor=not args.no_investor,
            assign_user=not args.skip_assign_user,
        )


if __name__ == "__main__":
    main()
