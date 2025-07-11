# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2019-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################
from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.exceptions import UserError


class CancelPurchaseRequest(models.TransientModel):
    _name = 'cancel.purchase.request'

    reason = fields.Text('Reason')

    def execute(self):
        request_id = self.env.context.get('active_id', False)
        request_obj = self.env['purchase.request'].browse(request_id)

        # Send Mail
        # mail_to = request_obj.create_uid.login
        mail_to = "samuel.alfius@gmail.com"
        data_template = self.env.ref('v16_asi.mail_template_purchase_request_cancelled')
        template = self.env['mail.template'].browse(data_template.id)
        email_values = {'email_to': mail_to}
        template.send_mail(request_obj.id, force_send=True, email_values=email_values)
        request_obj.write({
            'reason' : self.reason,
            'state' : 'Cancelled'
        })

        return {'type': 'ir.actions.act_window_close'}
