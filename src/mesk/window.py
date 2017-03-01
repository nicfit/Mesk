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
import gtk
from . import gtk_utils

class Window:
    def __init__(self, window_name, glade_file):
        self._window_pos =  (-1,-1)
        self._window_size = (-1,-1)

        self.xml = gtk_utils.get_glade(window_name, glade_file)
        self.window = self.xml.get_widget(window_name)
        self.window.set_icon_from_file('data/images/mesk-16.png')

        self.window.connect('delete-event', self._on_window_delete_event)
        self.window.connect('configure-event', self._on_window_configure_event)

        self.xml.signal_autoconnect(self)

    def show(self):
        self.window.show()
    def present(self):
        self.window.present()
    def hide(self):
        self.window.hide()

    def is_visible(self):
        return self.window.get_property("visible")

    def _on_window_configure_event(self, win, event):
        if event.type == gtk.gdk.CONFIGURE:
            # Call into the Window over the event coords since event does not
            # account for window manager decoration sizes.
            self._window_pos = self.window.get_position()
            self._window_size = self.window.get_size()

    def _on_window_delete_event(self, win, event):
        self.hide()
        return True
