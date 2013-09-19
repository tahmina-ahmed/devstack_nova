# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 OpenStack Foundation
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

import contextlib
import pkg_resources
import urlparse

import fixtures
import mox
from oslo.config import cfg

from nova.compute import flavors
from nova import context
from nova import db
from nova import exception
from nova.openstack.common.gettextutils import _
from nova.openstack.common import timeutils
from nova import test
from nova.tests.virt.xenapi import stubs
from nova.tests.virt.xenapi import test_xenapi
from nova import utils
from nova.virt.xenapi import driver as xenapi_conn
from nova.virt.xenapi import fake
from nova.virt.xenapi import vm_utils
from nova.virt.xenapi import volume_utils

CONF = cfg.CONF
XENSM_TYPE = 'xensm'
ISCSI_TYPE = 'iscsi'


def get_fake_connection_data(sr_type):
    fakes = {XENSM_TYPE: {'sr_uuid': 'falseSR',
                          'name_label': 'fake_storage',
                          'name_description': 'test purposes',
                          'server': 'myserver',
                          'serverpath': '/local/scratch/myname',
                          'sr_type': 'nfs',
                          'introduce_sr_keys': ['server',
                                                'serverpath',
                                                'sr_type'],
                          'vdi_uuid': 'falseVDI'},
             ISCSI_TYPE: {'volume_id': 'fake_volume_id',
                          'target_lun': 1,
                          'target_iqn': 'fake_iqn:volume-fake_volume_id',
                          'target_portal': u'localhost:3260',
                          'target_discovered': False}, }
    return fakes[sr_type]


@contextlib.contextmanager
def contextified(result):
    yield result


def _fake_noop(*args, **kwargs):
    return


class LookupTestCase(test.TestCase):

    def setUp(self):
        super(LookupTestCase, self).setUp()
        self.session = self.mox.CreateMockAnything('Fake Session')
        self.name_label = 'my_vm'

    def _do_mock(self, result):
        self.session.call_xenapi(
            "VM.get_by_name_label", self.name_label).AndReturn(result)
        self.mox.ReplayAll()

    def test_normal(self):
        self._do_mock(['x'])
        result = vm_utils.lookup(self.session, self.name_label)
        self.assertEqual('x', result)

    def test_no_result(self):
        self._do_mock([])
        result = vm_utils.lookup(self.session, self.name_label)
        self.assertEqual(None, result)

    def test_too_many(self):
        self._do_mock(['a', 'b'])
        self.assertRaises(exception.InstanceExists,
                          vm_utils.lookup,
                          self.session, self.name_label)

    def test_rescue_none(self):
        self.session.call_xenapi(
            "VM.get_by_name_label", self.name_label + '-rescue').AndReturn([])
        self._do_mock(['x'])
        result = vm_utils.lookup(self.session, self.name_label,
                                 check_rescue=True)
        self.assertEqual('x', result)

    def test_rescue_found(self):
        self.session.call_xenapi(
            "VM.get_by_name_label",
            self.name_label + '-rescue').AndReturn(['y'])
        self.mox.ReplayAll()
        result = vm_utils.lookup(self.session, self.name_label,
                                 check_rescue=True)
        self.assertEqual('y', result)

    def test_rescue_too_many(self):
        self.session.call_xenapi(
            "VM.get_by_name_label",
            self.name_label + '-rescue').AndReturn(['a', 'b', 'c'])
        self.mox.ReplayAll()
        self.assertRaises(exception.InstanceExists,
                          vm_utils.lookup,
                          self.session, self.name_label,
                          check_rescue=True)


class GenerateConfigDriveTestCase(test.TestCase):
    def test_no_admin_pass(self):
        # This is here to avoid masking errors, it shouldn't be used normally
        self.useFixture(fixtures.MonkeyPatch(
                'nova.virt.xenapi.vm_utils.destroy_vdi', _fake_noop))

        # Mocks
        instance = {}

        self.mox.StubOutWithMock(vm_utils, 'safe_find_sr')
        vm_utils.safe_find_sr('session').AndReturn('sr_ref')

        self.mox.StubOutWithMock(vm_utils, 'create_vdi')
        vm_utils.create_vdi('session', 'sr_ref', instance, 'config-2',
                            'configdrive',
                            64 * 1024 * 1024).AndReturn('vdi_ref')

        self.mox.StubOutWithMock(vm_utils, 'vdi_attached_here')
        vm_utils.vdi_attached_here(
            'session', 'vdi_ref', read_only=False).AndReturn(
                contextified('mounted_dev'))

        class FakeInstanceMetadata(object):
            def __init__(self, instance, content=None, extra_md=None):
                pass

            def metadata_for_config_drive(self):
                return []

        self.useFixture(fixtures.MonkeyPatch(
                'nova.api.metadata.base.InstanceMetadata',
                FakeInstanceMetadata))

        self.mox.StubOutWithMock(utils, 'execute')
        utils.execute('genisoimage', '-o', mox.IgnoreArg(), '-ldots',
                      '-allow-lowercase', '-allow-multidot', '-l',
                      '-publisher', mox.IgnoreArg(), '-quiet',
                      '-J', '-r', '-V', 'config-2', mox.IgnoreArg(),
                      attempts=1, run_as_root=False).AndReturn(None)
        utils.execute('dd', mox.IgnoreArg(), mox.IgnoreArg(),
                      run_as_root=True).AndReturn(None)

        self.mox.StubOutWithMock(vm_utils, 'create_vbd')
        vm_utils.create_vbd('session', 'vm_ref', 'vdi_ref', mox.IgnoreArg(),
                            bootable=False, read_only=True).AndReturn(None)

        self.mox.ReplayAll()

        # And the actual call we're testing
        vm_utils.generate_configdrive('session', instance, 'vm_ref',
                                      'userdevice')


