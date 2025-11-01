import logging
import os
from contextlib import nullcontext

from odoo import SUPERUSER_ID, api
from odoo.addons.base.models.assetsbundle import ANY_UNIQUE
from odoo.addons.web.controllers.binary import Binary
from odoo.http import request, route

_logger = logging.getLogger(__name__)


class BinaryWithAssetRecovery(Binary):
    @route(
        ['/web/assets/<string:unique>/<string:filename>'],
        type='http',
        auth='public',
        readonly=True,
    )
    def content_assets(self, filename=None, unique=ANY_UNIQUE, nocache=False, assets_params=None):
        try:
            return super().content_assets(
                filename=filename,
                unique=unique,
                nocache=nocache,
                assets_params=assets_params,
            )
        except FileNotFoundError as err:  # pragma: no cover - passthrough for logging clarity
            if not self._recover_missing_asset_file(filename, unique, assets_params):
                raise err
            return super().content_assets(
                filename=filename,
                unique=unique,
                nocache=nocache,
                assets_params=assets_params,
            )

    def _recover_missing_asset_file(self, filename, unique, assets_params):
        """Rebuild asset attachments when underlying filestore files disappear."""
        assets_params = assets_params or {}
        env = request.env
        debug_assets = unique == 'debug'
        normalized_unique = unique
        if normalized_unique in ('any', '%'):
            normalized_unique = ANY_UNIQUE

        if env.cr.readonly:
            env.cr.rollback()
            cursor_manager = env.registry.cursor(readonly=False)
        else:
            cursor_manager = nullcontext(env.cr)

        with cursor_manager as rw_cr:
            rw_env = api.Environment(rw_cr, SUPERUSER_ID, {})
            ira = rw_env['ir.attachment'].sudo()
            try:
                url = rw_env['ir.asset']._get_asset_bundle_url(filename, normalized_unique, assets_params)
            except Exception:
                return False

            domain = [
                ('public', '=', True),
                ('url', '!=', False),
                ('url', '=like', url),
                ('res_model', '=', 'ir.ui.view'),
                ('res_id', '=', 0),
                ('create_uid', '=', SUPERUSER_ID),
            ]
            attachments = ira.search(domain)

            filestore_root = ira._filestore()
            missing = attachments.filtered(
                lambda att: att.store_fname
                and not os.path.exists(os.path.join(filestore_root, att.store_fname))
            )
            if missing:
                _logger.warning(
                    "检测到缺失的资产文件，准备重新生成: %s",
                    missing.mapped('store_fname'),
                )
                missing.unlink()

            try:
                bundle_name, rtl, asset_type = rw_env['ir.asset']._parse_bundle_name(filename, debug_assets)
            except ValueError as parse_error:
                _logger.error("资产路径解析失败 %s: %s", filename, parse_error)
                return False

            bundle = rw_env['ir.qweb']._get_asset_bundle(
                bundle_name,
                css=asset_type == 'css',
                js=asset_type == 'js',
                debug_assets=debug_assets,
                rtl=rtl,
                assets_params=assets_params,
            )

            generated = False
            if asset_type == 'css' and bundle.stylesheets:
                bundle.css()
                generated = True
            if asset_type == 'js' and bundle.javascripts:
                bundle.js()
                generated = True

            if not generated:
                _logger.warning("资产 %s 未生成任何附件（可能无可生成资源）", filename)

        return True
