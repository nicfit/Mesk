################################################################################
#  Copyright (C) 2006  Travis Shirk <travis@pobox.com>
#  Copyright (C) 2003 Thomas Schueppel, Dirk Meyer (cdrom_disc_status)
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
################################################################################
import os
import gobject
import mesk, mesk.audio.cdaudio

from fcntl import ioctl

__DEVICE_MGR = None
def get_mgr():
    global __DEVICE_MGR
    if __DEVICE_MGR is None:
        __DEVICE_MGR = DeviceMgr()
    return __DEVICE_MGR

class Device(object):
    def __init__(self, hal_udi, hal_dev):
        self.udi = hal_udi
        self.dev = hal_dev
        self.volume_udi = None

class DeviceMgr(gobject.GObject):
    def __init__(self):
        gobject.GObject.__init__(self)
        self._optical_devices = {}

        # A signal emitted when the device media changes
        gobject.signal_new('media-changed', DeviceMgr,
                           gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
                           [gobject.TYPE_PYOBJECT])

        if mesk.info.DISABLE_DBUS_SUPPORT:
            mesk.log.info('DeviceMgr is a stub due to DBus being disabled.')
            return
        else:
            import dbus

        # Get a handle to HAL
        self.bus = dbus.SystemBus()
        hal_manager_obj = self.bus.get_object('org.freedesktop.Hal',
                                              '/org/freedesktop/Hal/Manager')
        self.hal_manager = dbus.Interface(hal_manager_obj,
                                          'org.freedesktop.Hal.Manager')

        if not mesk.info.DISABLE_CDROM_SUPPORT:
            # Find all optical (CDs, DVDs, etc.) drives
            cdroms = self.hal_manager.FindDeviceByCapability('storage.cdrom')
            for dev_udi in cdroms:
                # Get HAL device for drive
                dev_obj = self.bus.get_object('org.freedesktop.Hal', dev_udi)
                dev = dbus.Interface(dev_obj, 'org.freedesktop.Hal.Device')

                self._optical_devices[dev_udi] = Device(dev_udi, dev)

        if self._optical_devices:
            # Probe optical drives for media
            volumes = self.hal_manager.FindDeviceByCapability('volume')
            for vol_udi in volumes:
                dev_obj = self.bus.get_object('org.freedesktop.Hal', vol_udi)
                dev = dbus.Interface(dev_obj, 'org.freedesktop.Hal.Device')
                parent_udi = dev.GetProperty('info.parent')
                if parent_udi in self._optical_devices.keys():
                    # Stash volume_udi so we can map the volume being removed
                    self._optical_devices[parent_udi].volume_udi = vol_udi


        # Device add/remove callback
        def device_add(udi):
            dev_obj = self.bus.get_object('org.freedesktop.Hal', udi)
            hal_dev = dbus.Interface(dev_obj, 'org.freedesktop.Hal.Device')
            if hal_dev.QueryCapability('volume'):
                # We have a mountable volume, check to see if it is a volume
                # for one of the CD devices
                parent = hal_dev.GetProperty('info.parent')
                if parent in self._optical_devices.keys():
                    self._optical_devices[parent].volume_udi = udi
                    self.emit('media-changed', self._optical_devices[parent])

        def device_removed(udi):
            for cd in self._optical_devices.values():
                if cd.volume_udi == udi:
                    self.emit('media-changed', cd)
                    cd.volume_udi = None
                    break

        # Register for device added/removed callbacks
        self.bus.add_signal_receiver(device_add, 'DeviceAdded',
                                     'org.freedesktop.Hal.Manager',
                                     'org.freedesktop.Hal',
                                     '/org/freedesktop/Hal/Manager')
        self.bus.add_signal_receiver(device_removed, 'DeviceRemoved',
                                     'org.freedesktop.Hal.Manager',
                                     'org.freedesktop.Hal',
                                     '/org/freedesktop/Hal/Manager')

    def get_optical_devices(self):
        '''Returns a dictionary of optical device objects.  The key into the
        dict is the assigned unique name of the device, the value is the
        Hal.Device instance.'''
        return self._optical_devices

    def get_device_display_name(self, device):
        capability = 'CD'
        for cap in ['dvdrw', 'dvdr', 'dvd', 'cdrw', 'cdr']:
            if device.dev.GetProperty('storage.cdrom.%s' % cap):
                capability = cap.upper()
                break

        dev_file = os.path.basename(device.dev.GetProperty('block.device'))
        return '%s (%s)' % (capability, dev_file)

    def shutdown(self):
        pass

### CDROM utils ###

# Constants from linux/cdrom.h #
# ioctl's
CDROMEJECT           = 0x5309
CDROMCLOSETRAY       = 0x5319
CDROM_MEDIA_CHANGED  = 0x5325
CDROM_DRIVE_STATUS   = 0x5326
CDROM_DISC_STATUS    = 0x5327
CDROM_LOCKDOOR       = 0x5329
CDROM_GET_CAPABILITY = 0x5331
# Disc selector for multi disc drives
CDSL_CURRENT = (int)(~ 0 >> 1)
# Status Constants
CDS_DISC_OK = 4
CDS_AUDIO   = 100
CDS_MIXED   = 105
# Capability constants
CDC_CLOSE_TRAY    = 0x01
CDC_OPEN_TRAY     = 0x02
CDC_MEDIA_CHANGED = 0x80

# Return codes for cdrom_disc_status
(CD_STATUS_NONE,
 CD_STATUS_AUDIO,
 CD_STATUS_DATA,
 CD_STATUS_BLANK,
) = range(4)

def cdrom_check_capablities(device):
    caps = 0
    try:
        fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
        caps = ioctl(fd, CDROM_GET_CAPABILITY)
    finally:
        os.close(fd)
    return (caps & CDC_CLOSE_TRAY and
            caps & CDC_OPEN_TRAY and
            caps & CDC_MEDIA_CHANGED)

def cdrom_eject(device):
    s = -1
    try:
        fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
        s = ioctl(fd, CDROMEJECT)
    finally:
        os.close(fd)
    return bool(not s)

def cdrom_close(device):
    s = -1
    try:
        fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
        s = ioctl(fd, CDROMCLOSETRAY)
    finally:
        os.close(fd)
    return bool(not s)

def cdrom_disc_status(device):
    """
    Check status of CD device.
    return: CD_STATUS_NONE, CD_STATUS_AUDIO, CD_STATUS_DATA, CD_STATUS_BLANK
    """
    try:
        fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
        s = ioctl(fd, CDROM_DRIVE_STATUS, CDSL_CURRENT)
        if s != CDS_DISC_OK:
            return CD_STATUS_NONE
        s = ioctl(fd, CDROM_DISC_STATUS)
    finally:
        os.close(fd)

    if s == CDS_AUDIO or s == CDS_MIXED:
        return CD_STATUS_AUDIO

    try:
        fd = open(device, 'rb')
        # try to read from the disc to get information if the disc
        # is a rw medium not written yet
        fd.seek(32768) # 2048 multiple boundary for FreeBSD
        # FreeBSD doesn't return IOError unless we try and read:
        fd.read(1)
    except IOError:
        # not readable, blank disc
        fd.close()
	return CD_STATUS_BLANK
    else:
        # data disc
        fd.close()
	return CD_STATUS_DATA
