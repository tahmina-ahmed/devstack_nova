# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 OpenStack Foundation
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
Tests of the new image services, both as a service layer,
and as a WSGI layer
"""

import urlparse

from lxml import etree
import webob

from nova.api.openstack.compute.plugins.v3 import images
from nova.api.openstack.compute.views import images as images_view
from nova.api.openstack import xmlutil
from nova import exception
from nova.image import glance
from nova import test
from nova.tests.api.openstack import fakes
from nova.tests import matchers

NS = "{http://docs.openstack.org/compute/api/v1.1}"
ATOMNS = "{http://www.w3.org/2005/Atom}"
NOW_API_FORMAT = "2010-10-11T10:30:22Z"


class ImagesControllerTest(test.TestCase):
    """
    Test of the OpenStack API /images application controller w/Glance.
    """

    def setUp(self):
        """Run before each test."""
        super(ImagesControllerTest, self).setUp()
        fakes.stub_out_networking(self.stubs)
        fakes.stub_out_rate_limiting(self.stubs)
        fakes.stub_out_key_pair_funcs(self.stubs)
        fakes.stub_out_compute_api_snapshot(self.stubs)
        fakes.stub_out_compute_api_backup(self.stubs)
        fakes.stub_out_glance(self.stubs)

        self.controller = images.ImagesController()

    def test_get_image(self):
        fake_req = fakes.HTTPRequestV3.blank('/os-images/123')
        actual_image = self.controller.show(fake_req, '124')

        href = "http://localhost/v3/images/124"
        bookmark = "http://localhost/images/124"
        alternate = "%s/images/124" % glance.generate_glance_url()
        server_uuid = "aa640691-d1a7-4a67-9d3c-d35ee6b3cc74"
        server_href = "http://localhost/v3/servers/" + server_uuid
        server_bookmark = "http://localhost/servers/" + server_uuid

        expected_image = {
            "image": {
                "id": "124",
                "name": "queued snapshot",
                "updated": NOW_API_FORMAT,
                "created": NOW_API_FORMAT,
                "status": "SAVING",
                "progress": 25,
                "size": 25165824,
                "minDisk": 0,
                "minRam": 0,
                'server': {
                    'id': server_uuid,
                    "links": [{
                        "rel": "self",
                        "href": server_href,
                    },
                    {
                        "rel": "bookmark",
                        "href": server_bookmark,
                    }],
                },
                "metadata": {
                    "instance_uuid": server_uuid,
                    "user_id": "fake",
                },
                "links": [{
                    "rel": "self",
                    "href": href,
                },
                {
                    "rel": "bookmark",
                    "href": bookmark,
                },
                {
                    "rel": "alternate",
                    "type": "application/vnd.openstack.image",
                    "href": alternate
                }],
            },
        }

        self.assertThat(actual_image, matchers.DictMatches(expected_image))

    def test_get_image_with_custom_prefix(self):
        self.flags(osapi_compute_link_prefix='https://zoo.com:42',
                   osapi_glance_link_prefix='http://circus.com:34')
        fake_req = fakes.HTTPRequestV3.blank('/v3/os-images/124')
        actual_image = self.controller.show(fake_req, '124')
        href = "https://zoo.com:42/v3/images/124"
        bookmark = "https://zoo.com:42/images/124"
        alternate = "http://circus.com:34/images/124"
        server_uuid = "aa640691-d1a7-4a67-9d3c-d35ee6b3cc74"
        server_href = "https://zoo.com:42/v3/servers/" + server_uuid
        server_bookmark = "https://zoo.com:42/servers/" + server_uuid

        expected_image = {
            "image": {
                "id": "124",
                "name": "queued snapshot",
                "updated": NOW_API_FORMAT,
                "created": NOW_API_FORMAT,
                "status": "SAVING",
                "progress": 25,
                "size": 25165824,
                "minDisk": 0,
                "minRam": 0,
                'server': {
                    'id': server_uuid,
                    "links": [{
                        "rel": "self",
                        "href": server_href,
                    },
                    {
                        "rel": "bookmark",
                        "href": server_bookmark,
                    }],
                },
                "metadata": {
                    "instance_uuid": server_uuid,
                    "user_id": "fake",
                },
                "links": [{
                    "rel": "self",
                    "href": href,
                },
                {
                    "rel": "bookmark",
                    "href": bookmark,
                },
                {
                    "rel": "alternate",
                    "type": "application/vnd.openstack.image",
                    "href": alternate
                }],
            },
        }
        self.assertThat(actual_image, matchers.DictMatches(expected_image))

    def test_get_image_404(self):
        fake_req = fakes.HTTPRequestV3.blank('/os-images/unknown')
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.show, fake_req, 'unknown')

    def test_get_image_details(self):
        request = fakes.HTTPRequestV3.blank('/os-images/detail')
        response = self.controller.detail(request)
        response_list = response["images"]

        server_uuid = "aa640691-d1a7-4a67-9d3c-d35ee6b3cc74"
        server_href = "http://localhost/v3/servers/" + server_uuid
        server_bookmark = "http://localhost/servers/" + server_uuid
        alternate = "%s/images/%s"

        expected = [{
            'id': '123',
            'name': 'public image',
            'metadata': {'key1': 'value1'},
            'updated': NOW_API_FORMAT,
            'created': NOW_API_FORMAT,
            'status': 'ACTIVE',
            'progress': 100,
            "size": 25165824,
            'minDisk': 10,
            'minRam': 128,
            "links": [{
                "rel": "self",
                "href": "http://localhost/v3/images/123",
            },
            {
                "rel": "bookmark",
                "href": "http://localhost/images/123",
            },
            {
                "rel": "alternate",
                "type": "application/vnd.openstack.image",
                "href": alternate % (glance.generate_glance_url(), 123),
            }],
        },
        {
            'id': '124',
            'name': 'queued snapshot',
            'metadata': {
                u'instance_uuid': server_uuid,
                u'user_id': u'fake',
            },
            'updated': NOW_API_FORMAT,
            'created': NOW_API_FORMAT,
            'status': 'SAVING',
            'progress': 25,
            "size": 25165824,
            'minDisk': 0,
            'minRam': 0,
            'server': {
                'id': server_uuid,
                "links": [{
                    "rel": "self",
                    "href": server_href,
                },
                {
                    "rel": "bookmark",
                    "href": server_bookmark,
                }],
            },
            "links": [{
                "rel": "self",
                "href": "http://localhost/v3/images/124",
            },
            {
                "rel": "bookmark",
                "href": "http://localhost/images/124",
            },
            {
                "rel": "alternate",
                "type": "application/vnd.openstack.image",
                "href": alternate % (glance.generate_glance_url(), 124),
            }],
        },
        {
            'id': '125',
            'name': 'saving snapshot',
            'metadata': {
                u'instance_uuid': server_uuid,
                u'user_id': u'fake',
            },
            'updated': NOW_API_FORMAT,
            'created': NOW_API_FORMAT,
            'status': 'SAVING',
            'progress': 50,
            "size": 25165824,
            'minDisk': 0,
            'minRam': 0,
            'server': {
                'id': server_uuid,
                "links": [{
                    "rel": "self",
                    "href": server_href,
                },
                {
                    "rel": "bookmark",
                    "href": server_bookmark,
                }],
            },
            "links": [{
                "rel": "self",
                "href": "http://localhost/v3/images/125",
            },
            {
                "rel": "bookmark",
                "href": "http://localhost/images/125",
            },
            {
                "rel": "alternate",
                "type": "application/vnd.openstack.image",
                "href": "%s/images/125" % glance.generate_glance_url()
            }],
        },
        {
            'id': '126',
            'name': 'active snapshot',
            'metadata': {
                u'instance_uuid': server_uuid,
                u'user_id': u'fake',
            },
            'updated': NOW_API_FORMAT,
            'created': NOW_API_FORMAT,
            'status': 'ACTIVE',
            'progress': 100,
            "size": 25165824,
            'minDisk': 0,
            'minRam': 0,
            'server': {
                'id': server_uuid,
                "links": [{
                    "rel": "self",
                    "href": server_href,
                },
                {
                    "rel": "bookmark",
                    "href": server_bookmark,
                }],
            },
            "links": [{
                "rel": "self",
                "href": "http://localhost/v3/images/126",
            },
            {
                "rel": "bookmark",
                "href": "http://localhost/images/126",
            },
            {
                "rel": "alternate",
                "type": "application/vnd.openstack.image",
                "href": "%s/images/126" % glance.generate_glance_url()
            }],
        },
        {
            'id': '127',
            'name': 'killed snapshot',
            'metadata': {
                u'instance_uuid': server_uuid,
                u'user_id': u'fake',
            },
            'updated': NOW_API_FORMAT,
            'created': NOW_API_FORMAT,
            'status': 'ERROR',
            'progress': 0,
            "size": 25165824,
            'minDisk': 0,
            'minRam': 0,
            'server': {
                'id': server_uuid,
                "links": [{
                    "rel": "self",
                    "href": server_href,
                },
                {
                    "rel": "bookmark",
                    "href": server_bookmark,
                }],
            },
            "links": [{
                "rel": "self",
                "href": "http://localhost/v3/images/127",
            },
            {
                "rel": "bookmark",
                "href": "http://localhost/images/127",
            },
            {
                "rel": "alternate",
                "type": "application/vnd.openstack.image",
                "href": "%s/images/127" % glance.generate_glance_url()
            }],
        },
        {
            'id': '128',
            'name': 'deleted snapshot',
            'metadata': {
                u'instance_uuid': server_uuid,
                u'user_id': u'fake',
            },
            'updated': NOW_API_FORMAT,
            'created': NOW_API_FORMAT,
            'status': 'DELETED',
            'progress': 0,
            "size": 25165824,
            'minDisk': 0,
            'minRam': 0,
            'server': {
                'id': server_uuid,
                "links": [{
                    "rel": "self",
                    "href": server_href,
                },
                {
                    "rel": "bookmark",
                    "href": server_bookmark,
                }],
            },
            "links": [{
                "rel": "self",
                "href": "http://localhost/v3/images/128",
            },
            {
                "rel": "bookmark",
                "href": "http://localhost/images/128",
            },
            {
                "rel": "alternate",
                "type": "application/vnd.openstack.image",
                "href": "%s/images/128" % glance.generate_glance_url()
            }],
        },
        {
            'id': '129',
            'name': 'pending_delete snapshot',
            'metadata': {
                u'instance_uuid': server_uuid,
                u'user_id': u'fake',
            },
            'updated': NOW_API_FORMAT,
            'created': NOW_API_FORMAT,
            'status': 'DELETED',
            'progress': 0,
            "size": 25165824,
            'minDisk': 0,
            'minRam': 0,
            'server': {
                'id': server_uuid,
                "links": [{
                    "rel": "self",
                    "href": server_href,
                },
                {
                    "rel": "bookmark",
                    "href": server_bookmark,
                }],
            },
            "links": [{
                "rel": "self",
                "href": "http://localhost/v3/images/129",
            },
            {
                "rel": "bookmark",
                "href": "http://localhost/images/129",
            },
            {
                "rel": "alternate",
                "type": "application/vnd.openstack.image",
                "href": "%s/images/129" % glance.generate_glance_url()
            }],
        },
        {
            'id': '130',
            'name': None,
            'metadata': {},
            'updated': NOW_API_FORMAT,
            'created': NOW_API_FORMAT,
            'status': 'ACTIVE',
            'progress': 100,
            "size": 0,
            'minDisk': 0,
            'minRam': 0,
            "links": [{
                "rel": "self",
                "href": "http://localhost/v3/images/130",
            },
            {
                "rel": "bookmark",
                "href": "http://localhost/images/130",
            },
            {
                "rel": "alternate",
                "type": "application/vnd.openstack.image",
                "href": "%s/images/130" % glance.generate_glance_url()
            }],
        },
        {
            'id': '131',
            'name': None,
            'metadata': {},
            'updated': NOW_API_FORMAT,
            'created': NOW_API_FORMAT,
            'status': 'ACTIVE',
            'progress': 100,
            "size": 0,
            'minDisk': 0,
            'minRam': 0,
            "links": [{
                "rel": "self",
                "href": "http://localhost/v3/images/131",
            },
            {
                "rel": "bookmark",
                "href": "http://localhost/images/131",
            },
            {
                "rel": "alternate",
                "type": "application/vnd.openstack.image",
                "href": "%s/images/131" % glance.generate_glance_url()
            }],
        },
        ]

        self.assertThat(expected, matchers.DictListMatches(response_list))

    def test_get_image_details_with_limit(self):
        request = fakes.HTTPRequestV3.blank('/os-images/detail?limit=2')
        response = self.controller.detail(request)
        response_list = response["images"]
        response_links = response["images_links"]

        server_uuid = "aa640691-d1a7-4a67-9d3c-d35ee6b3cc74"
        server_href = "http://localhost/v3/servers/" + server_uuid
        server_bookmark = "http://localhost/servers/" + server_uuid
        alternate = "%s/images/%s"

        expected = [{
            'id': '123',
            'name': 'public image',
            'metadata': {'key1': 'value1'},
            'updated': NOW_API_FORMAT,
            'created': NOW_API_FORMAT,
            'status': 'ACTIVE',
            "size": 25165824,
            'minDisk': 10,
            'progress': 100,
            'minRam': 128,
            "links": [{
                "rel": "self",
                "href": "http://localhost/v3/images/123",
            },
            {
                "rel": "bookmark",
                "href": "http://localhost/images/123",
            },
            {
                "rel": "alternate",
                "type": "application/vnd.openstack.image",
                "href": alternate % (glance.generate_glance_url(), 123),
            }],
        },
        {
            'id': '124',
            'name': 'queued snapshot',
            'metadata': {
                u'instance_uuid': server_uuid,
                u'user_id': u'fake',
            },
            'updated': NOW_API_FORMAT,
            'created': NOW_API_FORMAT,
            'status': 'SAVING',
            "size": 25165824,
            'minDisk': 0,
            'progress': 25,
            'minRam': 0,
            'server': {
                'id': server_uuid,
                "links": [{
                    "rel": "self",
                    "href": server_href,
                },
                {
                    "rel": "bookmark",
                    "href": server_bookmark,
                }],
            },
            "links": [{
                "rel": "self",
                "href": "http://localhost/v3/images/124",
            },
            {
                "rel": "bookmark",
                "href": "http://localhost/images/124",
            },
            {
                "rel": "alternate",
                "type": "application/vnd.openstack.image",
                "href": alternate % (glance.generate_glance_url(), 124),
            }],
        }]

        self.assertThat(expected, matchers.DictListMatches(response_list))

        href_parts = urlparse.urlparse(response_links[0]['href'])
        self.assertEqual('/v3/images', href_parts.path)
        params = urlparse.parse_qs(href_parts.query)

        self.assertThat({'limit': ['2'], 'marker': ['124']},
                        matchers.DictMatches(params))

    def test_image_detail_filter_with_name(self):
        image_service = self.mox.CreateMockAnything()
        filters = {'name': 'testname'}
        request = fakes.HTTPRequestV3.blank('/v3/os-images/detail'
                                          '?name=testname')
        context = request.environ['nova.context']
        image_service.detail(context, filters=filters).AndReturn([])
        self.mox.ReplayAll()
        controller = images.ImagesController(image_service=image_service)
        controller.detail(request)

    def test_image_detail_filter_with_status(self):
        image_service = self.mox.CreateMockAnything()
        filters = {'status': 'active'}
        request = fakes.HTTPRequestV3.blank('/v3/os-images/detail'
                                          '?status=ACTIVE')
        context = request.environ['nova.context']
        image_service.detail(context, filters=filters).AndReturn([])
        self.mox.ReplayAll()
        controller = images.ImagesController(image_service=image_service)
        controller.detail(request)

    def test_image_detail_filter_with_property(self):
        image_service = self.mox.CreateMockAnything()
        filters = {'property-test': '3'}
        request = fakes.HTTPRequestV3.blank('/v3/os-images/detail'
                                          '?property-test=3')
        context = request.environ['nova.context']
        image_service.detail(context, filters=filters).AndReturn([])
        self.mox.ReplayAll()
        controller = images.ImagesController(image_service=image_service)
        controller.detail(request)

    def test_image_detail_filter_server_href(self):
        image_service = self.mox.CreateMockAnything()
        uuid = 'fa95aaf5-ab3b-4cd8-88c0-2be7dd051aaf'
        ref = 'http://localhost:8774/servers/' + uuid
        url = '/v3/os-images/detail?server=' + ref
        filters = {'property-instance_uuid': uuid}
        request = fakes.HTTPRequestV3.blank(url)
        context = request.environ['nova.context']
        image_service.detail(context, filters=filters).AndReturn([])
        self.mox.ReplayAll()
        controller = images.ImagesController(image_service=image_service)
        controller.detail(request)

    def test_image_detail_filter_server_uuid(self):
        image_service = self.mox.CreateMockAnything()
        uuid = 'fa95aaf5-ab3b-4cd8-88c0-2be7dd051aaf'
        url = '/v3/os-images/detail?server=' + uuid
        filters = {'property-instance_uuid': uuid}
        request = fakes.HTTPRequestV3.blank(url)
        context = request.environ['nova.context']
        image_service.detail(context, filters=filters).AndReturn([])
        self.mox.ReplayAll()
        controller = images.ImagesController(image_service=image_service)
        controller.detail(request)

    def test_image_detail_filter_changes_since(self):
        image_service = self.mox.CreateMockAnything()
        filters = {'changes-since': '2011-01-24T17:08Z'}
        request = fakes.HTTPRequestV3.blank('/v3/os-images/detail'
                                          '?changes-since=2011-01-24T17:08Z')
        context = request.environ['nova.context']
        image_service.detail(context, filters=filters).AndReturn([])
        self.mox.ReplayAll()
        controller = images.ImagesController(image_service=image_service)
        controller.detail(request)

    def test_image_detail_filter_with_type(self):
        image_service = self.mox.CreateMockAnything()
        filters = {'property-image_type': 'BASE'}
        request = fakes.HTTPRequestV3.blank('/v3/os-images/detail?type=BASE')
        context = request.environ['nova.context']
        image_service.detail(context, filters=filters).AndReturn([])
        self.mox.ReplayAll()
        controller = images.ImagesController(image_service=image_service)
        controller.detail(request)

    def test_image_detail_filter_not_supported(self):
        image_service = self.mox.CreateMockAnything()
        filters = {'status': 'active'}
        request = fakes.HTTPRequestV3.blank('/v3/os-images/detail?status='
                                          'ACTIVE&UNSUPPORTEDFILTER=testname')
        context = request.environ['nova.context']
        image_service.detail(context, filters=filters).AndReturn([])
        self.mox.ReplayAll()
        controller = images.ImagesController(image_service=image_service)
        controller.detail(request)

    def test_image_detail_no_filters(self):
        image_service = self.mox.CreateMockAnything()
        filters = {}
        request = fakes.HTTPRequestV3.blank('/v3/os-images/detail')
        context = request.environ['nova.context']
        image_service.detail(context, filters=filters).AndReturn([])
        self.mox.ReplayAll()
        controller = images.ImagesController(image_service=image_service)
        controller.detail(request)

    def test_image_detail_invalid_marker(self):
        class InvalidImageService(object):

            def detail(self, *args, **kwargs):
                raise exception.Invalid('meow')

        request = fakes.HTTPRequestV3.blank('/v3/os-images?marker=invalid')
        controller = images.ImagesController(
                                image_service=InvalidImageService())
        self.assertRaises(webob.exc.HTTPBadRequest, controller.detail,
                          request)

    def test_generate_alternate_link(self):
        view = images_view.ViewBuilderV3()
        request = fakes.HTTPRequestV3.blank('/v3/os-images/1')
        generated_url = view._get_alternate_link(request, 1)
        actual_url = "%s/images/1" % glance.generate_glance_url()
        self.assertEqual(generated_url, actual_url)

    def test_delete_image(self):
        request = fakes.HTTPRequestV3.blank('/v3/os-images/124')
        request.method = 'DELETE'
        response = self.controller.delete(request, '124')
        self.assertEqual(response.status_int, 204)

    def test_delete_deleted_image(self):
        """If you try to delete a deleted image, you get back 403 Forbidden."""

        deleted_image_id = 128
        # see nova.tests.api.openstack.fakes:_make_image_fixtures

        request = fakes.HTTPRequestV3.blank(
              '/v3/os-images/%s' % deleted_image_id)
        request.method = 'DELETE'
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.delete,
             request, '%s' % deleted_image_id)

    def test_delete_image_not_found(self):
        request = fakes.HTTPRequestV3.blank('/v3/os-images/300')
        request.method = 'DELETE'
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.delete, request, '300')


class ImageXMLSerializationTest(test.TestCase):

    TIMESTAMP = "2010-10-11T10:30:22Z"
    SERVER_UUID = 'aa640691-d1a7-4a67-9d3c-d35ee6b3cc74'
    SERVER_HREF = 'http://localhost/v3/servers/' + SERVER_UUID
    SERVER_BOOKMARK = 'http://localhost/servers/' + SERVER_UUID
    IMAGE_HREF = 'http://localhost/v3/os-images/%s'
    IMAGE_NEXT = 'http://localhost/v3/os-images?limit=%s&marker=%s'
    IMAGE_BOOKMARK = 'http://localhost/os-images/%s'

    def setUp(self):
        super(ImageXMLSerializationTest, self).setUp()
        self.fixture = {
            'image': {
                'id': 1,
                'name': 'Image1',
                'created': self.TIMESTAMP,
                'updated': self.TIMESTAMP,
                'status': 'ACTIVE',
                'progress': 80,
                'server': {
                    'id': self.SERVER_UUID,
                    'links': [
                        {
                            'href': self.SERVER_HREF,
                            'rel': 'self',
                        },
                        {
                            'href': self.SERVER_BOOKMARK,
                            'rel': 'bookmark',
                        },
                    ],
                },
                'metadata': {
                    'key1': 'value1',
                },
                'links': [
                    {
                        'href': self.IMAGE_HREF % 1,
                        'rel': 'self',
                    },
                    {
                        'href': self.IMAGE_BOOKMARK % 1,
                        'rel': 'bookmark',
                    },
                ],
            },
        }
        image = self.fixture['image']
        image['id'] = '2'
        image['name'] = 'Image2'
        image['status'] = 'SAVING'
        image['links'][0]['href'] = self.IMAGE_HREF % 2
        image['links'][1]['href'] = self.IMAGE_BOOKMARK % 2
        self.fixture_dict = {
            'images': [
                self.fixture['image'],
                image,
            ],
            'images_links': [
                {
                    'rel': 'next',
                    'href': self.IMAGE_NEXT % (2, 2),
                }
            ],
        }
        self.serializer = images.ImageTemplate()

    def test_xml_declaration(self):
        output = self.serializer.serialize(self.fixture)
        has_dec = output.startswith("<?xml version='1.0' encoding='UTF-8'?>")
        self.assertTrue(has_dec)

    def test_show(self):
        self.fixture['image']['minRam'] = 10
        self.fixture['image']['minDisk'] = 100
        output = self.serializer.serialize(self.fixture)
        root = etree.XML(output)
        xmlutil.validate_schema(root, 'image')
        image_dict = self.fixture['image']

        self._assertElementAndLinksEquals(root, image_dict, ['name', 'id',
                                          'updated', 'created', 'status',
                                          'progress'])
        self._assertMetadataEquals(root, image_dict)
        self._assertServerIdAndLinksEquals(root, image_dict)

    def test_show_zero_metadata(self):
        self.fixture['image']['metadata'] = {}
        output = self.serializer.serialize(self.fixture)
        root = etree.XML(output)
        xmlutil.validate_schema(root, 'image')
        image_dict = self.fixture['image']

        meta_nodes = root.findall('{0}meta'.format(ATOMNS))
        self.assertEqual(len(meta_nodes), 0)
        self._assertElementAndLinksEquals(root, image_dict, ['name', 'id',
                                          'updated', 'created', 'status'])
        self._assertServerIdAndLinksEquals(root, image_dict)

    def test_show_image_no_metadata_key(self):
        del self.fixture['image']['metadata']
        output = self.serializer.serialize(self.fixture)
        root = etree.XML(output)
        xmlutil.validate_schema(root, 'image')
        image_dict = self.fixture['image']

        meta_nodes = root.findall('{0}meta'.format(ATOMNS))
        self.assertEqual(len(meta_nodes), 0)
        self._assertElementAndLinksEquals(root, image_dict, ['name', 'id',
                                          'updated', 'created', 'status'])
        self._assertServerIdAndLinksEquals(root, image_dict)

    def test_show_no_server(self):
        del self.fixture['image']['server']
        output = self.serializer.serialize(self.fixture)
        root = etree.XML(output)
        xmlutil.validate_schema(root, 'image')
        image_dict = self.fixture['image']

        server_root = root.find('{0}server'.format(NS))
        self.assertIsNone(server_root)
        self._assertElementAndLinksEquals(root, image_dict, ['name', 'id',
                                          'updated', 'created', 'status'])
        self._assertMetadataEquals(root, image_dict)

    def test_show_with_min_ram(self):
        self.fixture['image']['minRam'] = 256
        output = self.serializer.serialize(self.fixture)
        root = etree.XML(output)
        xmlutil.validate_schema(root, 'image')
        image_dict = self.fixture['image']

        self._assertElementAndLinksEquals(root, image_dict, ['name', 'id',
                                          'updated', 'created', 'status',
                                          'progress', 'minRam'])
        self._assertMetadataEquals(root, image_dict)
        self._assertServerIdAndLinksEquals(root, image_dict)

    def test_show_with_min_disk(self):
        self.fixture['image']['minDisk'] = 5
        output = self.serializer.serialize(self.fixture)
        root = etree.XML(output)
        xmlutil.validate_schema(root, 'image')
        image_dict = self.fixture['image']

        self._assertElementAndLinksEquals(root, image_dict, ['name', 'id',
                                          'updated', 'created', 'status',
                                          'progress', 'minDisk'])
        self._assertMetadataEquals(root, image_dict)
        self._assertServerIdAndLinksEquals(root, image_dict)

    def test_index(self):
        serializer = images.MinimalImagesTemplate()
        output = serializer.serialize(self.fixture_dict)
        root = etree.XML(output)
        xmlutil.validate_schema(root, 'images_index')
        image_elems = root.findall('{0}image'.format(NS))
        self.assertEqual(len(image_elems), 2)
        for i, image_elem in enumerate(image_elems):
            image_dict = self.fixture_dict['images'][i]

            self._assertElementAndLinksEquals(image_elem, image_dict, ['name',
                                                                       'id'])

    def test_index_with_links(self):
        serializer = images.MinimalImagesTemplate()
        output = serializer.serialize(self.fixture_dict)
        root = etree.XML(output)
        xmlutil.validate_schema(root, 'images_index')
        image_elems = root.findall('{0}image'.format(NS))
        self.assertEqual(len(image_elems), 2)
        for i, image_elem in enumerate(image_elems):
            image_dict = self.fixture_dict['images'][i]

            self._assertElementAndLinksEquals(image_elem, image_dict, ['name',
                                                                       'id'])

            images_links = root.findall('{0}link'.format(ATOMNS))
            for i, link in enumerate(self.fixture_dict['images_links']):
                for key, value in link.items():
                    self.assertEqual(images_links[i].get(key), value)

    def test_index_zero_images(self):
        serializer = images.MinimalImagesTemplate()
        del self.fixture_dict['images']
        output = serializer.serialize(self.fixture_dict)
        root = etree.XML(output)
        xmlutil.validate_schema(root, 'images_index')
        image_elems = root.findall('{0}image'.format(NS))
        self.assertEqual(len(image_elems), 0)

    def test_detail(self):
        serializer = images.ImagesTemplate()
        output = serializer.serialize(self.fixture_dict)
        root = etree.XML(output)
        xmlutil.validate_schema(root, 'images')
        image_elems = root.findall('{0}image'.format(NS))
        self.assertEqual(len(image_elems), 2)
        for i, image_elem in enumerate(image_elems):
            image_dict = self.fixture_dict['images'][i]

            self._assertElementAndLinksEquals(image_elem, image_dict, ['name',
                                              'id', 'updated', 'created',
                                              'status'])

    def _assertElementAndLinksEquals(self, elem, dict, keys):
        for key in keys:
            self.assertEquals(elem.get(key), str(dict[key]))
        self._assertLinksEquals(elem, dict)

    def _assertLinksEquals(self, root, dict):
        link_nodes = root.findall('{0}link'.format(ATOMNS))
        self.assertEqual(len(link_nodes), 2)
        for i, link in enumerate(dict['links']):
            for key, value in link.items():
                self.assertEqual(link_nodes[i].get(key), value)

    def _assertServerIdAndLinksEquals(self, root, dict):
        server_root = root.find('{0}server'.format(NS))
        self.assertEqual(server_root.get('id'), dict['server']['id'])
        self._assertLinksEquals(server_root, dict['server'])

    def _assertMetadataEquals(self, root, dict):
        metadata_root = root.find('{0}metadata'.format(NS))
        metadata_elems = metadata_root.findall('{0}meta'.format(NS))
        self.assertEqual(len(metadata_elems), 1)
        for i, metadata_elem in enumerate(metadata_elems):
            (meta_key, meta_value) = dict['metadata'].items()[i]
            self.assertEqual(str(metadata_elem.get('key')), str(meta_key))
            self.assertEqual(str(metadata_elem.text).strip(), str(meta_value))
