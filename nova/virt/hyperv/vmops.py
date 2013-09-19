# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2010 Cloud.com, Inc
# Copyright 2012 Cloudbase Solutions Srl
# All Rights Reserved.
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

"""
Management class for basic VM operations.
"""
import os

from oslo.config import cfg

from nova.api.metadata import base as instance_metadata
from nova import exception
from nova.openstack.common import excutils
from nova.openstack.common.gettextutils import _
from nova.openstack.common import importutils
from nova.openstack.common import log as logging
from nova.openstack.common import processutils
from nova import utils
from nova.virt import configdrive
from nova.virt.hyperv import constants
from nova.virt.hyperv import hostutils
from nova.virt.hyperv import imagecache
from nova.virt.hyperv import pathutils
from nova.virt.hyperv import vhdutils
from nova.virt.hyperv import vmutils
from nova.virt.hyperv import volumeops

LOG = logging.getLogger(__name__)

hyperv_opts = [
    cfg.BoolOpt('limit_cpu_features',
                default=False,
                help='Required for live migration among '
                     'hosts with different CPU features'),
    cfg.BoolOpt('config_drive_inject_password',
                default=False,
                help='Sets the admin password in the config drive image'),
    cfg.StrOpt('qemu_img_cmd',
               default="qemu-img.exe",
               help='qemu-img is used to convert between '
                    'different image types'),
    cfg.BoolOpt('config_drive_cdrom',
                default=False,
                help='Attaches the Config Drive image as a cdrom drive '
                     'instead of a disk drive')
]

CONF = cfg.CONF
CONF.register_opts(hyperv_opts, 'hyperv')
CONF.import_opt('use_cow_images', 'nova.virt.driver')
CONF.import_opt('network_api_class', 'nova.network')


