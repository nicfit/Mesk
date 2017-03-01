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
import gtk
import logging
import mesk, mesk.window
_ = mesk.i18n._

class LogWindow(mesk.window.Window):
    def __init__(self):
        mesk.window.Window.__init__(self, 'log_window', 'main_window.glade')

        self._levels = mesk.log.LEVEL2STRINGS.keys()
        self._levels.sort()

        level_combobox = self.xml.get_widget('level_combobox')
        curr = mesk.log.get_logging_level()
        level_combobox.set_active(self._levels.index(curr))
        self.log_textview = self.xml.get_widget('log_textview')

    def _on_level_combobox_changed(self, combo):
        active = combo.get_active_text()
        mesk.log.set_logging_level(mesk.log.string_to_level(active))

    def _on_close_button_clicked(self, button):
        self.hide()

    def _on_save_button_clicked(self, button):
        buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                 gtk.STOCK_SAVE, gtk.RESPONSE_OK)
        d = gtk.FileChooserDialog(title=_('Save Log File'), parent=self.window,
                                  action=gtk.FILE_CHOOSER_ACTION_SAVE,
                                  buttons=buttons)
        d.set_current_folder(os.path.expandvars("$HOME"))
        resp = d.run()
        if resp == gtk.RESPONSE_OK:
            filename = d.get_filename()
            fp = file(filename, 'w')
            buf = self.log_textview.get_buffer()
            log_txt = buf.get_text(buf.get_start_iter(), buf.get_end_iter())
            fp.write(log_txt)
            fp.close()
        d.destroy()

    def _on_clear_button_clicked(self, button):
        self.log_textview.get_buffer().set_text('')
