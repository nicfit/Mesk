# -*- coding: utf-8 -*-
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
import os, sys
import gobject, gtk, gtk.glade, pango
import xml.sax.saxutils

def escape_pango_markup(s):
    escape_str = ''
    if s:
        escape_str = gobject.markup_escape_text(s)
    return escape_str

def unescape_pango_markup(s):
    unesc_str = ''
    if s:
        unesc_str = xml.sax.saxutils.unescape(s, {'&apos;': '\'',
                                                  '&quot;': '"',
                                                 })
    return unesc_str

# This function was ripped from Gajim (http://www.gajim.org)
def get_default_font():
    '''Get the desktop setting for application font
    first check for GNOME, then XFCE and last KDE
    it returns None on failure or else a string 'Font Size' '''

    # Gnome/gconf
    try:
        import gconf
        # in try because daemon may not be there
        client = gconf.client_get_default()
        return client.get_string('/desktop/gnome/interface/font_name')
    except:
        pass

    # try to get xfce default font
    # Xfce 4.2 adopts freedesktop.org's Base Directory Specification
    # see http://www.xfce.org/~benny/xfce/file-locations.html
    # and http://freedesktop.org/Standards/basedir-spec
    xdg_config_home = os.environ.get('XDG_CONFIG_HOME', '')
    if xdg_config_home == '':
        xdg_config_home = os.path.expanduser('~/.config') # default     
    xfce_config_file = os.path.join(xdg_config_home,
                                    'xfce4/mcs_settings/gtk.xml')

    # KDE
    kde_config_file = os.path.expanduser('~/.kde/share/config/kdeglobals')

    if os.path.exists(xfce_config_file):
        try:
            for line in file(xfce_config_file):
                if line.find('name="Gtk/FontName"') != -1:
                    start = line.find('value="') + 7
                    return line[start:line.find('"', start)]
        except:
            #we talk about file
            print >> sys.stderr, \
                     'Error: cannot open %s for reading' % xfce_config_file
    elif os.path.exists(kde_config_file):
        try:
            for line in file(kde_config_file):
                if line.find('font=') == 0: # font=Verdana,9,other_numbers
                    start = 5 # 5 is len('font=')
                    line = line[start:]
                    values = line.split(',')
                    font_name = values[0]
                    font_size = values[1]
                    font_string = '%s %s' % (font_name, font_size) # Verdana 9
                    return font_string
        except:
             #we talk about file
             print >> sys.stderr, \
                      'Error: cannot open %s for reading' % kde_config_file

    return 'Sans 10'

def get_glade(symbol, glade_file=None):
    '''Create a glade object for the named symbol.  By default the symbol
    name is also used as the glade filename.  This can be overridden by
    with the glade_file argument.'''
    glade_dir = os.path.join("data", "glade")
    if not glade_file:
        glade_file = '%s.glade' % symbol
    return gtk.glade.XML(os.path.join(glade_dir, glade_file), symbol, 'mesk')

def update_pending_events():
    while gtk.events_pending():
        gtk.main_iteration(False)

def default_linkbutton_callback(button, arg=None):
	import utils
	utils.load_web_page(button.get_uri())

def set_cursor(window, cursor):
    if not type(cursor) is gtk.gdk.Cursor and cursor is not None:
        cursor = gtk.gdk.Cursor(cursor)
    window.set_cursor(cursor)
    update_pending_events()

__LEFT_PTR_WATCH = None
def set_busy_cursor(window):
    global __LEFT_PTR_WATCH
    if __LEFT_PTR_WATCH is None:
        os.environ['XCURSOR_DISCOVER'] = '1' #Turn on logging in Xlib
        # Busy cursor code from Pádraig Brady <P@draigBrady.com>
        # cursor_data hash is 08e8e1c95fe2fc01f976f1e063a24ccd
        cursor_data = "\
\x00\x00\x00\x00\x00\x00\x00\x00\x04\x00\x00\x00\
\x0c\x00\x00\x00\x1c\x00\x00\x00\x3c\x00\x00\x00\
\x7c\x00\x00\x00\xfc\x00\x00\x00\xfc\x01\x00\x00\
\xfc\x3b\x00\x00\x7c\x38\x00\x00\x6c\x54\x00\x00\
\xc4\xdc\x00\x00\xc0\x44\x00\x00\x80\x39\x00\x00\
\x80\x39\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x00\x00\x00\x00\x00\x00\x00"

        try:
            pix = gtk.gdk.bitmap_create_from_data(None, cursor_data, 32, 32)
            color = gtk.gdk.Color()
            __LEFT_PTR_WATCH = gtk.gdk.Cursor(pix, pix, color, color, 2, 2)
        except TypeError:
            # old bug http://bugzilla.gnome.org/show_bug.cgi?id=103616
            # default "WATCH" cursor
            __LEFT_PTR_WATCH = gtk.gdk.Cursor(gtk.gdk.WATCH)
    set_cursor(window, __LEFT_PTR_WATCH)

__INVISIBLE_CURSOR = None
def set_invisible_cursor(window):
    global __INVISIBLE_CURSOR
    if __INVISIBLE_CURSOR is None:
        pixmap = gtk.gdk.Pixmap(None, 1, 1, 1)
        color = gtk.gdk.Color()
        __INVISIBLE_CURSOR = gtk.gdk.Cursor(pixmap, pixmap, color, color, 0, 0)
    set_cursor(window, __INVISIBLE_CURSOR)
