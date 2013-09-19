# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
#    Copyright (C) 2012 Red Hat, Inc.
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

from lxml import etree

from nova import test
from nova.tests import matchers
from nova.virt.libvirt import config


class LibvirtConfigBaseTest(test.TestCase):
    def assertXmlEqual(self, expectedXmlstr, actualXmlstr):
        self.assertThat(actualXmlstr, matchers.XMLMatches(expectedXmlstr))


class LibvirtConfigTest(LibvirtConfigBaseTest):

    def test_config_plain(self):
        obj = config.LibvirtConfigObject(root_name="demo")
        xml = obj.to_xml()

        self.assertXmlEqual(xml, "<demo/>")

    def test_config_ns(self):
        obj = config.LibvirtConfigObject(root_name="demo", ns_prefix="foo",
                                         ns_uri="http://example.com/foo")
        xml = obj.to_xml()

        self.assertXmlEqual(xml, """
            <foo:demo xmlns:foo="http://example.com/foo"/>""")

    def test_config_text(self):
        obj = config.LibvirtConfigObject(root_name="demo")
        root = obj.format_dom()
        root.append(obj._text_node("foo", "bar"))

        xml = etree.tostring(root)
        self.assertXmlEqual(xml, "<demo><foo>bar</foo></demo>")

    def test_config_parse(self):
        inxml = "<demo><foo/></demo>"
        obj = config.LibvirtConfigObject(root_name="demo")
        obj.parse_str(inxml)


class LibvirtConfigCapsTest(LibvirtConfigBaseTest):

    def test_config_host(self):
        xmlin = """
        <capabilities>
          <host>
            <uuid>c7a5fdbd-edaf-9455-926a-d65c16db1809</uuid>
            <cpu>
              <arch>x86_64</arch>
              <model>Opteron_G3</model>
              <vendor>AMD</vendor>
              <topology sockets='1' cores='4' threads='1'/>
              <feature name='ibs'/>
              <feature name='osvw'/>
            </cpu>
          </host>
          <guest>
            <os_type>hvm</os_type>
            <arch name='x86_64'/>
          </guest>
          <guest>
            <os_type>hvm</os_type>
            <arch name='i686'/>
          </guest>
        </capabilities>"""

        obj = config.LibvirtConfigCaps()
        obj.parse_str(xmlin)

        self.assertEqual(type(obj.host), config.LibvirtConfigCapsHost)
        self.assertEqual(obj.host.uuid, "c7a5fdbd-edaf-9455-926a-d65c16db1809")

        xmlout = obj.to_xml()

        self.assertXmlEqual(xmlin, xmlout)


class LibvirtConfigGuestTimerTest(LibvirtConfigBaseTest):
    def test_config_platform(self):
        obj = config.LibvirtConfigGuestTimer()
        obj.track = "host"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <timer name="platform" track="host"/>
        """)

    def test_config_pit(self):
        obj = config.LibvirtConfigGuestTimer()
        obj.name = "pit"
        obj.tickpolicy = "discard"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <timer name="pit" tickpolicy="discard"/>
        """)

    def test_config_hpet(self):
        obj = config.LibvirtConfigGuestTimer()
        obj.name = "hpet"
        obj.present = False

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <timer name="hpet" present="no"/>
        """)


class LibvirtConfigGuestClockTest(LibvirtConfigBaseTest):
    def test_config_utc(self):
        obj = config.LibvirtConfigGuestClock()

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <clock offset="utc"/>
        """)

    def test_config_localtime(self):
        obj = config.LibvirtConfigGuestClock()
        obj.offset = "localtime"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <clock offset="localtime"/>
        """)

    def test_config_timezone(self):
        obj = config.LibvirtConfigGuestClock()
        obj.offset = "timezone"
        obj.timezone = "EDT"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <clock offset="timezone" timezone="EDT"/>
        """)

    def test_config_variable(self):
        obj = config.LibvirtConfigGuestClock()
        obj.offset = "variable"
        obj.adjustment = "123456"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <clock offset="variable" adjustment="123456"/>
        """)

    def test_config_timers(self):
        obj = config.LibvirtConfigGuestClock()

        tmpit = config.LibvirtConfigGuestTimer()
        tmpit.name = "pit"
        tmpit.tickpolicy = "discard"

        tmrtc = config.LibvirtConfigGuestTimer()
        tmrtc.name = "rtc"
        tmrtc.tickpolicy = "merge"

        obj.add_timer(tmpit)
        obj.add_timer(tmrtc)

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <clock offset="utc">
               <timer name="pit" tickpolicy="discard"/>
               <timer name="rtc" tickpolicy="merge"/>
            </clock>
        """)


