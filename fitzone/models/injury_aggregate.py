from odoo import fields, models, tools


class InjuryAggregate(models.Model):
    _name = 'fitzone.injury.aggregate'
    _description = 'Aggregate Injury Statistics'
    _auto = False
    _rec_name = 'injury_cause'

    injury_cause = fields.Char(readonly=True)
    sport_type = fields.Char(readonly=True)
    count = fields.Integer(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW fitzone_injury_aggregate AS
            SELECT row_number() OVER (ORDER BY c.name, r.sport_type) AS id,
                   c.name AS injury_cause, r.sport_type, count(DISTINCT r.injury_id)::integer AS count
            FROM fitzone_rehabilitation r
            JOIN fitzone_injury i ON i.id = r.injury_id
            LEFT JOIN fitzone_injury_cause c ON c.id = i.injury_cause_id
            GROUP BY c.name, r.sport_type
        """)
