# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2013 Hewlett-Packard Development Company, L.P.
# Copyright (c) 2012 VMware, Inc.
# Copyright (c) 2011 Citrix Systems, Inc.
# Copyright 2011 OpenStack Foundation
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
A fake VMware VI API implementation.
"""

import collections
import pprint
import uuid

from nova import exception
from nova.openstack.common.gettextutils import _
from nova.openstack.common import log as logging
from nova.virt.vmwareapi import error_util

_CLASSES = ['Datacenter', 'Datastore', 'ResourcePool', 'VirtualMachine',
            'Network', 'HostSystem', 'HostNetworkSystem', 'Task', 'session',
            'files', 'ClusterComputeResource']

_FAKE_FILE_SIZE = 1024

_db_content = {}

LOG = logging.getLogger(__name__)


def log_db_contents(msg=None):
    """Log DB Contents."""
    LOG.debug(_("%(text)s: _db_content => %(content)s"),
              {'text': msg or "", 'content': pprint.pformat(_db_content)})


def reset():
    """Resets the db contents."""
    for c in _CLASSES:
        # We fake the datastore by keeping the file references as a list of
        # names in the db
        if c == 'files':
            _db_content[c] = []
        else:
            _db_content[c] = {}
    create_network()
    create_host_network_system()
    create_host()
    create_datacenter()
    create_datastore()
    create_res_pool()
    create_cluster()


def cleanup():
    """Clear the db contents."""
    for c in _CLASSES:
        _db_content[c] = {}


def _create_object(table, table_obj):
    """Create an object in the db."""
    _db_content[table][table_obj.obj] = table_obj


def _get_objects(obj_type):
    """Get objects of the type."""
    lst_objs = FakeRetrieveResult()
    for key in _db_content[obj_type]:
        lst_objs.add_object(_db_content[obj_type][key])
    return lst_objs


class FakeRetrieveResult(object):
    """Object to retrieve a ObjectContent list."""

    def __init__(self):
        self.objects = []

    def add_object(self, object):
        self.objects.append(object)


class Property(object):
    """Property Object base class."""

    def __init__(self, name=None, val=None):
        self.name = name
        self.val = val


class ManagedObjectReference(object):
    """A managed object reference is a remote identifier."""

    def __init__(self, value="object-123", _type="ManagedObject"):
        super(ManagedObjectReference, self)
        # Managed Object Reference value attributes
        # typically have values like vm-123 or
        # host-232 and not UUID.
        self.value = value
        # Managed Object Reference _type
        # attributes hold the name of the type
        # of the vCenter object the value
        # attribute is the identifier for
        self._type = _type


class ObjectContent(object):
    """ObjectContent array holds dynamic properties."""

    # This class is a *fake* of a class sent back to us by
    # SOAP. It has its own names. These names are decided
    # for us by the API we are *faking* here.
    def __init__(self, obj_ref, prop_list=None, missing_list=None):
        self.obj = obj_ref

        if not isinstance(prop_list, collections.Iterable):
            prop_list = []

        if not isinstance(missing_list, collections.Iterable):
            missing_list = []

        # propSet is the name your Python code will need to
        # use since this is the name that the API will use
        self.propSet = prop_list

        # missingSet is the name your python code will
        # need to use since this is the name that the
        # API we are talking to will use.
        self.missingSet = missing_list


class ManagedObject(object):
    """Managed Object base class."""

    def __init__(self, name="ManagedObject", obj_ref=None, value=None):
        """Sets the obj property which acts as a reference to the object."""
        super(ManagedObject, self).__setattr__('objName', name)

        # A managed object is a local representation of a
        # remote object that you can reference using the
        # object reference.
        if obj_ref is None:
            if value is None:
                value = 'obj-123'
            obj_ref = ManagedObjectReference(value, name)

        # we use __setattr__ here because below the
        # default setter has been altered for this class.
        object.__setattr__(self, 'obj', obj_ref)
        object.__setattr__(self, 'propSet', [])

    def set(self, attr, val):
        """
        Sets an attribute value. Not using the __setattr__ directly for we
        want to set attributes of the type 'a.b.c' and using this function
        class we set the same.
        """
        self.__setattr__(attr, val)

    def get(self, attr):
        """
        Gets an attribute. Used as an intermediary to get nested
        property like 'a.b.c' value.
        """
        return self.__getattr__(attr)

    def __setattr__(self, attr, val):
        # TODO(hartsocks): this is adds unnecessary complexity to the class
        for prop in self.propSet:
            if prop.name == attr:
                prop.val = val
                return
        elem = Property()
        elem.name = attr
        elem.val = val
        self.propSet.append(elem)

    def __getattr__(self, attr):
        # TODO(hartsocks): remove this
        # in a real ManagedObject you have to iterate the propSet
        # in a real ManagedObject, the propSet is a *set* not a list
        for elem in self.propSet:
            if elem.name == attr:
                return elem.val
        msg = _("Property %(attr)s not set for the managed object %(name)s")
        raise exception.NovaException(msg % {'attr': attr,
                                             'name': self.objName})


class DataObject(object):
    """Data object base class."""
    def __init__(self, obj_name=None):
        self.obj_name = obj_name


class HostInternetScsiHba():
    pass


class VirtualDisk(DataObject):
    """
    Virtual Disk class.
    """

    def __init__(self):
        super(VirtualDisk, self).__init__()
        self.key = 0
        self.unitNumber = 0


class VirtualDiskFlatVer2BackingInfo(DataObject):
    """VirtualDiskFlatVer2BackingInfo class."""

    def __init__(self):
        super(VirtualDiskFlatVer2BackingInfo, self).__init__()
        self.thinProvisioned = False
        self.eagerlyScrub = False


class VirtualDiskRawDiskMappingVer1BackingInfo(DataObject):
    """VirtualDiskRawDiskMappingVer1BackingInfo class."""

    def __init__(self):
        super(VirtualDiskRawDiskMappingVer1BackingInfo, self).__init__()
        self.lunUuid = ""


class VirtualLsiLogicController(DataObject):
    """VirtualLsiLogicController class."""
    pass


class VirtualPCNet32(DataObject):
    """VirtualPCNet32 class."""

    def __init__(self):
        super(VirtualPCNet32, self).__init__()
        self.key = 4000


class VirtualMachine(ManagedObject):
    """Virtual Machine class."""

    def __init__(self, **kwargs):
        super(VirtualMachine, self).__init__("VirtualMachine", value='vm-10')
        self.set("name", kwargs.get("name"))
        self.set("runtime.connectionState",
                 kwargs.get("conn_state", "connected"))
        self.set("summary.config.guestId", kwargs.get("guest", "otherGuest"))
        ds_do = DataObject()
        ds_do.ManagedObjectReference = [kwargs.get("ds").obj]
        self.set("datastore", ds_do)
        self.set("summary.guest.toolsStatus", kwargs.get("toolsstatus",
                                "toolsOk"))
        self.set("summary.guest.toolsRunningStatus", kwargs.get(
                                "toolsrunningstate", "guestToolsRunning"))
        self.set("runtime.powerState", kwargs.get("powerstate", "poweredOn"))
        self.set("config.files.vmPathName", kwargs.get("vmPathName"))
        self.set("summary.config.numCpu", kwargs.get("numCpu", 1))
        self.set("summary.config.memorySizeMB", kwargs.get("mem", 1))
        self.set("config.hardware.device", kwargs.get("virtual_device", None))
        self.set("config.extraConfig", kwargs.get("extra_config", None))
        self.set('runtime.host',
                 ManagedObjectReference(value='host-123', _type="HostSystem"))
        self.device = kwargs.get("virtual_device")

    def reconfig(self, factory, val):
        """
        Called to reconfigure the VM. Actually customizes the property
        setting of the Virtual Machine object.
        """
        try:
            # Case of Reconfig of VM to attach disk
            controller_key = val.deviceChange[1].device.controllerKey
            filename = val.deviceChange[1].device.backing.fileName

            disk = VirtualDisk()
            disk.controllerKey = controller_key

            disk_backing = VirtualDiskFlatVer2BackingInfo()
            disk_backing.fileName = filename
            disk_backing.key = -101
            disk.backing = disk_backing

            controller = VirtualLsiLogicController()
            controller.key = controller_key

            self.set("config.hardware.device", [disk, controller,
                                                  self.device[0]])
        except AttributeError:
            # Case of Reconfig of VM to set extra params
            self.set("config.extraConfig", val.extraConfig)


class Network(ManagedObject):
    """Network class."""

    def __init__(self):
        super(Network, self).__init__("Network")
        self.set("summary.name", "vmnet0")


class ResourcePool(ManagedObject):
    """Resource Pool class."""

    def __init__(self):
        super(ResourcePool, self).__init__("ResourcePool")
        self.set("name", "ResPool")


class ClusterComputeResource(ManagedObject):
    """Cluster class."""
    def __init__(self, **kwargs):
        super(ClusterComputeResource, self).__init__("ClusterComputeResource",
                                                     value="domain-test")
        r_pool = DataObject()
        obj = _get_objects("ResourcePool").objects[0].obj
        r_pool.ManagedObjectReference = [obj]
        self.set("resourcePool", r_pool)

        host_sys = DataObject()
        obj = _get_objects("HostSystem").objects[0].obj
        host_sys.ManagedObjectReference = [obj]
        self.set("host", host_sys)
        self.set("name", "test_cluster")

        datastore = DataObject()
        obj = _get_objects("Datastore").objects[0].obj
        datastore.ManagedObjectReference = [obj]
        self.set("datastore", datastore)


class Datastore(ManagedObject):
    """Datastore class."""

    def __init__(self):
        super(Datastore, self).__init__("Datastore")
        self.set("summary.type", "VMFS")
        self.set("summary.name", "fake-ds")
        self.set("summary.capacity", 1024 * 1024 * 1024 * 1024)
        self.set("summary.freeSpace", 500 * 1024 * 1024 * 1024)


class HostNetworkSystem(ManagedObject):
    """HostNetworkSystem class."""

    def __init__(self):
        super(HostNetworkSystem, self).__init__("HostNetworkSystem")
        self.set("name", "networkSystem")

        pnic_do = DataObject()
        pnic_do.device = "vmnic0"

        net_info_pnic = DataObject()
        net_info_pnic.PhysicalNic = [pnic_do]

        self.set("networkInfo.pnic", net_info_pnic)


class HostSystem(ManagedObject):
    """Host System class."""

    def __init__(self, obj_ref=None, value='host-123'):
        super(HostSystem, self).__init__("HostSystem", obj_ref, value)
        self.set("name", "ha-host")
        if _db_content.get("HostNetworkSystem", None) is None:
            create_host_network_system()
        host_net_key = _db_content["HostNetworkSystem"].keys()[0]
        host_net_sys = _db_content["HostNetworkSystem"][host_net_key].obj
        self.set("configManager.networkSystem", host_net_sys)

        summary = DataObject()
        hardware = DataObject()
        hardware.numCpuCores = 8
        hardware.numCpuPkgs = 2
        hardware.numCpuThreads = 16
        hardware.vendor = "Intel"
        hardware.cpuModel = "Intel(R) Xeon(R)"
        hardware.memorySize = 1024 * 1024 * 1024
        summary.hardware = hardware

        quickstats = DataObject()
        quickstats.overallMemoryUsage = 500
        summary.quickStats = quickstats

        product = DataObject()
        product.name = "VMware ESXi"
        product.version = "5.0.0"
        config = DataObject()
        config.product = product
        summary.config = config

        pnic_do = DataObject()
        pnic_do.device = "vmnic0"
        net_info_pnic = DataObject()
        net_info_pnic.PhysicalNic = [pnic_do]

        self.set("summary", summary)
        self.set("config.network.pnic", net_info_pnic)

        if _db_content.get("Network", None) is None:
            create_network()
        net_ref = _db_content["Network"][_db_content["Network"].keys()[0]].obj
        network_do = DataObject()
        network_do.ManagedObjectReference = [net_ref]
        self.set("network", network_do)

        vswitch_do = DataObject()
        vswitch_do.pnic = ["vmnic0"]
        vswitch_do.name = "vSwitch0"
        vswitch_do.portgroup = ["PortGroup-vmnet0"]

        net_swicth = DataObject()
        net_swicth.HostVirtualSwitch = [vswitch_do]
        self.set("config.network.vswitch", net_swicth)

        host_pg_do = DataObject()
        host_pg_do.key = "PortGroup-vmnet0"

        pg_spec = DataObject()
        pg_spec.vlanId = 0
        pg_spec.name = "vmnet0"

        host_pg_do.spec = pg_spec

        host_pg = DataObject()
        host_pg.HostPortGroup = [host_pg_do]
        self.set("config.network.portgroup", host_pg)

        config = DataObject()
        storageDevice = DataObject()

        hostBusAdapter = HostInternetScsiHba()
        hostBusAdapter.HostHostBusAdapter = [hostBusAdapter]
        hostBusAdapter.iScsiName = "iscsi-name"
        storageDevice.hostBusAdapter = hostBusAdapter
        config.storageDevice = storageDevice
        self.set("config.storageDevice.hostBusAdapter",
                 config.storageDevice.hostBusAdapter)

    def _add_port_group(self, spec):
        """Adds a port group to the host system object in the db."""
        pg_name = spec.name
        vswitch_name = spec.vswitchName
        vlanid = spec.vlanId

        vswitch_do = DataObject()
        vswitch_do.pnic = ["vmnic0"]
        vswitch_do.name = vswitch_name
        vswitch_do.portgroup = ["PortGroup-%s" % pg_name]

        vswitches = self.get("config.network.vswitch").HostVirtualSwitch
        vswitches.append(vswitch_do)

        host_pg_do = DataObject()
        host_pg_do.key = "PortGroup-%s" % pg_name

        pg_spec = DataObject()
        pg_spec.vlanId = vlanid
        pg_spec.name = pg_name

        host_pg_do.spec = pg_spec
        host_pgrps = self.get("config.network.portgroup").HostPortGroup
        host_pgrps.append(host_pg_do)


class Datacenter(ManagedObject):
    """Datacenter class."""

    def __init__(self):
        super(Datacenter, self).__init__("Datacenter")
        self.set("name", "ha-datacenter")
        self.set("vmFolder", "vm_folder_ref")
        if _db_content.get("Network", None) is None:
            create_network()
        net_ref = _db_content["Network"][_db_content["Network"].keys()[0]].obj
        network_do = DataObject()
        network_do.ManagedObjectReference = [net_ref]
        self.set("network", network_do)


class Task(ManagedObject):
    """Task class."""

    def __init__(self, task_name, state="running"):
        super(Task, self).__init__("Task")
        info = DataObject
        info.name = task_name
        info.state = state
        self.set("info", info)


def create_host_network_system():
    host_net_system = HostNetworkSystem()
    _create_object("HostNetworkSystem", host_net_system)


def create_host():
    host_system = HostSystem()
    _create_object('HostSystem', host_system)


def create_datacenter():
    data_center = Datacenter()
    _create_object('Datacenter', data_center)


def create_datastore():
    data_store = Datastore()
    _create_object('Datastore', data_store)


def create_res_pool():
    res_pool = ResourcePool()
    _create_object('ResourcePool', res_pool)


def create_network():
    network = Network()
    _create_object('Network', network)


def create_cluster():
    cluster = ClusterComputeResource()
    _create_object('ClusterComputeResource', cluster)


def create_task(task_name, state="running"):
    task = Task(task_name, state)
    _create_object("Task", task)
    return task


def _add_file(file_path):
    """Adds a file reference to the  db."""
    _db_content["files"].append(file_path)


def _remove_file(file_path):
    """Removes a file reference from the db."""
    if _db_content.get("files") is None:
        raise exception.NoFilesFound()
    # Check if the remove is for a single file object or for a folder
    if file_path.find(".vmdk") != -1:
        if file_path not in _db_content.get("files"):
            raise exception.FileNotFound(file_path=file_path)
        _db_content.get("files").remove(file_path)
    else:
        # Removes the files in the folder and the folder too from the db
        for file in _db_content.get("files"):
            if file.find(file_path) != -1:
                lst_files = _db_content.get("files")
                if lst_files and lst_files.count(file):
                    lst_files.remove(file)


def fake_plug_vifs(*args, **kwargs):
    """Fakes plugging vifs."""
    pass


def fake_get_network(*args, **kwargs):
    """Fake get network."""
    return {'type': 'fake'}


def fake_fetch_image(context, image, instance, **kwargs):
    """Fakes fetch image call. Just adds a reference to the db for the file."""
    ds_name = kwargs.get("datastore_name")
    file_path = kwargs.get("file_path")
    ds_file_path = "[" + ds_name + "] " + file_path
    _add_file(ds_file_path)


def fake_upload_image(context, image, instance, **kwargs):
    """Fakes the upload of an image."""
    pass


def fake_get_vmdk_size_and_properties(context, image_id, instance):
    """Fakes the file size and properties fetch for the image file."""
    props = {"vmware_ostype": "otherGuest",
            "vmware_adaptertype": "lsiLogic"}
    return _FAKE_FILE_SIZE, props


def _get_vm_mdo(vm_ref):
    """Gets the Virtual Machine with the ref from the db."""
    if _db_content.get("VirtualMachine", None) is None:
            raise exception.NotFound(_("There is no VM registered"))
    if vm_ref not in _db_content.get("VirtualMachine"):
        raise exception.NotFound(_("Virtual Machine with ref %s is not "
                        "there") % vm_ref)
    return _db_content.get("VirtualMachine")[vm_ref]


class FakeFactory(object):
    """Fake factory class for the suds client."""

    def create(self, obj_name):
        """Creates a namespace object."""
        return DataObject(obj_name)


class FakeVim(object):
    """Fake VIM Class."""

    def __init__(self, protocol="https", host="localhost", trace=None):
        """
        Initializes the suds client object, sets the service content
        contents and the cookies for the session.
        """
        self._session = None
        self.client = DataObject()
        self.client.factory = FakeFactory()

        transport = DataObject()
        transport.cookiejar = "Fake-CookieJar"
        options = DataObject()
        options.transport = transport

        self.client.options = options

        service_content = self.client.factory.create('ns0:ServiceContent')
        service_content.propertyCollector = "PropCollector"
        service_content.virtualDiskManager = "VirtualDiskManager"
        service_content.fileManager = "FileManager"
        service_content.rootFolder = "RootFolder"
        service_content.sessionManager = "SessionManager"
        self._service_content = service_content

    def get_service_content(self):
        return self._service_content

    def __repr__(self):
        return "Fake VIM Object"

    def __str__(self):
        return "Fake VIM Object"

    def _login(self):
        """Logs in and sets the session object in the db."""
        self._session = str(uuid.uuid4())
        session = DataObject()
        session.key = self._session
        _db_content['session'][self._session] = session
        return session

    def _logout(self):
        """Logs out and remove the session object ref from the db."""
        s = self._session
        self._session = None
        if s not in _db_content['session']:
            raise exception.NovaException(
                _("Logging out a session that is invalid or already logged "
                "out: %s") % s)
        del _db_content['session'][s]

    def _terminate_session(self, *args, **kwargs):
        """Terminates a session."""
        s = kwargs.get("sessionId")[0]
        if s not in _db_content['session']:
            return
        del _db_content['session'][s]

    def _check_session(self):
        """Checks if the session is active."""
        if (self._session is None or self._session not in
                 _db_content['session']):
            LOG.debug(_("Session is faulty"))
            raise error_util.VimFaultException(
                               [error_util.FAULT_NOT_AUTHENTICATED],
                               _("Session Invalid"))

    def _create_vm(self, method, *args, **kwargs):
        """Creates and registers a VM object with the Host System."""
        config_spec = kwargs.get("config")
        ds = _db_content["Datastore"][_db_content["Datastore"].keys()[0]]
        vm_dict = {"name": config_spec.name,
                  "ds": ds,
                  "powerstate": "poweredOff",
                  "vmPathName": config_spec.files.vmPathName,
                  "numCpu": config_spec.numCPUs,
                  "mem": config_spec.memoryMB,
                  "extra_config": config_spec.extraConfig,
                  "virtual_device": config_spec.deviceChange}
        virtual_machine = VirtualMachine(**vm_dict)
        _create_object("VirtualMachine", virtual_machine)
        task_mdo = create_task(method, "success")
        return task_mdo.obj

    def _reconfig_vm(self, method, *args, **kwargs):
        """Reconfigures a VM and sets the properties supplied."""
        vm_ref = args[0]
        vm_mdo = _get_vm_mdo(vm_ref)
        vm_mdo.reconfig(self.client.factory, kwargs.get("spec"))
        task_mdo = create_task(method, "success")
        return task_mdo.obj

    def _create_copy_disk(self, method, vmdk_file_path):
        """Creates/copies a vmdk file object in the datastore."""
        # We need to add/create both .vmdk and .-flat.vmdk files
        flat_vmdk_file_path = vmdk_file_path.replace(".vmdk", "-flat.vmdk")
        _add_file(vmdk_file_path)
        _add_file(flat_vmdk_file_path)
        task_mdo = create_task(method, "success")
        return task_mdo.obj

    def _snapshot_vm(self, method):
        """Snapshots a VM. Here we do nothing for faking sake."""
        task_mdo = create_task(method, "success")
        return task_mdo.obj

    def _delete_disk(self, method, *args, **kwargs):
        """Deletes .vmdk and -flat.vmdk files corresponding to the VM."""
        vmdk_file_path = kwargs.get("name")
        flat_vmdk_file_path = vmdk_file_path.replace(".vmdk", "-flat.vmdk")
        _remove_file(vmdk_file_path)
        _remove_file(flat_vmdk_file_path)
        task_mdo = create_task(method, "success")
        return task_mdo.obj

    def _delete_file(self, method, *args, **kwargs):
        """Deletes a file from the datastore."""
        _remove_file(kwargs.get("name"))
        task_mdo = create_task(method, "success")
        return task_mdo.obj

    def _just_return(self):
        """Fakes a return."""
        return

    def _just_return_task(self, method):
        """Fakes a task return."""
        task_mdo = create_task(method, "success")
        return task_mdo.obj

    def _unregister_vm(self, method, *args, **kwargs):
        """Unregisters a VM from the Host System."""
        vm_ref = args[0]
        _get_vm_mdo(vm_ref)
        del _db_content["VirtualMachine"][vm_ref]

    def _search_ds(self, method, *args, **kwargs):
        """Searches the datastore for a file."""
        ds_path = kwargs.get("datastorePath")
        if _db_content.get("files", None) is None:
            raise exception.NoFilesFound()
        for file in _db_content.get("files"):
            if file.find(ds_path) != -1:
                task_mdo = create_task(method, "success")
                return task_mdo.obj
        task_mdo = create_task(method, "error")
        return task_mdo.obj

    def _make_dir(self, method, *args, **kwargs):
        """Creates a directory in the datastore."""
        ds_path = kwargs.get("name")
        if _db_content.get("files", None) is None:
            raise exception.NoFilesFound()
        _db_content["files"].append(ds_path)

    def _set_power_state(self, method, vm_ref, pwr_state="poweredOn"):
        """Sets power state for the VM."""
        if _db_content.get("VirtualMachine", None) is None:
            raise exception.NotFound(_("No Virtual Machine has been "
                                       "registered yet"))
        if vm_ref not in _db_content.get("VirtualMachine"):
            raise exception.NotFound(_("Virtual Machine with ref %s is not "
                                       "there") % vm_ref)
        vm_mdo = _db_content.get("VirtualMachine").get(vm_ref)
        vm_mdo.set("runtime.powerState", pwr_state)
        task_mdo = create_task(method, "success")
        return task_mdo.obj

    def _retrieve_properties_continue(self, method, *args, **kwargs):
        """Continues the retrieve."""
        return FakeRetrieveResult()

    def _retrieve_properties_cancel(self, method, *args, **kwargs):
        """Cancels the retrieve."""
        return None

    def _retrieve_properties(self, method, *args, **kwargs):
        """Retrieves properties based on the type."""
        spec_set = kwargs.get("specSet")[0]
        type = spec_set.propSet[0].type
        properties = spec_set.propSet[0].pathSet
        if not isinstance(properties, list):
            properties = properties.split()
        objs = spec_set.objectSet
        lst_ret_objs = FakeRetrieveResult()
        for obj in objs:
            try:
                obj_ref = obj.obj
                # This means that we are doing a search for the managed
                # dataobjects of the type in the inventory
                if obj_ref == "RootFolder":
                    for mdo_ref in _db_content[type]:
                        mdo = _db_content[type][mdo_ref]
                        # Create a temp Managed object which has the same ref
                        # as the parent object and copies just the properties
                        # asked for. We need .obj along with the propSet of
                        # just the properties asked for
                        temp_mdo = ManagedObject(mdo.objName, mdo.obj)
                        for prop in properties:
                            temp_mdo.set(prop, mdo.get(prop))
                        lst_ret_objs.add_object(temp_mdo)
                else:
                    if obj_ref in _db_content[type]:
                        mdo = _db_content[type][obj_ref]
                        temp_mdo = ManagedObject(mdo.objName, obj_ref)
                        for prop in properties:
                            temp_mdo.set(prop, mdo.get(prop))
                        lst_ret_objs.add_object(temp_mdo)
            except Exception as exc:
                LOG.exception(exc)
                continue
        return lst_ret_objs

    def _add_port_group(self, method, *args, **kwargs):
        """Adds a port group to the host system."""
        _host_sk = _db_content["HostSystem"].keys()[0]
        host_mdo = _db_content["HostSystem"][_host_sk]
        host_mdo._add_port_group(kwargs.get("portgrp"))

    def __getattr__(self, attr_name):
        if attr_name != "Login":
            self._check_session()
        if attr_name == "Login":
            return lambda *args, **kwargs: self._login()
        elif attr_name == "Logout":
            self._logout()
        elif attr_name == "TerminateSession":
            return lambda *args, **kwargs: self._terminate_session(
                                               *args, **kwargs)
        elif attr_name == "CreateVM_Task":
            return lambda *args, **kwargs: self._create_vm(attr_name,
                                                *args, **kwargs)
        elif attr_name == "ReconfigVM_Task":
            return lambda *args, **kwargs: self._reconfig_vm(attr_name,
                                                *args, **kwargs)
        elif attr_name == "CreateVirtualDisk_Task":
            return lambda *args, **kwargs: self._create_copy_disk(attr_name,
                                                kwargs.get("name"))
        elif attr_name == "DeleteDatastoreFile_Task":
            return lambda *args, **kwargs: self._delete_file(attr_name,
                                                *args, **kwargs)
        elif attr_name == "PowerOnVM_Task":
            return lambda *args, **kwargs: self._set_power_state(attr_name,
                                                args[0], "poweredOn")
        elif attr_name == "PowerOffVM_Task":
            return lambda *args, **kwargs: self._set_power_state(attr_name,
                                                args[0], "poweredOff")
        elif attr_name == "RebootGuest":
            return lambda *args, **kwargs: self._just_return()
        elif attr_name == "ResetVM_Task":
            return lambda *args, **kwargs: self._set_power_state(attr_name,
                                                args[0], "poweredOn")
        elif attr_name == "SuspendVM_Task":
            return lambda *args, **kwargs: self._set_power_state(attr_name,
                                                args[0], "suspended")
        elif attr_name == "CreateSnapshot_Task":
            return lambda *args, **kwargs: self._snapshot_vm(attr_name)
        elif attr_name == "CopyVirtualDisk_Task":
            return lambda *args, **kwargs: self._create_copy_disk(attr_name,
                                                kwargs.get("destName"))
        elif attr_name == "DeleteVirtualDisk_Task":
            return lambda *args, **kwargs: self._delete_disk(attr_name,
                                                *args, **kwargs)
        elif attr_name == "Destroy_Task":
            return lambda *args, **kwargs: self._unregister_vm(attr_name,
                                                               *args, **kwargs)
        elif attr_name == "UnregisterVM":
            return lambda *args, **kwargs: self._unregister_vm(attr_name,
                                                *args, **kwargs)
        elif attr_name == "SearchDatastore_Task":
            return lambda *args, **kwargs: self._search_ds(attr_name,
                                                *args, **kwargs)
        elif attr_name == "MakeDirectory":
            return lambda *args, **kwargs: self._make_dir(attr_name,
                                                *args, **kwargs)
        elif attr_name == "RetrievePropertiesEx":
            return lambda *args, **kwargs: self._retrieve_properties(
                                                attr_name, *args, **kwargs)
        elif attr_name == "ContinueRetrievePropertiesEx":
            return lambda *args, **kwargs: self._retrieve_properties_continue(
                                                attr_name, *args, **kwargs)
        elif attr_name == "CancelRetrievePropertiesEx":
            return lambda *args, **kwargs: self._retrieve_properties_cancel(
                                                attr_name, *args, **kwargs)
        elif attr_name == "AcquireCloneTicket":
            return lambda *args, **kwargs: self._just_return()
        elif attr_name == "AddPortGroup":
            return lambda *args, **kwargs: self._add_port_group(attr_name,
                                                *args, **kwargs)
        elif attr_name == "RebootHost_Task":
            return lambda *args, **kwargs: self._just_return_task(attr_name)
        elif attr_name == "ShutdownHost_Task":
            return lambda *args, **kwargs: self._just_return_task(attr_name)
        elif attr_name == "PowerDownHostToStandBy_Task":
            return lambda *args, **kwargs: self._just_return_task(attr_name)
        elif attr_name == "PowerUpHostFromStandBy_Task":
            return lambda *args, **kwargs: self._just_return_task(attr_name)
        elif attr_name == "EnterMaintenanceMode_Task":
            return lambda *args, **kwargs: self._just_return_task(attr_name)
        elif attr_name == "ExitMaintenanceMode_Task":
            return lambda *args, **kwargs: self._just_return_task(attr_name)
