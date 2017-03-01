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
import gst
import gtk, gtk.glade

import mesk
from mesk.i18n import _

import mesk.gtk_utils

class AboutDialog:
    def __init__(self):
        self.xml = mesk.gtk_utils.get_glade('about_dialog',
                                            'about_dialog.glade')
        self.xml.signal_autoconnect(self)
        self.dialog = self.xml.get_widget('about_dialog')
        self.dialog.set_name("Mesk")
        self.dialog.set_version("%s (%s)" % (mesk.info.APP_VERSION,
                                             mesk.info.APP_CODENAME))
        self.dialog.set_license(mesk.info.GPLV2_LICENCE)

        img = gtk.Image()
        img.set_from_file('data/images/mesk_felon.png')
        self.dialog.set_logo(img.get_pixbuf())

        # XXX: How to you get markup in the comments??

        exts = mesk.audio.supported_extensions.keys()
        exts.sort()
        formats = _('Supported audio formats: %s\n') % ','.join(exts)

        def version_to_str(version_tuple):
            s = ''
            for num in version_tuple:
                s += str(num) + '.'
            return s[0:-1] # remove trailing dot
        extra = _('Gtk+ version: %s\n') % version_to_str(gtk.gtk_version)
        extra += _('PyGtk version: %s\n') % version_to_str(gtk.pygtk_version)
        extra += _('Gstreamer version: %s\n') % \
                 version_to_str(gst.pygst_version)
        extra += _('Installed in %s\n') % mesk.info.INSTALL_PREFIX

        self.dialog.set_comments((_('A Gtk+ audio player\n\n') +
                                 formats + extra))