class XenAPIGetUUID(test.TestCase):
    def test_get_this_vm_uuid_new_kernel(self):
        self.mox.StubOutWithMock(vm_utils, '_get_sys_hypervisor_uuid')

        vm_utils._get_sys_hypervisor_uuid().AndReturn(
            '2f46f0f5-f14c-ef1b-1fac-9eeca0888a3f')

        self.mox.ReplayAll()
        self.assertEquals('2f46f0f5-f14c-ef1b-1fac-9eeca0888a3f',
                          vm_utils.get_this_vm_uuid())
        self.mox.VerifyAll()

    def test_get_this_vm_uuid_old_kernel_reboot(self):
        self.mox.StubOutWithMock(vm_utils, '_get_sys_hypervisor_uuid')
        self.mox.StubOutWithMock(utils, 'execute')

        vm_utils._get_sys_hypervisor_uuid().AndRaise(
            IOError(13, 'Permission denied'))
        utils.execute('xenstore-read', 'domid', run_as_root=True).AndReturn(
            ('27', ''))
        utils.execute('xenstore-read', '/local/domain/27/vm',
                      run_as_root=True).AndReturn(
            ('/vm/2f46f0f5-f14c-ef1b-1fac-9eeca0888a3f', ''))

        self.mox.ReplayAll()
        self.assertEquals('2f46f0f5-f14c-ef1b-1fac-9eeca0888a3f',
                          vm_utils.get_this_vm_uuid())
        self.mox.VerifyAll()


class FakeSession():
    def call_xenapi(self, *args):
        pass

    def call_plugin_serialized_with_retry(self, plugin, fn, num_retries,
                                          callback, *args, **kwargs):
        pass


class FetchVhdImageTestCase(test.TestCase):
    def setUp(self):
        super(FetchVhdImageTestCase, self).setUp()
        self.context = context.get_admin_context()
        self.context.auth_token = 'auth_token'

        self.session = FakeSession()
        self.instance = {"uuid": "uuid"}
        self.image_id = "image_id"
        self.uuid_stack = ["uuid_stack"]
        self.sr_path = "sr_path"
        self.params = {'image_id': self.image_id,
                       'uuid_stack': self.uuid_stack,
                       'sr_path': self.sr_path}
        self.vdis = {'root': {'uuid': 'vdi'}}

        self.mox.StubOutWithMock(vm_utils, '_make_uuid_stack')
        self.mox.StubOutWithMock(vm_utils, 'get_sr_path')
        self.mox.StubOutWithMock(vm_utils, '_image_uses_bittorrent')
        self.mox.StubOutWithMock(vm_utils, '_add_bittorrent_params')
        self.mox.StubOutWithMock(vm_utils, 'safe_find_sr')
        self.mox.StubOutWithMock(vm_utils, '_scan_sr')
        self.mox.StubOutWithMock(vm_utils, '_check_vdi_size')
        self.mox.StubOutWithMock(vm_utils, 'destroy_vdi')
        self.mox.StubOutWithMock(
                self.session, 'call_plugin_serialized_with_retry')
        self.mox.StubOutWithMock(vm_utils, '_add_torrent_url')

        vm_utils._make_uuid_stack().AndReturn(self.uuid_stack)
        vm_utils.get_sr_path(self.session).AndReturn(self.sr_path)

    def test_fetch_vhd_image_works_with_glance(self):
        vm_utils._image_uses_bittorrent(
            self.context, self.instance).AndReturn(False)
        self.params['auth_token'] = 'auth_token'

        self.session.call_plugin_serialized_with_retry(
                'glance', 'download_vhd', 0, mox.IgnoreArg(),
                **self.params).AndReturn(self.vdis)

        vm_utils.safe_find_sr(self.session).AndReturn("sr")
        vm_utils._scan_sr(self.session, "sr")
        vm_utils._check_vdi_size(
                self.context, self.session, self.instance, "vdi")

        self.mox.ReplayAll()

        self.assertEqual("vdi", vm_utils._fetch_vhd_image(self.context,
            self.session, self.instance, self.image_id)['root']['uuid'])

        self.mox.VerifyAll()

    def _setup_bittorrent(self):
        vm_utils._image_uses_bittorrent(
            self.context, self.instance).AndReturn(True)

        def _add_torrent_url(instance, image_id, params):
            params['torrent_url'] = "%s.torrent" % image_id

        vm_utils._add_torrent_url(
                self.instance, self.image_id, mox.IgnoreArg()).AndReturn(True)

        vm_utils._add_bittorrent_params(self.image_id, self.params)

        self.session.call_plugin_serialized_with_retry(
                'bittorrent', 'download_vhd', 0, None,
                **self.params).AndReturn(self.vdis)

    def test_fetch_vhd_image_works_with_bittorrent(self):
        self._setup_bittorrent()

        vm_utils.safe_find_sr(self.session).AndReturn("sr")
        vm_utils._scan_sr(self.session, "sr")
        vm_utils._check_vdi_size(self.context, self.session, self.instance,
                                 "vdi")

        self.mox.ReplayAll()

        self.assertEqual("vdi", vm_utils._fetch_vhd_image(self.context,
            self.session, self.instance, self.image_id)['root']['uuid'])

        self.mox.VerifyAll()

    def test_fetch_vhd_image_cleans_up_vdi_on_fail(self):
        self.mox.StubOutWithMock(self.session, 'call_xenapi')
        self._setup_bittorrent()

        vm_utils.safe_find_sr(self.session).AndReturn("sr")
        vm_utils._scan_sr(self.session, "sr")
        vm_utils._check_vdi_size(self.context, self.session, self.instance,
                "vdi").AndRaise(exception.InstanceTypeDiskTooSmall)

        self.session.call_xenapi("VDI.get_by_uuid", "vdi").AndReturn("ref")
        vm_utils.destroy_vdi(self.session, "ref")

        self.mox.ReplayAll()

        self.assertRaises(exception.InstanceTypeDiskTooSmall,
                vm_utils._fetch_vhd_image, self.context, self.session,
                self.instance, self.image_id)

        self.mox.VerifyAll()


