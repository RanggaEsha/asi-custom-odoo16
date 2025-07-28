# -*- coding: utf-8 -*-
# Part of Peepl Sale Module

from odoo import api, fields, models, _


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def _selection_service_policy(self):
        """Override to add participant-based invoicing option"""
        service_policies = super()._selection_service_policy()
        
        # Insert participant policy after milestones
        participant_policy = ('delivered_participants', _('Based on Participants'))
        
        # Find the position to insert (after milestones if it exists)
        insert_pos = len(service_policies)
        for i, (policy, label) in enumerate(service_policies):
            if policy == 'delivered_milestones':
                insert_pos = i + 1
                break
            elif policy == 'delivered_manual':
                insert_pos = i
                break
        
        service_policies.insert(insert_pos, participant_policy)
        return service_policies

    service_type = fields.Selection(
        selection_add=[('participants', 'Project Participants')],
        ondelete={'participants': 'set null'}
    )

    def _get_service_to_general_map(self):
        """Override to include participant mapping"""
        mapping = super()._get_service_to_general_map()
        mapping['delivered_participants'] = ('delivery', 'participants')
        return mapping

    @api.depends('service_tracking', 'service_policy', 'type')
    def _compute_product_tooltip(self):
        """Override to add participant policy tooltips"""
        super()._compute_product_tooltip()
        
        for record in self.filtered(lambda r: r.type == 'service' and r.service_policy == 'delivered_participants'):
            if record.service_tracking == 'no':
                record.product_tooltip = _(
                    "Invoice based on participant completion. "
                    "Create participants manually to track test completion."
                )
            elif record.service_tracking == 'task_global_project':
                record.product_tooltip = _(
                    "Invoice based on participant completion. "
                    "Create a task in an existing project and track participants."
                )
            elif record.service_tracking == 'project_only':
                record.product_tooltip = _(
                    "Invoice based on participant completion. "
                    "Create an empty project and track participants."
                )
            elif record.service_tracking == 'task_in_project':
                record.product_tooltip = _(
                    "Invoice based on participant completion. "
                    "Create a project with a task and track participants for each sales order line."
                )