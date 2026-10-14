"""Preserve legacy selections before ORM type conversion; never create departments."""
import logging
from psycopg2 import sql
from odoo import api, models

_logger = logging.getLogger(__name__)
# Historical labels are migration aliases only, never reporting categories.
LEGACY_LABELS = {'gym': 'Gym', 'pool': 'Swimming Pool', 'physio': 'Physical Therapy',
                 'nutrition': 'Nutrition', 'retail': 'Retail Sales'}


def preserve_selection(cr, table, column):
    cr.execute("""SELECT data_type FROM information_schema.columns
        WHERE table_schema=current_schema() AND table_name=%s AND column_name=%s""", (table, column))
    row = cr.fetchone()
    if row and row[0] in ('character varying', 'text'):
        cr.execute(sql.SQL('ALTER TABLE {} RENAME COLUMN {} TO {}').format(
            sql.Identifier(table), sql.Identifier(column), sql.Identifier(column+'_legacy')))

    cr.execute("""SELECT 1 FROM information_schema.columns
        WHERE table_schema=current_schema() AND table_name=%s AND column_name=%s""", (table, column+'_legacy'))
    if cr.fetchone():
        cr.execute(sql.SQL('ALTER TABLE {} ALTER COLUMN {} DROP NOT NULL').format(
            sql.Identifier(table), sql.Identifier(column+'_legacy')))


class DepartmentMigration(models.Model):
    _inherit = 'hr.department'

    @api.model
    def _migrate_fitzone_departments(self):
        """Map unique names within the record company (or shared departments).

        Unmatched/ambiguous source values remain in backup columns for review and
        later retries. Successful mappings clear only the backup value; subsequent
        upgrades never overwrite an allocation made by the client.
        """
        self.env.flush_all()
        unresolved = []
        for table, column in [('product_template', 'fitzone_department'),
                              ('fitzone_management_expense', 'department')]:
            backup = column+'_legacy'
            self.env.cr.execute("""SELECT 1 FROM information_schema.columns
                WHERE table_schema=current_schema() AND table_name=%s AND column_name=%s""", (table, backup))
            if not self.env.cr.fetchone():
                continue
            self.env.cr.execute(sql.SQL('SELECT id, {}, company_id FROM {} WHERE {} IS NOT NULL AND {} IS NULL').format(
                sql.Identifier(backup), sql.Identifier(table), sql.Identifier(backup), sql.Identifier(column)))
            for record_id, value, company_id in self.env.cr.fetchall():
                label = LEGACY_LABELS.get(value, value)
                self.env.cr.execute('''SELECT id FROM hr_department WHERE EXISTS (
                    SELECT 1 FROM jsonb_each_text(name) n WHERE lower(n.value)=lower(%s))
                    AND (company_id IS NULL OR company_id=%s)''', (label, company_id))
                matches = self.env.cr.fetchall()
                if len(matches) != 1:
                    unresolved.append({'table': table, 'id': record_id, 'value': value, 'label': label})
                    continue
                self.env.cr.execute(sql.SQL('UPDATE {} SET {}=%s, {}=NULL WHERE id=%s AND {} IS NULL').format(
                    sql.Identifier(table), sql.Identifier(column), sql.Identifier(backup), sql.Identifier(column)),
                    (matches[0][0], record_id))
        self.env.invalidate_all()
        if unresolved:
            _logger.warning('FitZone unmapped legacy departments (no records created): %s', unresolved)
        return unresolved
