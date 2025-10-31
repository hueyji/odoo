import logging
import os

from odoo import models
from odoo.tools import SQL, config

_logger = logging.getLogger(__name__)


class ResDevice(models.Model):
    _inherit = "res.device"

    def init(self):
        super().init()
        self._ensure_device_view_access()

    def _ensure_device_view_access(self):
        """Grant SELECT on the res.device view to the database role running Odoo."""
        role_candidates = []

        configured_user = config['db_user']
        if configured_user:
            role_candidates.append(configured_user)

        env_pguser = os.environ.get("PGUSER")
        if env_pguser and env_pguser not in role_candidates:
            role_candidates.append(env_pguser)

        if not role_candidates:
            self.env.cr.execute("SELECT current_user")
            current_user = self.env.cr.fetchone()[0]
            role_candidates.append(current_user)

        for role in role_candidates:
            try:
                self.env.cr.execute(SQL(
                    "GRANT SELECT ON TABLE %s TO %s",
                    SQL.identifier(self._table),
                    SQL.identifier(role),
                ))
            except Exception as exc:  # pragma: no cover - defensive logging only
                _logger.warning(
                    "为数据库角色 %s 授予视图 %s 读取权限失败：%s",
                    role,
                    self._table,
                    exc,
                )
