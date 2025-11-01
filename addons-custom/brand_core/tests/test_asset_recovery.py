import os

from odoo.tests.common import HttpCase, tagged
from odoo.tools import config


@tagged('post_install', '-at_install', 'asset_recovery')
class TestAssetRecovery(HttpCase):
    def test_missing_asset_bundle_file_is_rebuilt(self):
        """当 filestore 丢失 bundle 文件时，应自动重建附件并成功返回资产。"""
        qweb = self.env['ir.qweb']

        bundle = qweb._get_asset_bundle('web.assets_web', css=True, js=False, debug_assets=False)
        attachment = bundle.css()
        self.assertTrue(attachment, "预期先生成 web.assets_web CSS 资产附件")

        filestore_root = config.filestore(self.env.cr.dbname)
        asset_path = os.path.join(filestore_root, attachment.store_fname)
        self.assertTrue(os.path.exists(asset_path), "资产文件应已写入 filestore")

        # 模拟运维误删生成的静态文件，保留数据库记录
        os.remove(asset_path)
        self.assertFalse(os.path.exists(asset_path), "删除后的资产文件不应再存在")

        # 访问资产路由应触发自愈逻辑，并返回 200
        response = self.url_open('/web/assets/debug/web.assets_web.css', allow_redirects=False)
        self.assertEqual(response.status_code, 200)

        # 请求完成后应重新生成文件
        refreshed = self.env['ir.attachment'].sudo().search([
            ('url', '=like', '/web/assets/%/web.assets_web.css'),
            ('res_model', '=', 'ir.ui.view'),
        ])
        self.assertTrue(
            any(
                att.store_fname and os.path.exists(os.path.join(filestore_root, att.store_fname))
                for att in refreshed
            ),
            "资产恢复后应重新写入 filestore",
        )
