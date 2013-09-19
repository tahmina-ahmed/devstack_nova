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

from oslo.config import cfg

from nova import exception
from nova.image import glance
from nova.virt.xenapi import agent
from nova.virt.xenapi import vm_utils

CONF = cfg.CONF
CONF.import_opt('glance_num_retries', 'nova.image.glance')


class GlanceStore(object):
    def _call_glance_plugin(self, session, fn, params):
        glance_api_servers = glance.get_api_servers()

        def pick_glance(kwargs):
            g_host, g_port, g_use_ssl = glance_api_servers.next()
            kwargs['glance_host'] = g_host
            kwargs['glance_port'] = g_port
            kwargs['glance_use_ssl'] = g_use_ssl

        return session.call_plugin_serialized_with_retry(
            'glance', fn, CONF.glance_num_retries, pick_glance, **params)

    def _make_params(self, context, session, image_id):
        return {'image_id': image_id,
                'sr_path': vm_utils.get_sr_path(session),
                'auth_token': getattr(context, 'auth_token', None)}

    def download_image(self, context, session, instance, image_id):
        params = self._make_params(context, session, image_id)
        params['uuid_stack'] = vm_utils._make_uuid_stack()

        try:
            vdis = self._call_glance_plugin(session, 'download_vhd', params)
        except exception.PluginRetriesExceeded:
            raise exception.CouldNotFetchImage(image_id=image_id)

        return vdis

    def upload_image(self, context, session, instance, vdi_uuids, image_id):
        params = self._make_params(context, session, image_id)
        params['vdi_uuids'] = vdi_uuids

        props = params['properties'] = {}
        props['auto_disk_config'] = instance['auto_disk_config']
        props['os_type'] = instance['os_type'] or CONF.default_os_type

        sys_meta = instance["system_metadata"]
        if agent.USE_AGENT_SM_KEY in sys_meta:
            props[agent.USE_AGENT_KEY] = sys_meta[agent.USE_AGENT_SM_KEY]

        try:
            self._call_glance_plugin(session, 'upload_vhd', params)
        except exception.PluginRetriesExceeded:
            raise exception.CouldNotUploadImage(image_id=image_id)