class LibvirtConfigCPUFeatureTest(LibvirtConfigBaseTest):

    def test_config_simple(self):
        obj = config.LibvirtConfigCPUFeature("mtrr")

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <feature name="mtrr"/>
        """)


class LibvirtConfigGuestCPUFeatureTest(LibvirtConfigBaseTest):

    def test_config_simple(self):
        obj = config.LibvirtConfigGuestCPUFeature("mtrr")
        obj.policy = "force"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <feature name="mtrr" policy="force"/>
        """)


class LibvirtConfigCPUTest(LibvirtConfigBaseTest):

    def test_config_simple(self):
        obj = config.LibvirtConfigCPU()
        obj.model = "Penryn"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <cpu>
              <model>Penryn</model>
            </cpu>
        """)

    def test_config_complex(self):
        obj = config.LibvirtConfigCPU()
        obj.model = "Penryn"
        obj.vendor = "Intel"
        obj.arch = "x86_64"

        obj.add_feature(config.LibvirtConfigCPUFeature("mtrr"))
        obj.add_feature(config.LibvirtConfigCPUFeature("apic"))

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <cpu>
              <arch>x86_64</arch>
              <model>Penryn</model>
              <vendor>Intel</vendor>
              <feature name="mtrr"/>
              <feature name="apic"/>
            </cpu>
        """)

    def test_config_topology(self):
        obj = config.LibvirtConfigCPU()
        obj.model = "Penryn"
        obj.sockets = 4
        obj.cores = 4
        obj.threads = 2

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <cpu>
              <model>Penryn</model>
              <topology sockets="4" cores="4" threads="2"/>
            </cpu>
        """)


class LibvirtConfigGuestCPUTest(LibvirtConfigBaseTest):

    def test_config_simple(self):
        obj = config.LibvirtConfigGuestCPU()
        obj.model = "Penryn"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <cpu match="exact">
              <model>Penryn</model>
            </cpu>
        """)

    def test_config_complex(self):
        obj = config.LibvirtConfigGuestCPU()
        obj.model = "Penryn"
        obj.vendor = "Intel"
        obj.arch = "x86_64"
        obj.mode = "custom"

        obj.add_feature(config.LibvirtConfigGuestCPUFeature("mtrr"))
        obj.add_feature(config.LibvirtConfigGuestCPUFeature("apic"))

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <cpu mode="custom" match="exact">
              <arch>x86_64</arch>
              <model>Penryn</model>
              <vendor>Intel</vendor>
              <feature name="mtrr" policy="require"/>
              <feature name="apic" policy="require"/>
            </cpu>
        """)

    def test_config_host(self):
        obj = config.LibvirtConfigGuestCPU()
        obj.mode = "host-model"
        obj.match = "exact"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <cpu mode="host-model" match="exact"/>
        """)


