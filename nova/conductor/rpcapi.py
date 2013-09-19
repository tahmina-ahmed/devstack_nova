#    Copyright 2013 IBM Corp.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Client side of the conductor RPC API."""

from oslo.config import cfg

from nova.objects import base as objects_base
from nova.openstack.common import jsonutils
from nova.openstack.common.rpc import common as rpc_common
import nova.openstack.common.rpc.proxy

CONF = cfg.CONF

rpcapi_cap_opt = cfg.StrOpt('conductor',
        default=None,
        help='Set a version cap for messages sent to conductor services')
CONF.register_opt(rpcapi_cap_opt, 'upgrade_levels')


class ConductorAPI(nova.openstack.common.rpc.proxy.RpcProxy):
    """Client side of the conductor RPC API

    API version history:

    1.0 - Initial version.
    1.1 - Added migration_update
    1.2 - Added instance_get_by_uuid and instance_get_all_by_host
    1.3 - Added aggregate_host_add and aggregate_host_delete
    1.4 - Added migration_get
    1.5 - Added bw_usage_update
    1.6 - Added get_backdoor_port()
    1.7 - Added aggregate_get_by_host, aggregate_metadata_add,
          and aggregate_metadata_delete
    1.8 - Added security_group_get_by_instance and
          security_group_rule_get_by_security_group
    1.9 - Added provider_fw_rule_get_all
    1.10 - Added agent_build_get_by_triple
    1.11 - Added aggregate_get
    1.12 - Added block_device_mapping_update_or_create
    1.13 - Added block_device_mapping_get_all_by_instance
    1.14 - Added block_device_mapping_destroy
    1.15 - Added instance_get_all_by_filters and
           instance_get_all_hung_in_rebooting and
           instance_get_active_by_window
           Deprecated instance_get_all_by_host
    1.16 - Added instance_destroy
    1.17 - Added instance_info_cache_delete
    1.18 - Added instance_type_get
    1.19 - Added vol_get_usage_by_time and vol_usage_update
    1.20 - Added migration_get_unconfirmed_by_dest_compute
    1.21 - Added service_get_all_by
    1.22 - Added ping
    1.23 - Added instance_get_all
           Un-Deprecate instance_get_all_by_host
    1.24 - Added instance_get
    1.25 - Added action_event_start and action_event_finish
    1.26 - Added instance_info_cache_update
    1.27 - Added service_create
    1.28 - Added binary arg to service_get_all_by
    1.29 - Added service_destroy
    1.30 - Added migration_create
    1.31 - Added migration_get_in_progress_by_host_and_node
    1.32 - Added optional node to instance_get_all_by_host
    1.33 - Added compute_node_create and compute_node_update
    1.34 - Added service_update
    1.35 - Added instance_get_active_by_window_joined
    1.36 - Added instance_fault_create
    1.37 - Added task_log_get, task_log_begin_task, task_log_end_task
    1.38 - Added service name to instance_update
    1.39 - Added notify_usage_exists
    1.40 - Added security_groups_trigger_handler and
                 security_groups_trigger_members_refresh
           Remove instance_get_active_by_window
    1.41 - Added fixed_ip_get_by_instance, network_get,
                 instance_floating_address_get_all, quota_commit,
                 quota_rollback
    1.42 - Added get_ec2_ids, aggregate_metadata_get_by_host
    1.43 - Added compute_stop
    1.44 - Added compute_node_delete
    1.45 - Added project_id to quota_commit and quota_rollback
    1.46 - Added compute_confirm_resize
    1.47 - Added columns_to_join to instance_get_all_by_host and
                 instance_get_all_by_filters
    1.48 - Added compute_unrescue

        ... Grizzly supports message version 1.48.  So, any changes to existing
        methods in 2.x after that point should be done such that they can
        handle the version_cap being set to 1.48.

    1.49 - Added columns_to_join to instance_get_by_uuid
    1.50 - Added object_action() and object_class_action()
    1.51 - Added the 'legacy' argument to
           block_device_mapping_get_all_by_instance
    1.52 - Pass instance objects for compute_confirm_resize
    1.53 - Added compute_reboot
    1.54 - Added 'update_cells' argument to bw_usage_update
    1.55 - Pass instance objects for compute_stop
    """

    BASE_RPC_API_VERSION = '1.0'

    VERSION_ALIASES = {
        'grizzly': '1.48',
    }

    def __init__(self):
        version_cap = self.VERSION_ALIASES.get(CONF.upgrade_levels.conductor,
                                               CONF.upgrade_levels.conductor)
        super(ConductorAPI, self).__init__(
            topic=CONF.conductor.topic,
            default_version=self.BASE_RPC_API_VERSION,
            serializer=objects_base.NovaObjectSerializer(),
            version_cap=version_cap)

    def instance_update(self, context, instance_uuid, updates,
                        service=None):
        updates_p = jsonutils.to_primitive(updates)
        return self.call(context,
                         self.make_msg('instance_update',
                                       instance_uuid=instance_uuid,
                                       updates=updates_p,
                                       service=service),
                         version='1.38')

    def instance_get(self, context, instance_id):
        msg = self.make_msg('instance_get',
                            instance_id=instance_id)
        return self.call(context, msg, version='1.24')

    def instance_get_by_uuid(self, context, instance_uuid,
                             columns_to_join=None):
        if self.can_send_version('1.49'):
            version = '1.49'
            msg = self.make_msg('instance_get_by_uuid',
                                instance_uuid=instance_uuid,
                                columns_to_join=columns_to_join)
        else:
            version = '1.2'
            msg = self.make_msg('instance_get_by_uuid',
                                instance_uuid=instance_uuid)
        return self.call(context, msg, version=version)

    def migration_get(self, context, migration_id):
        msg = self.make_msg('migration_get', migration_id=migration_id)
        return self.call(context, msg, version='1.4')

    def migration_get_unconfirmed_by_dest_compute(self, context,
                                                  confirm_window,
                                                  dest_compute):
        msg = self.make_msg('migration_get_unconfirmed_by_dest_compute',
                            confirm_window=confirm_window,
                            dest_compute=dest_compute)
        return self.call(context, msg, version='1.20')

    def migration_get_in_progress_by_host_and_node(self, context,
                                                   host, node):
        msg = self.make_msg('migration_get_in_progress_by_host_and_node',
                            host=host, node=node)
        return self.call(context, msg, version='1.31')

    def migration_create(self, context, instance, values):
        instance_p = jsonutils.to_primitive(instance)
        msg = self.make_msg('migration_create', instance=instance_p,
                            values=values)
        return self.call(context, msg, version='1.30')

    def migration_update(self, context, migration, status):
        migration_p = jsonutils.to_primitive(migration)
        msg = self.make_msg('migration_update', migration=migration_p,
                            status=status)
        return self.call(context, msg, version='1.1')

    def aggregate_host_add(self, context, aggregate, host):
        aggregate_p = jsonutils.to_primitive(aggregate)
        msg = self.make_msg('aggregate_host_add', aggregate=aggregate_p,
                            host=host)
        return self.call(context, msg, version='1.3')

    def aggregate_host_delete(self, context, aggregate, host):
        aggregate_p = jsonutils.to_primitive(aggregate)
        msg = self.make_msg('aggregate_host_delete', aggregate=aggregate_p,
                            host=host)
        return self.call(context, msg, version='1.3')

    def aggregate_get(self, context, aggregate_id):
        msg = self.make_msg('aggregate_get', aggregate_id=aggregate_id)
        return self.call(context, msg, version='1.11')

    def aggregate_get_by_host(self, context, host, key=None):
        msg = self.make_msg('aggregate_get_by_host', host=host, key=key)
        return self.call(context, msg, version='1.7')

    def aggregate_metadata_add(self, context, aggregate, metadata,
                               set_delete=False):
        aggregate_p = jsonutils.to_primitive(aggregate)
        msg = self.make_msg('aggregate_metadata_add', aggregate=aggregate_p,
                            metadata=metadata,
                            set_delete=set_delete)
        return self.call(context, msg, version='1.7')

    def aggregate_metadata_delete(self, context, aggregate, key):
        aggregate_p = jsonutils.to_primitive(aggregate)
        msg = self.make_msg('aggregate_metadata_delete', aggregate=aggregate_p,
                            key=key)
        return self.call(context, msg, version='1.7')

    def aggregate_metadata_get_by_host(self, context, host, key):
        msg = self.make_msg('aggregate_metadata_get_by_host', host=host,
                            key=key)
        return self.call(context, msg, version='1.42')

    def bw_usage_update(self, context, uuid, mac, start_period,
                        bw_in=None, bw_out=None,
                        last_ctr_in=None, last_ctr_out=None,
                        last_refreshed=None, update_cells=True):
        msg_kwargs = dict(uuid=uuid, mac=mac, start_period=start_period,
                          bw_in=bw_in, bw_out=bw_out, last_ctr_in=last_ctr_in,
                          last_ctr_out=last_ctr_out,
                          last_refreshed=last_refreshed)

        if self.can_send_version('1.54'):
            version = '1.54'
            msg_kwargs['update_cells'] = update_cells
        else:
            version = '1.5'

        msg = self.make_msg('bw_usage_update', **msg_kwargs)
        return self.call(context, msg, version=version)

    def security_group_get_by_instance(self, context, instance):
        instance_p = jsonutils.to_primitive(instance)
        msg = self.make_msg('security_group_get_by_instance',
                            instance=instance_p)
        return self.call(context, msg, version='1.8')

    def security_group_rule_get_by_security_group(self, context, secgroup):
        secgroup_p = jsonutils.to_primitive(secgroup)
        msg = self.make_msg('security_group_rule_get_by_security_group',
                            secgroup=secgroup_p)
        return self.call(context, msg, version='1.8')

    def provider_fw_rule_get_all(self, context):
        msg = self.make_msg('provider_fw_rule_get_all')
        return self.call(context, msg, version='1.9')

    def agent_build_get_by_triple(self, context, hypervisor, os, architecture):
        msg = self.make_msg('agent_build_get_by_triple',
                            hypervisor=hypervisor, os=os,
                            architecture=architecture)
        return self.call(context, msg, version='1.10')

    def block_device_mapping_update_or_create(self, context, values,
                                              create=None):
        msg = self.make_msg('block_device_mapping_update_or_create',
                            values=values, create=create)
        return self.call(context, msg, version='1.12')

    def block_device_mapping_get_all_by_instance(self, context, instance,
                                                 legacy=True):
        instance_p = jsonutils.to_primitive(instance)
        if self.can_send_version('1.51'):
            version = '1.51'
            msg = self.make_msg('block_device_mapping_get_all_by_instance',
                                instance=instance_p, legacy=legacy)
        elif legacy:
            # If the remote side is >= 1.51, it defaults to legacy=True.
            # If it's older, it only understands the legacy format.
            version = '1.13'
            msg = self.make_msg('block_device_mapping_get_all_by_instance',
                                instance=instance_p)
        else:
            # If we require new style data, but can't ask for it, then we must
            # fail here.
            raise rpc_common.RpcVersionCapError(version_cap=self.version_cap)

        return self.call(context, msg, version=version)

    def block_device_mapping_destroy(self, context, bdms=None,
                                     instance=None, volume_id=None,
                                     device_name=None):
        bdms_p = jsonutils.to_primitive(bdms)
        instance_p = jsonutils.to_primitive(instance)
        msg = self.make_msg('block_device_mapping_destroy',
                            bdms=bdms_p,
                            instance=instance_p, volume_id=volume_id,
                            device_name=device_name)
        return self.call(context, msg, version='1.14')

    def instance_get_all_by_filters(self, context, filters, sort_key,
                                    sort_dir, columns_to_join=None):
        msg = self.make_msg('instance_get_all_by_filters',
                            filters=filters, sort_key=sort_key,
                            sort_dir=sort_dir, columns_to_join=columns_to_join)
        return self.call(context, msg, version='1.47')

    def instance_get_active_by_window_joined(self, context, begin, end=None,
                                             project_id=None, host=None):
        msg = self.make_msg('instance_get_active_by_window_joined',
                            begin=begin, end=end, project_id=project_id,
                            host=host)
        return self.call(context, msg, version='1.35')

    def instance_destroy(self, context, instance):
        instance_p = jsonutils.to_primitive(instance)
        msg = self.make_msg('instance_destroy', instance=instance_p)
        self.call(context, msg, version='1.16')

    def instance_info_cache_delete(self, context, instance):
        instance_p = jsonutils.to_primitive(instance)
        msg = self.make_msg('instance_info_cache_delete', instance=instance_p)
        self.call(context, msg, version='1.17')

    def instance_type_get(self, context, instance_type_id):
        msg = self.make_msg('instance_type_get',
                            instance_type_id=instance_type_id)
        return self.call(context, msg, version='1.18')

    def vol_get_usage_by_time(self, context, start_time):
        start_time_p = jsonutils.to_primitive(start_time)
        msg = self.make_msg('vol_get_usage_by_time', start_time=start_time_p)
        return self.call(context, msg, version='1.19')

    def vol_usage_update(self, context, vol_id, rd_req, rd_bytes, wr_req,
                         wr_bytes, instance, last_refreshed=None,
                         update_totals=False):
        instance_p = jsonutils.to_primitive(instance)
        msg = self.make_msg('vol_usage_update', vol_id=vol_id, rd_req=rd_req,
                            rd_bytes=rd_bytes, wr_req=wr_req,
                            wr_bytes=wr_bytes,
                            instance=instance_p, last_refreshed=last_refreshed,
                            update_totals=update_totals)
        return self.call(context, msg, version='1.19')

    def service_get_all_by(self, context, topic=None, host=None, binary=None):
        msg = self.make_msg('service_get_all_by', topic=topic, host=host,
                            binary=binary)
        return self.call(context, msg, version='1.28')

    def instance_get_all_by_host(self, context, host, node=None,
                                 columns_to_join=None):
        msg = self.make_msg('instance_get_all_by_host', host=host, node=node,
                            columns_to_join=columns_to_join)
        return self.call(context, msg, version='1.47')

    def instance_fault_create(self, context, values):
        msg = self.make_msg('instance_fault_create', values=values)
        return self.call(context, msg, version='1.36')

    def action_event_start(self, context, values):
        values_p = jsonutils.to_primitive(values)
        msg = self.make_msg('action_event_start', values=values_p)
        return self.call(context, msg, version='1.25')

    def action_event_finish(self, context, values):
        values_p = jsonutils.to_primitive(values)
        msg = self.make_msg('action_event_finish', values=values_p)
        return self.call(context, msg, version='1.25')

    def instance_info_cache_update(self, context, instance, values):
        instance_p = jsonutils.to_primitive(instance)
        msg = self.make_msg('instance_info_cache_update',
                            instance=instance_p,
                            values=values)
        return self.call(context, msg, version='1.26')

    def service_create(self, context, values):
        msg = self.make_msg('service_create', values=values)
        return self.call(context, msg, version='1.27')

    def service_destroy(self, context, service_id):
        msg = self.make_msg('service_destroy', service_id=service_id)
        return self.call(context, msg, version='1.29')

    def compute_node_create(self, context, values):
        msg = self.make_msg('compute_node_create', values=values)
        return self.call(context, msg, version='1.33')

    def compute_node_update(self, context, node, values, prune_stats=False):
        node_p = jsonutils.to_primitive(node)
        msg = self.make_msg('compute_node_update', node=node_p, values=values,
                            prune_stats=prune_stats)
        return self.call(context, msg, version='1.33')

    def compute_node_delete(self, context, node):
        node_p = jsonutils.to_primitive(node)
        msg = self.make_msg('compute_node_delete', node=node_p)
        return self.call(context, msg, version='1.44')

    def service_update(self, context, service, values):
        service_p = jsonutils.to_primitive(service)
        msg = self.make_msg('service_update', service=service_p, values=values)
        return self.call(context, msg, version='1.34')

    def task_log_get(self, context, task_name, begin, end, host, state=None):
        msg = self.make_msg('task_log_get', task_name=task_name,
                            begin=begin, end=end, host=host, state=state)
        return self.call(context, msg, version='1.37')

    def task_log_begin_task(self, context, task_name, begin, end, host,
                            task_items=None, message=None):
        msg = self.make_msg('task_log_begin_task', task_name=task_name,
                            begin=begin, end=end, host=host,
                            task_items=task_items, message=message)
        return self.call(context, msg, version='1.37')

    def task_log_end_task(self, context, task_name, begin, end, host, errors,
                          message=None):
        msg = self.make_msg('task_log_end_task', task_name=task_name,
                            begin=begin, end=end, host=host, errors=errors,
                            message=message)
        return self.call(context, msg, version='1.37')

    def notify_usage_exists(self, context, instance, current_period=False,
                            ignore_missing_network_data=True,
                            system_metadata=None, extra_usage_info=None):
        instance_p = jsonutils.to_primitive(instance)
        system_metadata_p = jsonutils.to_primitive(system_metadata)
        extra_usage_info_p = jsonutils.to_primitive(extra_usage_info)
        msg = self.make_msg('notify_usage_exists', instance=instance_p,
                  current_period=current_period,
                  ignore_missing_network_data=ignore_missing_network_data,
                  system_metadata=system_metadata_p,
                  extra_usage_info=extra_usage_info_p)
        return self.call(context, msg, version='1.39')

    def security_groups_trigger_handler(self, context, event, args):
        args_p = jsonutils.to_primitive(args)
        msg = self.make_msg('security_groups_trigger_handler', event=event,
                            args=args_p)
        return self.call(context, msg, version='1.40')

    def security_groups_trigger_members_refresh(self, context, group_ids):
        msg = self.make_msg('security_groups_trigger_members_refresh',
                            group_ids=group_ids)
        return self.call(context, msg, version='1.40')

    def network_migrate_instance_start(self, context, instance, migration):
        instance_p = jsonutils.to_primitive(instance)
        migration_p = jsonutils.to_primitive(migration)
        msg = self.make_msg('network_migrate_instance_start',
                            instance=instance_p, migration=migration_p)
        return self.call(context, msg, version='1.41')

    def network_migrate_instance_finish(self, context, instance, migration):
        instance_p = jsonutils.to_primitive(instance)
        migration_p = jsonutils.to_primitive(migration)
        msg = self.make_msg('network_migrate_instance_finish',
                            instance=instance_p, migration=migration_p)
        return self.call(context, msg, version='1.41')

    def quota_commit(self, context, reservations, project_id=None,
                     user_id=None):
        reservations_p = jsonutils.to_primitive(reservations)
        msg = self.make_msg('quota_commit', reservations=reservations_p,
                            project_id=project_id, user_id=user_id)
        return self.call(context, msg, version='1.45')

    def quota_rollback(self, context, reservations, project_id=None,
                       user_id=None):
        reservations_p = jsonutils.to_primitive(reservations)
        msg = self.make_msg('quota_rollback', reservations=reservations_p,
                            project_id=project_id, user_id=user_id)
        return self.call(context, msg, version='1.45')

    def get_ec2_ids(self, context, instance):
        instance_p = jsonutils.to_primitive(instance)
        msg = self.make_msg('get_ec2_ids', instance=instance_p)
        return self.call(context, msg, version='1.42')

    def compute_stop(self, context, instance, do_cast=True):
        if not self.can_send_version('1.55'):
            instance = jsonutils.to_primitive(
                objects_base.obj_to_primitive(instance))
            version = '1.43'
        else:
            version = '1.55'
        msg = self.make_msg('compute_stop', instance=instance, do_cast=do_cast)
        return self.call(context, msg, version=version)

    def compute_confirm_resize(self, context, instance, migration_ref):
        migration_p = jsonutils.to_primitive(migration_ref)
        if not self.can_send_version('1.52'):
            instance = jsonutils.to_primitive(
                objects_base.obj_to_primitive(instance))
            version = '1.46'
        else:
            version = '1.52'
        msg = self.make_msg('compute_confirm_resize', instance=instance,
                            migration_ref=migration_p)
        return self.call(context, msg, version=version)

    def compute_unrescue(self, context, instance):
        instance_p = jsonutils.to_primitive(instance)
        msg = self.make_msg('compute_unrescue', instance=instance_p)
        return self.call(context, msg, version='1.48')

    def object_class_action(self, context, objname, objmethod, objver,
                            args, kwargs):
        msg = self.make_msg('object_class_action', objname=objname,
                            objmethod=objmethod, objver=objver,
                            args=args, kwargs=kwargs)
        return self.call(context, msg, version='1.50')

    def object_action(self, context, objinst, objmethod, args, kwargs):
        msg = self.make_msg('object_action', objinst=objinst,
                            objmethod=objmethod, args=args, kwargs=kwargs)
        return self.call(context, msg, version='1.50')

    def compute_reboot(self, context, instance, reboot_type):
        instance_p = jsonutils.to_primitive(instance)
        msg = self.make_msg('compute_reboot', instance=instance_p,
                            reboot_type=reboot_type)
        return self.call(context, msg, version='1.53')