class ResizeHelpersTestCase(test.TestCase):
    def test_get_min_sectors(self):
        self.mox.StubOutWithMock(utils, 'execute')

        utils.execute('resize2fs', '-P', "fakepath",
            run_as_root=True).AndReturn(("size is: 42", ""))

        self.mox.ReplayAll()

        result = vm_utils._get_min_sectors("fakepath")
        self.assertEquals(42 * 4096 / 512, result)

    def test_repair_filesystem(self):
        self.mox.StubOutWithMock(utils, 'execute')

        utils.execute('e2fsck', '-f', "-y", "fakepath",
            run_as_root=True, check_exit_code=[0, 1, 2]).AndReturn(
                ("size is: 42", ""))

        self.mox.ReplayAll()

        vm_utils._repair_filesystem("fakepath")

    def _call_tune2fs_remove_journal(self, path):
        utils.execute("tune2fs", "-O ^has_journal", path, run_as_root=True)

    def _call_tune2fs_add_journal(self, path):
        utils.execute("tune2fs", "-j", path, run_as_root=True)

    def _call_parted(self, path, start, end):
        utils.execute('parted', '--script', path, 'rm', '1',
            run_as_root=True)
        utils.execute('parted', '--script', path, 'mkpart',
            'primary', '%ds' % start, '%ds' % end, run_as_root=True)

    def test_resize_part_and_fs_down_succeeds(self):
        self.mox.StubOutWithMock(vm_utils, "_repair_filesystem")
        self.mox.StubOutWithMock(utils, 'execute')
        self.mox.StubOutWithMock(vm_utils, "_get_min_sectors")

        dev_path = "/dev/fake"
        partition_path = "%s1" % dev_path
        vm_utils._repair_filesystem(partition_path)
        self._call_tune2fs_remove_journal(partition_path)
        vm_utils._get_min_sectors(partition_path).AndReturn(9)
        utils.execute("resize2fs", partition_path, "10s", run_as_root=True)
        self._call_parted(dev_path, 0, 9)
        self._call_tune2fs_add_journal(partition_path)

        self.mox.ReplayAll()

        vm_utils._resize_part_and_fs("fake", 0, 20, 10)

    def test_log_progress_if_required(self):
        self.mox.StubOutWithMock(vm_utils.LOG, "debug")
        vm_utils.LOG.debug(_("Sparse copy in progress, "
                             "%(complete_pct).2f%% complete. "
                             "%(left) bytes left to copy"),
                           {"complete_pct": 50.0, "left": 1})
        current = timeutils.utcnow()
        timeutils.set_time_override(current)
        timeutils.advance_time_seconds(vm_utils.PROGRESS_INTERVAL_SECONDS + 1)
        self.mox.ReplayAll()
        vm_utils._log_progress_if_required(1, current, 2)

    def test_log_progress_if_not_required(self):
        self.mox.StubOutWithMock(vm_utils.LOG, "debug")
        current = timeutils.utcnow()
        timeutils.set_time_override(current)
        timeutils.advance_time_seconds(vm_utils.PROGRESS_INTERVAL_SECONDS - 1)
        self.mox.ReplayAll()
        vm_utils._log_progress_if_required(1, current, 2)

    def test_resize_part_and_fs_down_fails_disk_too_big(self):
        self.mox.StubOutWithMock(vm_utils, "_repair_filesystem")
        self.mox.StubOutWithMock(utils, 'execute')
        self.mox.StubOutWithMock(vm_utils, "_get_min_sectors")

        dev_path = "/dev/fake"
        partition_path = "%s1" % dev_path
        vm_utils._repair_filesystem(partition_path)
        self._call_tune2fs_remove_journal(partition_path)
        vm_utils._get_min_sectors(partition_path).AndReturn(10)

        self.mox.ReplayAll()

        self.assertRaises(exception.ResizeError,
            vm_utils._resize_part_and_fs, "fake", 0, 20, 10)

    def test_resize_part_and_fs_up_succeeds(self):
        self.mox.StubOutWithMock(vm_utils, "_repair_filesystem")
        self.mox.StubOutWithMock(utils, 'execute')

        dev_path = "/dev/fake"
        partition_path = "%s1" % dev_path
        vm_utils._repair_filesystem(partition_path)
        self._call_tune2fs_remove_journal(partition_path)
        self._call_parted(dev_path, 0, 29)
        utils.execute("resize2fs", partition_path, run_as_root=True)
        self._call_tune2fs_add_journal(partition_path)

        self.mox.ReplayAll()

        vm_utils._resize_part_and_fs("fake", 0, 20, 30)


