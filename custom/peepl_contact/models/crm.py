# inheriting from crm.lead to override the all operations, every operation will be logged into the contact related to the lead

import logging
from odoo import models, api, fields
_logger = logging.getLogger(__name__)
class CrmLead(models.Model):
    _inherit = 'crm.lead'

    def message_post(self, **kwargs):
        res = super(CrmLead, self).message_post(**kwargs)
        # Also post to related partner if exists
        if self.partner_id and getattr(self.partner_id, 'enable_crm_lead_logging', False):
            # Prefix for clarity
            body = kwargs.get('body', '')
            subject = kwargs.get('subject', 'Lead Note')
            partner_body = f"<b>[Lead Note]</b> (from Lead: {self.name})<br/>{body}"
            self.partner_id.message_post(
                body=partner_body,
                message_type=kwargs.get('message_type', 'comment'),
                subject=subject
            )
        return res

    @api.model
    def create(self, vals):
        """Override create method to log activity in related contact"""
        lead = super(CrmLead, self).create(vals)
        if lead.partner_id and getattr(lead.partner_id, 'enable_crm_activity_logging', False):
            lead.partner_id.log_activity('create', lead)
        return lead

    def write(self, vals):
        """Override write method to log activity in related contact with changed fields"""
        # Capture old values for changed fields
        changed_fields = list(vals.keys())
        old_values = {}
        for lead in self:
            for field in changed_fields:
                old_values.setdefault(lead.id, {})[field] = getattr(lead, field, False)
        # Perform the write
        result = super(CrmLead, self).write(vals)
        # Log changes after update
        for lead in self:
            if lead.partner_id and getattr(lead.partner_id, 'enable_crm_activity_logging', False):
                changes = []
                for field in changed_fields:
                    old_val = old_values.get(lead.id, {}).get(field, False)
                    new_val = getattr(lead, field, False)
                    if old_val != new_val:
                        changes.append({
                            'field': field,
                            'old': old_val,
                            'new': new_val
                        })
                lead.partner_id.log_activity('write', lead, changes)
        return result

    def unlink(self):
        """Override unlink method to log activity in related contact"""
        for lead in self:
            if lead.partner_id and getattr(lead.partner_id, 'enable_crm_activity_logging', False):
                lead.partner_id.log_activity('unlink', lead)
        return super(CrmLead, self).unlink()