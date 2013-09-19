# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
#    Copyright 2011 OpenStack Foundation
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

import errno
import platform
import socket

from oslo.config import cfg

from nova.compute import flavors
import nova.context
import nova.db
from nova import exception
from nova.image import glance
from nova.network import minidns
from nova.network import model as network_model

CONF = cfg.CONF
CONF.import_opt('use_ipv6', 'nova.netconf')


def get_test_admin_context():
    return nova.context.get_admin_context()


def get_test_image_info(context, instance_ref):
    if not context:
        context = get_test_admin_context()

    image_ref = instance_ref['image_ref']
    image_service, image_id = glance.get_remote_image_service(context,
                                                              image_ref)
    return image_service.show(context, image_id)


def get_test_instance_type(context=None):
    if not context:
        context = get_test_admin_context()

    test_instance_type = {'name': 'kinda.big',
                          'flavorid': 'someid',
                          'memory_mb': 2048,
                          'vcpus': 4,
                          'root_gb': 40,
                          'ephemeral_gb': 80,
                          'swap': 1024}
    try:
        instance_type_ref = nova.db.flavor_create(context,
                                                         test_instance_type)
    except (exception.InstanceTypeExists, exception.InstanceTypeIdExists):
        instance_type_ref = nova.db.flavor_get_by_name(context,
                                                              'kinda.big')
    return instance_type_ref


def get_test_instance(context=None, instance_type=None):
    if not context:
        context = get_test_admin_context()

    if not instance_type:
        instance_type = get_test_instance_type(context)

    metadata = {}
    flavors.save_flavor_info(metadata, instance_type, '')

    test_instance = {'memory_kb': '2048000',
                     'basepath': '/some/path',
                     'bridge_name': 'br100',
                     'vcpus': 4,
                     'root_gb': 40,
                     'project_id': 'fake',
                     'bridge': 'br101',
                     'image_ref': 'cedef40a-ed67-4d10-800e-17455edce175',
                     'instance_type_id': '5',
                     'system_metadata': metadata,
                     'extra_specs': {}}

    instance_ref = nova.db.instance_create(context, test_instance)
    return instance_ref


def get_test_network_info(count=1, legacy_model=True):
    ipv6 = CONF.use_ipv6
    fake = 'fake'
    fake_ip = '0.0.0.0/0'
    fake_ip_2 = '0.0.0.1/0'
    fake_ip_3 = '0.0.0.1/0'
    fake_netmask = '255.255.255.255'
    fake_vlan = 100
    fake_bridge_interface = 'eth0'

    def legacy():
        network = {'bridge': fake,
                   'cidr': fake_ip,
                   'cidr_v6': fake_ip,
                   'vlan': fake_vlan,
                   'bridge_interface': fake_bridge_interface,
                   'injected': False}
        mapping = {'mac': fake,
                   'vif_type': network_model.VIF_TYPE_BRIDGE,
                   'vif_uuid': 'vif-xxx-yyy-zzz',
                   'dhcp_server': fake,
                   'dns': ['fake1', 'fake2'],
                   'gateway': fake,
                   'gateway_v6': fake,
                   'ips': [{'ip': fake_ip, 'netmask': fake_netmask},
                           {'ip': fake_ip, 'netmask': fake_netmask}]}
        if ipv6:
            mapping['ip6s'] = [{'ip': fake_ip, 'netmask': fake_netmask},
                               {'ip': fake_ip_2},
                               {'ip': fake_ip_3}]
        return network, mapping

    def current():
        fake_ip = '0.0.0.0'
        subnet_4 = network_model.Subnet(cidr=fake_ip,
                                        dns=[network_model.IP(fake_ip),
                                             network_model.IP(fake_ip)],
                                        gateway=network_model.IP(fake_ip),
                                        ips=[network_model.IP(fake_ip),
                                             network_model.IP(fake_ip)],
                                        routes=None,
                                        dhcp_server=network_model.IP(fake_ip))
        subnet_6 = network_model.Subnet(cidr=fake_ip,
                                        gateway=network_model.IP(fake_ip),
                                        ips=[network_model.IP(fake_ip),
                                             network_model.IP(fake_ip),
                                             network_model.IP(fake_ip)],
                                        routes=None,
                                        version=6)
        subnets = [subnet_4]
        if ipv6:
            subnets.append(subnet_6)
        network = network_model.Network(id=None,
                                        bridge=fake,
                                        label=None,
                                        subnets=subnets,
                                        vlan=fake_vlan,
                                        bridge_interface=fake_bridge_interface,
                                        injected=False)
        vif = network_model.VIF(id='vif-xxx-yyy-zzz',
                                address=fake,
                                network=network,
                                type=network_model.VIF_TYPE_BRIDGE,
                                devname=None,
                                ovs_interfaceid=None)

        return vif

    if legacy_model:
        return [legacy() for x in xrange(0, count)]
    else:
        return network_model.NetworkInfo([current() for x in xrange(0, count)])


def is_osx():
    return platform.mac_ver()[0] != ''


test_dns_managers = []


def dns_manager():
    global test_dns_managers
    manager = minidns.MiniDNS()
    test_dns_managers.append(manager)
    return manager


def cleanup_dns_managers():
    global test_dns_managers
    for manager in test_dns_managers:
        manager.delete_dns_file()
    test_dns_managers = []


def killer_xml_body():
    return (("""<!DOCTYPE x [
            <!ENTITY a "%(a)s">
            <!ENTITY b "%(b)s">
            <!ENTITY c "%(c)s">]>
        <foo>
            <bar>
                <v1>%(d)s</v1>
            </bar>
        </foo>""") % {
        'a': 'A' * 10,
        'b': '&a;' * 10,
        'c': '&b;' * 10,
        'd': '&c;' * 9999,
    }).strip()


def is_ipv6_supported():
    has_ipv6_support = True
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    except socket.error as e:
        if e.errno == errno.EAFNOSUPPORT:
            has_ipv6_support = False
        else:
            raise
    return has_ipv6_support
