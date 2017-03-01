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
import datetime, tempfile, shutil

import gobject, gtk, gtk.gdk, gtk.glade
import pango

import mesk
import mesk.utils, mesk.gtk_utils, mesk.uri, mesk.playlist, mesk.audio
from mesk.i18n import _

import config, control

# Data model.  These do not have to correspond to the column order, nor
# are they all meant to be displayed values.
(MODEL_STATE,
 MODEL_STATUS_IMG,
 MODEL_STATUS_TEXT,
 MODEL_URI,
 MODEL_NUM,
 MODEL_TITLE,
 MODEL_ARTIST,
 MODEL_ALBUM,
 MODEL_TIME,
 MODEL_YEAR,
) = range(10)

MODEL_STATE_ACTIVE   = 0
MODEL_STATE_INACTIVE = 1

MAX_ROWS_PENDING = 20

class PlaylistControl(control.Control):

    def __init__(self, name, status_bar):
        control.Control.__init__(self)
        self.name = name
        self._status_bar = status_bar
        self._pl_config = config.PlaylistConfig(self.name)

        # A signal for knowing nothing more than the playlist has changed
        if gobject.signal_lookup('playlist_changed', PlaylistControl) == 0:
            gobject.signal_new('playlist_changed', PlaylistControl,
                               gobject.SIGNAL_RUN_LAST,
                               gobject.TYPE_NONE, [])

        self._playlist = None
        self._playlist_save_id = None
        self._initial_active = False
        self._audio_control = None
        self._row_activated_awaiting_active = None
        # Used to deselect when a sected row is clicked on
        self._current_selection_path = None
        self._last_row_status = None

        # Playlist stats
        self._list_len = 0
        self._list_bytes = long(0)
        self._list_secs = long(0)

        # Setup tab label
        self.tab_label_xml = mesk.gtk_utils.get_glade('playlist_tab_ebox',
                                                      'main_window.glade')
        self.tab_widget = self.tab_label_xml.get_widget('playlist_tab_ebox')
        self.tab_widget.connect('button-press-event',
                                self._on_playlist_tab_ebox_button_press_event)
        self.tab_label_label = \
            self.tab_label_xml.get_widget('playlist_tab_label')
        self.tab_label_label.set_max_width_chars(12)
        self.tab_label_label.set_markup(self.name)

        # The central widget for this control
        self.widget_xml = mesk.gtk_utils.get_glade('playlist_control',
                                                   'main_window.glade')
        self.widget = self.widget_xml.get_widget('playlist_control')
        self.widget_xml.signal_autoconnect(self)

        img = gtk.Image()
        pix = gtk.gdk.pixbuf_new_from_file('data/images/stock_shuffle.png')
        img.set_from_pixbuf(pix)
        self.widget_xml.get_widget('shuffle_togglebutton').set_image(img)

        img = gtk.Image()
        pix = gtk.gdk.pixbuf_new_from_file('data/images/stock_repeat.png')
        img.set_from_pixbuf(pix)
        self.widget_xml.get_widget('repeat_togglebutton').set_image(img)

        # Playlist treeview data store
        self._pl_view = self.widget_xml.get_widget('playlist_view')
        # Although this seems nice it prevents of DnD operations
        self._pl_view.set_reorderable(False)
        # A search UI is provided, so disable the native handler
        self._pl_view.set_enable_search(False)
        # Allow multi-select
        self._pl_view.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        self._pl_view.set_rules_hint(True)

        # Clipboard for cut/paste of playlist entires
        self._drag_data_get_handler = None
        self._drag_data_recv_handler = None

        self._clipboard = gtk.clipboard_get(gtk.gdk.atom_intern('_MESK_PL'))
        self.PL_ROW_TARGET_ID     = 0
        self.URI_LIST_TARGET_ID   = 1
        self.TEXT_PLAIN_TARGET_ID = 2
        self._targets = [
            # Target for playlist row reordering
            ('_PL_TREE_MODEL_ROW', gtk.TARGET_SAME_WIDGET,
             self.PL_ROW_TARGET_ID),
            # A list of uris for internal cut/paste and drops from
            # external apps
            ('text/uri-list', 0, self.URI_LIST_TARGET_ID),
            # LCD
            ('text/plain', 0, self.TEXT_PLAIN_TARGET_ID),
        ]
        self._pl_view.enable_model_drag_source(gtk.gdk.BUTTON1_MASK,
                                               self._targets,
                                               gtk.gdk.ACTION_DEFAULT |
                                               gtk.gdk.ACTION_MOVE)
        self._pl_view.enable_model_drag_dest(self._targets,
                                             gtk.gdk.ACTION_DEFAULT)

        # Connect for notification of scrolled window events
        scroll_win = self.widget_xml.get_widget('playlist_scrolledwindow')
        scroll_win.get_vadjustment().connect('value-changed',
                                             self._on_playlist_vscroll)
        # A value of None disables this value from updating, set to 0 to enable
        self._last_vscroll = 0
        self.AUTO_SCROLL_TIMEOUT = 15 # seconds

        # Hide search box
        self._search_widget = self.widget_xml.get_widget('playlist_search_hbox')
        self._search_widget.hide()
        # Get search widget refs
        self._search_entry = self.widget_xml.get_widget('search_entry')
        self._search_next = self.widget_xml.get_widget('search_next_button')
        self._search_next.set_sensitive(False)
        self._search_prev = self.widget_xml.get_widget('search_prev_button')
        self._search_prev.set_sensitive(False)

        # Playlist data model
        self._pl_model = gtk.ListStore(int, # Column state
                                       str, # Status pixbuf
                                       str, # Status text
                                       str, # Source URI
                                       int, # Source #
                                       str, # Source title
                                       str, # Source artist
                                       str, # Source album
                                       str, # Source time (formatted)
                                       str, # Source year
                                      )

        # Helper for making text columns
        def append_text_column(title, model_index, expand=True):
            col = TextColumn(title, expand=expand)
            col.add_attribute(col.txt_renderer, 'markup', model_index)
            col.add_attribute(col.txt_renderer, 'strikethrough', MODEL_STATE)
            self._pl_view.append_column(col)

        # Status column
        col = StatusColumn()
        self._pl_view.append_column(col)
        # Text columns
        append_text_column(_('Title'), MODEL_TITLE)
        append_text_column(_('Artist'), MODEL_ARTIST)
        append_text_column(_('Album'), MODEL_ALBUM)

        append_text_column(mesk.utils.pad_string(_('#'), 3), MODEL_NUM,
                           expand=False)
        append_text_column(mesk.utils.pad_string(_('Year'), 6), MODEL_YEAR,
                           expand=False)
        append_text_column(mesk.utils.pad_string(_('Time'), 7), MODEL_TIME,
                           expand=False)

        if mesk.log.getLogger().isEnabledFor(mesk.log.DEBUG):
            # Debugging load time
            import time
            t1 = time.time()
        # Load playlist
        pl = mesk.playlist.load(self._pl_config.uri, name=self._pl_config.name)
        if mesk.log.getLogger().isEnabledFor(mesk.log.DEBUG):
            # Debugging load time
            t2 = time.time()
            mesk.log.debug("Playlist '%s' loaded in %fs" %
                           (self._pl_config.name, t2 - t1))

        self._set_playlist(pl)
        self._set_read_only(pl.read_only)

        # Reset since no _manual_ scrolling has been done yet
        self._last_vscroll = 0
        self.widget.show()

    def has_playlist(self):
        return True
    def is_playlist_saved(self):
        return True

    def _save_playlist(self, interval=10000):
        def _save_cb():
            self._pl_config.update()

            # Write to a tempfile to avoid corruptions on errors
            (tmp_fd, tmp_filename) = tempfile.mkstemp()
            temp_file = os.fdopen(tmp_fd, 'wb+')
            mesk.playlist.xspf.save(temp_file, self._playlist)
            temp_file.close()
            # Move temp file over playlist
            shutil.copyfile(tmp_filename,
                            mesk.uri.unescape(self._pl_config.uri.path))
            os.unlink(tmp_filename)

            # XXX: For debugging
            #self._debug_show_playlist()

            self._playlist_save_id = None
            return False # No more callbacks

        if self._playlist_save_id:
            gobject.source_remove(self._playlist_save_id)
        if interval:
            self._playlist_save_id = gobject.timeout_add(interval, _save_cb)
        else:
            _save_cb()

    def shutdown(self):
        if self._audio_control:
            self._audio_control.stop()
        self._save_playlist(interval=0)

    def _get_model_metadata(self, src):
        row_data = {}

        if src.meta_data is None:
            return row_data

        row_data[MODEL_TITLE] = \
          mesk.gtk_utils.escape_pango_markup(src.meta_data.title)
        row_data[MODEL_ARTIST] = \
          mesk.gtk_utils.escape_pango_markup(src.meta_data.artist)
        row_data[MODEL_ALBUM] = \
          mesk.gtk_utils.escape_pango_markup(src.meta_data.album)

        if src.meta_data.year:
            year = unicode(src.meta_data.year)
        else:
            year = u''
        row_data[MODEL_YEAR] = year

        track_num = src.meta_data.track_num
        if track_num is None:
            track_num = 0
        row_data[MODEL_NUM] = track_num

        duration = mesk.utils.format_track_time(src.meta_data.time_secs)
        row_data[MODEL_TIME] = duration

        return row_data

    def _new_model_row(self, src):
        model_data = self._get_model_metadata(src)
        return [MODEL_STATE_ACTIVE, None, None,
                str(src.uri),
                model_data[MODEL_NUM],
                model_data[MODEL_TITLE],
                model_data[MODEL_ARTIST],
                model_data[MODEL_ALBUM],
                model_data[MODEL_TIME],
                model_data[MODEL_YEAR],
               ]

    def set_active(self, active=True, audio_ctrl=None):
        control.Control.set_active(self, active, audio_ctrl)

        if not active:
            if self._audio_control:
                self._audio_control.stop()
            self._audio_control = None
        else:
            self._audio_control = audio_ctrl

        # Connect events for audio_control on first activation
        if self._is_active and not self._initial_active:
            assert(self._audio_control)
            self._initial_active = True
            self._audio_control.connect('play', self._on_audio_playing)
            self._audio_control.connect('pause', self._on_audio_paused)
            self._audio_control.connect('stopped', self._on_audio_stopped)
            self._audio_control.connect('next', self._on_audio_next)
            self._audio_control.connect('prev', self._on_audio_prev)
            self._audio_control.connect('source-changed',
                                        self._on_audio_source_changed)
            self._error_count = 0
            self._audio_control.connect('error', self._on_audio_error)
            self._audio_control.connect('playlist-reset',
                                        self._on_playlist_reset)
            self._audio_control.connect('tag-update', self._on_audio_tag_update)

        self._update_tab_label()

        if self._row_activated_awaiting_active is not None:
            assert(self._audio_control)
            self._activate_row_cb(self._row_activated_awaiting_active)
            self._row_activated_awaiting_active = None

    def _update_tab_label(self):
        # Bold label for active tab
        label = self.name
        if self._is_active:
            label = '<b>%s</b>' % label
        self.tab_label_label.set_markup(label)

    def set_focused(self, focused=True):
        if focused:
            self._pl_view.grab_focus()

    def _set_read_only(self, read_only=True):
        self._playlist.read_only = read_only

        # Tweak for for when the playlist is read-only
        if read_only:
            self.widget_xml.get_widget('add_button').hide()

            if self._drag_data_get_handler:
                self._pl_view.disconnect(self._drag_data_get_handler)
            if self._drag_data_recv_handler:
                self._pl_view.disconnect(self._drag_data_recv_handler)

            self.widget_xml.get_widget('read_only_image_eventbox').show()
        else:
            self.widget_xml.get_widget('add_button').show()

            self._drag_data_get_handler = \
                self._pl_view.connect("drag-data-get", self._on_drag_data_get)
            self._drag_data_recv_handler = \
                self._pl_view.connect("drag-data-received",
                                      self._on_drag_data_received)

            self.widget_xml.get_widget('read_only_image_eventbox').hide()

    def _set_playlist(self, playlist):
        self._playlist = playlist

        self._pl_model.clear()
        for src in self._playlist:
            self._pl_model.append(self._new_model_row(src))
        self._pl_view.set_model(self._pl_model)

        # Mark current position in playlist
        if self._playlist.get_curr_index() < 0 and self._playlist.has_next():
            self._set_row_status(gtk.STOCK_MEDIA_STOP, 0);
        else:
            self._set_row_status(gtk.STOCK_MEDIA_STOP);

        shuffled = self._playlist.is_shuffled()
        repeating = self._playlist.is_repeating()
        self.widget_xml.get_widget('shuffle_togglebutton').set_active(shuffled)
        self.widget_xml.get_widget('repeat_togglebutton').set_active(repeating)

        self._update_playlist_stats()
        self.emit('playlist_changed')

    def get_playlist(self):
        '''NOTE: Treat as read-only (for now)'''
        return self._playlist

    def _on_playlist_vscroll(self, widget):
        # Using this event to prevent song changes from scrolling when there
        # was a recent manual scroll action.  So if you're looking for something
        # in the treeview and the song changes you don't lose your place.
        if self._last_vscroll is not None:
            self._last_vscroll = gobject.get_current_time()

    def _on_playlist_view_row_activated(self, treeview, path, view_col):
        row = path[0]
        if not self._is_active:
            self._row_activated_awaiting_active = row
            self.emit('control_request_active')
        else:
            self._activate_row_cb(row)

    def _activate_row_cb(self, row):
        self._set_row_status()
        self._audio_control.enqueue_source(absolute=row)
        self._audio_control.play()

    def _on_playlist_view_cursor_changed(self, treeview):
        select_path = treeview.get_cursor()[0]
        # Clear selection if the current selection is clicked
        if (self._current_selection_path and
            (select_path == self._current_selection_path)):
            treeview.get_selection().unselect_path(select_path)
            self._current_selection_path = None
        else:
            self._current_selection_path = select_path

    def _on_playlist_view_button_press_event(self, treeview, event):
        # Intercept right clicks for context menu
        if event.button == 3:
            # Calculate selected rows, if any
            x, y = int(event.x), int(event.y)
            path_info = treeview.get_path_at_pos(x, y)
            selected_rows = []
            if path_info is not None:
                path, col, cellx, celly = path_info
                selected_rows = self.get_selected_rows()
                if not selected_rows or (path[0] not in selected_rows):
                    # No selections or click was outside selections, so select
                    # row under mouse click
                    treeview.grab_focus()
                    treeview.set_cursor(path[0])
                    selected_rows = [path[0]]

            self._playlist_context_menu_popup(selected_rows, event)
            return True
        else:
            # Let all other clicks pass through unhandled
            return False

    def _supports_properties(self):
        '''A hook for subclasses to specify if playlist props are supported,
        read-only is not enough'''
        return True

    def _process_tab_menu(self, menu_xml, menu):
        if not self._supports_properties():
            menu_xml.get_widget('properties_menuitem').hide()

        # Tweak for read-only menu
        if self._playlist.read_only:
            menu_xml.get_widget('separator1').hide()
            menu_xml.get_widget('delete_menuitem').hide()

    def _playlist_tab_menu_popup(self, event):
        tab_menu_xml = mesk.gtk_utils.get_glade('playlist_tab_menu',
                                                'playlist.glade')
        tab_menu_xml.signal_autoconnect(self)
        tab_menu = tab_menu_xml.get_widget('playlist_tab_menu')

        if self.name == mesk.DEFAULT_PLAYLIST_NAME:
            # The default playlist cannot be deleted
            tab_menu_xml.get_widget('separator1').hide()
            tab_menu_xml.get_widget('delete_menuitem').hide()

        self._process_tab_menu(tab_menu_xml, tab_menu)
        tab_menu.popup(None, None, None, event.button, event.time)

    def _playlist_context_menu_popup(self, selected_rows, event):
        menu_xml = mesk.gtk_utils.get_glade('playlist_context_menu',
                                            'playlist.glade')
        pl_menu = menu_xml.get_widget('playlist_context_menu')
        menu_xml.signal_autoconnect(self)
        pl_menu.show_all()

        # Filter menuitems per the current playlist state
        for menuitem in pl_menu.get_children():
            menuitem_name = menuitem.get_name()

            if menuitem_name in ['properties_menuitem']:
                if self._supports_properties():
                    menuitem.show()
                else:
                    menuitem.hide()
            elif menuitem_name in ['add_menuitem']:
                if self._playlist.read_only:
                    menuitem.hide()
                else:
                    menuitem.show()
            elif menuitem_name in ['copy_menuitem']:
                if selected_rows:
                    menuitem.show()
                else:
                    menuitem.hide()
            elif menuitem_name in ['remove_menuitem', 'cut_menuitem']:
                # Hide these menuitems when there are no selections or
                # read-only
                if not self._playlist.read_only and selected_rows:
                    menuitem.show()
                else:
                    menuitem.hide()
            elif menuitem_name == 'paste_menuitem':
                if self._playlist.read_only:
                    menuitem.hide()
                else:
                    available_targets = self._clipboard.wait_for_targets()
                    # Show paste menu only if the clipboard contains data
                    if (available_targets and
                        (self._targets[self.URI_LIST_TARGET_ID][0] in
                         self._clipboard.wait_for_targets())):
                        menuitem.show()
                    else:
                        menuitem.hide()
            elif menuitem_name == 'queue_menuitem':
                # Show/hide Queue menuitem
                if not len(self._playlist):
                    menuitem.hide()
                else:
                    menuitem.show()
                    sub_menu = menuitem.get_submenu()
                    sub_children = sub_menu.get_children()
                    num_subs_hidden = 0
                    num_sub_children = len(sub_children)
                    # Process children of the queue menuitem
                    for sub_item in sub_children:
                        if sub_item.get_name() in ['queue_unqueue_menuitem',
                                                   'queue_front_menuitem']:
                            if selected_rows:
                                sub_item.show()
                            else:
                                sub_item.hide()
                                num_subs_hidden +=1
                        elif sub_item.get_name() == 'clear_queue_menuitem':
                            if self._playlist.get_queue():
                                sub_item.show()
                            else:
                                sub_item.hide()
                                num_subs_hidden +=1
                    # If all submenus are hidden we can hide the parent
                    if num_subs_hidden == num_sub_children:
                        menuitem.hide()
            else:
                menuitem.show()

        pl_menu.popup(None, None, None, event.button, event.time)

    def _on_playlist_tab_ebox_button_press_event(self, tab, event):
        if event.button == 3:
            self._playlist_tab_menu_popup(event)
            return True
        return False

    def _on_close_menuitem_activate(self, menuitem):
        self.emit('control_request_close')

    def _on_properties_menuitem_activate(self, menuitem):
        self.edit_properties()

    def _on_delete_menuitem_activate(self, menuitem):
        # Confirm
        from dialogs import ConfirmationDialog
        d = ConfirmationDialog(None, type=gtk.MESSAGE_WARNING)
        d.set_markup(_('Are you sure you want to delete playlist \'%s\'?') % \
                     self._pl_config.name)
        d.format_secondary_text(_('All playlist data will be lost.'))
        if not d.confirm():
            return

        # Delete
        os.remove(mesk.uri.unescape(self._pl_config.uri.path))
        self._pl_config.delete()
        self.emit('control_request_close')

    def edit_properties(self):
        # Run properties dialog
        props_dialog = PlaylistPropertiesDialog(self._playlist)
        resp = props_dialog.run()
        if resp != gtk.RESPONSE_OK:
            return

        # Update state
        self.name = props_dialog.name
        self._playlist.name = props_dialog.name
        self._pl_config.set_name(props_dialog.name)
        self._update_tab_label()

        self._playlist.annotation = props_dialog.annotation
        # Toggle read-only only when it's changed
        if self._playlist.read_only != props_dialog.read_only:
            self._set_read_only(props_dialog.read_only)

    ### AudioControl signal handlers ###
    def _on_audio_playing(self, audio_control):
        if self._is_active:
            self._set_row_status(gtk.STOCK_MEDIA_PLAY)
    def _on_audio_paused(self, audio_control):
        if self._is_active:
            self._set_row_status(gtk.STOCK_MEDIA_PAUSE)
    def _on_audio_stopped(self, audio_control):
        if self._is_active:
            self._set_row_status(gtk.STOCK_MEDIA_STOP)
    def _on_audio_next(self, audio_control):
        self.scroll_to_row(self._playlist.get_curr_index(), force=True)
    def _on_audio_prev(self, audio_control):
        self.scroll_to_row(self._playlist.get_curr_index(), force=True)

    def _on_audio_source_changed(self, audio_control, old, new):
        # tuple element 0 is the playlist index, 1 the source object
        if self._is_active:
            # Clear old status
            if old[0] >= 0 and old[0] != new[0]:
                self._set_row_status(None, old[0])
            # Update stopped rows
            if audio_control.is_stopped() and new[0] >= 0 and new[1]:
                self._set_row_status(gtk.STOCK_MEDIA_STOP, new[0])

    def _on_playlist_reset(self, audio_source):
        self._set_row_status(None, self._playlist.get_curr_index())

    def _on_audio_error(self, audio_control, err, audio_src):
        if audio_control != self._audio_control:
            # We are not the ative playlist.
            return

        self._clear_row_status()

        src_index = self._playlist.index(audio_src)
        src_iter = self._pl_model.get_iter(src_index)

        # Check active state of source in model
        is_active = self._pl_model.get_value(src_iter, MODEL_STATE)
        self._audio_control.stop()

        if is_active == MODEL_STATE_ACTIVE:
            self._pl_model.set_value(src_iter, MODEL_STATE,
                                     MODEL_STATE_INACTIVE)
            self._status_bar.add_log_msg(
                '<b>%s</b>: %s' % (str(err),
                                   mesk.uri.unescape(str(audio_src.uri))))

        # Don't loop to the beginning (regardless of repeat mode) to prevent
        # endless loops
        play_continue = True
        if src_index != len(self._playlist) - 1:
            if self._error_count >= 5:
                play_continue = False
                self._error_count = 0
            else:
                self._error_count += 1
            self._audio_control.next(play=play_continue)

    def _on_audio_tag_update(self, audio_control, audio_src):
        if not self._is_active:
            return
        # If we got a tag the track is playing and the error count can be reset
        self._error_count = 0
        self._update_source_row(audio_src)

    def _update_source_row(self, audio_src):
        # Update model data with tag update
        row = self._playlist.index(audio_src)
        model_iter = self._pl_model.get_iter(row)

        model_data = self._get_model_metadata(audio_src)
        for key in model_data:
            self._pl_model.set_value(model_iter, key, model_data[key])

    def _on_dialog_close(self, dialog, response):
        dialog.destroy()

    def scroll_to_row(self, row, force=False):
        '''Ensure row is showing in scroll view unless the user has manually
        scrolled recently'''
        if row < 0 or row > len(self._playlist):
            return

        last_scroll = self._last_vscroll

        now = gobject.get_current_time()
        if force or (not last_scroll) or \
           (now >= (last_scroll + self.AUTO_SCROLL_TIMEOUT)):
            self._pl_view.scroll_to_cell(row, use_align=False, row_align=0.1)
            self._last_vscroll = 0

    def _clear_row_status(self):
        if self._last_row_status and self._last_row_status.get_path():
            iter = self._pl_model.get_iter(self._last_row_status.get_path())
            self._pl_model.set_value(iter, MODEL_STATUS_IMG, None)
        self._last_row_status = None

    def _set_row_status(self, stock_id=None, row=None):
        # Use current if none specified
        if row is None:
            row = self._playlist.get_curr_index()
        if row < 0 or row >= len(self._playlist):
            return

        if stock_id:
            self.scroll_to_row(row)

        # Set new
        self._last_row_status = gtk.TreeRowReference(self._pl_model, row)
        model_iter = self._pl_model.get_iter(row)
        self._pl_model.set_value(model_iter, MODEL_STATUS_IMG, stock_id)

        # If playing reset model row to active
        if stock_id == gtk.STOCK_MEDIA_PLAY:
            self._pl_model.set_value(model_iter, MODEL_STATE,
                                     MODEL_STATE_ACTIVE)

        # Update queue display
        if row not in self._playlist.get_queue():
            self._pl_model.set_value(model_iter, MODEL_STATUS_TEXT, '')
            self._update_playlist_queue()

    def _get_status_icon(self):
        stock_id = None
        if not self._audio_control:
            stock_id = None
        elif self._audio_control.is_playing():
            stock_id = gtk.STOCK_MEDIA_PLAY
        elif self._audio_control.is_stopped():
            stock_id = gtk.STOCK_MEDIA_STOP
        elif self._audio_control.is_paused():
            stock_id = gtk.STOCK_MEDIA_PAUSE
        return stock_id

    def _update_playlist_stats(self, count_inc = None, size_bytes_inc = None,
                               time_secs_inc = None):
        if count_inc is None and size_bytes_inc is None and \
           time_secs_inc is None:
            self._list_len = len(self._playlist)
            self._list_bytes = long(0)
            self._list_secs = long(0)

            for src in self._playlist:
                if src.meta_data.time_secs is not None:
                    self._list_secs += src.meta_data.time_secs
                if src.meta_data.size_bytes is not None:
                    self._list_bytes += src.meta_data.size_bytes
        else:
            if count_inc:
                self._list_len += count_inc
            if size_bytes_inc:
                self._list_bytes += size_bytes_inc
            if time_secs_inc:
                self._list_secs += time_secs_inc

        delta = datetime.timedelta(seconds=self._list_secs);
        label = self.widget_xml.get_widget('playlist_stats_label')
        txt = "%d %s [%s] - %s" % (self._list_len, _('tracks'),
                                   mesk.utils.format_size(self._list_bytes),
                                   mesk.utils.format_time_delta(delta))
        label.set_markup(txt)

    def get_selected_rows(self):
        '''Returns a sorted list of the selected rows'''
        rows = []
        (model, selected) = self._pl_view.get_selection().get_selected_rows()
        iters = [model.get_iter(path) for path in selected]
        for iter in iters:
            row = model.get_path(iter)[0]
            rows.append(row)
        rows.sort()
        return rows

    def delete_rows(self, rows=None):
        '''When rows is None, all selected rows are deleted'''
        count = 0
        byte_count = 0
        sec_count = 0

        if not rows:
            rows = self.get_selected_rows()
            if not rows:
                return
        have_audio_ctrl = self._audio_control is not None

        if (len(rows) == len(self._playlist)):
            # Deleting all row, so stop now rather than reenqueue a play below
            have_audio_ctrl and self._audio_control.stop()

        first_row = rows[0]
        do_play = False
        for row in rows:
            row -= count
            count += 1

            src = self._playlist[row]
            byte_count += src.meta_data.size_bytes or 0
            sec_count += src.meta_data.time_secs or 0

            # The rows are in ascending order, so each will adjust as we delete
            curr = self._playlist.get_curr_index()
            self._playlist.remove(row)
            self._pl_model.remove(self._pl_model.get_iter(row))

            # Handle current playlist deletion
            row_to_enqueue = None
            if (have_audio_ctrl and (row == curr)):
                if self._audio_control.is_playing():
                    have_audio_ctrl and self._audio_control.stop()
                    do_play = True

                if len(self._playlist) != 0:
                    if row >= len(self._playlist):
                        # Deleted from end, adjust row
                        row = len(self._playlist) - 1
                    row_to_enqueue = row
                else:
                    row_to_enqueue = None

        if row_to_enqueue is not None:
            self._audio_control.enqueue_source(absolute=row,
                                               start_playing=do_play)

        self._pl_view.set_cursor(first_row)

        # Update display
        self._set_row_status(self._get_status_icon())
        have_audio_ctrl and self._audio_control.set_widget_sensitivites()
        self._update_playlist_stats(count_inc=(-1 * count),
                                    size_bytes_inc=(-1 * byte_count),
                                    time_secs_inc=(-1 * sec_count))
        self._save_playlist()
        self.emit('playlist_changed')

    def _update_playlist_queue(self, old_queue=None, new_queue=None):
        old_queue = old_queue or []
        new_queue = new_queue or self._playlist.get_queue()

        for old in old_queue:
            try:
                mod_iter = self._pl_model.get_iter(old)
                self._pl_model.set_value(mod_iter, MODEL_STATUS_TEXT, '')
            except ValueError:
                mesk.log.warn("Invalid queue index: %d" % old)

        count = 1
        for new in new_queue:
            try:
                mod_iter = self._pl_model.get_iter(new)
                self._pl_model.set_value(mod_iter, MODEL_STATUS_TEXT,
                                         '[%d]' % count)
                count += 1
            except ValueError:
                mesk.log.warn("Invalid queue index: %d" % old)

    def _on_playlist_view_key_press_event(self, widget, event):
        # This handler is for key press events on just the treeview, 
        # whereas the normal handler is on the container
        return self._on_playlist_control_key_press_event(widget, event)

    def _on_playlist_control_key_press_event(self, widget, event):
        if event.state & gtk.gdk.CONTROL_MASK:
            # CTRL+c - Copy
            if event.keyval == gtk.keysyms.c:
                self._on_copy_menuitem_activate(None)
                return True
            # CTRL+x - Cut
            elif event.keyval == gtk.keysyms.x and not self._playlist.read_only:
                self._on_cut_menuitem_activate(None)
                return True
            # CTRL+v - Paste
            elif event.keyval == gtk.keysyms.v and not self._playlist.read_only:
                self._on_paste_menuitem_activate(None)
                return True
            # CTRL+f - Show search box 
            elif event.keyval == gtk.keysyms.f:
                self._show_search()
                return True
        elif event.state & gtk.gdk.MOD1_MASK:
            # ALT+q - Clear queue
            if event.keyval == gtk.keysyms.q:
                self.clear_queue()
                return True
        else:
            # Delete - deletes selected rows
            if (event.keyval == gtk.keysyms.Delete and
                    not self._playlist.read_only):
                self.delete_rows()
                return True
            # 'q' - To enqueue/deque selections
            elif event.keyval == gtk.keysyms.q:
                self.queue_selected_rows()
                return True
            # 'Q' - To enqueue to the front of the list
            elif event.keyval == gtk.keysyms.Q:
                self.queue_selected_rows(position=0, replace=True)
                return True
            # '/' - Show search box 
            elif event.keyval == gtk.keysyms.slash:
                self._show_search()
                return True
            # Escape - Hide search box 
            elif event.keyval == gtk.keysyms.Escape:
                self._hide_search()
                return True
            # F2 - Rename playlist
            elif (event.keyval == gtk.keysyms.F2 and
                    not self._playlist.read_only):
                self.edit_properties()
                return True
        return False

    def _hide_search(self):
        self._search_widget.hide()
        self._pl_view.grab_focus()
    def _show_search(self):
        self._search_widget.show()
        self._search_entry.grab_focus()

    def scroll_to_current(self):
        # XXX: This could be better, often gtk scrolls so it is "just" in view
        self.scroll_to_row(self._playlist.get_curr_index(), force=True)

    def queue_selected_rows(self, position=-1, replace=False):
        '''Add selected rows to the playlist queue.  If the row is already in
        the queue it is removed instead (use replace=True to change this).
        By default the rows are added to the end of the queue, use position to
        insert at a specific index.'''
        selected_rows = self.get_selected_rows()
        # If position is given this is not an append, but an insert and the rows
        # need to be reversed to have the correct queue indices.
        if position >= 0:
            selected_rows.reverse()

        for row in selected_rows:
            old_queue = self._playlist.get_queue()

            if row in old_queue:
                self._playlist.dequeue(row)
                if replace:
                    self._playlist.enqueue(row, position)
            else:
                self._playlist.enqueue(row, position)

            new_queue = self._playlist.get_queue()
            self._update_playlist_queue(old_queue, new_queue)

        # Clear selection
        selection_path = self._pl_view.get_cursor()[0]
        (model, selected) = self._pl_view.get_selection().get_selected_rows()

        self.emit('playlist_changed')

    def clear_queue(self):
        curr_queue = self._playlist.get_queue()
        for row in curr_queue:
            self._playlist.dequeue(row)
        self._update_playlist_queue(curr_queue, [])
        self.emit('playlist_changed')

    # DnD of playlist rows for reordering
    def _on_drag_data_get(self, treeview, context, selection, target_id, etime):
        model, path = treeview.get_selection().get_selected_rows()
        if not path:
            return
        # XXX: Gtk.Treeview does not seem to support dragging multiple rows
        path = path[0]
        row_str = str(path[0])
        iter = self._pl_model.get_iter(path)
        # Store the row as the drag data since this is only used for reordering
        selection.set('_PL_TREE_MODEL_ROW', 8, row_str)

    # DnD from external source
    def _on_drag_data_received(self, treeview, context, x, y, selection, info,
                               timestamp):

        drop_row = self._pl_view.get_dest_row_at_pos(x, y)
        if drop_row is not None:
            drop_path, drop_pos = drop_row
            drop_row = drop_path[0]
        else:
            if len(self._playlist):
                drop_row = len(self._playlist) - 1
                drop_path = (drop_row,)
                drop_pos = gtk.TREE_VIEW_DROP_AFTER
            else:
                # The list/model is empty
                drop_row = 0
                drop_path = (drop_row,)
                drop_pos = gtk.TREE_VIEW_DROP_INTO_OR_BEFORE

        # Handle playlist reordering
        if ((selection.target == '_PL_TREE_MODEL_ROW') and (drop_row >= 0) and
            (selection.data is not None)):
            src_row = int(selection.data)
            src = self._playlist[src_row]
            current_index = self._playlist.get_curr_index()

            src_iter = self._pl_model.get_iter(src_row)
            drop_iter = self._pl_model.get_iter(drop_row)

            # Get persistent references to all queued rows
            queued_rows = []
            for qi in self._playlist.get_queue():
                queued_rows.append(gtk.TreeRowReference(self._pl_model, qi))

            insert_before = (drop_pos == gtk.TREE_VIEW_DROP_BEFORE or \
                             drop_pos == gtk.TREE_VIEW_DROP_INTO_OR_BEFORE)

            # Insert
            if insert_before:
                self._pl_model.move_before(src_iter, drop_iter)
                self._playlist.insert(drop_row, src)
            else:
                self._pl_model.move_after(src_iter, drop_iter)
                self._playlist.insert_after(drop_row, src)
            # Remove
            if src_row > drop_row:
                self._playlist.remove(src_row + 1)
            else:
                self._playlist.remove(src_row)

            # Handle the current row being moved
            if src_row == current_index:
                curr_row = drop_row
                if src_row > drop_row:
                    curr_row += 1
                # The current track is being moved
                if insert_before:
                    self._playlist.set_curr_index(curr_row - 1)
                else:
                    self._playlist.set_curr_index(curr_row)
                if self._audio_control:
                    self._audio_control.set_widget_sensitivites()

            # Update new queue after the rearrangement
            new_queue = []
            for row_ref in queued_rows:
                new_queue.append(row_ref.get_path()[0])
            if new_queue:
                self._playlist.set_queue(new_queue)

            self.emit('playlist_changed')
        # Handle a drop from external source
        # Note: Nautilus uses ACTION_COPY while konqueror uses ACTION_MOVE
        elif (context.action == gtk.gdk.ACTION_COPY or
              context.action == gtk.gdk.ACTION_MOVE):
            # Use drag data URIs
            uris = list(selection.get_uris())
            if not uris and selection.get_text():
                # No URIs, use drag data text
                uris.append(selection.get_text())
            if not uris:
                # Still nothing, bail
                context.finish(False, False, timestamp)
                return

            uris.sort()
            self.add_uris(uris, drop_pos, drop_row)

            self.emit('playlist_changed')

        context.finish(True, False, timestamp)
        self._save_playlist()

    def _debug_show_playlist(self):
        # Dump the modified playlist for debugging
        if mesk.log.getLogger().isEnabledFor(mesk.log.DEBUG):
            msg = 'Modified Playlist:\n'
            for src in self._playlist:
                msg += str(src.uri) + '\n'
            mesk.log.debug(msg)

    def add_uris(self, uris, drop_pos=gtk.TREE_VIEW_DROP_AFTER, drop_row=None):
        orig_size = self._playlist.get_length()
        if drop_row is None:
            drop_row = orig_size

        status_msg = _('Adding items to \'%s\'...') % self.name
        self._status_bar.push_status_msg(status_msg)

        import time
        t1_read = time.time()

        mesk.gtk_utils.set_busy_cursor(self.widget.get_parent_window())

        count = 0
        srcs = []
        try:
            for uri in uris:
                if not mesk.uri.is_uri(uri):
                    uri = mesk.uri.make_uri(uri)

                uri_path = mesk.uri.unescape(uri.path)

                # Handle files/directories
                if uri.scheme == 'file' and os.path.isdir(uri_path):
                    # Recurse into a directory
                    for (root, dirs, files) in os.walk(uri_path):
                        # Add files in this directory
                        dir_files = []
                        for f in files:
                            f = os.path.abspath(root + os.sep + f);
                            dir_files.append(f)
                        dir_files.sort()
                        for f in dir_files:
                            f = mesk.uri.escape_path(f)
                            uris.append(f)
                        # Add directories in this directory
                        dirs.sort()
                        for d in dirs:
                            d = mesk.uri.escape_path(os.path.abspath(root +
                                                                     os.sep +
                                                                     d))
                            uris.append(d)
                        # To do proper directory ordering we break and let
                        # the next pass recurse into any directories
                        break
                else:
                    # Handle local and remote URIs
                    fname = os.path.basename(uri_path)
                    ext = os.path.splitext(fname)[1]

                    if mesk.playlist.is_supported_ext(ext):
                        # Playlists
                        pl = mesk.playlist.load(uri)
                        for src in pl:
                            srcs.append(src)
                        del pl
                    elif mesk.audio.is_supported_ext(ext):
                        # Audio files
                        src = mesk.audio.load(uri)
                        srcs.append(src)
                    else:
                        uri_str = mesk.uri.unescape(str(uri))
                        # Skip types that we don't ever expect to handle,
                        # but set a status msg about unsupported audio types
                        import mimetypes
                        mt = mimetypes.guess_type(str(uri))
                        mesk.log.debug('Skipping URI %s (mimetype: %s)' %
                                       (uri_str, mt))
                        if mt and mt[0] and mt[0].split('/')[0] == 'audio':
                            msg = '<b>%s</b>: (%s, %s) %s' % \
                                  (_('Unsupported audio format'), mt[0],
                                   ext,
                                   mesk.gtk_utils.escape_pango_markup(uri_str))
                            self._status_bar.add_log_msg(msg)

                mesk.gtk_utils.update_pending_events()

            t2_read = time.time()
            mesk.log.debug("Time to read all URIs: %fs" % (t2_read - t1_read))

            for src in srcs:
                self._insert_source(drop_pos, drop_row + count, src)
                count += 1
                # For every N inserts update UI
                if count % MAX_ROWS_PENDING == 0:
                    mesk.gtk_utils.update_pending_events()

        except Exception, ex:
            import traceback
            from dialogs import ErrorDialog

            exc_str = traceback.format_exc()
            msg = _('Error dropping source: %s\n\n%s') % \
                  (mesk.uri.unescape(str(uri)), str(ex))
            mesk.log.error("%s:\n%s" % (msg, exc_str))

            d = gtk.MessageDialog(None, markup=msg)
            d.run()
            d.destroy()

        mesk.gtk_utils.set_cursor(self.widget.get_parent_window(), None)

        self._audio_control and self._audio_control.set_widget_sensitivites()
        # Adding to an empty playlist initialization
        if (orig_size == 0 and self._playlist.get_length() and
            self._audio_control and self._audio_control.is_stopped()):

            self._audio_control.enqueue_source(next=True,
                                               start_playing=False)
            if self._playlist.get_curr_index() < 0:
                self._playlist.set_curr_index(0)
            self._set_row_status(gtk.STOCK_MEDIA_STOP)

        add_count = self._playlist.get_length() - orig_size
        # Update status bar
        self._status_bar.pop_status_msg(status_msg)
        self._set_status_msg(_('%d items added to \'%s\'') % (add_count,
                                                              self.name))
        return add_count

    def _insert_source(self, drop_pos, drop_row, src):
        new_row = None
        drop_iter = None

        if (drop_row < len(self._playlist)):
            drop_iter = self._pl_model.get_iter((drop_row,))

            if (drop_pos == gtk.TREE_VIEW_DROP_BEFORE or \
                    drop_pos == gtk.TREE_VIEW_DROP_INTO_OR_BEFORE):
                self._pl_model.insert_before(drop_iter,
                                             self._new_model_row(src))
                self._playlist.insert(drop_row, src)
                new_row = drop_row
            else:
                self._pl_model.insert_after(drop_iter,
                                            self._new_model_row(src))
                self._playlist.insert(drop_row + 1, src)
                new_row = drop_row + 1
        else:
            self._pl_model.append(self._new_model_row(src))
            self._playlist.append(src)
            new_row = len(self._playlist) - 1

        self._update_playlist_stats(count_inc=1,
                                    size_bytes_inc=src.meta_data.size_bytes,
                                    time_secs_inc=src.meta_data.time_secs)
        self.emit('playlist_changed')
        return new_row

    def _on_add_button_clicked(self, button):
        uris = self._browse_for_uris()
        if uris:
            self.add_uris(uris, gtk.TREE_VIEW_DROP_AFTER, len(self._playlist))
            self._save_playlist()

    def _make_file_filter(self, name, extensions):
        filter = gtk.FileFilter()
        filter.set_name(name)
        for ext in extensions:
            filter.add_pattern('*%s' % ext)
        return filter

    def _browse_for_uris(self):
        buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT,
                   gtk.STOCK_ADD, gtk.RESPONSE_OK)
        dialog = gtk.FileChooserDialog(title=_('Add Audio'),
                                       action=gtk.FILE_CHOOSER_ACTION_OPEN,
                                       buttons=buttons)
        dialog.set_select_multiple(True)
        dialog.set_current_folder(self._playlist.browse_dir or '')

        def folder_changed(chooser):
            self._playlist.browse_dir = chooser.get_current_folder()
        dialog.connect('current-folder-changed', folder_changed)

        filters = []
        # Initialize file dialog filters based on supported audio formats
        def add_filter(name, exts):
            filter = self._make_file_filter(name, exts)
            filters.append(filter)
            dialog.add_filter(filter)

        pl_exts = mesk.playlist.supported_extensions.keys()
        audio_exts = mesk.audio.supported_extensions.keys()
        add_filter(_('All'), pl_exts + audio_exts)
        add_filter(_('Audio'), audio_exts)
        add_filter(_('Playlists'), pl_exts)

        # This madness allows the file dialog to select directories when
        # the checkbox is toggles and files when not since this is not
        # possible by default
        dir_check = gtk.CheckButton(_('Enable to select directories instead of '
                                      'files.'),
                                    use_underline = True)

        def on_toggled(button, dialog):
            # Toggling causes the current selections to become unselected,
            # workaround by reselecting
            if button.get_active():
                selected = dialog.get_filenames()
                dialog.set_action(gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)
                for f in filters:
                    if f in dialog.list_filters():
                        dialog.remove_filter(f)
                # Restore any selected dirs
                for f in selected:
                    dialog.select_filename(f)
            else:
                dialog.set_action(gtk.FILE_CHOOSER_ACTION_OPEN)
                for f in filters:
                    if f not in dialog.list_filters():
                        dialog.add_filter(f)
            self._playlist.dir_select = dir_check.get_active()

        dir_check.connect('toggled', on_toggled, dialog)
        dir_check.show()
        dialog.set_extra_widget(dir_check)
        dir_check.set_active(self._playlist.dir_select)
        if self._playlist.dir_select:
            dialog.set_action(gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)
        else:
            dialog.set_action(gtk.FILE_CHOOSER_ACTION_OPEN)

        uris = []
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            uris = dialog.get_uris()
            uris.sort()
        dialog.destroy()
        return uris

    def _on_shuffle_togglebutton_toggled(self, button):
        state = button.get_active()
        self._playlist.set_shuffle(state)
        if self._audio_control:
            self._audio_control.set_widget_sensitivites()
        self.emit('playlist_changed')

    def _on_repeat_togglebutton_toggled(self, button):
        state = button.get_active()
        self._playlist.set_repeat(state)
        if self._audio_control:
            self._audio_control.set_widget_sensitivites()
        self.emit('playlist_changed')

    def _on_search_close_button_clicked(self, button):
        self._hide_search()
    def _on_search_clear_button_clicked(self, button):
        self._search_entry.set_text('')
    def _on_search_next_button_clicked(self, button):
        self._search(dir='next')
    def _on_search_prev_button_clicked(self, button):
        self._search(dir='prev')

    def _on_search_entry_activate(self, entry):
        self._search_next.emit('clicked')
    def _on_search_entry_changed(self, entry):
        # Changes next/prev button sensitivies based on whether text exists
        if entry.get_text():
            state = True
        else:
            state = False
        for button in [self._search_next, self._search_prev]:
            button.set_sensitive(state)

    def _search(self, dir='next'):
        if len(self._playlist) == 0:
            return

        search_txt = self._search_entry.get_text()

        # Get playlist model data and selection
        (model, selected) = self._pl_view.get_selection().get_selected_rows()
        if not model or not search_txt:
            return

        search_txt = unicode(search_txt, 'utf-8')
        normalized_search = search_txt.lower()

        # Selection determines where search starts
        if not selected:
            start_iter = model.get_iter_first()
        else:
            try:
                path = selected[0]
                if dir == 'next':
                    start_iter = model.get_iter((path[0] + 1,))
                else:
                    start_iter = model.get_iter((path[0] - 1,))
            except ValueError:
                if dir == 'next':
                    start_iter = model.get_iter_first()
                else:
                    start_iter = model.get_iter((len(self._playlist) - 1,))

        searchable_cols = [MODEL_TITLE, MODEL_ARTIST, MODEL_ALBUM, MODEL_TIME,
                           MODEL_YEAR]
        iter = start_iter
        found_match = False
        looped_to_beginning = False
        while iter is not None:
            for col in searchable_cols:
                data = model.get_value(iter, col)
                data = mesk.gtk_utils.unescape_pango_markup(data)
                data = unicode(data, 'utf-8').lower()
                if data.find(normalized_search) != -1:
                    found_match = True
                    # Found a match, select and display matching row
                    selection = self._pl_view.get_selection()
                    selection.unselect_all()
                    selection.select_iter(iter)
                    self.scroll_to_row(model.get_path(iter)[0], force=True)
                    # Pass focus to the playlist
                    self.set_focused()
                    self._pl_view.set_cursor(model.get_path(iter)[0])
                    break

            if found_match:
                iter = None
            else:
                if dir == 'next':
                    iter = model.iter_next(iter)
                else:
                    # Sorta lame the model does not provide iter_prev...
                    path = model.get_path(iter)
                    prev_row = path[0] - 1
                    if prev_row < 0:
                        prev_row = len(self._playlist) - 1
                    new_path = (prev_row,)
                    iter = model.get_iter(new_path)

                if iter is None and not looped_to_beginning:
                    looped_to_beginning = True
                    iter = model.get_iter_first()

        if not found_match:
            d = gtk.MessageDialog(None, gtk.DIALOG_MODAL,
                                  type=gtk.MESSAGE_ERROR,
                                  buttons=gtk.BUTTONS_CLOSE)

            d.set_markup('<big><b>%s</b></big>' % _('No match found'))
            msg = _("The string '%s' does not match any playlist entries.") % \
                  search_txt
            d.format_secondary_text(msg)
            d.run()
            d.destroy()

    def _get_last_select_row(self):
        selected_rows = self.get_selected_rows()
        if selected_rows:
            # End of the selections
            r = selected_rows[-1:][0]
        else:
            # End of the playlist
            r = len(self._playlist)
        return r

    ## Context menu handlers ##
    def _on_add_menuitem_activate(self, widget):
        uris = self._browse_for_uris()
        if not uris:
            return

        add_row = self._get_last_select_row()
        self.add_uris(uris, gtk.TREE_VIEW_DROP_AFTER, add_row)
        self._save_playlist()

    ### Clipboard and cuty/copy/paste functions ###
    def _clipboard_set_cb(self, clipboard, selection, info, op_info):
        # Convert URI objects to strings
        uris = []
        for uri in op_info.uris:
            uris.append(str(uri))

        selection.set_uris(uris)

    def _clipboard_clear_cb(self, clipboard, op_info):
        pass

    def _get_clipboard_status_msg(self, action, num_items):
        if num_items < 0:
            return ''
        if num_items == 0 or num_items > 1:
            form = _('items')
        else:
            form = _('item')
        return '%s %s %s' % (num_items, form, action)


    def _on_cut_menuitem_activate(self, widget):
        selected_rows = self.get_selected_rows()
        if not selected_rows:
            return

        self._clipboard.clear()
        info = CutCopyInfo(self._playlist, selected_rows)
        self.delete_rows(selected_rows)
        self._clipboard.set_with_data([self._targets[self.URI_LIST_TARGET_ID]],
                                      self._clipboard_set_cb,
                                      self._clipboard_clear_cb,
                                      info)

        self._set_status_msg(self._get_clipboard_status_msg(_('cut'),
                                                            len(selected_rows)))

    def _on_copy_menuitem_activate(self, widget):
        selected_rows = self.get_selected_rows()
        if not selected_rows:
            return

        self._clipboard.clear()
        info = CutCopyInfo(self._playlist, selected_rows)
        self._clipboard.set_with_data([self._targets[self.URI_LIST_TARGET_ID]],
                                      self._clipboard_set_cb,
                                      self._clipboard_clear_cb,
                                      info)

        self._set_status_msg(self._get_clipboard_status_msg(_('copied'),
                                                            len(selected_rows)))

    def _on_paste_menuitem_activate(self, widget):
        num_added = 0

        # Async callback for clipboard contents
        def clipboard_contents(cb, selection, data):
            uris = selection.get_uris()
            if not uris:
                return

            paste_row = self._get_last_select_row()
            num_added = self.add_uris(uris, gtk.TREE_VIEW_DROP_AFTER, paste_row)
            self._save_playlist()

        self._clipboard.request_contents(
            self._targets[self.URI_LIST_TARGET_ID][0], clipboard_contents)

        self._set_status_msg(self._get_clipboard_status_msg(_('pasted'),
                                                            num_added))

    def _on_remove_menuitem_activate(self, widget):
        self.delete_rows()

    def _on_queue_menuitem_activate(self, widget):
        self.queue_selected_rows()
    def _on_queue_front_menuitem_activate(self, widget):
        self.queue_selected_rows(position=0, replace=True)
    def _on_queue_clear_menuitem_activate(self, widget):
        self.clear_queue()

    def _on_export_menuitem_activate(self, widget):
        import playlist_export
        dialog = playlist_export.PlaylistExportDialog(self._playlist)

        status = dialog.show()

    def _set_status_msg(self, msg, delay=5000):
        self._status_bar.push_status_msg(msg)
        self._status_bar.pop_status_msg(msg, delay)

