# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""For Odoo Magento2 Connector Module"""
from odoo import models, fields, api, _
from datetime import datetime
MAGENTO_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
import json

class SaleOrderLine(models.Model):
    """
    Describes Sale order line
    """
    _inherit = 'sale.order.line'

    magento_sale_order_line_ref = fields.Char(
        string="Magento Sale Order Line Reference",
        help="Magento Sale Order Line Reference"
    )

    def create_order_line(self, item, instance, log, line_id):
        order_lines = item.get('items')
        rounding = bool(instance.magento_tax_rounding_method == 'round_per_line')
        for line in order_lines:
            if line.get('product_type') in ['configurable', 'bundle']:
                continue
            product = line.get('line_product')
            price = self.__find_order_item_price(item, line)
            customer_option = self.__get_custom_option(item, line)
            line_vals = self.with_context(custom_options=customer_option).prepare_order_line_vals(
                item, line, product, price)
            order_line = self.create(line_vals)
            order_line.with_context(round=rounding)._compute_amount()
            self.__create_line_desc_note(customer_option, item.get('sale_order_id'))
        return True

    def __find_order_item_price(self, item, order_line):
        tax_type = item.get('website').tax_calculation_method
        if tax_type == 'including_tax':
            price = self.__get_price(order_line, 'price_incl_tax')
        else:
            price = self.__get_price(order_line, 'price')
        original_price = self.__get_price(order_line, 'original_price')
        item_price = price if price != original_price else original_price
        return item_price

    @staticmethod
    def __get_price(item, price):
        return item.get('parent_item').get(price) if "parent_item" in item else item.get(price)

    @staticmethod
    def _find_option_desc(item, line_item_id):
        description = ""
        ept_option_title = item.get("extension_attributes").get('ept_option_title')
        if ept_option_title:
            for custom_opt_itm in ept_option_title:
                custom_opt = json.loads(custom_opt_itm)
                if line_item_id == int(custom_opt.get('order_item_id')):
                    for option_data in custom_opt.get('option_data'):
                        description += option_data.get('label') + " : " + option_data.get('value') + "\n"
        return description

    def find_order_item(self, items, instance, log, line_id):
        for item in items.get('items'):
            if 'bundle_ept' in list(self.env.context.keys()):
                return False
            product_sku = item.get('sku')
            magento_product = self.env['magento.product.product'].search([
                '|', ('magento_product_id', '=', item.get('product_id')),
                ('magento_sku', '=', product_sku),
                ('magento_instance_id', '=', instance.id)
            ], limit=1)
            if not magento_product:
                product_obj = self.env['product.product'].search([('default_code', '=', product_sku)])
                if len(product_obj) > 1:
                    message = _(f"""
                    An order {item['increment_id']} was skipped because the ordered product {product_sku} 
                    exists multiple times in Odoo.
                    """)
                    log.write({'log_lines': [(0, 0, {
                        'message': message, 'order_ref': item['increment_id'],
                        'magento_order_data_queue_line_id': line_id
                    })]})
                    return False
                odoo_product = product_obj
            else:
                odoo_product = magento_product.odoo_product_id
            item.update({'line_product': odoo_product})
        return True

    def __get_custom_option(self, item, line):
        custom_options = ''
        description = self._find_option_desc(item, line.get('item_id'))
        if description:
            product_name = _("Custom Option for Product : %s \n" % line.get('line_product').name)
            custom_options = product_name + description
        return custom_options

    def prepare_order_line_vals(self, item, line, product, price):
        order_qty = float(line.get('qty_ordered', 1.0))
        sale_order = item.get('sale_order_id')
        order_line_ref = line.get('parent_item_id') or line.get('item_id')
        line_vals = {
            'order_id': sale_order.id,
            'product_id': product.id,
            'company_id': sale_order.company_id.id,
            'name': item.get('name'),
            'description': product.name or (sale_order and sale_order.name),
            'product_uom': product.uom_id.id,
            'order_qty': order_qty,
            'price_unit': price,
        }
        line_vals = self.create_sale_order_line_ept(line_vals)
        line_vals.update({'magento_sale_order_line_ref': order_line_ref})
        if item.get(f'order_tax_{line.get("item_id")}'):
            line_vals.update({'tax_id': [(6, 0, item.get(f'order_tax_{line.get("item_id")}'))]})
        return line_vals

    def __find_sales_taxes(self, percent, tax_type, instance, apply_tax):
        magento_tax = False
        if apply_tax == "create_magento_tax":
            account_tax_obj = self.env["account.tax"]
            tax_included = (tax_type == 'including_tax')
            if percent > 0.0:
                title = '%s %% ' % percent
                magento_tax = account_tax_obj.get_tax_from_rate(
                    float(percent), title, tax_included)
                if not magento_tax:
                    tax_vals = self.prepare_tax_dict(title, percent, tax_included)
                    tax_vals.update({
                        'invoice_repartition_line_ids': [
                            (6, 0, {
                                'account_id': instance.magento_invoice_tax_account_id.id,
                            })],
                        'refund_repartition_line_ids': [
                            (6, 0, {
                                'account_id': instance.magento_credit_tax_account_id.id,
                            })],
                    })
                    magento_tax = account_tax_obj.sudo().create(tax_vals)
        return magento_tax

    @staticmethod
    def prepare_tax_dict(tax, instance):
        tax_dict = {
            'name': tax.get('tax_title'),
            'description': tax.get('tax_title'),
            'amount_type': 'percent',
            'price_include': tax.get('tax_type'),
            'amount': float(tax.get('tax_percent')),
            'type_tax_use': 'sale',
        }
        if tax.get('line_tax') == 'order':
            tax_dict.update({
                'invoice_repartition_line_ids': [
                    (6, 0, {'account_id': instance.magento_invoice_tax_account_id.id})],
                'refund_repartition_line_ids': [
                    (6, 0, {'account_id': instance.magento_credit_tax_account_id.id,})],
            })
        return tax_dict

    def __create_line_desc_note(self, description, sale_order):
        if description:
            self.env['sale.order.line'].create({
                'name': description,
                'display_type': 'line_note',
                'product_id': False,
                'product_uom': False,
                'price_unit': 0,
                'order_id': sale_order.id,
            })
