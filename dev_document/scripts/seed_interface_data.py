#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
接口演示数据脚本
================================

用途：
    1. 为跨团队接口准备一套可复用的演示数据。
    2. 保证 Postman 集合中的示例请求能够直接调通。

使用方法：
    odoo-bin shell -d <数据库名> -c <配置文件> < dev_document/scripts/seed_interface_data.py
"""

from datetime import date, timedelta

from odoo import fields


try:
    env  # type: ignore[name-defined]
except NameError as exc:
    raise RuntimeError(
        "请在 odoo-bin shell 环境中运行此脚本，例如：\n"
        "  odoo-bin shell -d demo -c odoo.conf < dev_document/scripts/seed_interface_data.py"
    ) from exc


# ---------- 工具函数 ----------


def log(message):
    print(f"[接口演示数据] {message}")


def ensure_group(xml_id):
    group = env.ref(xml_id, raise_if_not_found=False)
    if group and env.user not in group.users:
        env.user.write({"groups_id": [(4, group.id)]})
        log(f"当前用户已加入权限组：{group.display_name}")
    return group


def ensure_company(name, parent=None):
    Company = env["res.company"].with_context(active_test=False)
    company = Company.search([("name", "=", name)], limit=1)
    if company:
        if parent and company.parent_id != parent:
            company.parent_id = parent.id
        return company
    values = {"name": name}
    if parent:
        values["parent_id"] = parent.id
    company = Company.create(values)
    log(f"已创建公司：{company.display_name}")
    return company


def ensure_partner(name, mobile=None, email=None, is_company=False, company=False):
    Partner = env["res.partner"].with_context(active_test=False)
    domain = [("name", "=", name)]
    partner = Partner.search(domain, limit=1)
    if partner:
        updates = {}
        if mobile and partner.mobile != mobile:
            updates["mobile"] = mobile
        if email and partner.email != email:
            updates["email"] = email
        if is_company and not partner.is_company:
            updates["is_company"] = True
        if company and partner.company_id != company:
            updates["company_id"] = company.id
        if updates:
            partner.write(updates)
        return partner
    values = {
        "name": name,
        "mobile": mobile,
        "email": email,
        "is_company": is_company,
    }
    if company:
        values["company_id"] = company.id
    partner = Partner.create(values)
    log(f"已创建联系人：{partner.display_name}")
    return partner


def ensure_employee(name, company, job_name=None):
    Employee = env["hr.employee"].with_context(active_test=False)
    employee = Employee.search(
        [("name", "=", name), ("company_id", "=", company.id)], limit=1
    )
    if employee:
        return employee
    Job = env["hr.job"]
    job = False
    if job_name:
        job = Job.search([("name", "=", job_name)], limit=1)
        if not job:
            job = Job.create({"name": job_name})
    employee_vals = {"name": name, "company_id": company.id}
    if job:
        employee_vals["job_id"] = job.id
    employee = Employee.create(employee_vals)
    log(f"已创建员工：{employee.name}")
    return employee


def ensure_finance_channel(code, name, channel_type, company, auto_reconcile=True):
    Channel = env["store.finance.channel"].with_company(company)
    channel = Channel.search(
        [("code", "=", code), ("company_id", "=", company.id)], limit=1
    )
    if channel:
        if channel.channel_type != channel_type:
            channel.channel_type = channel_type
        return channel
    channel = Channel.create(
        {
            "code": code,
            "name": name,
            "channel_type": channel_type,
            "company_id": company.id,
            "auto_reconcile": auto_reconcile,
        }
    )
    log(f"已创建支付渠道：{channel.display_name}")
    return channel


def ensure_product(name, default_code, company):
    Product = env["product.product"].with_context(active_test=False)
    product = Product.search(
        [("default_code", "=", default_code), ("company_id", "in", [company.id, False])],
        limit=1,
    )
    if product:
        return product
    categ = env["product.category"].search([("name", "=", "雪茄酒类")], limit=1)
    if not categ:
        categ = env["product.category"].create({"name": "雪茄酒类"})
    uom_unit = env.ref("uom.product_uom_unit")
    template = env["product.template"].create(
        {
            "name": name,
            "default_code": default_code,
            "type": "product",
            "list_price": 368.0,
            "standard_price": 210.0,
            "categ_id": categ.id,
            "company_id": company.id,
            "uom_id": uom_unit.id,
            "uom_po_id": uom_unit.id,
        }
    )
    product = template.product_variant_id
    log(f"已创建商品：{product.display_name}")
    return product


def ensure_supplier(company, partner, name):
    Supplier = env["store.supplier"].with_company(company)
    supplier = Supplier.search(
        [("partner_id", "=", partner.id), ("company_id", "=", company.id)], limit=1
    )
    if supplier:
        return supplier
    supplier = Supplier.create(
        {
            "name": name,
            "partner_id": partner.id,
            "company_id": company.id,
            "rating": "good",
            "delivery_lead_days": 5,
            "cooperation_note": "<p>演示合作供应商。</p>",
        }
    )
    log(f"已创建供应商档案：{supplier.name}")
    return supplier


def ensure_inventory_batch(company, product, supplier_partner, supplier_record):
    Batch = env["store.inventory.batch"].with_company(company)
    batch = Batch.search(
        [("name", "=", "DEMO-BATCH-001"), ("company_id", "=", company.id)], limit=1
    )
    if not batch:
        batch = Batch.create(
            {
                "name": "DEMO-BATCH-001",
                "product_id": product.id,
                "qty_initial": 50,
                "qty_available": 0.0,
                "purchase_price": 180.0,
                "aging_start_date": fields.Date.today() - timedelta(days=45),
                "supplier_id": supplier_partner.id,
                "supplier_record_id": supplier_record.id if supplier_record else False,
                "company_id": company.id,
            }
        )
        log(f"已创建库存批次：{batch.name}")
    Move = env["store.inventory.move"].with_company(company)
    move = Move.search(
        [
            ("batch_id", "=", batch.id),
            ("move_type", "=", "incoming"),
            ("state", "=", "done"),
        ],
        limit=1,
    )
    if not move:
        move = Move.create(
            {
                "batch_id": batch.id,
                "move_type": "incoming",
                "quantity": 50,
                "unit_price": batch.purchase_price,
                "note": "演示批次入库",
            }
        )
        move.with_context(skip_approval_activity=True).action_submit()
        move.with_context(bypass_inventory_approval=True).action_approve()
        log(f"已生成入库动作：{move.name}")
    return batch


def ensure_inventory_transfer(batch, target_company, link_group):
    Transfer = env["store.inventory.transfer"].sudo()
    transfer = Transfer.search(
        [
            ("batch_id", "=", batch.id),
            ("target_company_id", "=", target_company.id),
            ("state", "=", "done"),
        ],
        limit=1,
    )
    if transfer:
        return transfer
    transfer = Transfer.create(
        {
            "batch_id": batch.id,
            "target_company_id": target_company.id,
            "qty": 5,
            "unit_price": batch.purchase_price,
            "reason": "演示互通调拨",
        }
    )
    transfer.action_submit()
    transfer.action_approve()
    log(f"已完成互通调拨：{transfer.name}（互通组 {link_group.display_name}）")
    return transfer


def ensure_commission_rule(company):
    Rule = env["store.commission.rule"].with_company(company)
    rule = Rule.search(
        [("code", "=", "DEMO-COMMISSION-ORDER"), ("company_id", "=", company.id)],
        limit=1,
    )
    if not rule:
        rule = Rule.create(
            {
                "name": "演示整单 10% 提成",
                "code": "DEMO-COMMISSION-ORDER",
                "company_id": company.id,
                "rule_type": "order",
                "rate_type": "percent",
                "rate_value": 10.0,
                "scope_type": "all",
                "start_date": fields.Date.today() - timedelta(days=30),
            }
        )
        rule.action_activate()
        log("已创建提成规则：演示整单 10% 提成")
    elif rule.state != "active":
        rule.action_activate()
    return rule


def ensure_sale_order(company, customer, employee, product):
    SaleOrder = env["sale.order"].with_company(company)
    order = SaleOrder.search(
        [("client_order_ref", "=", "DEMO-STORE-SALE")], limit=1
    )
    if order:
        return order
    pricelist = (
        env.ref("product.list0", raise_if_not_found=False)
        or env["product.pricelist"].search([], limit=1)
    )
    if not pricelist:
        pricelist = env["product.pricelist"].create(
            {"name": "演示价目表", "currency_id": company.currency_id.id}
        )
    order = SaleOrder.create(
        {
            "partner_id": customer.id,
            "company_id": company.id,
            "pricelist_id": pricelist.id,
            "responsible_employee_id": employee.id,
            "client_order_ref": "DEMO-STORE-SALE",
        }
    )
    env["sale.order.line"].create(
        {
            "order_id": order.id,
            "product_id": product.id,
            "product_uom_qty": 2,
            "price_unit": 368.0,
        }
    )
    order.action_confirm()
    log(f"已确认销售订单：{order.name}")
    return order


def ensure_finance_transaction(company, channel, partner):
    Transaction = env["store.account.transaction"].with_company(company)
    transaction = Transaction.search(
        [("description", "=", "演示手工充值"), ("company_id", "=", company.id)], limit=1
    )
    if transaction:
        return transaction
    transaction = Transaction.create(
        {
            "transaction_type": "recharge",
            "amount": 500.0,
            "company_id": company.id,
            "currency_id": company.currency_id.id,
            "channel_id": channel.id,
            "member_id": partner.id,
            "description": "演示手工充值",
        }
    )
    transaction.action_confirm()
    log(f"已生成演示充值流水：{transaction.name}")
    return transaction


def ensure_member(name, mobile, origin_store, link_group):
    member = ensure_partner(name, mobile=mobile)
    if member.member_level != "gold":
        member.write({"member_level": "gold"})
    if member.origin_store_id != origin_store:
        member.origin_store_id = origin_store.id
    member.write({"enable_investment": True})
    if link_group not in member.share_with_group_ids:
        member.share_with_group_ids = [(4, link_group.id)]
    return member


def ensure_member_balance(member, company, minimum=600.0):
    balance = member.member_balance or 0.0
    delta = max(minimum - balance, 0.0)
    if delta > 0.0:
        member.action_member_recharge(
            delta,
            company=company,
            note="演示数据充值",
        )
        log(f"会员储值增加 {delta} 元，当前余额 {member.member_balance}")


def ensure_bar_table(company, employee):
    Table = env["store.bar.table"].with_company(company)
    table = Table.search(
        [("code", "=", "DEMO-TABLE-01"), ("company_id", "=", company.id)], limit=1
    )
    if table:
        if table.responsible_employee_id != employee:
            table.responsible_employee_id = employee.id
        return table
    table = Table.create(
        {
            "code": "DEMO-TABLE-01",
            "name": "演示吧台 01",
            "company_id": company.id,
            "capacity": 4,
            "responsible_employee_id": employee.id,
        }
    )
    log(f"已创建桌台：{table.display_name}")
    return table


def ensure_bar_order(table, employee, member, channel, batch, product):
    Order = env["store.bar.order"].with_company(table.company_id)
    order = Order.search([("name", "=", "DEMO-BAR-ORDER")], limit=1)
    if not order:
        order = Order.create(
            {
                "name": "DEMO-BAR-ORDER",
                "table_id": table.id,
                "company_id": table.company_id.id,
                "responsible_employee_id": employee.id,
                "assistant_employee_ids": [(4, employee.id)],
                "member_id": member.id,
                "payment_channel_id": channel.id,
                "amount_service": 20.0,
            }
        )
        env["store.bar.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "batch_id": batch.id,
                "quantity": 1,
                "price_unit": 368.0,
                "requires_preparation": True,
            }
        )
        log("已创建吧台订单与明细。")
    if order.state == "draft":
        order.action_confirm()
        order.action_set_serving()
        order.task_ids.action_done()
        order.action_request_bill()
        log(f"吧台订单进入结账中状态：{order.name}")
    return order


def ensure_link_group(brand_company, members, owner):
    Group = env["store.link.group"].sudo()
    group = Group.search(
        [("code", "=", "DEMO-LINK-GROUP"), ("brand_company_id", "=", brand_company.id)],
        limit=1,
    )
    if not group:
        group = Group.create(
            {
                "code": "DEMO-LINK-GROUP",
                "name": "演示互通组",
                "brand_company_id": brand_company.id,
                "owner_id": owner.id,
                "share_inventory": True,
                "share_member": True,
                "share_finance": True,
                "member_company_ids": [(6, 0, [company.id for company in members])],
                "state": "active",
            }
        )
        log("已创建演示互通组。")
    else:
        new_members = [
            (4, company.id)
            for company in members
            if company not in group.member_company_ids
        ]
        if new_members:
            group.write({"member_company_ids": new_members})
        if group.state != "active":
            group.action_activate()
    return group


def ensure_link_group_application(group, applicant, target):
    Application = env["store.link.group.application"].sudo()
    application = Application.search(
        [
            ("group_id", "=", group.id),
            ("request_company_id", "=", applicant.id),
            ("state", "=", "submitted"),
        ],
        limit=1,
    )
    if application:
        return application
    application = Application.create(
        {
            "group_id": group.id,
            "request_company_id": applicant.id,
            "requested_member_ids": [(6, 0, [applicant.id, target.id])],
            "description": "演示数据：申请加入互通组。",
            "share_inventory": True,
            "share_member": True,
            "share_finance": False,
        }
    )
    application.action_submit()
    log(f"已提交互通申请：{application.name}")
    return application


def ensure_crowdfunding_project(company, brand_company, link_group, contact):
    Project = env["store.crowdfunding.project"].with_company(company)
    project = Project.search([("code", "=", "DEMO-CFP-001")], limit=1)
    if not project:
        project = Project.create(
            {
                "code": "DEMO-CFP-001",
                "name": "演示雪茄房升级项目",
                "company_id": company.id,
                "brand_company_id": brand_company.id,
                "link_group_id": link_group.id,
                "target_amount": 100000.0,
                "min_invest_amount": 2000.0,
                "max_invest_amount": 20000.0,
                "min_success_ratio": 0.7,
                "funding_start_date": date.today() - timedelta(days=7),
                "funding_end_date": date.today() + timedelta(days=30),
                "state": "funding",
                "company_contact_id": contact.id,
                "description": "<p>用于升级雪茄品鉴区及威士忌陈列。</p>",
                "risk_note": "<p>请按月查看执行进度。</p>",
            }
        )
        log("已创建众筹项目：演示雪茄房升级项目")
    else:
        if project.state == "draft":
            project.write({"state": "funding"})
    return project


def ensure_crowdfunding_investment(project, member):
    Investment = env["store.crowdfunding.investment"].sudo()
    investment = Investment.search(
        [
            ("project_id", "=", project.id),
            ("partner_id", "=", member.id),
            ("state", "in", ["draft", "confirmed"]),
        ],
        limit=1,
    )
    if not investment:
        investment = Investment.create(
            {
                "project_id": project.id,
                "partner_id": member.id,
                "amount": 5000.0,
            }
        )
        investment.action_confirm()
        log(f"已确认众筹投资：{investment.name}")
    elif investment.state == "draft":
        investment.action_confirm()
    return investment


def main():
    ensure_group("stock.group_stock_manager")
    ensure_group("store_commission.group_store_commission_user")
    ensure_group("store_commission.group_store_commission_manager")
    ensure_group("store_bar.group_store_bar_manager")
    ensure_group("store_member.group_member_sensitive")

    brand_company = env.company
    store_company = brand_company
    target_company = ensure_company("演示门店 B", parent=brand_company)
    owner_partner = ensure_partner("演示品牌老板", mobile="13800000001")
    link_group = ensure_link_group(
        brand_company, [store_company, target_company], owner_partner
    )
    application = ensure_link_group_application(link_group, store_company, target_company)

    supplier_partner = ensure_partner(
        "演示供应商有限公司", mobile="021-88886666", is_company=True
    )
    supplier_record = ensure_supplier(store_company, supplier_partner, "演示供应商有限公司")

    product = ensure_product("演示典藏雪茄", "DEMO-CIGAR-001", store_company)
    batch = ensure_inventory_batch(store_company, product, supplier_partner, supplier_record)
    transfer = ensure_inventory_transfer(batch, target_company, link_group)

    commission_rule = ensure_commission_rule(store_company)
    bartender = ensure_employee("演示调酒师", store_company, job_name="调酒师")
    assistant = ensure_employee("演示侍酒师", store_company, job_name="侍酒师")

    cash_channel = ensure_finance_channel("DEMO-CASH", "前台现金", "cash", store_company)
    stored_channel = ensure_finance_channel(
        "DEMO-STORED", "会员储值", "stored_value", store_company
    )
    internal_channel = ensure_finance_channel(
        "DEMO-INTERNAL", "内部结算", "internal", store_company, auto_reconcile=False
    )

    customer = ensure_partner("演示团购客户", mobile="13900000002")
    sale_order = ensure_sale_order(store_company, customer, assistant, product)

    member = ensure_member("演示会员张先生", mobile="13800000003", origin_store=store_company, link_group=link_group)
    ensure_member_balance(member, store_company, minimum=800.0)
    ensure_finance_transaction(store_company, cash_channel, member)

    table = ensure_bar_table(store_company, bartender)
    bar_order = ensure_bar_order(table, bartender, member, stored_channel, batch, product)

    project = ensure_crowdfunding_project(store_company, brand_company, link_group, owner_partner)
    investment = ensure_crowdfunding_investment(project, member)

    env.cr.commit()

    log("演示数据创建完成。")
    print(
        "\n=== Postman 环境变量建议 ===\n"
        f"- link_group_id: {link_group.id}\n"
        f"- link_group_application_id: {application.id}\n"
        f"- store_company_id: {store_company.id}\n"
        f"- target_company_id: {target_company.id}\n"
        f"- supplier_record_id: {supplier_record.id}\n"
        f"- supplier_partner_id: {supplier_partner.id}\n"
        f"- product_id: {product.id}\n"
        f"- inventory_batch_id: {batch.id}\n"
        f"- inventory_transfer_id: {transfer.id}\n"
        f"- commission_rule_id: {commission_rule.id}\n"
        f"- sale_order_id: {sale_order.id}\n"
        f"- commission_employee_id: {assistant.id}\n"
        f"- bartender_employee_id: {bartender.id}\n"
        f"- bar_table_id: {table.id}\n"
        f"- bar_order_id: {bar_order.id}\n"
        f"- member_id: {member.id}\n"
        f"- member_phone: {member.mobile or ''}\n"
        f"- finance_channel_cash: {cash_channel.id}\n"
        f"- finance_channel_stored: {stored_channel.id}\n"
        f"- finance_channel_internal: {internal_channel.id}\n"
        f"- crowdfunding_project_id: {project.id}\n"
        f"- crowdfunding_investment_id: {investment.id}\n"
    )


if __name__ == "__main__":
    main()
