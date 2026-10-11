from odoo import fields, models


class TrainerSchedule(models.Model):
    """Unified, read-only schedule: classes + PT + pool."""

    _name = 'fitzone.trainer.schedule'
    _description = 'Unified Trainer Schedule'
    _auto = False
    _order = 'start_datetime'
    _rec_name = 'name'

    trainer_id = fields.Many2one('fitzone.trainer', readonly=True)

    activity_type = fields.Selection(
        [
            ('class', 'Group Class'),
            ('pt', 'Personal Training'),
            ('pool', 'Pool Private Session'),
        ],
        readonly=True,
    )

    name = fields.Char(readonly=True)
    start_datetime = fields.Datetime(readonly=True)
    end_datetime = fields.Datetime(readonly=True)
    duration_hours = fields.Float(readonly=True)
    member_id = fields.Many2one('res.partner', readonly=True)
    member_count = fields.Integer(readonly=True)
    res_model = fields.Char(readonly=True)
    res_id = fields.Integer(readonly=True)

    def init(self):
        self.env.cr.execute(
            "DROP VIEW IF EXISTS %s" % self._table
        )

        self.env.cr.execute("""
            CREATE VIEW %s AS (
                SELECT
                    t.id,
                    t.activity_type,
                    t.trainer_id,
                    t.name,
                    t.start_datetime,
                    t.end_datetime,
                    EXTRACT(
                        EPOCH FROM (
                            t.end_datetime - t.start_datetime
                        )
                    ) / 3600.0 AS duration_hours,
                    t.member_id,
                    t.member_count,
                    t.res_model,
                    t.res_id
                FROM (
                    -- Group classes
                    SELECT
                        (c.id::bigint * 10 + 1) AS id,
                        'class'::varchar AS activity_type,
                        c.trainer_id AS trainer_id,
                        c.name::varchar AS name,
                        c.start_datetime AS start_datetime,
                        c.end_datetime AS end_datetime,
                        NULL::integer AS member_id,
                        (
                            SELECT COUNT(*)::integer
                            FROM fitzone_class_booking cb
                            WHERE cb.class_id = c.id
                              AND cb.status IN ('booked', 'attended')
                        ) AS member_count,
                        'fitzone.gym.class'::varchar AS res_model,
                        c.id AS res_id
                    FROM fitzone_gym_class c
                    WHERE c.trainer_id IS NOT NULL
                      AND c.start_datetime IS NOT NULL
                      AND c.end_datetime IS NOT NULL
                      AND c.end_datetime > c.start_datetime

                    UNION ALL

                    -- Personal training sessions
                    SELECT
                        (s.id::bigint * 10 + 2) AS id,
                        'pt'::varchar AS activity_type,
                        s.trainer_id AS trainer_id,
                        'Personal Training'::varchar AS name,
                        s.session_date AS start_datetime,
                        s.end_datetime AS end_datetime,
                        s.member_id AS member_id,
                        0::integer AS member_count,
                        'fitzone.pt.session'::varchar AS res_model,
                        s.id AS res_id
                    FROM fitzone_pt_session s
                    WHERE s.trainer_id IS NOT NULL
                      AND s.session_date IS NOT NULL
                      AND s.end_datetime IS NOT NULL
                      AND s.end_datetime > s.session_date
                      AND COALESCE(s.state, '') != 'cancelled'

                    UNION ALL

                    -- Pool bookings
                    SELECT
                        (b.id::bigint * 10 + 3) AS id,
                        'pool'::varchar AS activity_type,
                        b.trainer_id AS trainer_id,
                        'Pool Private Session'::varchar AS name,
                        date_trunc('day', b.booking_date)
                            + (
                                sl.start_time * interval '1 hour'
                            ) AS start_datetime,
                        date_trunc('day', b.booking_date)
                            + (
                                sl.end_time * interval '1 hour'
                            ) AS end_datetime,
                        b.member_id AS member_id,
                        0::integer AS member_count,
                        'fitzone.pool.booking'::varchar AS res_model,
                        b.id AS res_id
                    FROM fitzone_pool_booking b
                    JOIN fitzone_pool_slot sl
                      ON sl.id = b.pool_slot_id
                    WHERE b.trainer_id IS NOT NULL
                      AND b.booking_date IS NOT NULL
                      AND COALESCE(b.status, '') != 'cancelled'
                      AND sl.end_time > sl.start_time
                ) t
            )
        """ % self._table)