class CheckVDISizeTestCase(test.TestCase):
    def setUp(self):
        super(CheckVDISizeTestCase, self).setUp()
        self.context = 'fakecontext'
        self.session = 'fakesession'
        self.instance = dict(uuid='fakeinstance')
        self.vdi_uuid = 'fakeuuid'

    def test_not_too_large(self):
        self.mox.StubOutWithMock(flavors, 'extract_flavor')
        flavors.extract_flavor(self.instance).AndReturn(
                dict(root_gb=1))

        self.mox.StubOutWithMock(vm_utils, '_get_vdi_chain_size')
        vm_utils._get_vdi_chain_size(self.session,
                self.vdi_uuid).AndReturn(1073741824)

        self.mox.ReplayAll()

        vm_utils._check_vdi_size(self.context, self.session, self.instance,
                self.vdi_uuid)

    def test_too_large(self):
        self.mox.StubOutWithMock(flavors, 'extract_flavor')
        flavors.extract_flavor(self.instance).AndReturn(
                dict(root_gb=1))

        self.mox.StubOutWithMock(vm_utils, '_get_vdi_chain_size')
        vm_utils._get_vdi_chain_size(self.session,
                self.vdi_uuid).AndReturn(1073741825)

        self.mox.ReplayAll()

        self.assertRaises(exception.InstanceTypeDiskTooSmall,
                vm_utils._check_vdi_size, self.context, self.session,
                self.instance, self.vdi_uuid)

    def test_zero_root_gb_disables_check(self):
        self.mox.StubOutWithMock(flavors, 'extract_flavor')
        flavors.extract_flavor(self.instance).AndReturn(
                dict(root_gb=0))

        self.mox.ReplayAll()

        vm_utils._check_vdi_size(self.context, self.session, self.instance,
                self.vdi_uuid)


class GetInstanceForVdisForSrTestCase(stubs.XenAPITestBase):
    def setUp(self):
        super(GetInstanceForVdisForSrTestCase, self).setUp()
        self.flags(disable_process_locking=True,
                   instance_name_template='%d',
                   firewall_driver='nova.virt.xenapi.firewall.'
                                   'Dom0IptablesFirewallDriver',
                   xenapi_connection_url='test_url',
                   xenapi_connection_password='test_pass',)

    def test_get_instance_vdis_for_sr(self):
        vm_ref = fake.create_vm("foo", "Running")
        sr_ref = fake.create_sr()

        vdi_1 = fake.create_vdi('vdiname1', sr_ref)
        vdi_2 = fake.create_vdi('vdiname2', sr_ref)

        for vdi_ref in [vdi_1, vdi_2]:
            fake.create_vbd(vm_ref, vdi_ref)

        stubs.stubout_session(self.stubs, fake.SessionBase)
        driver = xenapi_conn.XenAPIDriver(False)

        result = list(vm_utils.get_instance_vdis_for_sr(
            driver._session, vm_ref, sr_ref))

        self.assertEquals([vdi_1, vdi_2], result)

    def test_get_instance_vdis_for_sr_no_vbd(self):
        vm_ref = fake.create_vm("foo", "Running")
        sr_ref = fake.create_sr()

        stubs.stubout_session(self.stubs, fake.SessionBase)
        driver = xenapi_conn.XenAPIDriver(False)

        result = list(vm_utils.get_instance_vdis_for_sr(
            driver._session, vm_ref, sr_ref))

        self.assertEquals([], result)

    def test_get_vdi_uuid_for_volume_with_sr_uuid(self):
        connection_data = get_fake_connection_data(XENSM_TYPE)
        stubs.stubout_session(self.stubs, fake.SessionBase)
        driver = xenapi_conn.XenAPIDriver(False)

        vdi_uuid = vm_utils.get_vdi_uuid_for_volume(
                driver._session, connection_data)
        self.assertEquals(vdi_uuid, 'falseVDI')

    def test_get_vdi_uuid_for_volume_failure(self):
        stubs.stubout_session(self.stubs, fake.SessionBase)
        driver = xenapi_conn.XenAPIDriver(False)

        def bad_introduce_sr(session, sr_uuid, label, sr_params):
            return None

        self.stubs.Set(volume_utils, 'introduce_sr', bad_introduce_sr)
        connection_data = get_fake_connection_data(XENSM_TYPE)
        self.assertRaises(exception.NovaException,
                          vm_utils.get_vdi_uuid_for_volume,
                          driver._session, connection_data)

    def test_get_vdi_uuid_for_volume_from_iscsi_vol_missing_sr_uuid(self):
        connection_data = get_fake_connection_data(ISCSI_TYPE)
        stubs.stubout_session(self.stubs, fake.SessionBase)
        driver = xenapi_conn.XenAPIDriver(False)

        vdi_uuid = vm_utils.get_vdi_uuid_for_volume(
                driver._session, connection_data)
        self.assertNotEquals(vdi_uuid, None)