### TreeViewColumn types ###
class StatusColumn(gtk.TreeViewColumn):

    def __init__(self):
        gtk.TreeViewColumn.__init__(self, ' ' * 3)

        self._img_renderer = gtk.CellRendererPixbuf()
        self._img_renderer.set_property('stock-size', gtk.ICON_SIZE_MENU)

        self.txt_renderer = gtk.CellRendererText()
        # Make text font slightly smaller
        font = mesk.gtk_utils.get_default_font()
        font_desc = pango.FontDescription(font)
        # 1024 pango units per device unit, subtract N points
        font_desc.set_size(font_desc.get_size() - (3 * 1024))
        self.txt_renderer.set_property('font-desc', font_desc)
        self.txt_renderer.set_property('foreground', 'blue')

        self.pack_start(self._img_renderer, False)
        self.pack_start(self.txt_renderer, False)

        self.set_resizable(False)
        self.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
        self.set_reorderable(False)

        self.add_attribute(self._img_renderer, 'stock-id', MODEL_STATUS_IMG)
        self.add_attribute(self.txt_renderer, 'markup', MODEL_STATUS_TEXT)

class TextColumn(gtk.TreeViewColumn):

    def __init__(self, title, expand=True):
        gtk.TreeViewColumn.__init__(self, title)

        self.txt_renderer = gtk.CellRendererText()
        # Make text font slightly smaller
        font = mesk.gtk_utils.get_default_font()
        font_desc = pango.FontDescription(font)
        # 1024 pango units per device unit, subtract 2 points
        font_desc.set_size(font_desc.get_size() - (2 * 1024))
        self.txt_renderer.set_property('font-desc', font_desc)
        self.txt_renderer.set_property('ellipsize', pango.ELLIPSIZE_END)

        self.pack_start(self.txt_renderer, True)
        self.set_resizable(True)
        self.set_reorderable(True)
        self.set_property('expand', expand)

