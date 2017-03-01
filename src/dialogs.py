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
import mesk
from mesk.i18n import _

class MessageDialog(gtk.MessageDialog):
    def __init__(self, parent, modal=True):
        gtk.MessageDialog.__init__(self, parent=parent, flags=0,
                                   type=gtk.MESSAGE_INFO,
                                   buttons=gtk.BUTTONS_OK)

class WarningDialog(gtk.MessageDialog):
    def __init__(self, parent, modal=True):
        gtk.MessageDialog.__init__(self, parent=parent, flags=0,
                                   type=gtk.MESSAGE_WARNING,
                                   buttons=gtk.BUTTONS_OK)

class ErrorDialog(gtk.MessageDialog):
    def __init__(self, parent, markup=None, secondary_txt=None, modal=True):
        gtk.MessageDialog.__init__(self, parent=parent, flags=0,
                                   type=gtk.MESSAGE_ERROR,
                                   buttons=gtk.BUTTONS_OK)
        if markup:
            self.set_markup(markup)
        if secondary_txt:
            self.format_secondary_text(secondary_txt)

class ConfirmationDialog(gtk.MessageDialog):
    def __init__(self, parent, modal=True, type=gtk.MESSAGE_QUESTION):
        gtk.MessageDialog.__init__(self, parent=parent, flags=0, type=type)
        self.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
        self.add_button(gtk.STOCK_OK, gtk.RESPONSE_OK)
        self.set_position(gtk.WIN_POS_MOUSE)

    def confirm(self):
        resp = self.run()
        self.destroy()
        return (resp == gtk.RESPONSE_OK)

class ConfirmationWithDisableOptionDialog(ConfirmationDialog):
    def __init__(self, parent, modal=True, type=gtk.MESSAGE_QUESTION):
        ConfirmationDialog.__init__(self, parent=parent, modal=modal, type=type)
        self.checkbutton = gtk.CheckButton(_('Do not ask me again.'))
        self.vbox.pack_start(self.checkbutton, expand=False, fill=False)
        self.checkbutton.show()

    def confirm(self):
        confirmed = ConfirmationDialog.confirm(self)
        return (confirmed, self.checkbutton.get_active())