class VMRefOrRaiseVMFoundTestCase(test.TestCase):

    def test_lookup_call(self):
        mock = mox.Mox()
        mock.StubOutWithMock(vm_utils, 'lookup')

        vm_utils.lookup('session', 'somename').AndReturn('ignored')

        mock.ReplayAll()
        vm_utils.vm_ref_or_raise('session', 'somename')
        mock.VerifyAll()

    def test_return_value(self):
        mock = mox.Mox()
        mock.StubOutWithMock(vm_utils, 'lookup')

        vm_utils.lookup(mox.IgnoreArg(), mox.IgnoreArg()).AndReturn('vmref')

        mock.ReplayAll()
        self.assertEquals(
            'vmref', vm_utils.vm_ref_or_raise('session', 'somename'))
        mock.VerifyAll()


class VMRefOrRaiseVMNotFoundTestCase(test.TestCase):

    def test_exception_raised(self):
        mock = mox.Mox()
        mock.StubOutWithMock(vm_utils, 'lookup')

        vm_utils.lookup('session', 'somename').AndReturn(None)

        mock.ReplayAll()
        self.assertRaises(
            exception.InstanceNotFound,
            lambda: vm_utils.vm_ref_or_raise('session', 'somename')
        )
        mock.VerifyAll()

    def test_exception_msg_contains_vm_name(self):
        mock = mox.Mox()
        mock.StubOutWithMock(vm_utils, 'lookup')

        vm_utils.lookup('session', 'somename').AndReturn(None)

        mock.ReplayAll()
        try:
            vm_utils.vm_ref_or_raise('session', 'somename')
        except exception.InstanceNotFound as e:
            self.assertTrue(
                'somename' in str(e))
        mock.VerifyAll()


class BittorrentTestCase(stubs.XenAPITestBase):
    def setUp(self):
        super(BittorrentTestCase, self).setUp()
        self.context = context.get_admin_context()

    def test_image_uses_bittorrent(self):
        sys_meta = {'image_bittorrent': True}
        instance = db.instance_create(self.context,
                                      {'system_metadata': sys_meta})
        instance = db.instance_get_by_uuid(self.context, instance['uuid'])
        self.flags(xenapi_torrent_images='some')
        self.assertTrue(vm_utils._image_uses_bittorrent(self.context,
                                                        instance))

    def _test_create_image(self, cache_type):
        sys_meta = {'image_cache_in_nova': True}
        instance = db.instance_create(self.context,
                                      {'system_metadata': sys_meta})
        instance = db.instance_get_by_uuid(self.context, instance['uuid'])
        self.flags(cache_images=cache_type)

        was = {'called': None}

        def fake_create_cached_image(*args):
            was['called'] = 'some'
            return {}
        self.stubs.Set(vm_utils, '_create_cached_image',
                       fake_create_cached_image)

        def fake_fetch_image(*args):
            was['called'] = 'none'
            return {}
        self.stubs.Set(vm_utils, '_fetch_image',
                       fake_fetch_image)

        vm_utils._create_image(self.context, None, instance,
                               'foo', 'bar', 'baz')

        self.assertEqual(was['called'], cache_type)

    def test_create_image_cached(self):
        self._test_create_image('some')

    def test_create_image_uncached(self):
        self._test_create_image('none')


class ShutdownTestCase(test.TestCase):

    def test_hardshutdown_should_return_true_when_vm_is_shutdown(self):
        self.mock = mox.Mox()
        session = FakeSession()
        instance = "instance"
        vm_ref = "vm-ref"
        self.mock.StubOutWithMock(vm_utils, 'is_vm_shutdown')
        vm_utils.is_vm_shutdown(session, vm_ref).AndReturn(True)
        self.mock.StubOutWithMock(vm_utils, 'LOG')
        self.assertTrue(vm_utils.hard_shutdown_vm(
            session, instance, vm_ref))

    def test_cleanshutdown_should_return_true_when_vm_is_shutdown(self):
        self.mock = mox.Mox()
        session = FakeSession()
        instance = "instance"
        vm_ref = "vm-ref"
        self.mock.StubOutWithMock(vm_utils, 'is_vm_shutdown')
        vm_utils.is_vm_shutdown(session, vm_ref).AndReturn(True)
        self.mock.StubOutWithMock(vm_utils, 'LOG')
        self.assertTrue(vm_utils.clean_shutdown_vm(
            session, instance, vm_ref))


