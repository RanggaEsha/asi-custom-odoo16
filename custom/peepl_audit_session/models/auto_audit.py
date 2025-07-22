# -*- coding: utf-8 -*-

import json
import logging
from datetime import datetime
from odoo import models, api, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


class BaseModel(models.AbstractModel):
    """Extend BaseModel to add automatic audit logging"""
    _inherit = 'base'

    def _should_audit_operation(self, operation):
        """Check if operation should be audited for this model and user"""
        try:
            # Skip during module installation/upgrade
            if self.env.context.get('module') or self.env.context.get('install_mode'):
                return False
            
            # Skip if we're in a test environment or during init
            if self.env.context.get('test_enable') or hasattr(self.env, '_cr') and self.env._cr.is_test:
                return False
                
            # Skip audit models themselves to prevent infinite loops
            if self._name.startswith('audit.'):
                return False
                
            # Skip system models that generate too much noise
            skip_models = [
                'ir.logging', 'ir.attachment', 'ir.translation', 'ir.config_parameter',
                'ir.cron', 'ir.mail_server', 'ir.sequence', 'bus.bus', 'ir.ui.view'
            ]
            if self._name in skip_models:
                return False
            
            # Check if audit tables exist (safety check during installation)
            try:
                self.env.cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'audit_config' LIMIT 1")
                if not self.env.cr.fetchone():
                    return False
            except Exception:
                return False
                
            # Get active configuration
            config = self.env['audit.config'].sudo().get_active_config()
            if not config:
                return False
                
            # Check if current user should be audited
            current_user = self.env.user.id if self.env.user else None
            if not current_user or not config.should_audit_user(current_user):
                return False
                
            # Check if this model should be audited
            if not config.should_audit_model(self._name):
                return False
                
            # Check if this operation type is enabled
            operation_checks = {
                'create': config.log_create,
                'write': config.log_write,
                'read': config.log_read,
                'unlink': config.log_unlink
            }
            
            return operation_checks.get(operation, False)
            
        except Exception as e:
            _logger.debug(f"Error checking audit operation for {self._name}: {e}")
            return False

    def _get_current_session_id(self):
        """Get current audit session ID"""
        try:
            if request and hasattr(request, 'session') and request.session.uid:
                session = self.env['audit.session'].sudo().search([
                    ('session_id', '=', request.session.sid),
                    ('user_id', '=', request.session.uid),
                    ('status', '=', 'active')
                ], limit=1)
                return session.id if session else None
        except Exception:
            pass
        return None

    def _prepare_audit_values(self, vals, operation):
        """Prepare values for audit logging, filtering sensitive data"""
        if not vals:
            return vals
            
        # Fields to exclude from logging
        exclude_fields = {
            'password', 'access_token', 'api_key', 'secret', '__last_update',
            'write_date', 'write_uid', 'create_date', 'create_uid'
        }
        
        # Filter out excluded fields
        filtered_vals = {}
        for key, value in vals.items():
            if key not in exclude_fields:
                # Handle special field types
                if isinstance(value, datetime):
                    filtered_vals[key] = value.isoformat()
                elif hasattr(value, 'ids'):  # Many2many/One2many fields
                    filtered_vals[key] = f"[{len(value)} records]"
                else:
                    filtered_vals[key] = value
                    
        return filtered_vals

    @api.model_create_multi  
    def create(self, vals_list):
        """Override create to add audit logging"""
        records = super().create(vals_list)
        
        if self._should_audit_operation('create'):
            session_id = self._get_current_session_id()
            
            for record, vals in zip(records, vals_list):
                try:
                    audit_vals = self._prepare_audit_values(vals, 'create')
                    
                    self.env['audit.log.entry'].sudo().create({
                        'user_id': self.env.user.id,
                        'session_id': session_id,
                        'model_id': self.env['ir.model'].sudo().search([('model', '=', self._name)], limit=1).id,
                        'res_id': record.id,
                        'res_name': record.display_name if hasattr(record, 'display_name') else f"ID: {record.id}",
                        'action_type': 'create',
                        'action_date': fields.Datetime.now(),
                        'method': 'create',
                        'new_values': json.dumps(audit_vals) if audit_vals else None,
                    })
                except Exception as e:
                    _logger.warning(f"Failed to log create operation for {self._name}: {e}")
                    
        return records

    def write(self, vals):
        """Override write to add audit logging"""
        if not vals:
            return super().write(vals)
            
        # Store old values before write
        old_values_by_record = {}
        if self._should_audit_operation('write'):
            session_id = self._get_current_session_id()
            
            for record in self:
                old_values = {}
                for field_name in vals.keys():
                    if field_name in record._fields and hasattr(record, field_name):
                        try:
                            old_values[field_name] = getattr(record, field_name)
                        except Exception:
                            old_values[field_name] = "<could not read>"
                old_values_by_record[record.id] = old_values
        
        # Perform the write operation
        result = super().write(vals)
        
        # Log the audit entry
        if self._should_audit_operation('write'):
            for record in self:
                try:
                    old_vals = old_values_by_record.get(record.id, {})
                    audit_old_vals = self._prepare_audit_values(old_vals, 'write')
                    audit_new_vals = self._prepare_audit_values(vals, 'write')
                    
                    # Determine which fields actually changed
                    changed_fields = []
                    for field_name in vals.keys():
                        if field_name in old_vals:
                            if old_vals[field_name] != vals[field_name]:
                                changed_fields.append(field_name)
                    
                    if changed_fields:  # Only log if something actually changed
                        self.env['audit.log.entry'].sudo().create({
                            'user_id': self.env.user.id,
                            'session_id': session_id,
                            'model_id': self.env['ir.model'].sudo().search([('model', '=', self._name)], limit=1).id,
                            'res_id': record.id,
                            'res_name': record.display_name if hasattr(record, 'display_name') else f"ID: {record.id}",
                            'action_type': 'write',
                            'action_date': fields.Datetime.now(),
                            'method': 'write',
                            'old_values': json.dumps(audit_old_vals) if audit_old_vals else None,
                            'new_values': json.dumps(audit_new_vals) if audit_new_vals else None,
                            'changed_fields': json.dumps(changed_fields) if changed_fields else None,
                        })
                except Exception as e:
                    _logger.warning(f"Failed to log write operation for {self._name}: {e}")
                    
        return result

    def unlink(self):
        """Override unlink to add audit logging"""
        # Store record info before deletion
        records_info = []
        if self._should_audit_operation('unlink'):
            session_id = self._get_current_session_id()
            
            for record in self:
                try:
                    # Get all stored field values
                    old_values = {}
                    for field_name, field in record._fields.items():
                        if field.store and hasattr(record, field_name):
                            try:
                                old_values[field_name] = getattr(record, field_name)
                            except Exception:
                                old_values[field_name] = "<could not read>"
                    
                    records_info.append({
                        'id': record.id,
                        'name': record.display_name if hasattr(record, 'display_name') else f"ID: {record.id}",
                        'values': old_values
                    })
                except Exception as e:
                    _logger.warning(f"Failed to prepare unlink audit for {self._name}({record.id}): {e}")
        
        # Perform the unlink operation
        result = super().unlink()
        
        # Log the audit entries
        if self._should_audit_operation('unlink'):
            for record_info in records_info:
                try:
                    audit_vals = self._prepare_audit_values(record_info['values'], 'unlink')
                    
                    self.env['audit.log.entry'].sudo().create({
                        'user_id': self.env.user.id,
                        'session_id': session_id,
                        'model_id': self.env['ir.model'].sudo().search([('model', '=', self._name)], limit=1).id,
                        'res_id': record_info['id'],
                        'res_name': record_info['name'],
                        'action_type': 'unlink',
                        'action_date': fields.Datetime.now(),
                        'method': 'unlink',
                        'old_values': json.dumps(audit_vals) if audit_vals else None,
                    })
                except Exception as e:
                    _logger.warning(f"Failed to log unlink operation for {self._name}: {e}")
                    
        return result

    def read(self, fields=None, load='_classic_read'):
        """Override read to add audit logging"""
        result = super().read(fields, load)
        
        # Only log read operations if explicitly enabled and not too noisy
        if self._should_audit_operation('read') and len(self) <= 10:  # Limit to avoid spam
            session_id = self._get_current_session_id()
            
            for record in self:
                try:
                    # Only log read of specific important models or if explicitly requested
                    important_models = [
                        'res.users', 'res.partner', 'sale.order', 'purchase.order',
                        'account.move', 'hr.employee', 'project.project'
                    ]
                    
                    if self._name in important_models:
                        self.env['audit.log.entry'].sudo().create({
                            'user_id': self.env.user.id,
                            'session_id': session_id,
                            'model_id': self.env['ir.model'].sudo().search([('model', '=', self._name)], limit=1).id,
                            'res_id': record.id,
                            'res_name': record.display_name if hasattr(record, 'display_name') else f"ID: {record.id}",
                            'action_type': 'read',
                            'action_date': fields.Datetime.now(),
                            'method': 'read',
                            'context_info': json.dumps({'fields': fields}) if fields else None,
                        })
                except Exception as e:
                    _logger.debug(f"Failed to log read operation for {self._name}: {e}")
                    
        return result