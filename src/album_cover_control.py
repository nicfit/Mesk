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
import os, tempfile, sha
import gobject, gtk, gtk.glade

import mesk
import mesk.gtk_utils, mesk.uri
from mesk.i18n import _

import control

class AlbumCover:
    def __init__(self, front_cover):
        # Mapping covers to image file names
        self._cover_files = {'front': front_cover}
        # Mapping covers to Image objects
        self._cover_images = {}

        for type in self._cover_files:
            self._cover_images[type] = None
            f = self._cover_files[type]
            if f:
                img = gtk.Image()
                img.set_from_file(f)
                self._cover_images[type] = img

    def get_image(self, which = 'front'):
        return self._cover_images[which]
    def get_file(self, which = 'front'):
        return self._cover_files[which]

class AlbumCoverControl(control.Control):
    COVER_NAMES = ['cover-front', 'cover', 'folder', 'album']
    COVER_EXTS = ['.png', '.jpg', '.gif', '.jpeg']
    DISPLAY_WIDTH  = 64
    DISPLAY_HEIGHT = 64
    MAX_LARGE_DISPLAY_WIDTH = 600
    MAX_LARGE_DISPLAY_HEIGHT = 600
    DEFAULT_COVER = 'data/images/mesk.svg'

    def __init__(self, parent_xml, audio_control):
        control.Control.__init__(self)

        self._parent_xml = parent_xml
        self._parent_xml.signal_autoconnect(self)
        self._cover_image = self._parent_xml.get_widget('album_cover_image')
        self._current_cover = None
        self._display_full_timeout_id = None

        audio_control.connect('source-changed', self._on_audio_source_changed)
        self._set_cover(self.DEFAULT_COVER)

        # State for the last cover shown.
        self._last_cover = {'filename': None,
                            'dirname': None,
                            'digest': None,
                           }

    def clear(self):
        self._set_cover(self.DEFAULT_COVER)

    def _set_cover(self, cover_file):
        if (self._current_cover and
            self._current_cover.get_file('front') == cover_file):
            return

        self._current_cover = AlbumCover(cover_file)

        # Scale cover
        pixbuf = self._current_cover.get_image('front').get_pixbuf()
        pixbuf = pixbuf.scale_simple(self.DISPLAY_WIDTH, self.DISPLAY_HEIGHT,
                                     gtk.gdk.INTERP_HYPER)
        self._cover_image.set_from_pixbuf(pixbuf)

    def _set_last_cover_state(self, filename = None, dirname = None,
                              digest = None):
        self._last_cover['filename'] = filename
        self._last_cover['dirname'] = dirname
        self._last_cover['digest'] = digest

    def _on_audio_source_changed(self, ctrl, old, new):
        """old and new are 2-tuples (playlist_index, AudioSource)"""
        if new[1] is None:
            self._set_last_cover_state()
            self._set_cover(self.DEFAULT_COVER)
            return

        src = new[1]
        src_dir = os.path.dirname(mesk.uri.unescape(src.uri.path))

        # Compute SHA digest for source metadata
        hash = '%s%s%s' % (src.meta_data.artist,
                           str(src.meta_data.year),
                           src.meta_data.album)
        digest = sha.new(hash).hexdigest()

        # Short circuit the search for a cover depending on last cover loaded
        if (self._last_cover['digest'] == digest):
            return

        # Search for a cover in the same directory as the source
        for fn in self.COVER_NAMES:
            for ext in self.COVER_EXTS:
                cover_file = src_dir + os.sep + fn + ext
                if os.path.exists(cover_file):
                    # Found a cover, set it
                    self._set_last_cover_state(cover_file, src_dir, digest)
                    self._set_cover(cover_file)
                    return

        # No cover found in file directory, see if the tag has an image
        img = src.get_cover_image()
        if img:
            mimetype, data = img
            filename = self._temp_image_file_from_data(data, mimetype)

            # Set cover from tag
            self._set_last_cover_state(None, None, digest)
            self._set_cover(filename)
            os.remove(filename)
            return

        # Search external sources asynchronously
        from mesk.plugin.interfaces import MetaDataSearch
        def search_callback(results, arg):
            # This callback happens on the Gtk thread
            data = results[MetaDataSearch.CAP_ALBUM_ART]
            if data:
                tmpfile = self._temp_image_file_from_data(data)
                self._set_last_cover_state(None, None, digest)
                self._set_cover(tmpfile)
                os.remove(tmpfile)

        mesk.plugin.search(MetaDataSearch.CAP_ALBUM_ART, src.meta_data.artist,
                           src.meta_data.album, None, search_callback)

        # No covers found, show default.
        self._set_last_cover_state()
        self._set_cover(self.DEFAULT_COVER)

    def _temp_image_file_from_data(self, data, mimetype=None):
        if mimetype:
            ext = '.%s' % mimetype.split("/")[1]
        else:
            ext = ''

        file_d, filename = tempfile.mkstemp(ext)
        os.write(file_d, data)
        os.close(file_d)
        return filename

    def _on_album_cover_eventbox_button_press_event(self, ebox, event):
        pass

    def _on_album_cover_eventbox_enter_notify_event(self, ebox, event):
        if not self._current_cover:
            return

        pixbuf = self._current_cover.get_image('front').get_pixbuf()
        pixbuf_width = pixbuf.get_width()
        pixbuf_height = pixbuf.get_height()

        if pixbuf_width < self.DISPLAY_WIDTH and \
           pixbuf_height < self.DISPLAY_HEIGHT:
            return

        # Set a timer to display full size in the case that the mouse just 
        # passes through
        self._display_full_timeout_id = \
            gobject.timeout_add(750, self._display_large_size, ebox)

    def _on_album_cover_eventbox_leave_notify_event(self, ebox, event):
        if self._display_full_timeout_id is not None:
            gobject.source_remove(self._display_full_timeout_id)
            self._display_full_timeout_id = None

    def _display_large_size(self, event_box):
        # Note: much of this code is taken from Gajim

        pixbuf = self._current_cover.get_image('front').get_pixbuf()
        pixbuf_width = pixbuf.get_width()
        pixbuf_height = pixbuf.get_height()
        if pixbuf_width > self.MAX_LARGE_DISPLAY_WIDTH or \
           pixbuf_height > self.MAX_LARGE_DISPLAY_HEIGHT:
            pixbuf_width = self.MAX_LARGE_DISPLAY_WIDTH
            pixbuf_height = self.MAX_LARGE_DISPLAY_HEIGHT
            pixbuf = pixbuf.scale_simple(pixbuf_width, pixbuf_height,
                                         gtk.gdk.INTERP_HYPER)

        # Create window to display full cover
        window = gtk.Window(gtk.WINDOW_POPUP)
        pixmap, mask = pixbuf.render_pixmap_and_mask()
        window.set_size_request(pixbuf_width, pixbuf_height)
        # we should make the cursor visible
        # gtk+ doesn't make use of the motion notify on gtkwindow by default
        # so this line adds that
        window.set_events(gtk.gdk.POINTER_MOTION_MASK)
        window.set_app_paintable(True)

        window.realize()
        window.window.set_back_pixmap(pixmap, False) # make it transparent
        window.window.shape_combine_mask(mask, 0, 0)

        # make the bigger avatar window show up centered 
        screen_width = gtk.gdk.screen_width()
        screen_height = gtk.gdk.screen_height()
        x0, y0 = event_box.window.get_origin()
        center_x = x0 + (event_box.allocation.width / 2)
        center_y = y0 + (event_box.allocation.height / 2)
        pos_x = center_x - (pixbuf_width / 2)
        pos_y = center_y - (pixbuf_height / 2)
        if pos_x < 0:
            pos_x = 0
        elif pos_x + pixbuf_width > screen_width:
            pos_x = screen_width - pixbuf_width
        if pos_y < 0:
            pos_y = 0
        elif pos_y + pixbuf_height > screen_height:
            pos_y = screen_height - pixbuf_height
        window.move(pos_x, pos_y)
        # make the cursor invisible so we can see the image
        mesk.gtk_utils.set_invisible_cursor(window.window)

        # we should hide the window
        window.connect('leave_notify_event',
                       self._on_full_display_leave_event)
        window.connect('motion-notify-event',
                      self._on_full_display_motion_event)

        window.show_all()
        self._full_cover_window = window

    def _on_full_display_leave_event(self, window, event):
        self._full_cover_window.destroy()
        self._set_cover(self._current_cover.get_file('front'))
    def _on_full_display_motion_event(self, window, event):
        # Restore cursor to default
        mesk.gtk_utils.set_cursor(self._full_cover_window.window, None)