class CreateVBDTestCase(test.TestCase):
    def setUp(self):
        super(CreateVBDTestCase, self).setUp()
        self.session = FakeSession()
        self.mock = mox.Mox()
        self.mock.StubOutWithMock(self.session, 'call_xenapi')
        self.vbd_rec = self._generate_vbd_rec()

    def _generate_vbd_rec(self):
        vbd_rec = {}
        vbd_rec['VM'] = 'vm_ref'
        vbd_rec['VDI'] = 'vdi_ref'
        vbd_rec['userdevice'] = '0'
        vbd_rec['bootable'] = False
        vbd_rec['mode'] = 'RW'
        vbd_rec['type'] = 'disk'
        vbd_rec['unpluggable'] = True
        vbd_rec['empty'] = False
        vbd_rec['other_config'] = {}
        vbd_rec['qos_algorithm_type'] = ''
        vbd_rec['qos_algorithm_params'] = {}
        vbd_rec['qos_supported_algorithms'] = []
        return vbd_rec

    def test_create_vbd_default_args(self):
        self.session.call_xenapi('VBD.create',
                self.vbd_rec).AndReturn("vbd_ref")
        self.mock.ReplayAll()

        result = vm_utils.create_vbd(self.session, "vm_ref", "vdi_ref", 0)
        self.assertEquals(result, "vbd_ref")
        self.mock.VerifyAll()

    def test_create_vbd_osvol(self):
        self.session.call_xenapi('VBD.create',
                self.vbd_rec).AndReturn("vbd_ref")
        self.session.call_xenapi('VBD.add_to_other_config', "vbd_ref",
                                 "osvol", "True")
        self.mock.ReplayAll()
        result = vm_utils.create_vbd(self.session, "vm_ref", "vdi_ref", 0,
                                     osvol=True)
        self.assertEquals(result, "vbd_ref")
        self.mock.VerifyAll()

    def test_create_vbd_extra_args(self):
        self.vbd_rec['VDI'] = 'OpaqueRef:NULL'
        self.vbd_rec['type'] = 'a'
        self.vbd_rec['mode'] = 'RO'
        self.vbd_rec['bootable'] = True
        self.vbd_rec['empty'] = True
        self.vbd_rec['unpluggable'] = False
        self.session.call_xenapi('VBD.create',
                self.vbd_rec).AndReturn("vbd_ref")
        self.mock.ReplayAll()

        result = vm_utils.create_vbd(self.session, "vm_ref", None, 0,
                vbd_type="a", read_only=True, bootable=True,
                empty=True, unpluggable=False)
        self.assertEquals(result, "vbd_ref")
        self.mock.VerifyAll()

    def test_attach_cd(self):
        self.mock.StubOutWithMock(vm_utils, 'create_vbd')

        vm_utils.create_vbd(self.session, "vm_ref", None, 1,
                vbd_type='cd', read_only=True, bootable=True,
                empty=True, unpluggable=False).AndReturn("vbd_ref")
        self.session.call_xenapi('VBD.insert', "vbd_ref", "vdi_ref")
        self.mock.ReplayAll()

        result = vm_utils.attach_cd(self.session, "vm_ref", "vdi_ref", 1)
        self.assertEquals(result, "vbd_ref")
        self.mock.VerifyAll()