class LibvirtConfigGuestSMBIOSTest(LibvirtConfigBaseTest):

    def test_config_simple(self):
        obj = config.LibvirtConfigGuestSMBIOS()

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <smbios mode="sysinfo"/>
        """)


class LibvirtConfigGuestSysinfoTest(LibvirtConfigBaseTest):

    def test_config_simple(self):
        obj = config.LibvirtConfigGuestSysinfo()

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <sysinfo type="smbios"/>
        """)

    def test_config_bios(self):
        obj = config.LibvirtConfigGuestSysinfo()
        obj.bios_vendor = "Acme"
        obj.bios_version = "6.6.6"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <sysinfo type="smbios">
              <bios>
                <entry name="vendor">Acme</entry>
                <entry name="version">6.6.6</entry>
              </bios>
            </sysinfo>
        """)

    def test_config_system(self):
        obj = config.LibvirtConfigGuestSysinfo()
        obj.system_manufacturer = "Acme"
        obj.system_product = "Wile Coyote"
        obj.system_version = "6.6.6"
        obj.system_serial = "123456"
        obj.system_uuid = "c7a5fdbd-edaf-9455-926a-d65c16db1809"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <sysinfo type="smbios">
              <system>
                <entry name="manufacturer">Acme</entry>
                <entry name="product">Wile Coyote</entry>
                <entry name="version">6.6.6</entry>
                <entry name="serial">123456</entry>
                <entry name="uuid">c7a5fdbd-edaf-9455-926a-d65c16db1809</entry>
              </system>
            </sysinfo>
        """)

    def test_config_mixed(self):
        obj = config.LibvirtConfigGuestSysinfo()
        obj.bios_vendor = "Acme"
        obj.system_manufacturer = "Acme"
        obj.system_product = "Wile Coyote"
        obj.system_uuid = "c7a5fdbd-edaf-9455-926a-d65c16db1809"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <sysinfo type="smbios">
              <bios>
                <entry name="vendor">Acme</entry>
              </bios>
              <system>
                <entry name="manufacturer">Acme</entry>
                <entry name="product">Wile Coyote</entry>
                <entry name="uuid">c7a5fdbd-edaf-9455-926a-d65c16db1809</entry>
              </system>
            </sysinfo>
        """)


class LibvirtConfigGuestDiskTest(LibvirtConfigBaseTest):

    def test_config_file(self):
        obj = config.LibvirtConfigGuestDisk()
        obj.source_type = "file"
        obj.source_path = "/tmp/hello"
        obj.target_dev = "/dev/hda"
        obj.target_bus = "ide"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <disk type="file" device="disk">
              <source file="/tmp/hello"/>
              <target bus="ide" dev="/dev/hda"/>
            </disk>""")

    def test_config_file_serial(self):
        obj = config.LibvirtConfigGuestDisk()
        obj.source_type = "file"
        obj.source_path = "/tmp/hello"
        obj.target_dev = "/dev/hda"
        obj.target_bus = "ide"
        obj.serial = "7a97c4a3-6f59-41d4-bf47-191d7f97f8e9"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <disk type="file" device="disk">
              <source file="/tmp/hello"/>
              <target bus="ide" dev="/dev/hda"/>
              <serial>7a97c4a3-6f59-41d4-bf47-191d7f97f8e9</serial>
            </disk>""")

    def test_config_block(self):
        obj = config.LibvirtConfigGuestDisk()
        obj.source_type = "block"
        obj.source_path = "/tmp/hello"
        obj.source_device = "cdrom"
        obj.driver_name = "qemu"
        obj.target_dev = "/dev/hdc"
        obj.target_bus = "ide"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <disk type="block" device="cdrom">
              <driver name="qemu"/>
              <source dev="/tmp/hello"/>
              <target bus="ide" dev="/dev/hdc"/>
            </disk>""")

    def test_config_network(self):
        obj = config.LibvirtConfigGuestDisk()
        obj.source_type = "network"
        obj.source_protocol = "iscsi"
        obj.source_name = "foo.bar.com"
        obj.driver_name = "qemu"
        obj.driver_format = "qcow2"
        obj.target_dev = "/dev/hda"
        obj.target_bus = "ide"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <disk type="network" device="disk">
              <driver name="qemu" type="qcow2"/>
              <source name="foo.bar.com" protocol="iscsi"/>
              <target bus="ide" dev="/dev/hda"/>
            </disk>""")

    def test_config_network_no_name(self):
        obj = config.LibvirtConfigGuestDisk()
        obj.source_type = 'network'
        obj.source_protocol = 'nbd'
        obj.source_hosts = ['foo.bar.com']
        obj.source_ports = [None]
        obj.driver_name = 'qemu'
        obj.driver_format = 'raw'
        obj.target_dev = '/dev/vda'
        obj.target_bus = 'virtio'

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <disk type="network" device="disk">
              <driver name="qemu" type="raw"/>
              <source protocol="nbd">
                <host name="foo.bar.com"/>
              </source>
              <target bus="virtio" dev="/dev/vda"/>
            </disk>""")

    def test_config_network_multihost(self):
        obj = config.LibvirtConfigGuestDisk()
        obj.source_type = 'network'
        obj.source_protocol = 'rbd'
        obj.source_name = 'pool/image'
        obj.source_hosts = ['foo.bar.com', '::1', '1.2.3.4']
        obj.source_ports = [None, '123', '456']
        obj.driver_name = 'qemu'
        obj.driver_format = 'raw'
        obj.target_dev = '/dev/vda'
        obj.target_bus = 'virtio'

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <disk type="network" device="disk">
              <driver name="qemu" type="raw"/>
              <source name="pool/image" protocol="rbd">
                <host name="foo.bar.com"/>
                <host name="::1" port="123"/>
                <host name="1.2.3.4" port="456"/>
              </source>
              <target bus="virtio" dev="/dev/vda"/>
            </disk>""")

    def test_config_network_auth(self):
        obj = config.LibvirtConfigGuestDisk()
        obj.source_type = "network"
        obj.source_protocol = "rbd"
        obj.source_name = "pool/image"
        obj.driver_name = "qemu"
        obj.driver_format = "raw"
        obj.target_dev = "/dev/vda"
        obj.target_bus = "virtio"
        obj.auth_username = "foo"
        obj.auth_secret_type = "ceph"
        obj.auth_secret_uuid = "b38a3f43-4be2-4046-897f-b67c2f5e0147"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <disk type="network" device="disk">
              <driver name="qemu" type="raw"/>
              <source name="pool/image" protocol="rbd"/>
              <auth username="foo">
                <secret type="ceph"
                uuid="b38a3f43-4be2-4046-897f-b67c2f5e0147"/>
              </auth>
              <target bus="virtio" dev="/dev/vda"/>
            </disk>""")

    def test_config_iotune(self):
        obj = config.LibvirtConfigGuestDisk()
        obj.source_type = "file"
        obj.source_path = "/tmp/hello"
        obj.target_dev = "/dev/hda"
        obj.target_bus = "ide"
        obj.disk_read_bytes_sec = 1024000
        obj.disk_read_iops_sec = 1000
        obj.disk_total_bytes_sec = 2048000
        obj.disk_write_bytes_sec = 1024000
        obj.disk_write_iops_sec = 1000
        obj.disk_total_iops_sec = 2000

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <disk type="file" device="disk">
              <source file="/tmp/hello"/>
              <target bus="ide" dev="/dev/hda"/>
              <iotune>
                <read_bytes_sec>1024000</read_bytes_sec>
                <read_iops_sec>1000</read_iops_sec>
                <write_bytes_sec>1024000</write_bytes_sec>
                <write_iops_sec>1000</write_iops_sec>
                <total_bytes_sec>2048000</total_bytes_sec>
                <total_iops_sec>2000</total_iops_sec>
              </iotune>
            </disk>""")


class LibvirtConfigGuestFilesysTest(LibvirtConfigBaseTest):

    def test_config_mount(self):
        obj = config.LibvirtConfigGuestFilesys()
        obj.source_type = "mount"
        obj.source_dir = "/tmp/hello"
        obj.target_dir = "/mnt"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <filesystem type="mount">
              <source dir="/tmp/hello"/>
              <target dir="/mnt"/>
            </filesystem>""")


