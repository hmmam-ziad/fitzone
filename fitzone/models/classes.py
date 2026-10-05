from odoo import api, fields, models
from odoo.exceptions import ValidationError


class Room(models.Model):
    _name = 'fitzone.room'
    _description = 'Room / Studio'

    name = fields.Char(required=True)
    capacity = fields.Integer(required=True)

    @api.constrains('capacity')
    def _check_capacity(self):
        for rec in self:
            if rec.capacity <= 0:
                raise ValidationError('Room capacity must be greater than zero.')


class GymClass(models.Model):
    _name = 'fitzone.gym.class'
    _description = 'Group Class'
    _order = 'start_datetime'

    name = fields.Char(required=True)
    trainer_id = fields.Many2one('fitzone.trainer', required=True)
    room_id = fields.Many2one('fitzone.room', required=True)
    capacity = fields.Integer()
    start_datetime = fields.Datetime(required=True)
    end_datetime = fields.Datetime(required=True)
    booking_ids = fields.One2many('fitzone.class.booking', 'class_id')

    @api.onchange('room_id')
    def _onchange_room_id(self):
        if self.room_id:
            self.capacity = self.room_id.capacity

    @api.constrains('start_datetime', 'end_datetime', 'capacity', 'room_id', 'trainer_id')
    def _check_class(self):
        for rec in self:
            if rec.end_datetime <= rec.start_datetime:
                raise ValidationError('End time must be after start time.')
            if rec.room_id and rec.capacity > rec.room_id.capacity:
                raise ValidationError(
                    'Class capacity cannot exceed the room capacity (%s).'
                    % rec.room_id.capacity)
            overlap = self.search([
                ('id', '!=', rec.id),
                ('trainer_id', '=', rec.trainer_id.id),
                ('start_datetime', '<', rec.end_datetime),
                ('end_datetime', '>', rec.start_datetime),
            ], limit=1)
            if overlap:
                raise ValidationError(
                    'Trainer %s is already booked in another class at this time.'
                    % rec.trainer_id.name)


class ClassBooking(models.Model):
    _name = 'fitzone.class.booking'
    _description = 'Class Booking'

    member_id = fields.Many2one(
        'res.partner', string='Member', required=True, ondelete='restrict')
    membership_id = fields.Many2one(
        'fitzone.membership', string='Membership', required=True, ondelete='restrict')
    class_id = fields.Many2one(
        'fitzone.gym.class', string='Class', required=True, ondelete='cascade')
    booking_date = fields.Datetime(default=fields.Datetime.now)
    status = fields.Selection([
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    ], default='confirmed', required=True)

    _member_class_uniq = models.Constraint(
        'unique(member_id, class_id)', 'This member is already booked in this class.')

    @api.constrains('class_id', 'status')
    def _check_capacity(self):
        for rec in self:
            confirmed = self.search_count([
                ('class_id', '=', rec.class_id.id),
                ('status', '=', 'confirmed'),
            ])
            if confirmed > rec.class_id.capacity:
                raise ValidationError('This class is full.')


class Attendance(models.Model):
    _name = 'fitzone.attendance'
    _description = 'Class Attendance'

    booking_id = fields.Many2one(
        'fitzone.class.booking', string='Booking', required=True, ondelete='cascade')
    attended = fields.Boolean()

    _booking_uniq = models.Constraint(
        'unique(booking_id)', 'Attendance is already recorded for this booking.')