class VDIOtherConfigTestCase(stubs.XenAPITestBase):
    """Tests to ensure that the code is populating VDI's `other_config`
    attribute with the correct metadta.
    """

    def setUp(self):
        super(VDIOtherConfigTestCase, self).setUp()

        class _FakeSession():
            def call_xenapi(self, operation, *args, **kwargs):
                # VDI.add_to_other_config -> VDI_add_to_other_config
                method = getattr(self, operation.replace('.', '_'), None)
                if method:
                    return method(*args, **kwargs)

                self.operation = operation
                self.args = args
                self.kwargs = kwargs

        self.session = _FakeSession()
        self.context = context.get_admin_context()
        self.fake_instance = {'uuid': 'aaaa-bbbb-cccc-dddd',
                              'name': 'myinstance'}

    def test_create_vdi(self):
        # Some images are registered with XenServer explicitly by calling
        # `create_vdi`
        vm_utils.create_vdi(self.session, 'sr_ref', self.fake_instance,
                            'myvdi', 'root', 1024, read_only=True)

        expected = {'nova_disk_type': 'root',
                    'nova_instance_uuid': 'aaaa-bbbb-cccc-dddd'}

        self.assertEqual(expected, self.session.args[0]['other_config'])

    def test_create_image(self):
        # Other images are registered implicitly when they are dropped into
        # the SR by a dom0 plugin or some other process
        self.flags(cache_images='none')

        def fake_fetch_image(*args):
            return {'root': {'uuid': 'fake-uuid'}}

        self.stubs.Set(vm_utils, '_fetch_image', fake_fetch_image)

        other_config = {}

        def VDI_add_to_other_config(ref, key, value):
            other_config[key] = value

        def VDI_get_record(ref):
            return {'other_config': {}}

        # Stubbing on the session object and not class so we don't pollute
        # other tests
        self.session.VDI_add_to_other_config = VDI_add_to_other_config
        self.session.VDI_get_record = VDI_get_record

        vm_utils._create_image(self.context, self.session, self.fake_instance,
                'myvdi', 'image1', vm_utils.ImageType.DISK_VHD)

        expected = {'nova_disk_type': 'root',
                    'nova_instance_uuid': 'aaaa-bbbb-cccc-dddd'}

        self.assertEqual(expected, other_config)

    def test_move_disks(self):
        # Migrated images should preserve the `other_config`
        other_config = {}

        def VDI_add_to_other_config(ref, key, value):
            other_config[key] = value

        def VDI_get_record(ref):
            return {'other_config': {}}

        def call_plugin_serialized(*args, **kwargs):
            return {'root': {'uuid': 'aaaa-bbbb-cccc-dddd'}}

        # Stubbing on the session object and not class so we don't pollute
        # other tests
        self.session.VDI_add_to_other_config = VDI_add_to_other_config
        self.session.VDI_get_record = VDI_get_record
        self.session.call_plugin_serialized = call_plugin_serialized

        self.stubs.Set(vm_utils, 'get_sr_path', lambda *a, **k: None)
        self.stubs.Set(vm_utils, 'scan_default_sr', lambda *a, **k: None)

        vm_utils.move_disks(self.session, self.fake_instance, {})

        expected = {'nova_disk_type': 'root',
                    'nova_instance_uuid': 'aaaa-bbbb-cccc-dddd'}

        self.assertEqual(expected, other_config)


def bad_fetcher(instance, image_id):
    raise test.TestingException("just plain bad.")


def another_fetcher(instance, image_id):
    return "http://www.foobar.com/%s" % image_id


class MockEntryPoint(object):
    name = "torrent_url"

    def load(self):
        return another_fetcher


class BitTorrentMiscTestCase(test.TestCase):

    def tearDown(self):
        vm_utils._TORRENT_URL_FN = None
        super(BitTorrentMiscTestCase, self).tearDown()

    def test_default_fetch_url(self):
        def mock_iter_none(namespace):
            return []
        self.stubs.Set(pkg_resources, 'iter_entry_points', mock_iter_none)

        image_id = "1-2-3-4-5"
        params = {}
        self.assertTrue(vm_utils._add_torrent_url({}, image_id, params))
        expected = urlparse.urljoin(CONF.xenapi_torrent_base_url,
                                    "%s.torrent" % image_id)
        self.assertEqual(expected, params['torrent_url'])
        self.assertEqual(vm_utils.get_torrent_url,
                         vm_utils._TORRENT_URL_FN)

    def test_with_extension(self):
        def mock_iter_single(namespace):
            return [MockEntryPoint()]
        self.stubs.Set(pkg_resources, 'iter_entry_points', mock_iter_single)

        image_id = "1-2-3-4-5"
        params = {}
        self.assertTrue(vm_utils._add_torrent_url({}, image_id, params))
        expected = "http://www.foobar.com/%s" % image_id
        self.assertEqual(expected, params['torrent_url'])
        self.assertEqual(another_fetcher, vm_utils._TORRENT_URL_FN)

    def test_more_than_one_extension(self):
        def mock_iter_multiple(namespace):
            return [MockEntryPoint(), MockEntryPoint()]
        self.stubs.Set(pkg_resources, 'iter_entry_points', mock_iter_multiple)
        image_id = "1-2-3-4-5"
        params = {}
        self.assertRaises(RuntimeError, vm_utils._add_torrent_url, {},
                          image_id, params)

    def test_fetch_url_failure(self):
        # fetcher function fails:
        vm_utils._TORRENT_URL_FN = bad_fetcher
        self.assertFalse(vm_utils._add_torrent_url({}, '1-2-3-4-5', {}))


