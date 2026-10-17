from odoo import Command, api, models


class ResGroups(models.Model):
    _inherit = 'res.groups'

    @api.model
    def _configure_fitzone_admin_interface(self):
        # The exemption is noupdate so assignments are initialized only once.
        self.env.ref('fitzone.group_fitzone_full_admin_ui').write({
            'implied_ids': [Command.link(self.env.ref('fitzone.group_fitzone_manager').id)],
        })

    @api.model
    def _initialize_fitzone_admin_interface(self):
        """One-time XML migration; keep existing administrators' interface intact."""
        parameters = self.env['ir.config_parameter']
        key = 'fitzone.admin_interface_initialized'
        if not parameters.get_param(key):
            users = self.env.ref('base.group_system').with_context(active_test=False).all_user_ids
            users.write({'group_ids': [Command.link(
                self.env.ref('fitzone.group_fitzone_full_admin_ui').id)]})
            parameters.set_param(key, 'True')

    @api.model
    def _merge_fitzone_owner_group(self):
        """Upgrade data step: preserve access before removing the legacy role.

        Private so it cannot be called through RPC. The XML loader calls it
        after defining Manager, on installation and every upgrade.
        """
        manager = self.env.ref('fitzone.group_fitzone_manager')
        owner = self.env.ref('fitzone.group_fitzone_owner', raise_if_not_found=False)
        if owner:
            # Include archived users and users inheriting Owner via other groups.
            users = owner.with_context(active_test=False).all_user_ids
            users.write({'group_ids': [Command.link(manager.id)]})
            owner.implied_by_ids.write({'implied_ids': [Command.link(manager.id)]})
            owner.unlink()
        privilege = self.env.ref('fitzone.privilege_fitzone_owner', raise_if_not_found=False)
        if privilege:
            privilege.unlink()

    @api.model
    def _cleanup_fitzone_legacy_dashboard(self):
        """Remove legacy XML records only when present, also safe on fresh installs."""
        for name in ['menu_management_overview', 'action_management_dashboard', 'view_management_dashboard_form', 'view_management_finance_graph', 'view_management_finance_pivot', 'view_management_injury_graph', 'view_management_injury_pivot', 'view_management_workload_graph', 'view_management_workload_pivot', 'access_task34_fitzone_management_dashboard_manager', 'access_management_report_line_manager']:
            record = self.env.ref('fitzone.' + name, raise_if_not_found=False)
            if record:
                record.unlink()