class ComputeTaskAPI(nova.openstack.common.rpc.proxy.RpcProxy):
    """Client side of the conductor 'compute' namespaced RPC API

    API version history:

    1.0 - Initial version (empty).
    1.1 - Added unified migrate_server call.
    1.2 - Added build_instances
    1.3 - Added unshelve_instance
    1.4 - Added reservations to migrate_server.
    """

    BASE_RPC_API_VERSION = '1.0'
    RPC_API_NAMESPACE = 'compute_task'

    def __init__(self):
        super(ComputeTaskAPI, self).__init__(
                topic=CONF.conductor.topic,
                default_version=self.BASE_RPC_API_VERSION,
                serializer=objects_base.NovaObjectSerializer())

    def migrate_server(self, context, instance, scheduler_hint, live, rebuild,
                  flavor, block_migration, disk_over_commit,
                  reservations=None):
        instance_p = jsonutils.to_primitive(instance)
        flavor_p = jsonutils.to_primitive(flavor)
        msg = self.make_msg('migrate_server', instance=instance_p,
            scheduler_hint=scheduler_hint, live=live, rebuild=rebuild,
            flavor=flavor_p, block_migration=block_migration,
            disk_over_commit=disk_over_commit, reservations=reservations)
        return self.call(context, msg, version='1.4')

    def build_instances(self, context, instances, image, filter_properties,
            admin_password, injected_files, requested_networks,
            security_groups, block_device_mapping):
        instances_p = [jsonutils.to_primitive(inst) for inst in instances]
        image_p = jsonutils.to_primitive(image)
        msg = self.make_msg('build_instances', instances=instances_p,
                image=image_p, filter_properties=filter_properties,
                admin_password=admin_password, injected_files=injected_files,
                requested_networks=requested_networks,
                security_groups=security_groups,
                block_device_mapping=block_device_mapping)
        self.cast(context, msg, version='1.2')

    def unshelve_instance(self, context, instance):
        msg = self.make_msg('unshelve_instance', instance=instance)
        self.cast(context, msg, version='1.3')