class GenerateDiskTestCase(stubs.XenAPITestBase):
    def setUp(self):
        super(GenerateDiskTestCase, self).setUp()
        self.flags(disable_process_locking=True,
                   instance_name_template='%d',
                   firewall_driver='nova.virt.xenapi.firewall.'
                                   'Dom0IptablesFirewallDriver',
                   xenapi_connection_url='test_url',
                   xenapi_connection_password='test_pass',)
        stubs.stubout_session(self.stubs, fake.SessionBase)
        driver = xenapi_conn.XenAPIDriver(False)
        self.session = driver._session
        self.vm_ref = fake.create_vm("foo", "Running")

    def tearDown(self):
        super(GenerateDiskTestCase, self).tearDown()
        fake.destroy_vm(self.vm_ref)

    def _expect_parted_calls(self):
        self.mox.StubOutWithMock(utils, "execute")
        self.mox.StubOutWithMock(vm_utils, "destroy_vdi")
        utils.execute('parted', '--script', '/dev/fakedev', 'mklabel',
            'msdos', run_as_root=True)
        utils.execute('parted', '--script', '/dev/fakedev', 'mkpart',
            'primary', '0', '10', run_as_root=True)

    def _check_vdi(self, vdi_ref):
        vdi_rec = self.session.call_xenapi("VDI.get_record", vdi_ref)
        self.assertEqual(str(10 * 1024 * 1024), vdi_rec["virtual_size"])
        vbd_ref = vdi_rec["VBDs"][0]
        vbd_rec = self.session.call_xenapi("VBD.get_record", vbd_ref)
        self.assertEqual(self.vm_ref, vbd_rec['VM'])

    @test_xenapi.stub_vm_utils_with_vdi_attached_here
    def test_generate_disk_with_no_fs_given(self):
        self._expect_parted_calls()

        self.mox.ReplayAll()
        vdi_ref = vm_utils._generate_disk(self.session, {"uuid": "fake_uuid"},
            self.vm_ref, "2", "name", "user", 10, None)
        self._check_vdi(vdi_ref)

    @test_xenapi.stub_vm_utils_with_vdi_attached_here
    def test_generate_disk_swap(self):
        self._expect_parted_calls()
        utils.execute('mkswap', '/dev/fakedev1', run_as_root=True)

        self.mox.ReplayAll()
        vdi_ref = vm_utils._generate_disk(self.session, {"uuid": "fake_uuid"},
            self.vm_ref, "2", "name", "swap", 10, "linux-swap")
        self._check_vdi(vdi_ref)

    @test_xenapi.stub_vm_utils_with_vdi_attached_here
    def test_generate_disk_ephemeral(self):
        self._expect_parted_calls()
        utils.execute('mkfs', '-t', 'ext4', '/dev/fakedev1',
            run_as_root=True)

        self.mox.ReplayAll()
        vdi_ref = vm_utils._generate_disk(self.session, {"uuid": "fake_uuid"},
            self.vm_ref, "2", "name", "ephemeral", 10, "ext4")
        self._check_vdi(vdi_ref)

    @test_xenapi.stub_vm_utils_with_vdi_attached_here
    def test_generate_disk_ensure_cleanup_called(self):
        self._expect_parted_calls()
        utils.execute('mkfs', '-t', 'ext4', '/dev/fakedev1',
            run_as_root=True).AndRaise(test.TestingException)
        vm_utils.destroy_vdi(self.session, mox.IgnoreArg())

        self.mox.ReplayAll()
        self.assertRaises(test.TestingException, vm_utils._generate_disk,
            self.session, {"uuid": "fake_uuid"},
            self.vm_ref, "2", "name", "ephemeral", 10, "ext4")


class GenerateEphemeralTestCase(test.TestCase):
    def setUp(self):
        super(GenerateEphemeralTestCase, self).setUp()
        self.session = "session"
        self.instance = "instance"
        self.vm_ref = "vm_ref"
        self.name_label = "name"
        self.userdevice = 4
        self.mox.StubOutWithMock(vm_utils, "_generate_disk")
        self.mox.StubOutWithMock(vm_utils, "safe_destroy_vdis")

    def _expect_generate_disk(self, size, device, name_label):
        vm_utils._generate_disk(self.session, self.instance, self.vm_ref,
            str(device), name_label, 'ephemeral', size * 1024,
            None).AndReturn(device)

    def test_generate_ephemeral_adds_one_disk(self):
        self._expect_generate_disk(20, self.userdevice, self.name_label)
        self.mox.ReplayAll()

        vm_utils.generate_ephemeral(self.session, self.instance, self.vm_ref,
            str(self.userdevice), self.name_label, 20)

    def test_generate_ephemeral_adds_multiple_disks(self):
        self._expect_generate_disk(2000, self.userdevice, self.name_label)
        self._expect_generate_disk(2000, self.userdevice + 1, "name (1)")
        self._expect_generate_disk(30, self.userdevice + 2, "name (2)")
        self.mox.ReplayAll()

        vm_utils.generate_ephemeral(self.session, self.instance, self.vm_ref,
            str(self.userdevice), self.name_label, 4030)

    def test_generate_ephemeral_with_1TB_split(self):
        self._expect_generate_disk(1024, self.userdevice, self.name_label)
        self._expect_generate_disk(1024, self.userdevice + 1, "name (1)")
        self.mox.ReplayAll()

        vm_utils.generate_ephemeral(self.session, self.instance, self.vm_ref,
            str(self.userdevice), self.name_label, 2048)

    def test_generate_ephemeral_cleans_up_on_error(self):
        self._expect_generate_disk(2000, self.userdevice, self.name_label)
        self._expect_generate_disk(2000, self.userdevice + 1, "name (1)")

        vm_utils._generate_disk(self.session, self.instance, self.vm_ref,
            str(self.userdevice + 2), "name (2)", 'ephemeral', 30 * 1024,
            None).AndRaise(exception.NovaException)

        vm_utils.safe_destroy_vdis(self.session, [4, 5])

        self.mox.ReplayAll()

        self.assertRaises(exception.NovaException, vm_utils.generate_ephemeral,
            self.session, self.instance, self.vm_ref,
            str(self.userdevice), self.name_label, 4030)