class LibvirtConfigGuestInputTest(LibvirtConfigBaseTest):

    def test_config_tablet(self):
        obj = config.LibvirtConfigGuestInput()

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <input type="tablet" bus="usb"/>""")


class LibvirtConfigGuestGraphicsTest(LibvirtConfigBaseTest):

    def test_config_graphics(self):
        obj = config.LibvirtConfigGuestGraphics()
        obj.type = "vnc"
        obj.autoport = True
        obj.keymap = "en_US"
        obj.listen = "127.0.0.1"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
  <graphics type="vnc" autoport="yes" keymap="en_US" listen="127.0.0.1"/>
                            """)


class LibvirtConfigGuestSerialTest(LibvirtConfigBaseTest):

    def test_config_file(self):
        obj = config.LibvirtConfigGuestSerial()
        obj.type = "file"
        obj.source_path = "/tmp/vm.log"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <serial type="file">
              <source path="/tmp/vm.log"/>
            </serial>""")


class LibvirtConfigGuestConsoleTest(LibvirtConfigBaseTest):
    def test_config_pty(self):
        obj = config.LibvirtConfigGuestConsole()
        obj.type = "pty"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <console type="pty"/>""")


class LibvirtConfigGuestChannelTest(LibvirtConfigBaseTest):
    def test_config_spice_minimal(self):
        obj = config.LibvirtConfigGuestChannel()
        obj.type = "spicevmc"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <channel type="spicevmc">
              <target type='virtio'/>
            </channel>""")

    def test_config_spice_full(self):
        obj = config.LibvirtConfigGuestChannel()
        obj.type = "spicevmc"
        obj.target_name = "com.redhat.spice.0"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <channel type="spicevmc">
              <target type='virtio' name='com.redhat.spice.0'/>
            </channel>""")


