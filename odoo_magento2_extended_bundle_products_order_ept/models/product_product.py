# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""For Odoo Magento2 Connector Module"""
from odoo import models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _compute_average_price(self, qty_invoiced, qty_to_invoice, stock_moves):
        # This method are override for make the proper valuation when any bundled product
        # ordered from Magento. If order is magento order and magento_bom_id is set in the
        # sale order line, then we will set that BOM in DO.
        self.ensure_one()
        if stock_moves.product_id == self:
            return super()._compute_average_price(qty_invoiced, qty_to_invoice, stock_moves)
        bom = self.env['mrp.bom']._bom_find(products=self, company_id=stock_moves.company_id.id,
                                            bom_type='phantom')
        if not bom:
            return super()._compute_average_price(qty_invoiced, qty_to_invoice, stock_moves)
        dummy, bom_lines = bom.explode(self, 1)
        bom_lines = {line: data for line, data in bom_lines}
        value = 0
        for move in stock_moves:
            bom_line = move.bom_line_id
            magento_bom_data = dict()
            if move.sale_line_id and move.sale_line_id.magento_bom_id:
                saleline_bom = move.sale_line_id.magento_bom_id
                dummy1, sale_bom_lines = saleline_bom.explode(self, 1)
                magento_bom_data = {line: data for line, data in sale_bom_lines}

            if bom_line:
                if move.sale_line_id and move.sale_line_id.magento_bom_id:
                    bom_line_data = magento_bom_data[bom_line]
                    line_qty = bom_line_data['qty']
                else:
                    bom_line_data = bom_lines[bom_line]
                    line_qty = bom_line_data['qty']
            else:
                # bom was altered (i.e. bom line removed) after being used
                line_qty = move.product_qty
            value += line_qty * move.product_id._compute_average_price(qty_invoiced * line_qty,
                                                                       qty_to_invoice * line_qty,
                                                                       move)
        return value
