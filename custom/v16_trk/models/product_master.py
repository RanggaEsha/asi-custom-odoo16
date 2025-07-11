# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import odoo.addons.decimal_precision as dp
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from odoo.osv import expression

class TrkValveTag(models.Model):
    _name = 'trk.valve.tag'

    name = fields.Char('Valve Tag')
    code = fields.Char('Code')

class TrkDatasheet(models.Model):
    _name = 'trk.datasheet'

    name = fields.Char('Datasheet')
    code = fields.Char('Code')

class TrkBodyConstruction(models.Model):
    _name = 'trk.body.construction'

    name = fields.Char('Body Construction')
    code = fields.Char('Code')
    
class TrkTypeDesign(models.Model):
    _name = 'trk.type.design'

    name = fields.Char('Type Design')
    code = fields.Char('Code')
    
class TrkSeatDesign(models.Model):
    _name = 'trk.seat.design'

    name = fields.Char('Seat Design')
    code = fields.Char('Code')
    
class TrkSize(models.Model):
    _name = 'trk.size'

    name = fields.Char('Size')
    code = fields.Char('Code')
    
class TrkRating(models.Model):
    _name = 'trk.rating'

    name = fields.Char('Rating')
    code = fields.Char('Code')
    
class TrkBore(models.Model):
    _name = 'trk.bore'
    
    name = fields.Char('Bore')
    code = fields.Char('Code')
    
class TrkEndCon(models.Model):
    _name = 'trk.end.con'

    name = fields.Char('End Con')
    code = fields.Char('Code')
    
class TrkBody(models.Model):
    _name = 'trk.body'

    name = fields.Char('Body')
    code = fields.Char('Code')
    
class TrkBall(models.Model):
    _name = 'trk.ball'

    name = fields.Char('Ball')
    code = fields.Char('Code')
    
class TrkSeat(models.Model):
    _name = 'trk.seat'

    name = fields.Char('Seat')
    code = fields.Char('Code')
    
class TrkSeatInsert(models.Model):
    _name = 'trk.seat.insert'

    name = fields.Char('Seat Insert')
    code = fields.Char('Code')
    
class TrkStem(models.Model):
    _name = 'trk.stem'

    name = fields.Char('Stem')
    code = fields.Char('Code')
    
class TrkSeal(models.Model):
    _name = 'trk.seal'

    name = fields.Char('Seal')
    code = fields.Char('Code')
    
class TrkBolt(models.Model):
    _name = 'trk.bolt'

    name = fields.Char('Bolt')
    code = fields.Char('Code')
    
class TrkDisc(models.Model):
    _name = 'trk.disc'

    name = fields.Char('Disc')
    code = fields.Char('Code')
    
class TrkShaft(models.Model):
    _name = 'trk.shaft'

    name = fields.Char('Shaft')
    code = fields.Char('Code')
    
class TrkArmPin(models.Model):
    _name = 'trk.arm.pin'

    name = fields.Char('Arm Pin')
    code = fields.Char('Code')
    
class TrkBackseat(models.Model):
    _name = 'trk.backseat'

    name = fields.Char('Backseat')
    code = fields.Char('Code')
    
class TrkPlates(models.Model):
    _name = 'trk.plates'

    name = fields.Char('Plates')
    code = fields.Char('Code')
    
class TrkSpring(models.Model):
    _name = 'trk.spring'

    name = fields.Char('Spring')
    code = fields.Char('Code')
    
class TrkArm(models.Model):
    _name = 'trk.arm'

    name = fields.Char('Arm')
    code = fields.Char('Code')
    
class TrkHingePin(models.Model):
    _name = 'trk.hinge.pin'

    name = fields.Char('Hinge Pin')
    code = fields.Char('Code')
    
class TrkStopPin(models.Model):
    _name = 'trk.stop.pin'

    name = fields.Char('Stop Pin')
    code = fields.Char('Code')
    
class TrkOperator(models.Model):
    _name = 'trk.operator'

    name = fields.Char('Operator')
    code = fields.Char('Code')
    