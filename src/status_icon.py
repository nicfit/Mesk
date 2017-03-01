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
import mesk.gtk_utils
from mesk.i18n import _

class StatusIcon(object):
    ICON_IMG = 'data/images/mesk-22.png'

    def __init__(self, main_window, audio_ctrl):
        self.main_window = main_window
        self.audio_ctrl = audio_ctrl
        self.status_icon = gtk.status_icon_new_from_file(self.ICON_IMG)
        self.status_icon.connect('activate', self._on_trayicon_activate)
        self.status_icon.connect('popup-menu', self._on_trayicon_menu)
        self.status_icon.set_tooltip(None)

        # Connect to source change signals for updating tooltip
        audio_ctrl.connect('source-changed', self._on_audio_source_changed)
        audio_ctrl.connect('tag-update', self._on_audio_source_tag_update)

        # Right click menu
        self.status_icon_menu = StatusIconMenu(self.main_window,
                                               self.audio_ctrl)

        self.status_icon.set_visible(True)

    def _on_trayicon_activate(self, status_icon):
        if not self.main_window.is_visible():
            self.main_window.show()
        else:
            self.main_window.hide()

    def _on_trayicon_menu(self, status_icon, button, time):
        self.status_icon_menu.popup(None, None, gtk.status_icon_position_menu,
                                    button, time, status_icon)

    def _on_audio_source_changed(self, ctrl, old, new):
        if new is None and new[1]:
            return
        src = new[1]
        self._update_tooltip(src)

    def _on_audio_source_tag_update(self, ctrl, src):
        self._update_tooltip(src)

    def _update_tooltip(self, src):
        if src is None:
            self.status_icon.set_tooltip(None)
            return

        title = src.meta_data.title
        artist = src.meta_data.artist
        album = src.meta_data.album
        year = src.meta_data.year

        tooltip = u''
        if title:
            tooltip += title
        if artist or album:
            if artist:
                tooltip += u'\n%s' % artist
            if album:
                tooltip += u'\n%s' % album
                if year:
                    tooltip += ' (%d)' % int(year)

        self.status_icon.set_tooltip(tooltip)

class StatusIconMenu(gtk.Menu):
    def __init__(self, main_window, audio_ctrl):
        gtk.Menu.__init__(self)
        self.main_window = main_window
        self.audio_ctrl = audio_ctrl

        play = gtk.ImageMenuItem(stock_id='gtk-media-play',
                                 accel_group=None)
        play.connect('activate', self._on_play)
        self.add(play)
        self.play_menuitem = play

        pause = gtk.ImageMenuItem(stock_id='gtk-media-pause',
                                  accel_group=None)
        pause.connect('activate', self._on_pause)
        self.add(pause)
        self.pause_menuitem = pause

        stop = gtk.ImageMenuItem(stock_id='gtk-media-stop',
                                 accel_group=None)
        stop.connect('activate', self._on_stop)
        self.add(stop)
        self.stop_menuitem = stop

        prev = gtk.ImageMenuItem(stock_id='gtk-media-previous',
                                 accel_group=None)
        prev.connect('activate', self._on_prev)
        self.add(prev)
        self.prev_menuitem = prev

        next = gtk.ImageMenuItem(stock_id='gtk-media-next', accel_group=None)
        next.connect('activate', self._on_next)
        self.add(next)
        self.next_menuitem = next

        self.add(gtk.SeparatorMenuItem())

        quit = gtk.ImageMenuItem(stock_id=gtk.STOCK_QUIT, accel_group=None)
        quit.connect('activate', self._on_quit)
        self.add(quit)

        self.show_all()

    def popup(self, parent_menu_shell, parent_menu_item, func, button,
              activate_time, data=None):
        # Show/hide menuitems based on player state.
        if self.audio_ctrl.is_stopped():
            self.play_menuitem.show()
            self.pause_menuitem.hide()
            self.stop_menuitem.hide()
            self.prev_menuitem.hide()
            self.next_menuitem.hide()
        elif self.audio_ctrl.is_paused():
            self.play_menuitem.show()
            self.pause_menuitem.hide()
            self.stop_menuitem.show()
            self.prev_menuitem.show()
            self.next_menuitem.show()
        elif self.audio_ctrl.is_playing():
            self.play_menuitem.hide()
            self.pause_menuitem.show()
            self.stop_menuitem.show()
            self.prev_menuitem.show()
            self.next_menuitem.show()

        gtk.Menu.popup(self, parent_menu_shell, parent_menu_item, func, button,
                       activate_time, data)

    def _on_play(self, widget):
        self.audio_ctrl.play()

    def _on_stop(self, widget):
        self.audio_ctrl.stop()

    def _on_pause(self, widget):
        self.audio_ctrl.pause()

    def _on_next(self, widget):
        self.audio_ctrl.next()

    def _on_prev(self, widget):
        self.audio_ctrl.prev()

    def _on_quit(self, widget):
        self.main_window.quit()
