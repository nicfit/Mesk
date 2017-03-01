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
_ = mesk.i18n._


class StatusBar(object):
    def __init__(self, xml):
        self.xml = xml
        self._status_hbox = self.xml.get_widget('status_bar')
        self._status_label = self.xml.get_widget('status_bar_label1')

        self._status_image = self.xml.get_widget('status_bar_img_ebox')
        self._status_image.hide()
        self._status_image.connect('button-release-event',
                                   self._on_status_image_clicked)
        self._status_image_tip = gtk.Tooltips()

        self._msg_stack = StatusMsgStack()
        self.clear()

        self._status_log_window = StatusLogWindow()
        self._status_log_window.window.connect('hide', self._on_log_window_hide)

    def clear(self):
        self._msg_stack.clear()
        self._update_status()

    def push_status_msg(self, msg):
        self._msg_stack.push(msg)
        self._update_status()

    def __pop_status_msg(self, msg):
        self._msg_stack.pop(msg)
        self._update_status()
        return False # One-time callback

    def pop_status_msg(self, msg=None, delay=0):
        if delay:
            gobject.timeout_add(delay, self.__pop_status_msg, msg)
        else:
            self.__pop_status_msg(msg)

    def _update_status(self):
        # Update all status labels.
        msg = self._msg_stack.peek()
        if msg:
            self._status_label.set_text(msg)
        else:
            self._status_label.set_text('')
        mesk.gtk_utils.update_pending_events()

    def add_log_msg(self, msg):
        self._status_log_window.add_msg(msg)
        self._status_image_tip.set_tip(self._status_image,
                                       _('%d messages') %
                                         self._status_log_window.num_msgs())
        self._status_image.show()

    def hide(self):
        self._status_hbox.hide()
    def show(self):
        self._status_hbox.show()

    def _on_status_image_clicked(self, widget, event):
        self._status_log_window.show()

    def _on_log_window_hide(self, widget):
        if self._status_log_window.has_msgs():
            self._status_image.show()
        else:
            self._status_image.hide()

class StatusMsgStack(object):
    def __init__(self):
        self.__data = []

    def clear(self):
        self.__data = []

    def push(self, msg):
        if msg:
            self.__data.append(msg)

    def peek(self):
        if self.__data:
            return self.__data[-1]
        else:
            return None

    def pop(self, msg=None):
        if not self.__data:
            return

        if not msg:
            self.__data.pop()
        else:
            try:
                self.__data.remove(msg)
            except ValueError:
                pass

class StatusLogWindow(mesk.window.Window):
    def __init__(self):
        mesk.window.Window.__init__(self, 'status_log_window',
                                    'main_window.glade')
        self.xml.get_widget('close_button').connect('clicked',
                                                    self._on_close_clicked)
        self.xml.get_widget('clear_button').connect('clicked',
                                                    self._on_clear_clicked)
        self._treeview = self.xml.get_widget('msg_treeview')
        self._treeview.get_selection().set_mode(gtk.SELECTION_NONE)
        self._messages = gtk.ListStore(gobject.TYPE_STRING)
        self._treeview.set_model(self._messages)
        col = gtk.TreeViewColumn('Messages', gtk.CellRendererText(), markup=0)
        self._treeview.append_column(col)

    def add_msg(self, msg):
        self._messages.append([msg])

    def has_msgs(self):
        return self._messages.get_iter_first() is not None

    def num_msgs(self):
        return len(self._messages)

    def _on_close_clicked(self, button):
        self.hide()
    def _on_clear_clicked(self, button):
        self._messages.clear()
