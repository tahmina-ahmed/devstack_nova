# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
#    Copyright 2010 OpenStack Foundation
#    Copyright 2012 University Of Minho
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

import fixtures
import os

from oslo.config import cfg

from nova import exception
from nova.storage import linuxscsi
from nova import test
from nova.tests.virt.libvirt import fake_libvirt_utils
from nova import utils
from nova.virt import fake
from nova.virt.libvirt import utils as libvirt_utils
from nova.virt.libvirt import volume

CONF = cfg.CONF


class LibvirtVolumeTestCase(test.TestCase):

    def setUp(self):
        super(LibvirtVolumeTestCase, self).setUp()
        self.executes = []

        def fake_execute(*cmd, **kwargs):
            self.executes.append(cmd)
            return None, None

        self.stubs.Set(utils, 'execute', fake_execute)

        class FakeLibvirtDriver(object):
            def __init__(self, hyperv="QEMU", version=1005001):
                self.hyperv = hyperv
                self.version = version

            def get_hypervisor_version(self):
                return self.version

            def get_hypervisor_type(self):
                return self.hyperv

            def get_all_block_devices(self):
                return []

        self.fake_conn = FakeLibvirtDriver(fake.FakeVirtAPI())
        self.connr = {
            'ip': '127.0.0.1',
            'initiator': 'fake_initiator',
            'host': 'fake_host'
        }
        self.disk_info = {
            "bus": "virtio",
            "dev": "vde",
            "type": "disk",
        }
        self.name = 'volume-00000001'
        self.location = '10.0.2.15:3260'
        self.iqn = 'iqn.2010-10.org.openstack:%s' % self.name
        self.vol = {'id': 1, 'name': self.name}
        self.uuid = '875a8070-d0b9-4949-8b31-104d125c9a64'
        self.user = 'foo'

    def _assertNetworkAndProtocolEquals(self, tree):
        self.assertEqual(tree.get('type'), 'network')
        self.assertEqual(tree.find('./source').get('protocol'), 'rbd')
        rbd_name = '%s/%s' % ('rbd', self.name)
        self.assertEqual(tree.find('./source').get('name'), rbd_name)

    def _assertFileTypeEquals(self, tree, file_path):
        self.assertEqual(tree.get('type'), 'file')
        self.assertEqual(tree.find('./source').get('file'), file_path)

    def test_libvirt_volume_driver_serial(self):
        libvirt_driver = volume.LibvirtVolumeDriver(self.fake_conn)
        connection_info = {
            'driver_volume_type': 'fake',
            'data': {
                'device_path': '/foo',
            },
            'serial': 'fake_serial',
        }
        conf = libvirt_driver.connect_volume(connection_info, self.disk_info)
        tree = conf.format_dom()
        self.assertEqual(tree.get('type'), 'block')
        self.assertEqual(tree.find('./serial').text, 'fake_serial')

    def iscsi_connection(self, volume, location, iqn):
        return {
                'driver_volume_type': 'iscsi',
                'data': {
                    'volume_id': volume['id'],
                    'target_portal': location,
                    'target_iqn': iqn,
                    'target_lun': 1,
                }
        }

    def test_libvirt_iscsi_driver(self):
        # NOTE(vish) exists is to make driver assume connecting worked
        self.stubs.Set(os.path, 'exists', lambda x: True)
        libvirt_driver = volume.LibvirtISCSIVolumeDriver(self.fake_conn)
        connection_info = self.iscsi_connection(self.vol, self.location,
                                                self.iqn)
        conf = libvirt_driver.connect_volume(connection_info, self.disk_info)
        tree = conf.format_dom()
        dev_str = '/dev/disk/by-path/ip-%s-iscsi-%s-lun-1' % (self.location,
                                                              self.iqn)
        self.assertEqual(tree.get('type'), 'block')
        self.assertEqual(tree.find('./source').get('dev'), dev_str)
        libvirt_driver.disconnect_volume(connection_info, "vde")
        expected_commands = [('iscsiadm', '-m', 'node', '-T', self.iqn,
                              '-p', self.location),
                             ('iscsiadm', '-m', 'session'),
                             ('iscsiadm', '-m', 'node', '-T', self.iqn,
                              '-p', self.location, '--login'),
                             ('iscsiadm', '-m', 'node', '-T', self.iqn,
                              '-p', self.location, '--op', 'update',
                              '-n', 'node.startup', '-v', 'automatic'),
                             ('iscsiadm', '-m', 'node', '-T', self.iqn,
                              '-p', self.location, '--op', 'update',
                              '-n', 'node.startup', '-v', 'manual'),
                             ('iscsiadm', '-m', 'node', '-T', self.iqn,
                              '-p', self.location, '--logout'),
                             ('iscsiadm', '-m', 'node', '-T', self.iqn,
                              '-p', self.location, '--op', 'delete')]
        self.assertEqual(self.executes, expected_commands)

    def test_libvirt_iscsi_driver_still_in_use(self):
        # NOTE(vish) exists is to make driver assume connecting worked
        self.stubs.Set(os.path, 'exists', lambda x: True)
        libvirt_driver = volume.LibvirtISCSIVolumeDriver(self.fake_conn)
        devs = ['/dev/disk/by-path/ip-%s-iscsi-%s-lun-1' % (self.location,
                                                            self.iqn)]
        self.stubs.Set(self.fake_conn, 'get_all_block_devices', lambda: devs)
        vol = {'id': 1, 'name': self.name}
        connection_info = self.iscsi_connection(vol, self.location, self.iqn)
        conf = libvirt_driver.connect_volume(connection_info, self.disk_info)
        tree = conf.format_dom()
        dev_str = '/dev/disk/by-path/ip-%s-iscsi-%s-lun-1' % (self.location,
                                                              self.iqn)
        self.assertEqual(tree.get('type'), 'block')
        self.assertEqual(tree.find('./source').get('dev'), dev_str)
        libvirt_driver.disconnect_volume(connection_info, "vde")
        expected_commands = [('iscsiadm', '-m', 'node', '-T', self.iqn,
                              '-p', self.location),
                             ('iscsiadm', '-m', 'session'),
                             ('iscsiadm', '-m', 'node', '-T', self.iqn,
                              '-p', self.location, '--login'),
                             ('iscsiadm', '-m', 'node', '-T', self.iqn,
                              '-p', self.location, '--op', 'update',
                              '-n', 'node.startup', '-v', 'automatic')]
        self.assertEqual(self.executes, expected_commands)

    def sheepdog_connection(self, volume):
        return {
            'driver_volume_type': 'sheepdog',
            'data': {
                'name': volume['name']
            }
        }

    def test_libvirt_sheepdog_driver(self):
        libvirt_driver = volume.LibvirtNetVolumeDriver(self.fake_conn)
        connection_info = self.sheepdog_connection(self.vol)
        conf = libvirt_driver.connect_volume(connection_info, self.disk_info)
        tree = conf.format_dom()
        self.assertEqual(tree.get('type'), 'network')
        self.assertEqual(tree.find('./source').get('protocol'), 'sheepdog')
        self.assertEqual(tree.find('./source').get('name'), self.name)
        libvirt_driver.disconnect_volume(connection_info, "vde")

    def rbd_connection(self, volume):
        return {
            'driver_volume_type': 'rbd',
            'data': {
                'name': '%s/%s' % ('rbd', volume['name']),
                'auth_enabled': CONF.rbd_secret_uuid is not None,
                'auth_username': CONF.rbd_user,
                'secret_type': 'ceph',
                'secret_uuid': CONF.rbd_secret_uuid,
            }
        }

    def test_libvirt_rbd_driver(self):
        libvirt_driver = volume.LibvirtNetVolumeDriver(self.fake_conn)
        connection_info = self.rbd_connection(self.vol)
        conf = libvirt_driver.connect_volume(connection_info, self.disk_info)
        tree = conf.format_dom()
        self._assertNetworkAndProtocolEquals(tree)
        self.assertEqual(tree.find('./source/auth'), None)
        libvirt_driver.disconnect_volume(connection_info, "vde")

    def test_libvirt_rbd_driver_hosts(self):
        libvirt_driver = volume.LibvirtNetVolumeDriver(self.fake_conn)
        connection_info = self.rbd_connection(self.vol)
        hosts = ['example.com', '1.2.3.4', '::1']
        ports = [None, '6790', '6791']
        connection_info['data']['hosts'] = hosts
        connection_info['data']['ports'] = ports
        conf = libvirt_driver.connect_volume(connection_info, self.disk_info)
        tree = conf.format_dom()
        self._assertNetworkAndProtocolEquals(tree)
        self.assertEqual(tree.find('./source/auth'), None)
        found_hosts = tree.findall('./source/host')
        self.assertEqual([host.get('name') for host in found_hosts], hosts)
        self.assertEqual([host.get('port') for host in found_hosts], ports)
        libvirt_driver.disconnect_volume(connection_info, "vde")

    def test_libvirt_rbd_driver_auth_enabled(self):
        libvirt_driver = volume.LibvirtNetVolumeDriver(self.fake_conn)
        connection_info = self.rbd_connection(self.vol)
        secret_type = 'ceph'
        connection_info['data']['auth_enabled'] = True
        connection_info['data']['auth_username'] = self.user
        connection_info['data']['secret_type'] = secret_type
        connection_info['data']['secret_uuid'] = self.uuid

        conf = libvirt_driver.connect_volume(connection_info, self.disk_info)
        tree = conf.format_dom()
        self._assertNetworkAndProtocolEquals(tree)
        self.assertEqual(tree.find('./auth').get('username'), self.user)
        self.assertEqual(tree.find('./auth/secret').get('type'), secret_type)
        self.assertEqual(tree.find('./auth/secret').get('uuid'), self.uuid)
        libvirt_driver.disconnect_volume(connection_info, "vde")

    def test_libvirt_rbd_driver_auth_enabled_flags_override(self):
        libvirt_driver = volume.LibvirtNetVolumeDriver(self.fake_conn)
        connection_info = self.rbd_connection(self.vol)
        secret_type = 'ceph'
        connection_info['data']['auth_enabled'] = True
        connection_info['data']['auth_username'] = self.user
        connection_info['data']['secret_type'] = secret_type
        connection_info['data']['secret_uuid'] = self.uuid

        flags_uuid = '37152720-1785-11e2-a740-af0c1d8b8e4b'
        flags_user = 'bar'
        self.flags(rbd_user=flags_user,
                   rbd_secret_uuid=flags_uuid)

        conf = libvirt_driver.connect_volume(connection_info, self.disk_info)
        tree = conf.format_dom()
        self._assertNetworkAndProtocolEquals(tree)
        self.assertEqual(tree.find('./auth').get('username'), flags_user)
        self.assertEqual(tree.find('./auth/secret').get('type'), secret_type)
        self.assertEqual(tree.find('./auth/secret').get('uuid'), flags_uuid)
        libvirt_driver.disconnect_volume(connection_info, "vde")

    def test_libvirt_rbd_driver_auth_disabled(self):
        libvirt_driver = volume.LibvirtNetVolumeDriver(self.fake_conn)
        connection_info = self.rbd_connection(self.vol)
        secret_type = 'ceph'
        connection_info['data']['auth_enabled'] = False
        connection_info['data']['auth_username'] = self.user
        connection_info['data']['secret_type'] = secret_type
        connection_info['data']['secret_uuid'] = self.uuid

        conf = libvirt_driver.connect_volume(connection_info, self.disk_info)
        tree = conf.format_dom()
        self._assertNetworkAndProtocolEquals(tree)
        self.assertEqual(tree.find('./auth'), None)
        libvirt_driver.disconnect_volume(connection_info, "vde")

    def test_libvirt_rbd_driver_auth_disabled_flags_override(self):
        libvirt_driver = volume.LibvirtNetVolumeDriver(self.fake_conn)
        connection_info = self.rbd_connection(self.vol)
        secret_type = 'ceph'
        connection_info['data']['auth_enabled'] = False
        connection_info['data']['auth_username'] = self.user
        connection_info['data']['secret_type'] = secret_type
        connection_info['data']['secret_uuid'] = self.uuid

        # NOTE: Supplying the rbd_secret_uuid will enable authentication
        # locally in nova-compute even if not enabled in nova-volume/cinder
        flags_uuid = '37152720-1785-11e2-a740-af0c1d8b8e4b'
        flags_user = 'bar'
        self.flags(rbd_user=flags_user,
                   rbd_secret_uuid=flags_uuid)

        conf = libvirt_driver.connect_volume(connection_info, self.disk_info)
        tree = conf.format_dom()
        self._assertNetworkAndProtocolEquals(tree)
        self.assertEqual(tree.find('./auth').get('username'), flags_user)
        self.assertEqual(tree.find('./auth/secret').get('type'), secret_type)
        self.assertEqual(tree.find('./auth/secret').get('uuid'), flags_uuid)
        libvirt_driver.disconnect_volume(connection_info, "vde")

    def test_libvirt_kvm_volume(self):
        self.stubs.Set(os.path, 'exists', lambda x: True)
        libvirt_driver = volume.LibvirtISCSIVolumeDriver(self.fake_conn)
        connection_info = self.iscsi_connection(self.vol, self.location,
                                                self.iqn)
        conf = libvirt_driver.connect_volume(connection_info, self.disk_info)
        tree = conf.format_dom()
        dev_str = '/dev/disk/by-path/ip-%s-iscsi-%s-lun-1' % (self.location,
                                                              self.iqn)
        self.assertEqual(tree.get('type'), 'block')
        self.assertEqual(tree.find('./source').get('dev'), dev_str)
        libvirt_driver.disconnect_volume(connection_info, 'vde')

    def test_libvirt_kvm_volume_with_multipath(self):
        self.flags(libvirt_iscsi_use_multipath=True)
        self.stubs.Set(os.path, 'exists', lambda x: True)
        devs = ['/dev/mapper/sda', '/dev/mapper/sdb']
        self.stubs.Set(self.fake_conn, 'get_all_block_devices', lambda: devs)
        libvirt_driver = volume.LibvirtISCSIVolumeDriver(self.fake_conn)
        connection_info = self.iscsi_connection(self.vol, self.location,
                                                self.iqn)
        mpdev_filepath = '/dev/mapper/foo'
        connection_info['data']['device_path'] = mpdev_filepath
        target_portals = ['fake_portal1', 'fake_portal2']
        libvirt_driver._get_multipath_device_name = lambda x: mpdev_filepath
        conf = libvirt_driver.connect_volume(connection_info, self.disk_info)
        tree = conf.format_dom()
        self.assertEqual(tree.find('./source').get('dev'), mpdev_filepath)
        libvirt_driver.disconnect_volume(connection_info, 'vde')

    def test_libvirt_kvm_volume_with_multipath_getmpdev(self):
        self.flags(libvirt_iscsi_use_multipath=True)
        self.stubs.Set(os.path, 'exists', lambda x: True)
        libvirt_driver = volume.LibvirtISCSIVolumeDriver(self.fake_conn)
        name0 = 'volume-00000000'
        iqn0 = 'iqn.2010-10.org.openstack:%s' % name0
        dev0 = '/dev/disk/by-path/ip-%s-iscsi-%s-lun-0' % (self.location, iqn0)
        dev = '/dev/disk/by-path/ip-%s-iscsi-%s-lun-1' % (self.location,
                                                          self.iqn)
        devs = [dev0, dev]
        self.stubs.Set(self.fake_conn, 'get_all_block_devices', lambda: devs)
        connection_info = self.iscsi_connection(self.vol, self.location,
                                                self.iqn)
        mpdev_filepath = '/dev/mapper/foo'
        target_portals = ['fake_portal1', 'fake_portal2']
        libvirt_driver._get_multipath_device_name = lambda x: mpdev_filepath
        conf = libvirt_driver.connect_volume(connection_info, self.disk_info)
        tree = conf.format_dom()
        self.assertEqual(tree.find('./source').get('dev'), mpdev_filepath)
        libvirt_driver.disconnect_volume(connection_info, 'vde')

    def test_libvirt_nfs_driver(self):
        # NOTE(vish) exists is to make driver assume connecting worked
        mnt_base = '/mnt'
        self.flags(nfs_mount_point_base=mnt_base)

        libvirt_driver = volume.LibvirtNFSVolumeDriver(self.fake_conn)
        export_string = '192.168.1.1:/nfs/share1'
        export_mnt_base = os.path.join(mnt_base,
                libvirt_driver.get_hash_str(export_string))
        file_path = os.path.join(export_mnt_base, self.name)

        connection_info = {'data': {'export': export_string,
                                    'name': self.name}}
        conf = libvirt_driver.connect_volume(connection_info, self.disk_info)
        tree = conf.format_dom()
        self._assertFileTypeEquals(tree, file_path)
        libvirt_driver.disconnect_volume(connection_info, "vde")

        expected_commands = [
            ('mkdir', '-p', export_mnt_base),
            ('mount', '-t', 'nfs', export_string, export_mnt_base)]
        self.assertEqual(self.executes, expected_commands)

    def test_libvirt_nfs_driver_with_opts(self):
        mnt_base = '/mnt'
        self.flags(nfs_mount_point_base=mnt_base)

        libvirt_driver = volume.LibvirtNFSVolumeDriver(self.fake_conn)
        export_string = '192.168.1.1:/nfs/share1'
        options = '-o intr,nfsvers=3'
        export_mnt_base = os.path.join(mnt_base,
                libvirt_driver.get_hash_str(export_string))
        file_path = os.path.join(export_mnt_base, self.name)

        connection_info = {'data': {'export': export_string,
                                    'name': self.name,
                                    'options': options}}
        conf = libvirt_driver.connect_volume(connection_info, self.disk_info)
        tree = conf.format_dom()
        self._assertFileTypeEquals(tree, file_path)
        libvirt_driver.disconnect_volume(connection_info, "vde")

        expected_commands = [
            ('mkdir', '-p', export_mnt_base),
            ('mount', '-t', 'nfs', '-o', 'intr,nfsvers=3',
             export_string, export_mnt_base)
        ]
        self.assertEqual(self.executes, expected_commands)

    def aoe_connection(self, shelf, lun):
        return {
                'driver_volume_type': 'aoe',
                'data': {
                    'target_shelf': shelf,
                    'target_lun': lun,
                }
        }

    def test_libvirt_aoe_driver(self):
        # NOTE(jbr_) exists is to make driver assume connecting worked
        self.stubs.Set(os.path, 'exists', lambda x: True)
        libvirt_driver = volume.LibvirtAOEVolumeDriver(self.fake_conn)
        shelf = '100'
        lun = '1'
        connection_info = self.aoe_connection(shelf, lun)
        conf = libvirt_driver.connect_volume(connection_info, self.disk_info)
        tree = conf.format_dom()
        aoedevpath = '/dev/etherd/e%s.%s' % (shelf, lun)
        self.assertEqual(tree.get('type'), 'block')
        self.assertEqual(tree.find('./source').get('dev'), aoedevpath)
        libvirt_driver.disconnect_volume(connection_info, "vde")

    def test_libvirt_glusterfs_driver(self):
        mnt_base = '/mnt'
        self.flags(glusterfs_mount_point_base=mnt_base)

        libvirt_driver = volume.LibvirtGlusterfsVolumeDriver(self.fake_conn)
        export_string = '192.168.1.1:/volume-00001'
        export_mnt_base = os.path.join(mnt_base,
                libvirt_driver.get_hash_str(export_string))
        file_path = os.path.join(export_mnt_base, self.name)

        connection_info = {'data': {'export': export_string,
                                    'name': self.name}}
        conf = libvirt_driver.connect_volume(connection_info, self.disk_info)
        tree = conf.format_dom()
        self._assertFileTypeEquals(tree, file_path)
        libvirt_driver.disconnect_volume(connection_info, "vde")

        expected_commands = [
            ('mkdir', '-p', export_mnt_base),
            ('mount', '-t', 'glusterfs', export_string, export_mnt_base)]
        self.assertEqual(self.executes, expected_commands)

    def test_libvirt_glusterfs_driver_with_opts(self):
        mnt_base = '/mnt'
        self.flags(glusterfs_mount_point_base=mnt_base)

        libvirt_driver = volume.LibvirtGlusterfsVolumeDriver(self.fake_conn)
        export_string = '192.168.1.1:/volume-00001'
        options = '-o backupvolfile-server=192.168.1.2'
        export_mnt_base = os.path.join(mnt_base,
                libvirt_driver.get_hash_str(export_string))
        file_path = os.path.join(export_mnt_base, self.name)

        connection_info = {'data': {'export': export_string,
                                    'name': self.name,
                                    'options': options}}
        conf = libvirt_driver.connect_volume(connection_info, self.disk_info)
        tree = conf.format_dom()
        self._assertFileTypeEquals(tree, file_path)
        libvirt_driver.disconnect_volume(connection_info, "vde")

        expected_commands = [
            ('mkdir', '-p', export_mnt_base),
            ('mount', '-t', 'glusterfs',
             '-o', 'backupvolfile-server=192.168.1.2',
             export_string, export_mnt_base)]
        self.assertEqual(self.executes, expected_commands)

    def fibrechan_connection(self, volume, location, wwn):
        return {
                'driver_volume_type': 'fibrechan',
                'data': {
                    'volume_id': volume['id'],
                    'target_portal': location,
                    'target_wwn': wwn,
                    'target_lun': 1,
                }
        }

    def test_libvirt_fibrechan_driver(self):
        self.stubs.Set(libvirt_utils, 'get_fc_hbas',
                       fake_libvirt_utils.get_fc_hbas)
        self.stubs.Set(libvirt_utils, 'get_fc_hbas_info',
                       fake_libvirt_utils.get_fc_hbas_info)
        # NOTE(vish) exists is to make driver assume connecting worked
        self.stubs.Set(os.path, 'exists', lambda x: True)
        self.stubs.Set(os.path, 'realpath', lambda x: '/dev/sdb')
        libvirt_driver = volume.LibvirtFibreChannelVolumeDriver(self.fake_conn)
        multipath_devname = '/dev/md-1'
        devices = {"device": multipath_devname,
                   "id": "1234567890",
                   "devices": [{'device': '/dev/sdb',
                                'address': '1:0:0:1',
                                'host': 1, 'channel': 0,
                                'id': 0, 'lun': 1}]}
        self.stubs.Set(linuxscsi, 'find_multipath_device', lambda x: devices)
        self.stubs.Set(linuxscsi, 'remove_device', lambda x: None)
        wwn = '1234567890123456'
        connection_info = self.fibrechan_connection(self.vol, self.location,
                                                    wwn)
        mount_device = "vde"
        conf = libvirt_driver.connect_volume(connection_info, self.disk_info)
        tree = conf.format_dom()
        dev_str = '/dev/disk/by-path/pci-0000:05:00.2-fc-0x%s-lun-1' % wwn
        self.assertEqual(tree.get('type'), 'block')
        self.assertEqual(tree.find('./source').get('dev'), multipath_devname)
        connection_info["data"]["devices"] = devices["devices"]
        libvirt_driver.disconnect_volume(connection_info, mount_device)
        expected_commands = []
        self.assertEqual(self.executes, expected_commands)

        self.stubs.Set(libvirt_utils, 'get_fc_hbas',
                       lambda: [])
        self.stubs.Set(libvirt_utils, 'get_fc_hbas_info',
                       lambda: [])
        self.assertRaises(exception.NovaException,
                          libvirt_driver.connect_volume,
                          connection_info, self.disk_info)

        self.stubs.Set(libvirt_utils, 'get_fc_hbas', lambda: [])
        self.stubs.Set(libvirt_utils, 'get_fc_hbas_info', lambda: [])
        self.assertRaises(exception.NovaException,
                          libvirt_driver.connect_volume,
                          connection_info, self.disk_info)

    def test_libvirt_fibrechan_getpci_num(self):
        libvirt_driver = volume.LibvirtFibreChannelVolumeDriver(self.fake_conn)
        hba = {'device_path': "/sys/devices/pci0000:00/0000:00:03.0"
                                  "/0000:05:00.3/host2/fc_host/host2"}
        pci_num = libvirt_driver._get_pci_num(hba)
        self.assertEqual("0000:05:00.3", pci_num)

        hba = {'device_path': "/sys/devices/pci0000:00/0000:00:03.0"
                              "/0000:05:00.3/0000:06:00.6/host2/fc_host/host2"}
        pci_num = libvirt_driver._get_pci_num(hba)
        self.assertEqual("0000:06:00.6", pci_num)

    def test_libvirt_scality_driver(self):
        tempdir = self.useFixture(fixtures.TempDir()).path
        TEST_MOUNT = os.path.join(tempdir, 'fake_mount')
        TEST_CONFIG = os.path.join(tempdir, 'fake_config')
        TEST_VOLDIR = 'volumes'
        TEST_VOLNAME = 'volume_name'
        TEST_CONN_INFO = {
            'data': {
                'sofs_path': os.path.join(TEST_VOLDIR, TEST_VOLNAME)
            }
        }
        TEST_VOLPATH = os.path.join(TEST_MOUNT,
                                    TEST_VOLDIR,
                                    TEST_VOLNAME)
        open(TEST_CONFIG, "w+").close()
        os.makedirs(os.path.join(TEST_MOUNT, 'sys'))

        def _access_wrapper(path, flags):
            if path == '/sbin/mount.sofs':
                return True
            else:
                return os.access(path, flags)

        self.stubs.Set(os, 'access', _access_wrapper)
        self.flags(scality_sofs_config=TEST_CONFIG,
                   scality_sofs_mount_point=TEST_MOUNT)
        driver = volume.LibvirtScalityVolumeDriver(self.fake_conn)
        conf = driver.connect_volume(TEST_CONN_INFO, self.disk_info)

        tree = conf.format_dom()
        self._assertFileTypeEquals(tree, TEST_VOLPATH)
