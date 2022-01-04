# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes methods to store sync/ Import product queue line
"""
from odoo import models, _


class MagentoProductQueueLine(models.Model):
    """
    Describes sync/ Import product Queue Line
    """
    _inherit = "sync.import.magento.product.queue.line"

    def __search_product(self, line, item):
        product = self.env['product.product']
        product = product.search([('default_code', '=', item.get('sku'))], limit=1)
        if item.get('type_id') == 'bundle':
            return True
        if not product:
            message = _(
                "Order '{}' has been skipped because the product type '{}' SKU '{}' is not found "
                "in Odoo. \n"
                "Please create the product in Odoo with the same SKU to import the order. \n"
                "Note: \n"
                "- In the case where the Magento product type is a group, please create a "
                "Storable or Service type product with the same SKU for every child product of "
                "the Magento group. \n- Create a Service type product in Odoo if the Magento "
                "group's child product is virtual or downloadable, and if the child product is "
                "simple in Magento, create a storable \n type product in Odoo with the same "
                "SKU.").format(item.get('increment_id'), item.get('type_id'), item.get('sku'))
            line.instance_id.create_log_line(message=message, model=line._name, res_id=line.id,
                                             log_id=line.queue_id.log_book_id.id,
                                             order_ref=item.get('increment_id', ''))
            line.queue_id.write({'is_process_queue': False})
            self._cr.commit()
            return False
        return True
