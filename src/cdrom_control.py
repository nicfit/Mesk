################################################################################
#  Copyright (C) 2006  Travis Shirk <travis@pobox.com>
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
from fcntl import ioctl
import gobject, gtk, gnomevfs

from mesk import MeskException
import mesk.playlist
from mesk.i18n import _
from mesk.audio.source import AudioMetaData
from mesk.audio.cdaudio import CDAudioSource
from playlist_control import PlaylistControl
import devices, dialogs

class CDROMControl(PlaylistControl):

    def __init__(self, hal_udi, status_bar, **keywords):
        PlaylistControl.__init__(self, hal_udi, status_bar)
        self.hal_udi = hal_udi

        self.device_manager = devices.get_mgr()
        self.device = self.device_manager.get_optical_devices()[self.hal_udi]
        self.block_device = self.device.dev.GetProperty('block.device')
        display_name = self.device_manager.get_device_display_name(self.device)
        self.name = display_name

        # Check capabilities
        if not devices.cdrom_check_capablities(self.block_device):
            raise MeskException(_('<b>Unsupported CDROM device.</b>') ,
                                _("CD device %s does not support open, close "
                                  "and/or media changed."))

        # Setup tab label
        tab_label = self.tab_label_xml.get_widget('playlist_tab_label')
        tab_label.set_text(display_name)
        tab_label_img = self.tab_label_xml.get_widget('playlist_tab_image')
        tab_label_img.set_from_stock(gtk.STOCK_CDROM, gtk.ICON_SIZE_BUTTON)

        # Add buttons
        button_box = self.widget_xml.get_widget('playlist_buttons_hbox')
        eject_button = gtk.Button(label=None)
        eject_button.set_image(gtk.image_new_from_stock(gtk.STOCK_REMOVE,
                                                        gtk.ICON_SIZE_BUTTON))
        self._tooltips = gtk.Tooltips()
        self._tooltips.set_tip(eject_button, _('Eject'))
        button_box.add(eject_button)
        eject_button.show()
        eject_button.connect('clicked', self._eject)

        self._read_cd()

    def _supports_properties(self):
        return False

    def _read_cd(self):
        # Read CD prompting for insert if necessary
        pl = None
        while not pl:
            status = devices.cdrom_disc_status(self.block_device)
            if status != devices.CD_STATUS_AUDIO:
                # No audio CD found, eject
                try:
                    devices.cdrom_eject(self.block_device)
                except IOError, ex:
                    # The device may be busy
                    raise MeskException(_('<b>Unable to eject CD</b>'),
                                        _("Another application is using the "
                                          "CDROM device (%s).\nTry again when "
                                          "the device is not busy.") %
                                        self.block_device)

                # Prompt for CD insert
                d = dialogs.ConfirmationDialog(self.widget.get_parent_window())
                d.set_markup(_('<b>Insert audio CD into %s</b>') %
                             self.block_device)
                if d.confirm():
                    devices.cdrom_close(self.block_device)
                else:
                    raise mesk.MeskException(None)

            else:
                pl = self._read_cdinfo()
                if pl.get_length() == 0:
                    pl = None

        assert(pl and pl.get_length())
        self._set_playlist(pl)
        self._set_read_only(True)

    def _read_cdinfo(self):
        import DiscID
        pl = mesk.playlist.Playlist()
        disc = DiscID.open(self.block_device)

        try:
            disc_info = DiscID.disc_id(disc)
        except:
            disc.close()
            return pl
        disc.close()

        disc_id = disc_info[0]
        num_tracks = disc_info[1]

        # Create playlist from CD tracks
        minus = 0
        total = 0
        for i in range(num_tracks):
            length = (disc_info[i + 3] / 75) - minus
            if i + 1 == disc_info[1]:
                length = disc_info[i + 3] - total

            metadata = AudioMetaData()
            metadata.time_secs = length
            metadata.track_num = i + 1
            pl.append(CDAudioSource(self.block_device, metadata.track_num,
                                    metadata))

            minus = disc_info[i + 3] / 75
            total += length

        # Fetch metadata from CDDB
        self.cddb_fetcher = CDDBThread(disc_info, self._update_metadata_cddb)
        self.cddb_fetcher.start()

        return pl

    ## Override base class methods
    def shutdown(self):
        mesk.log.debug("Shutting down CDROMControl %s" % self.block_device)
        # Remove config section (added by base class)
        self._pl_config.delete()


    def is_playlist_saved(self):
        return False
    def _save_playlist(self, interval = 10000):
        pass

    def _process_tab_menu(self, menu_xml, menu):
        eject_menuitem = gtk.MenuItem('_Eject', use_underline=True)
        eject_menuitem.connect('activate', self._eject)
        eject_menuitem.show()
        menu.append(eject_menuitem)
        # Base class impl
        PlaylistControl._process_tab_menu(self, menu_xml, menu)

    def _eject(self, widget):
        mesk.log.debug("Ejecting %s" % self.block_device)
        devices.cdrom_eject(self.block_device)

    def _update_metadata_cddb(self, disc_id, cddb_info):
        num_tracks = disc_id[1]
        encoding = 'iso8859-1'
        if CDDB.proto >= 6:
            encoding = 'utf-8'

        artist, album = cddb_info['DTITLE'].split(' / ')
        artist = artist.decode(encoding, 'replace')
        album = album.decode(encoding, 'replace')
        year = cddb_info['DYEAR']
        for i in range(num_tracks):
            src = self._playlist[i]
            src.meta_data.artist = artist
            src.meta_data.album = album
            if year:
                src.meta_data.year = int(year)
            src.meta_data.title = cddb_info['TTITLE%d' % i].decode(encoding,
                                                                   'replace')
            src.meta_data.frozen = True  # No further updates necessary
            self._update_source_row(src)

import threading, CDDB
class CDDBThread(threading.Thread):
    def __init__(self, disc_id, cb):
        threading.Thread.__init__(self)
        self._disc_id = disc_id
        self._cb = cb

    def run(self):
        (status, info) = CDDB.query(self._disc_id,
                                    client_name=mesk.info.APP_NAME,
                                    client_version=mesk.info.APP_VERSION)
        if status in [200, 210, 211]:
            if status in [210, 211]:
                info = info[0]
        else:
            mesk.log.verbose('Unable to fetch CDDB info, status=%d' % status)

        if not info:
            mesk.log.verbose('No CDDB info')
            return

        (status, info) = CDDB.read(info['category'], info['disc_id'])
        if status != 210:
            mesk.log.verbose('Unable to fetch CDDB info, status=%d' % status)
            return

        gobject.idle_add(self._cb, self._disc_id, info)
