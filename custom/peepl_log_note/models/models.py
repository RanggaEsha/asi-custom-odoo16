# -*- coding: utf-8 -*-


from odoo import models, fields, api, _


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def action_open_log_note_dashboard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Log Notes'),
            'res_model': 'mail.message',
            'view_mode': 'tree',
            'target': 'current',
            'domain': [
                ('model', '=', 'res.partner'),
                ('res_id', '=', self.id),
                ('message_type', '=', 'comment'),
                ('subtype_id.name', '=', 'Note'),
            ],
            'context': {
                'default_model': 'res.partner',
                'default_res_id': self.id,
            },
        }
