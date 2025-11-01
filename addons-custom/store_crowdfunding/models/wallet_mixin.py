# -*- coding: utf-8 -*-
from odoo import _
from odoo import models
from odoo.tools import float_is_zero


class StoreCrowdfundingWalletMixin(models.AbstractModel):
    _name = "store.crowdfunding.wallet.mixin"
    _description = "众筹会员钱包对接帮助类"

    def _post_member_wallet_entry(self, partner, amount, description, extra_vals=None):
        """Try to push investment/dividend movements to store_member wallet.

        Gracefully no-op when目标模型或字段不存在，避免 Team E 模块尚未上线时出错。
        """
        self.ensure_one()
        currency = partner.company_id.currency_id or self.env.company.currency_id
        if not partner or float_is_zero(amount, precision_rounding=currency.rounding):
            return False

        registry = self.env.registry
        if "store.member.wallet" not in registry.models:
            return False

        Wallet = self.env["store.member.wallet"].sudo()
        expected_fields = Wallet._fields

        vals = {}
        field_map = {
            "partner_id": partner.id,
            "company_id": partner.company_id.id or self.env.company.id,
            "balance_type": "crowdfunding",
            "amount": amount,
            "description": description,
            "origin_model": self._name,
            "origin_res_id": self.id if isinstance(self.id, int) else False,
        }
        if extra_vals:
            field_map.update(extra_vals)

        for key, value in field_map.items():
            if key in expected_fields:
                vals[key] = value

        if not vals:
            return False

        entry = Wallet.create(vals)
        return entry
