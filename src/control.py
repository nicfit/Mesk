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
import gobject, gtk
import mesk.gtk_utils

class Control(gobject.GObject):
    '''A GUI element'''

    # The notebook tab widget
    tab_widget = gtk.Label('')
    # The notebook page widget
    widget = None

    def __init__(self):
        gobject.GObject.__init__(self)
        # A signal all controls can emit when requesting to become active.
        # Right now this means getting control of the AudioControl
        if gobject.signal_lookup('control_request_active', Control) == 0:
            gobject.signal_new('control_request_active', Control,
                               gobject.SIGNAL_RUN_LAST,
                               gobject.TYPE_NONE, [])

        # The control wishes to close
        if gobject.signal_lookup('control_request_close', Control) == 0:
            gobject.signal_new('control_request_close', Control,
                               gobject.SIGNAL_RUN_LAST,
                               gobject.TYPE_NONE, [])
        self._is_active = False

    def shutdown(self):
        pass

    def set_active(self, state=True, audio_ctrl=None):
        self._is_active = state
    def is_active(self):
        return self._is_active

    def set_focused(self, state=True):
        pass

    def has_playlist(self):
        return False
    def get_playlist(self):
        return None
    def is_playlist_saved(self):
        return False

class EmptyControl(Control):
    '''A placeholder control for when there are no others to display'''

    def __init__(self):
        Control.__init__(self)
        self.xml = mesk.gtk_utils.get_glade('empty_control',
                                            'main_window.glade')
        self.widget = self.xml.get_widget('empty_control')
        splash = self.xml.get_widget('splash_image')
        splash.set_from_file('data/images/mesk-splash.jpg')
        self.widget.show()