### Utils ###
class CutCopyInfo:
    def __init__(self, playlist, rows):
        self.rows = rows
        self.uris = []
        for i in rows:
            self.uris.append(playlist[i].uri)

### Dialogs ###
class PlaylistPropertiesDialog(gobject.GObject):
    def __init__(self, playlist=None):
        gobject.GObject.__init__(self)

        # Properties
        self.name = ''
        self.annotation = ''
        self.read_only = False
        if playlist is not None:
            self.name = playlist.name
            self.annotation = playlist.annotation
            self.read_only = playlist.read_only
        self.playlist = playlist

        # Get glade xml and hookup signals
        xml = mesk.gtk_utils.get_glade('playlist_props_dialog',
                                       'playlist.glade')
        xml.signal_autoconnect(self)
        self.dialog = xml.get_widget('playlist_props_dialog')

        if playlist is None:
            xml.get_widget('playlist_extra_expander').hide()

        self.ok_button = xml.get_widget('okbutton')


        self.name_entry = xml.get_widget('playlist_name_entry')
        self.name_entry.set_text(self.name)

        self.annotation_textview = \
            xml.get_widget('playlist_annotation_textview')
        self.annotation_textview.get_buffer().set_text(self.annotation)

        xml.get_widget('read_only_checkbutton').set_active(self.read_only)
        self._update_read_only_state()

    def run(self):
        '''Runs the dialog and returns the response'''
        resp = self.dialog.run()

        if resp == gtk.RESPONSE_OK:
            # Capture props
            self.name = self.name_entry.get_text()
            start = self.annotation_textview.get_buffer().get_start_iter()
            end = self.annotation_textview.get_buffer().get_end_iter()
            self.annotation = \
                self.annotation_textview.get_buffer().get_text(start, end)
        else:
            self.name = None
            self.annotation = None

        self.dialog.destroy()
        return resp

    def _on_playlist_name_entry_changed(self, entry):
        name = entry.get_text()
        if not name:
            # Must have a name
            self.ok_button.set_sensitive(False)
        elif (self.playlist is not None) and name == self.playlist.name:
            # The is allowed not to change
            self.ok_button.set_sensitive(True)
        elif name not in config.get_all_playlist_names():
            # The name is unique
            self.ok_button.set_sensitive(True)
        else:
            self.ok_button.set_sensitive(False)

    def _on_read_only_checkbutton_toggled(self, checkbutton):
        self.read_only = checkbutton.get_active()
        self._update_read_only_state()

    def _update_read_only_state(self):
        if self.name == mesk.DEFAULT_PLAYLIST_NAME or self.read_only:
            self.name_entry.set_sensitive(False)
        else:
            self.name_entry.set_sensitive(True)
            self.name_entry.select_region(0, -1)

        if self.read_only:
            self.annotation_textview.set_sensitive(False)
        else:
            self.annotation_textview.set_sensitive(True)

