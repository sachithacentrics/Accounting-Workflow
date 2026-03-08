from odoo import fields, api, models


class InheritAccountTax(models.Model):
    _inherit = 'account.tax'

    vat_type = fields.Selection([('vat', 'VAT'), ('s_vat', 'SVAT'), ('other', 'Other')], string="Local Tax Type")

    _sql_constraints = [
        ('name_company_uniq', 'unique(name, company_id, type_tax_use, vat_type)', 'Tax names must be unique !'),
    ]


class CustomerInherit(models.Model):
    _inherit = 'res.partner'

    vat_type = fields.Selection([('non_vat', 'Non VAT'),
                                 ('s_vat', 'SVAT'),
                                 ('vat', 'VAT')], string="VAT Type", default='non_vat')
    svat_no = fields.Char('SVAT No')
    vat = fields.Char(string='Tax No',
                      help="The Tax Identification Number. Complete it if the contact is subjected to government taxes. Used in some legal statements.")


class CompanyInherit(models.Model):
    _inherit = 'res.company'

    svat_no = fields.Char(related='partner_id.svat_no', string='SVAT No', readonly=False)
    vat = fields.Char(related='partner_id.vat', string="VAT No", readonly=False)
    active = fields.Boolean(string="Active", default=True)


class InheritSaleOrder(models.Model):
    _inherit = 'sale.order'

    svat = fields.Float(string="SVAT Amount", compute='get_svat_value')
    vat_type = fields.Selection([('non_vat', 'Non VAT'),
                                 ('s_vat', 'SVAT'),
                                 ('vat', 'VAT')], string="VAT Type")

    @api.onchange('vat_type')
    def _onchange_vat_type(self):
        for record in self:
            if record.vat_type:
                if record.order_line:
                    if record.vat_type == 'vat':
                        for line in record.order_line:
                            if line.product_id:
                                taxes = line.product_id.mapped('taxes_id').filtered(lambda x: not line.company_id or x.company_id == line.company_id and x.vat_type == 'vat')
                                if taxes:
                                    line.tax_id = taxes.ids
                    if record.vat_type == 's_vat':
                        for line in record.order_line:
                            if line.product_id:
                                taxes = line.product_id.mapped('taxes_id').filtered(lambda x: not line.company_id or x.company_id == line.company_id and x.vat_type == 's_vat')
                                if taxes:
                                    line.tax_id = taxes.ids
                    if record.vat_type == 'non_vat':
                        for line in record.order_line:
                            if line.tax_id:
                                line.tax_id = False

    @api.depends('amount_untaxed')
    def get_svat_value(self):
        """get svat amount calculation"""
        for line in self:
            if line.vat_type == 's_vat':
                svat = 0
                for item in line.order_line:
                    if_tax = item.tax_id
                    tax = if_tax[0].amount if if_tax else 0
                    svat += item.price_subtotal * ((tax) / 100)
                line.svat = svat
            else:
                line.svat = line.amount_tax

    @api.onchange('partner_id')
    def odoo_onchange_partner_id(self):
        """calling the order line function to compute"""
        self.order_line._compute_tax_id()

    def _prepare_invoice(self):
        """Overing prepare invoice function and setting vat_type"""
        invoice_vals = super()._prepare_invoice()
        if self.order_line:
            for line in self.order_line:
                if line.tax_id:
                    invoice_vals['report_vat_type'] = self.vat_type
                    invoice_vals['vat_type'] = self.vat_type
        return invoice_vals


class InheritSaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _compute_tax_id(self):
        for line in self:
            """overding core function"""
            fpos = line.order_id.fiscal_position_id or line.order_id.partner_id.property_account_position_id
            # If company_id is set, always filter taxes by the company
            taxes = line.product_id.taxes_id.filtered(lambda r: not line.company_id or r.company_id == line.company_id)
            if line.order_id:
                if line.order_id.vat_type  == 'vat':
                    taxes = taxes.filtered(lambda x: x.vat_type == 'vat')
                elif line.order_id.vat_type  == 's_vat':
                    taxes = taxes.filtered(lambda x: x.vat_type == 's_vat')
                else:
                    taxes = False
            if taxes:
                line.tax_id = fpos.map_tax(taxes, line.product_id, line.order_id.partner_shipping_id) if fpos else taxes

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """ Overriding core function to add taxes automatically based on the vat type when selecting the product """
        if not self.product_id:
            return
        self._reset_price_unit()
        # Start Overriding
        if self.order_id.vat_type == 'vat':
            taxes = self.product_id.mapped('taxes_id').filtered(
                lambda x: not self.company_id or x.company_id == self.company_id and x.vat_type == 'vat')
            if taxes:
                self.tax_id = taxes.ids
        elif self.order_id.vat_type == 's_vat':
            taxes = self.product_id.mapped('taxes_id').filtered(
                lambda x: not self.company_id or x.company_id == self.company_id and x.vat_type == 's_vat')
            if taxes:
                self.tax_id = taxes.ids
        else:
            self.tax_id = False