class LibvirtConfigGuestInterfaceTest(LibvirtConfigBaseTest):
    def test_config_ethernet(self):
        obj = config.LibvirtConfigGuestInterface()
        obj.net_type = "ethernet"
        obj.mac_addr = "DE:AD:BE:EF:CA:FE"
        obj.model = "virtio"
        obj.target_dev = "vnet0"
        obj.driver_name = "vhost"
        obj.vif_inbound_average = 1024000
        obj.vif_inbound_peak = 10240000
        obj.vif_inbound_burst = 1024000
        obj.vif_outbound_average = 1024000
        obj.vif_outbound_peak = 10240000
        obj.vif_outbound_burst = 1024000

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <interface type="ethernet">
              <mac address="DE:AD:BE:EF:CA:FE"/>
              <model type="virtio"/>
              <driver name="vhost"/>
              <target dev="vnet0"/>
              <bandwidth>
                <inbound average="1024000" peak="10240000" burst="1024000"/>
                <outbound average="1024000" peak="10240000" burst="1024000"/>
              </bandwidth>
            </interface>""")

    def test_config_bridge(self):
        obj = config.LibvirtConfigGuestInterface()
        obj.net_type = "bridge"
        obj.source_dev = "br0"
        obj.mac_addr = "DE:AD:BE:EF:CA:FE"
        obj.model = "virtio"
        obj.target_dev = "tap12345678"
        obj.filtername = "clean-traffic"
        obj.filterparams.append({"key": "IP", "value": "192.168.122.1"})
        obj.vif_inbound_average = 1024000
        obj.vif_inbound_peak = 10240000
        obj.vif_inbound_burst = 1024000
        obj.vif_outbound_average = 1024000
        obj.vif_outbound_peak = 10240000
        obj.vif_outbound_burst = 1024000

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <interface type="bridge">
              <mac address="DE:AD:BE:EF:CA:FE"/>
              <model type="virtio"/>
              <source bridge="br0"/>
              <target dev="tap12345678"/>
              <filterref filter="clean-traffic">
                <parameter name="IP" value="192.168.122.1"/>
              </filterref>
              <bandwidth>
                <inbound average="1024000" peak="10240000" burst="1024000"/>
                <outbound average="1024000" peak="10240000" burst="1024000"/>
              </bandwidth>
            </interface>""")

    def test_config_bridge_ovs(self):
        obj = config.LibvirtConfigGuestInterface()
        obj.net_type = "bridge"
        obj.source_dev = "br0"
        obj.mac_addr = "DE:AD:BE:EF:CA:FE"
        obj.model = "virtio"
        obj.target_dev = "tap12345678"
        obj.vporttype = "openvswitch"
        obj.vportparams.append({"key": "instanceid", "value": "foobar"})

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <interface type="bridge">
              <mac address="DE:AD:BE:EF:CA:FE"/>
              <model type="virtio"/>
              <source bridge="br0"/>
              <target dev="tap12345678"/>
              <virtualport type="openvswitch">
                <parameters instanceid="foobar"/>
              </virtualport>
            </interface>""")

    def test_config_8021Qbh(self):
        obj = config.LibvirtConfigGuestInterface()
        obj.net_type = "direct"
        obj.mac_addr = "DE:AD:BE:EF:CA:FE"
        obj.model = "virtio"
        obj.target_dev = "tap12345678"
        obj.source_dev = "eth0"
        obj.vporttype = "802.1Qbh"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <interface type="direct">
              <mac address="DE:AD:BE:EF:CA:FE"/>
              <model type="virtio"/>
              <source dev="eth0" mode="private"/>
              <target dev="tap12345678"/>
              <virtualport type="802.1Qbh"/>
            </interface>""")