class VMOps(object):
    _vif_driver_class_map = {
        'nova.network.neutronv2.api.API':
        'nova.virt.hyperv.vif.HyperVNeutronVIFDriver',
        'nova.network.api.API':
        'nova.virt.hyperv.vif.HyperVNovaNetworkVIFDriver',
    }

    def __init__(self):
        self._hostutils = hostutils.HostUtils()
        self._vmutils = vmutils.VMUtils()
        self._vhdutils = vhdutils.VHDUtils()
        self._pathutils = pathutils.PathUtils()
        self._volumeops = volumeops.VolumeOps()
        self._imagecache = imagecache.ImageCache()
        self._vif_driver = None
        self._load_vif_driver_class()

    def _load_vif_driver_class(self):
        try:
            class_name = self._vif_driver_class_map[CONF.network_api_class]
            self._vif_driver = importutils.import_object(class_name)
        except KeyError:
            raise TypeError(_("VIF driver not found for "
                              "network_api_class: %s") %
                            CONF.network_api_class)

    def list_instances(self):
        return self._vmutils.list_instances()

    def get_info(self, instance):
        """Get information about the VM."""
        LOG.debug(_("get_info called for instance"), instance=instance)

        instance_name = instance['name']
        if not self._vmutils.vm_exists(instance_name):
            raise exception.InstanceNotFound(instance_id=instance['uuid'])

        info = self._vmutils.get_vm_summary_info(instance_name)

        state = constants.HYPERV_POWER_STATE[info['EnabledState']]
        return {'state': state,
                'max_mem': info['MemoryUsage'],
                'mem': info['MemoryUsage'],
                'num_cpu': info['NumberOfProcessors'],
                'cpu_time': info['UpTime']}

    def _create_root_vhd(self, context, instance):
        base_vhd_path = self._imagecache.get_cached_image(context, instance)
        root_vhd_path = self._pathutils.get_vhd_path(instance['name'])

        try:
            if CONF.use_cow_images:
                LOG.debug(_("Creating differencing VHD. Parent: "
                            "%(base_vhd_path)s, Target: %(root_vhd_path)s"),
                          {'base_vhd_path': base_vhd_path,
                           'root_vhd_path': root_vhd_path})
                self._vhdutils.create_differencing_vhd(root_vhd_path,
                                                       base_vhd_path)
            else:
                LOG.debug(_("Copying VHD image %(base_vhd_path)s to target: "
                            "%(root_vhd_path)s"),
                          {'base_vhd_path': base_vhd_path,
                           'root_vhd_path': root_vhd_path})
                self._pathutils.copyfile(base_vhd_path, root_vhd_path)

                base_vhd_info = self._vhdutils.get_vhd_info(base_vhd_path)
                base_vhd_size = base_vhd_info['MaxInternalSize']
                root_vhd_size = instance['root_gb'] * 1024 ** 3

                if root_vhd_size < base_vhd_size:
                    raise vmutils.HyperVException(_("Cannot resize a VHD to a "
                                                    "smaller size"))
                elif root_vhd_size > base_vhd_size:
                    LOG.debug(_("Resizing VHD %(root_vhd_path)s to new "
                                "size %(root_vhd_size)s"),
                              {'base_vhd_path': base_vhd_path,
                               'root_vhd_path': root_vhd_path})
                    self._vhdutils.resize_vhd(root_vhd_path, root_vhd_size)
        except Exception:
            with excutils.save_and_reraise_exception():
                if self._pathutils.exists(root_vhd_path):
                    self._pathutils.remove(root_vhd_path)

        return root_vhd_path

    def spawn(self, context, instance, image_meta, injected_files,
              admin_password, network_info, block_device_info=None):
        """Create a new VM and start it."""
        LOG.info(_("Spawning new instance"), instance=instance)

        instance_name = instance['name']
        if self._vmutils.vm_exists(instance_name):
            raise exception.InstanceExists(name=instance_name)

        # Make sure we're starting with a clean slate.
        self._delete_disk_files(instance_name)

        if self._volumeops.ebs_root_in_block_devices(block_device_info):
            root_vhd_path = None
        else:
            root_vhd_path = self._create_root_vhd(context, instance)

        try:
            self.create_instance(instance, network_info, block_device_info,
                                 root_vhd_path)

            if configdrive.required_by(instance):
                self._create_config_drive(instance, injected_files,
                                          admin_password)

            self.power_on(instance)
        except Exception as ex:
            LOG.exception(ex)
            self.destroy(instance)
            raise vmutils.HyperVException(_('Spawn instance failed'))

    def create_instance(self, instance, network_info,
                        block_device_info, root_vhd_path):
        instance_name = instance['name']

        self._vmutils.create_vm(instance_name,
                                instance['memory_mb'],
                                instance['vcpus'],
                                CONF.hyperv.limit_cpu_features)

        if root_vhd_path:
            self._vmutils.attach_ide_drive(instance_name,
                                           root_vhd_path,
                                           0,
                                           0,
                                           constants.IDE_DISK)

        self._vmutils.create_scsi_controller(instance_name)

        self._volumeops.attach_volumes(block_device_info,
                                       instance_name,
                                       root_vhd_path is None)

        for vif in network_info:
            LOG.debug(_('Creating nic for instance: %s'), instance_name)
            self._vmutils.create_nic(instance_name,
                                     vif['id'],
                                     vif['address'])
            self._vif_driver.plug(instance, vif)

    def _create_config_drive(self, instance, injected_files, admin_password):
        if CONF.config_drive_format != 'iso9660':
            vmutils.HyperVException(_('Invalid config_drive_format "%s"') %
                                    CONF.config_drive_format)

        LOG.info(_('Using config drive for instance: %s'), instance=instance)

        extra_md = {}
        if admin_password and CONF.hyperv.config_drive_inject_password:
            extra_md['admin_pass'] = admin_password

        inst_md = instance_metadata.InstanceMetadata(instance,
                                                     content=injected_files,
                                                     extra_md=extra_md)

        instance_path = self._pathutils.get_instance_dir(
            instance['name'])
        configdrive_path_iso = os.path.join(instance_path, 'configdrive.iso')
        LOG.info(_('Creating config drive at %(path)s'),
                 {'path': configdrive_path_iso}, instance=instance)

        with configdrive.ConfigDriveBuilder(instance_md=inst_md) as cdb:
            try:
                cdb.make_drive(configdrive_path_iso)
            except processutils.ProcessExecutionError as e:
                with excutils.save_and_reraise_exception():
                    LOG.error(_('Creating config drive failed with error: %s'),
                              e, instance=instance)

        if not CONF.hyperv.config_drive_cdrom:
            drive_type = constants.IDE_DISK
            configdrive_path = os.path.join(instance_path,
                                            'configdrive.vhd')
            utils.execute(CONF.hyperv.qemu_img_cmd,
                          'convert',
                          '-f',
                          'raw',
                          '-O',
                          'vpc',
                          configdrive_path_iso,
                          configdrive_path,
                          attempts=1)
            self._pathutils.remove(configdrive_path_iso)
        else:
            drive_type = constants.IDE_DVD
            configdrive_path = configdrive_path_iso

        self._vmutils.attach_ide_drive(instance['name'], configdrive_path,
                                       1, 0, drive_type)

    def _disconnect_volumes(self, volume_drives):
        for volume_drive in volume_drives:
            self._volumeops.disconnect_volume(volume_drive)

    def _delete_disk_files(self, instance_name):
        self._pathutils.get_instance_dir(instance_name,
                                         create_dir=False,
                                         remove_dir=True)

    def destroy(self, instance, network_info=None, block_device_info=None,
                destroy_disks=True):
        instance_name = instance['name']
        LOG.info(_("Got request to destroy instance: %s"), instance_name)
        try:
            if self._vmutils.vm_exists(instance_name):

                #Stop the VM first.
                self.power_off(instance)

                storage = self._vmutils.get_vm_storage_paths(instance_name)
                (disk_files, volume_drives) = storage

                self._vmutils.destroy_vm(instance_name)
                self._disconnect_volumes(volume_drives)
            else:
                LOG.debug(_("Instance not found: %s"), instance_name)

            if destroy_disks:
                self._delete_disk_files(instance_name)
        except Exception as ex:
            LOG.exception(ex)
            raise vmutils.HyperVException(_('Failed to destroy instance: %s') %
                                          instance_name)

    def reboot(self, instance, network_info, reboot_type):
        """Reboot the specified instance."""
        LOG.debug(_("reboot instance"), instance=instance)
        self._set_vm_state(instance['name'],
                           constants.HYPERV_VM_STATE_REBOOT)

    def pause(self, instance):
        """Pause VM instance."""
        LOG.debug(_("Pause instance"), instance=instance)
        self._set_vm_state(instance["name"],
                           constants.HYPERV_VM_STATE_PAUSED)

    def unpause(self, instance):
        """Unpause paused VM instance."""
        LOG.debug(_("Unpause instance"), instance=instance)
        self._set_vm_state(instance["name"],
                           constants.HYPERV_VM_STATE_ENABLED)

    def suspend(self, instance):
        """Suspend the specified instance."""
        LOG.debug(_("Suspend instance"), instance=instance)
        self._set_vm_state(instance["name"],
                           constants.HYPERV_VM_STATE_SUSPENDED)

    def resume(self, instance):
        """Resume the suspended VM instance."""
        LOG.debug(_("Resume instance"), instance=instance)
        self._set_vm_state(instance["name"],
                           constants.HYPERV_VM_STATE_ENABLED)

    def power_off(self, instance):
        """Power off the specified instance."""
        LOG.debug(_("Power off instance"), instance=instance)
        self._set_vm_state(instance["name"],
                           constants.HYPERV_VM_STATE_DISABLED)

    def power_on(self, instance):
        """Power on the specified instance."""
        LOG.debug(_("Power on instance"), instance=instance)
        self._set_vm_state(instance["name"],
                           constants.HYPERV_VM_STATE_ENABLED)

    def _set_vm_state(self, vm_name, req_state):
        try:
            self._vmutils.set_vm_state(vm_name, req_state)
            LOG.debug(_("Successfully changed state of VM %(vm_name)s"
                        " to: %(req_state)s"),
                      {'vm_name': vm_name, 'req_state': req_state})
        except Exception as ex:
            LOG.exception(ex)
            msg = (_("Failed to change vm state of %(vm_name)s"
                     " to %(req_state)s") %
                   {'vm_name': vm_name, 'req_state': req_state})
            raise vmutils.HyperVException(msg)