class InheritAccountMove(models.Model):
    _inherit = 'account.move'

    svat = fields.Float(string="SVAT Amount", compute='get_svat_value')
    vat_type = fields.Selection([('non_vat', 'Non VAT'), ('s_vat', 'SVAT'), ('vat', 'VAT')], string="Partner VAT Type")
    report_vat_type = fields.Selection([('non_vat', 'Non VAT'), ('s_vat', 'SVAT'), ('vat', 'VAT')], string="VAT Type",
                                       store=True)

    # @api.onchange('partner_id')
    # def onchange_partner_vat(self):
    #     """Onchange partner id, set vat type of partner"""
    #     self.report_vat_type = self.partner_id.vat_type

    @api.depends('amount_untaxed')
    def get_svat_value(self):
        """get svat amount calculation"""
        for line in self:
            if line.vat_type == 's_vat':
                svat = 0
                for item in line.invoice_line_ids:
                    if_tax = item.tax_ids
                    tax = if_tax[0].amount if if_tax else 0
                    svat += item.price_subtotal * ((tax) / 100)
                line.svat = svat
            else:
                line.svat = line.amount_tax

            if line.invoice_line_ids:
                for move in line.invoice_line_ids:
                    if move.tax_ids:
                        line.write({'report_vat_type': move.tax_ids[0].vat_type, 'vat_type': move.tax_ids[0].vat_type})
                        break
            if line.invoice_origin:
                sales_obj = self.env['sale.order'].search([('name', '=', line.invoice_origin)])
                if sales_obj:
                    line.write({'vat_type': sales_obj.vat_type})
                    break

    @api.onchange('partner_id')
    def odoo_onchange_partner_id(self):
        """calling the order line function to compute"""
        for line in self.invoice_line_ids:
            line._onchange_product_id()


class InheritAccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _get_computed_taxes(self):
        self.ensure_one()

        company_domain = self.env['account.tax']._check_company_domain(self.move_id.company_id)
        if self.move_id.is_sale_document(include_receipts=True):
            # Out invoice.
            filtered_taxes_id = self.product_id.taxes_id.filtered_domain(company_domain)
            tax_ids = filtered_taxes_id or self.account_id.tax_ids.filtered(lambda tax: tax.type_tax_use == 'sale')
            if self.move_id.partner_id:
                if self.move_id.partner_id.vat_type in ['non_vat', 'vat']:
                    tax_ids = tax_ids.filtered(lambda x: x.vat_type == 'vat')
                else:
                    tax_ids = tax_ids.filtered(lambda x: x.vat_type == 's_vat')

        elif self.move_id.is_purchase_document(include_receipts=True):
            # In invoice.
            filtered_supplier_taxes_id = self.product_id.supplier_taxes_id.filtered_domain(company_domain)
            tax_ids = filtered_supplier_taxes_id or self.account_id.tax_ids.filtered(
                lambda tax: tax.type_tax_use == 'purchase')
            if self.move_id.partner_id:
                if self.move_id.partner_id.vat_type in ['non_vat', 'vat']:
                    tax_ids = tax_ids.filtered(lambda x: x.vat_type == 'vat')
                else:
                    tax_ids = tax_ids.filtered(lambda x: x.vat_type == 's_vat')

        else:
            tax_ids = False if self.env.context.get('skip_computed_taxes') else self.account_id.tax_ids

        if self.company_id and tax_ids:
            tax_ids = tax_ids._filter_taxes_by_company(self.company_id)

        if tax_ids and self.move_id.fiscal_position_id:
            tax_ids = self.move_id.fiscal_position_id.map_tax(tax_ids)

        return tax_ids