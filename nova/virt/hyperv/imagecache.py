# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 Cloudbase Solutions Srl
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
Image caching and management.
"""
import os

from oslo.config import cfg

from nova.compute import flavors
from nova.openstack.common import excutils
from nova.openstack.common.gettextutils import _
from nova.openstack.common import log as logging
from nova import utils
from nova.virt.hyperv import pathutils
from nova.virt.hyperv import vhdutils
from nova.virt.hyperv import vmutils
from nova.virt import images

LOG = logging.getLogger(__name__)

CONF = cfg.CONF
CONF.import_opt('use_cow_images', 'nova.virt.driver')


class ImageCache(object):
    def __init__(self):
        self._pathutils = pathutils.PathUtils()
        self._vhdutils = vhdutils.VHDUtils()

    def _validate_vhd_image(self, vhd_path):
        try:
            self._vhdutils.validate_vhd(vhd_path)
        except Exception as ex:
            LOG.exception(ex)
            raise vmutils.HyperVException(_('The image is not a valid VHD: %s')
                                          % vhd_path)

    def _get_root_vhd_size_gb(self, instance):
        try:
            # In case of resizes we need the old root disk size
            old_instance_type = flavors.extract_flavor(
                instance, prefix='old_')
            return old_instance_type['root_gb']
        except KeyError:
            return instance['root_gb']

    def _resize_and_cache_vhd(self, instance, vhd_path):
        vhd_info = self._vhdutils.get_vhd_info(vhd_path)
        vhd_size = vhd_info['MaxInternalSize']

        root_vhd_size_gb = self._get_root_vhd_size_gb(instance)
        root_vhd_size = root_vhd_size_gb * 1024 ** 3

        if root_vhd_size < vhd_size:
            raise vmutils.HyperVException(
                _("Cannot resize the image to a size smaller than the VHD "
                  "max. internal size: %(vhd_size)s. Requested disk size: "
                  "%(root_vhd_size)s") %
                {'vhd_size': vhd_size, 'root_vhd_size': root_vhd_size}
            )
        if root_vhd_size > vhd_size:
            path_parts = os.path.splitext(vhd_path)
            resized_vhd_path = '%s_%s%s' % (path_parts[0],
                                            root_vhd_size_gb,
                                            path_parts[1])

            @utils.synchronized(resized_vhd_path)
            def copy_and_resize_vhd():
                if not self._pathutils.exists(resized_vhd_path):
                    try:
                        LOG.debug(_("Copying VHD %(vhd_path)s to "
                                    "%(resized_vhd_path)s"),
                                  {'vhd_path': vhd_path,
                                   'resized_vhd_path': resized_vhd_path})
                        self._pathutils.copyfile(vhd_path, resized_vhd_path)
                        LOG.debug(_("Resizing VHD %(resized_vhd_path)s to new "
                                    "size %(root_vhd_size)s"),
                                  {'resized_vhd_path': resized_vhd_path,
                                   'root_vhd_size': root_vhd_size})
                        self._vhdutils.resize_vhd(resized_vhd_path,
                                                  root_vhd_size)
                    except Exception:
                        with excutils.save_and_reraise_exception():
                            if self._pathutils.exists(resized_vhd_path):
                                self._pathutils.remove(resized_vhd_path)

            copy_and_resize_vhd()
            return resized_vhd_path

    def get_cached_image(self, context, instance):
        image_id = instance['image_ref']

        base_vhd_dir = self._pathutils.get_base_vhd_dir()
        vhd_path = os.path.join(base_vhd_dir, image_id + ".vhd")

        @utils.synchronized(vhd_path)
        def fetch_image_if_not_existing():
            if not self._pathutils.exists(vhd_path):
                try:
                    images.fetch(context, image_id, vhd_path,
                                 instance['user_id'],
                                 instance['project_id'])
                except Exception:
                    with excutils.save_and_reraise_exception():
                        if self._pathutils.exists(vhd_path):
                            self._pathutils.remove(vhd_path)

        fetch_image_if_not_existing()

        if CONF.use_cow_images:
            # Resize the base VHD image as it's not possible to resize a
            # differencing VHD.
            resized_vhd_path = self._resize_and_cache_vhd(instance, vhd_path)
            if resized_vhd_path:
                return resized_vhd_path

        return vhd_path
