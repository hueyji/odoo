# -*- coding: utf-8 -*-
"""Module hooks for brand_core."""

def post_init_hook(cr, registry):
    """Ensure company lead time columns have safe defaults for demo creation."""
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'res_company' AND column_name = 'po_lead'
        """
    )
    if cr.fetchone():
        cr.execute("ALTER TABLE res_company ALTER COLUMN po_lead SET DEFAULT 0")
        cr.execute("UPDATE res_company SET po_lead = 0 WHERE po_lead IS NULL")