class LibvirtConfigGuestTest(LibvirtConfigBaseTest):

    def test_config_lxc(self):
        obj = config.LibvirtConfigGuest()
        obj.virt_type = "lxc"
        obj.memory = 1024 * 1024 * 100
        obj.vcpus = 2
        obj.cpuset = "0-3,^2,4-5"
        obj.name = "demo"
        obj.uuid = "b38a3f43-4be2-4046-897f-b67c2f5e0147"
        obj.os_type = "exe"
        obj.os_init_path = "/sbin/init"

        fs = config.LibvirtConfigGuestFilesys()
        fs.source_dir = "/root/lxc"
        fs.target_dir = "/"

        obj.add_device(fs)

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <domain type="lxc">
              <uuid>b38a3f43-4be2-4046-897f-b67c2f5e0147</uuid>
              <name>demo</name>
              <memory>104857600</memory>
              <vcpu cpuset="0-3,^2,4-5">2</vcpu>
              <os>
                <type>exe</type>
                <init>/sbin/init</init>
              </os>
              <devices>
                <filesystem type="mount">
                  <source dir="/root/lxc"/>
                  <target dir="/"/>
                </filesystem>
              </devices>
            </domain>""")

    def test_config_xen_pv(self):
        obj = config.LibvirtConfigGuest()
        obj.virt_type = "xen"
        obj.memory = 1024 * 1024 * 100
        obj.vcpus = 2
        obj.cpuset = "0-3,^2,4-5"
        obj.name = "demo"
        obj.uuid = "b38a3f43-4be2-4046-897f-b67c2f5e0147"
        obj.os_type = "linux"
        obj.os_kernel = "/tmp/vmlinuz"
        obj.os_initrd = "/tmp/ramdisk"
        obj.os_root = "root=xvda"
        obj.os_cmdline = "console=xvc0"

        disk = config.LibvirtConfigGuestDisk()
        disk.source_type = "file"
        disk.source_path = "/tmp/img"
        disk.target_dev = "/dev/xvda"
        disk.target_bus = "xen"

        obj.add_device(disk)

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <domain type="xen">
              <uuid>b38a3f43-4be2-4046-897f-b67c2f5e0147</uuid>
              <name>demo</name>
              <memory>104857600</memory>
              <vcpu cpuset="0-3,^2,4-5">2</vcpu>
              <os>
                <type>linux</type>
                <kernel>/tmp/vmlinuz</kernel>
                <initrd>/tmp/ramdisk</initrd>
                <cmdline>console=xvc0</cmdline>
                <root>root=xvda</root>
              </os>
              <devices>
                <disk type="file" device="disk">
                  <source file="/tmp/img"/>
                  <target bus="xen" dev="/dev/xvda"/>
                </disk>
              </devices>
            </domain>""")

    def test_config_xen_hvm(self):
        obj = config.LibvirtConfigGuest()
        obj.virt_type = "xen"
        obj.memory = 1024 * 1024 * 100
        obj.vcpus = 2
        obj.cpuset = "0-3,^2,4-5"
        obj.name = "demo"
        obj.uuid = "b38a3f43-4be2-4046-897f-b67c2f5e0147"
        obj.os_type = "hvm"
        obj.os_loader = '/usr/lib/xen/boot/hvmloader'
        obj.os_root = "root=xvda"
        obj.os_cmdline = "console=xvc0"
        obj.acpi = True
        obj.apic = True

        disk = config.LibvirtConfigGuestDisk()
        disk.source_type = "file"
        disk.source_path = "/tmp/img"
        disk.target_dev = "/dev/xvda"
        disk.target_bus = "xen"

        obj.add_device(disk)

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <domain type="xen">
              <uuid>b38a3f43-4be2-4046-897f-b67c2f5e0147</uuid>
              <name>demo</name>
              <memory>104857600</memory>
              <vcpu cpuset="0-3,^2,4-5">2</vcpu>
              <os>
                <type>hvm</type>
                <loader>/usr/lib/xen/boot/hvmloader</loader>
                <cmdline>console=xvc0</cmdline>
                <root>root=xvda</root>
              </os>
              <features>
                <acpi/>
                <apic/>
              </features>
              <devices>
                <disk type="file" device="disk">
                  <source file="/tmp/img"/>
                  <target bus="xen" dev="/dev/xvda"/>
                </disk>
              </devices>
            </domain>""")

    def test_config_kvm(self):
        obj = config.LibvirtConfigGuest()
        obj.virt_type = "kvm"
        obj.memory = 1024 * 1024 * 100
        obj.vcpus = 2
        obj.cpuset = "0-3,^2,4-5"
        obj.cpu_shares = 100
        obj.cpu_quota = 50000
        obj.cpu_period = 25000
        obj.name = "demo"
        obj.uuid = "b38a3f43-4be2-4046-897f-b67c2f5e0147"
        obj.os_type = "linux"
        obj.os_boot_dev = "hd"
        obj.os_smbios = config.LibvirtConfigGuestSMBIOS()
        obj.acpi = True
        obj.apic = True

        obj.sysinfo = config.LibvirtConfigGuestSysinfo()
        obj.sysinfo.bios_vendor = "Acme"
        obj.sysinfo.system_version = "1.0.0"

        disk = config.LibvirtConfigGuestDisk()
        disk.source_type = "file"
        disk.source_path = "/tmp/img"
        disk.target_dev = "/dev/vda"
        disk.target_bus = "virtio"

        obj.add_device(disk)

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <domain type="kvm">
              <uuid>b38a3f43-4be2-4046-897f-b67c2f5e0147</uuid>
              <name>demo</name>
              <memory>104857600</memory>
              <vcpu cpuset="0-3,^2,4-5">2</vcpu>
              <sysinfo type='smbios'>
                 <bios>
                   <entry name="vendor">Acme</entry>
                 </bios>
                 <system>
                   <entry name="version">1.0.0</entry>
                 </system>
              </sysinfo>
              <os>
                <type>linux</type>
                <boot dev="hd"/>
                <smbios mode="sysinfo"/>
              </os>
              <features>
                <acpi/>
                <apic/>
              </features>
              <cputune>
                <shares>100</shares>
                <quota>50000</quota>
                <period>25000</period>
              </cputune>
              <devices>
                <disk type="file" device="disk">
                  <source file="/tmp/img"/>
                  <target bus="virtio" dev="/dev/vda"/>
                </disk>
              </devices>
            </domain>""")


class LibvirtConfigGuestSnapshotTest(LibvirtConfigBaseTest):

    def test_config_snapshot(self):
        obj = config.LibvirtConfigGuestSnapshot()
        obj.name = "Demo"

        xml = obj.to_xml()
        self.assertXmlEqual(xml, """
            <domainsnapshot>
              <name>Demo</name>
            </domainsnapshot>""")
