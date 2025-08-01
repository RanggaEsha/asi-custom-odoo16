# -*- coding: utf-8 -*-

from odoo import models, fields


class ProjectTask(models.Model):
    _inherit = 'project.task'

    project_participant_ids = fields.Many2many(
        comodel_name='participant',
        compute='_compute_project_participant_ids',
        string='Project Participants',
        readonly=True,
        help='Participants linked to the parent project.'
    )

    has_project_participants = fields.Boolean(
        string='Has Project Participants',
        compute='_compute_has_project_participants',
        store=False
    )

    def _compute_has_project_participants(self):
        for task in self:
            task.has_project_participants = bool(task.project_id and task.project_id.participant_ids)

    def _compute_project_participant_ids(self):
        for task in self:
            if task.project_id and task.project_id.participant_ids:
                task.project_participant_ids = task.project_id.participant_ids
            else:
                task.project_participant_ids = False
