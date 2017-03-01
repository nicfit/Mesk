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
import gtk, gtk.glade

import mesk
import mesk.plugin
import mesk.gtk_utils
import mesk.window
from mesk.i18n import _

import config
from control import EmptyControl
from audio_control import AudioControl
from about_dialog import AboutDialog
from playlist_control import PlaylistControl, PlaylistPropertiesDialog
from album_cover_control import AlbumCoverControl
from preference_window import PreferenceWindow
from dialogs import ErrorDialog, ConfirmationWithDisableOptionDialog
from status_bar import StatusBar

import devices
if mesk.info.DISABLE_CDROM_SUPPORT or mesk.info.DISABLE_DBUS_SUPPORT:
    class CDROMControl:
        pass  # A stub for type checks
else:
    from cdrom_control import CDROMControl

class MainWindow(mesk.window.Window):

    def __init__(self, profile):
        self.profile = profile
        self._is_compact = False
        self._controls = []

        mesk.window.Window.__init__(self, 'main_window', 'main_window.glade')
        self.window.connect('key-press-event',
                            self._on_window_key_press_event)
        self.window.connect('focus-in-event', self._on_window_focus_in_event)

        self._notebook = self.xml.get_widget('notebook')
        # Remove all glade pages from notebook
        while self._notebook.get_n_pages():
            self._notebook.remove_page(0)
        self._notebook.set_show_tabs(True)

        self._status_bar = StatusBar(self.xml)
        self._marquee_label = self.xml.get_widget('marquee_label')

        self._audio_control = AudioControl(self.xml, self.window)
        self._audio_control.connect('source-changed',
                                    self._on_audio_source_changed)
        self._audio_control.connect('tag-update',
                                    self._on_audio_source_tag_update)

        if not mesk.info.DISABLE_DBUS_SUPPORT:
            # Initialize Dbus service
            import dbus, dbus_service
            service_name = dbus_service.get_service_name(self.profile)
            bus_name = dbus.service.BusName(service_name, bus=dbus.SessionBus())
            self.mesk_dbus = dbus_service.MeskDbusService(bus_name,
                                                          self.profile,
                                                          self)
            mesk.log.verbose("DBus service activated")
        else:
            self.mesk_dbus = None
            mesk.log.info('DBus disabled')

        self._album_cover_control = AlbumCoverControl(self.xml,
                                                      self._audio_control)

        # Status tray icon
        try:
            # tray support requires gtk >= 2.10
            import status_icon
            self.status_icon = status_icon.StatusIcon(self, self._audio_control)
        except AttributeError:
            mesk.log.info('Status tray support disabled, upgrade to Gtk+ 2.10 '
                          'for support.')
            self.status_icon = None

        # The active control is the one that has ownership of the AudioControl
        self._active_control = None
        self._empty_control = EmptyControl()

        # Load active playlists
        playlists = mesk.config.getlist(mesk.CONFIG_MAIN, 'playlists')
        active = mesk.config.get(mesk.CONFIG_MAIN, 'active_playlist')
        for pl_name in playlists:
            self.add_control(PlaylistControl, pl_name,
                             set_active=(active==pl_name))

        if self._notebook.get_n_pages() == 0:
            # Add a placeholder when there is nothing else to display
            self.add_notebook_control(self._empty_control)
            self._empty_control.widget.show()
            self._notebook.set_show_tabs(False)
        elif not self._active_control:
            self.set_active_control(self._controls[0])

        # Show active control
        if self._active_control:
            page_num = self._notebook.page_num(self._active_control.widget)
            self._notebook.set_current_page(page_num)

        self._pref_window = None
        self._logs_window = None

        # Register for device changes
        devices.get_mgr().connect('media-changed', self._media_changed)

        # Initialize plugins
        mesk.plugin.set_manager(mesk.plugin.PluginMgr())

    def add_control(self, clazz, name, set_active=False):
        status_msg = _('Loading playlist \'%s\'...') % name
        self._status_bar.push_status_msg(status_msg)
        mesk.log.verbose(status_msg)

        ctrl = None
        try:
            ctrl = clazz(name, self._status_bar)
        except mesk.MeskException, ex:
            if ex.primary_msg:
                d = ErrorDialog(self.window,
                                markup='<b>%s</b>' % ex.primary_msg,
                                secondary_txt=ex.secondary_msg)
                d.run()
                d.destroy()
        except Exception, ex:
            import traceback
            d = ErrorDialog(self.window)
            d.set_markup("<b>%s</b>" % (_("Error loading '%s'") % name))
            d.format_secondary_text('%s\n%s' % (str(ex),
                                                traceback.format_exc()))
            d.run()
            d.destroy()
        else:
            if isinstance(ctrl, PlaylistControl):
                ctrl.connect('playlist_changed', self._on_playlist_ctrl_changed)
            ctrl.connect('control_request_active',
                         self._on_control_request_active)
            ctrl.connect('control_request_close',
                         self._on_control_request_close)

            self.add_notebook_control(ctrl)
            if set_active or self._notebook.get_n_pages() == 1:
                self.set_active_control(ctrl)

        self._status_bar.pop_status_msg(status_msg)
        status_msg = _('\'%s\' loaded') % name
        self._status_bar.push_status_msg(status_msg)
        self._status_bar.pop_status_msg(status_msg, delay=1500)

        return ctrl

    def _on_playlist_ctrl_changed(self, ctrl):
        if ctrl == self._active_control:
            if not len(ctrl.get_playlist()):
                # Playlist is empty, current display
                self._update_current_display(None)

    def _on_control_request_close(self, ctrl):
        self.remove_notebook_control(ctrl)

    def _on_control_request_active(self, ctrl):
        # A control is requesting the AudioControl.  Grant it.
        self.set_active_control(ctrl)

    def set_active_control(self, ctrl):
        if ctrl == self._active_control:
            return

        # Clear state
        self._update_current_display(None)

        self._audio_control.stop()

        # If we have an active control, tell it is no longer active
        if self._active_control:
            self._active_control.set_active(False, None)

        self._active_control = ctrl
        if self._active_control:
            pl = self._active_control.get_playlist()
            self._audio_control.set_playlist(pl)
            self._active_control.set_active(True, self._audio_control)
        else:
            self._audio_control.set_playlist(None)

    def add_notebook_control(self, ctrl):
        new_index = self._notebook.append_page(ctrl.widget, ctrl.tab_widget)
        self._notebook.set_current_page(new_index)

        if ctrl != self._empty_control:
            self._notebook.set_show_tabs(True)
            # Handle tab close button if it is to be displayed, otherwise hide
            # it
            close_button = \
                ctrl.tab_widget.get_children()[0].get_children()[2]
            if mesk.config.getboolean(mesk.CONFIG_UI, 'show_tab_close_button'):
                close_button.connect('clicked',
                                     self._on_tab_close_button_clicked, ctrl)
            else:
                close_button.hide()

            # Remove placeholder control
            page_num = self._notebook.page_num(self._empty_control.widget)
            if page_num >= 0:
                self._notebook.remove_page(page_num)
        else:
            self._notebook.set_show_tabs(False)

        # This list order does not necessarily correspond to the tab order
        self._controls.append(ctrl)
        self._uptate_open_menus()

        self._notebook.set_tab_reorderable(ctrl.widget, True)

    def remove_notebook_control(self, ctrl):
        page_num = self._notebook.page_num(ctrl.widget)
        new_active = False

        # Transition active tab if necessary
        if ctrl == self._active_control:
            new_active = True
            ctrl.set_active(False)

        # Remove
        self._controls.remove(ctrl)
        self._notebook.remove_page(page_num)

        # Set the new active control
        if new_active and self._notebook.get_n_pages():
            page = self._notebook.get_current_page()
            page = self._notebook.get_nth_page(page)
            ctrl = self.get_control_by_widget(page)
            self.set_active_control(ctrl)

        self._uptate_open_menus()

        # Add special widget for whenever there are none
        if self._notebook.get_n_pages() == 0:
            self.add_notebook_control(self._empty_control)
            self.set_active_control(None)
        elif self._notebook.get_n_pages() < 2:
            # Disable DnD when num tabs < 2
            self._notebook.drag_dest_unset()

    def get_control_by_widget(self, widget):
        for ctrl in self._controls:
            if ctrl.widget == widget:
                return ctrl
        return None

    def get_controls_by_type(self, t, accept_base_type=False):
        controls = []
        for ctrl in self._controls:
            if (accept_base_type and isinstance(ctrl, t)) or type(ctrl) is t:
                controls.append(ctrl)
        return controls

    def get_focused_control(self):
        curr = self._notebook.get_current_page()
        page_widget = self._notebook.get_nth_page(curr)
        return self.get_control_by_widget(page_widget)

    def _on_window_focus_in_event(self, window, event):
        control = self.get_focused_control()
        control and control.set_focused()

    def _on_notebook_switch_page(self, notebook, page, page_num):
        page = self._notebook.get_nth_page(page_num)
        ctrl = self.get_control_by_widget(page)
        if ctrl:
            ctrl.set_focused()

    def _on_tab_close_button_clicked(self, widget, ctrl):
        self.remove_notebook_control(ctrl)

    def show(self):
        if not hasattr(self, "_first_show"):
            self._first_show = False
            compact = mesk.config.getboolean(mesk.CONFIG_UI, 'compact_state')
            self.xml.get_widget('compact_menuitem').set_active(compact)
            self.set_compact_mode(compact)
        self._restore_window_attrs()
        mesk.window.Window.show(self)

    def quit(self, prompt=mesk.config.getboolean(mesk.CONFIG_MAIN,
                                                 'confirm_quit')):
        if prompt:
            # Confirm the quit
            d = ConfirmationWithDisableOptionDialog(self.window)
            d.set_markup('<b>%s</b>' % _('Are you sure you want to quit?'))
            (confirmed, disable_prompt) = d.confirm()
            if not confirmed:
                return False
            mesk.config.set(mesk.CONFIG_MAIN, 'confirm_quit',
                            str(not disable_prompt))

        self.window.hide()

        # Cleanup hidden windows
        if self._pref_window:
            self._pref_window.window.destroy()

        # Shutdown plugins
        mesk.plugin.shutdown()

        # Shutdown device manager and monitoring
        devices.get_mgr().shutdown()

        # Shutdown all controls
        playlists = []
        for i in range(self._notebook.get_n_pages()):
            # Notebook order traversal for saving state
            ctrl = self.get_control_by_widget(self._notebook.get_nth_page(i))
            if ctrl.is_playlist_saved():
                playlists.append(ctrl.name)
            ctrl.shutdown()

        # Remember open playlists
        mesk.config.set(mesk.CONFIG_MAIN, 'playlists', playlists)
        active_playlist = ''
        if self._active_control and self._active_control.get_playlist():
            active_playlist = self._active_control.name
        mesk.config.set(mesk.CONFIG_MAIN, 'active_playlist', active_playlist)

        # Exit the gtk event loop
        try:
            gtk.main_quit()
        except RuntimeError:
            # This has already happened
            pass

        return True

    def _restore_window_attrs(self):
        if not self._is_compact:
            x = mesk.config.getint(mesk.CONFIG_UI, 'main_window_pos_x')
            y = mesk.config.getint(mesk.CONFIG_UI, 'main_window_pos_y')
            self.window.move(x, y)
            mesk.log.debug('_restore_window_attrs pos (%d,%d)' % (x, y))

            width = mesk.config.getint(mesk.CONFIG_UI, 'main_window_width')
            height = mesk.config.getint(mesk.CONFIG_UI, 'main_window_height')
            self.window.resize(width, height)
            mesk.log.debug('_restore_window_attrs size %dx%d' % (width, height))
        else:
            # Restore compact window position
            x = mesk.config.getint(mesk.CONFIG_UI, 'compact_main_window_pos_x')
            y = mesk.config.getint(mesk.CONFIG_UI, 'compact_main_window_pos_y')
            self.window.move(x, y)
            mesk.log.debug('_restore_window_attrs (compact) pos (%d,%d)' %
                           (x, y))

    def _on_window_configure_event(self, win, event):
        mesk.window.Window._on_window_configure_event(self, win, event)
        (width, height) = self._window_size
        (x, y) = self._window_pos

        if not self._is_compact:
            mesk.config.set(mesk.CONFIG_UI, 'main_window_width', str(width))
            mesk.config.set(mesk.CONFIG_UI, 'main_window_height', str(height))
            mesk.config.set(mesk.CONFIG_UI, 'main_window_pos_x', str(x))
            mesk.config.set(mesk.CONFIG_UI, 'main_window_pos_y', str(y))
            mesk.log.debug('window attrs: pos (MAIN) (%d,%d)' % (x, y))
            mesk.log.debug('window attrs: size (MAIN) %dx%d' % (width,
                                                                     height))
        else:
            mesk.config.set(mesk.CONFIG_UI, 'compact_main_window_pos_x', str(x))
            mesk.config.set(mesk.CONFIG_UI, 'compact_main_window_pos_y', str(y))
            mesk.log.debug('window attrs: pos (COMPACT) (%d,%d)' % (x, y))

    def _on_window_delete_event(self, widget, event):
        '''Overridden from mesk.window.Window'''
        if mesk.config.getboolean(mesk.CONFIG_UI, 'window_hide_on_close'):
            self.window.hide()
            return True
        else:
            if not self.quit():
                return True
            else:
                # Return yes, you may delete me
                return False

    def set_compact_mode(self, state):
        if self._is_compact == state:
            return

        mesk.config.set(mesk.CONFIG_UI, 'compact_state', str(state))
        if state:
            self._notebook.hide()
            self._status_bar.hide()

            # Size window for compact view
            (curr_width, curr_height) = self.window.get_size()
            (pref_width, pref_height) = self.window.size_request()
            self.window.resize(curr_width, pref_height)
            self.window.set_resizable(False)
        else:
            self.window.set_resizable(True)
            self._notebook.show()
            self._status_bar.show()

        self._is_compact = state
        self._restore_window_attrs()

    def display_current_playlist(self):
        if self._active_control and isinstance(self._active_control,
                                               PlaylistControl):
            self._active_control.scroll_to_current()
            if self._active_control != self.get_focused_control():
                num = self._notebook.page_num(self._active_control.widget)
                self._notebook.set_current_page(num)

    ### Menu callbacks ###
    def _on_quit_menuitem_activate(self, widget):
        self.quit()

    def _on_preferences_menuitem_activate(self, widget):
        if self._pref_window is None:
            self._pref_window = PreferenceWindow()
            self._pref_window.window.set_transient_for(self.window)
        self._pref_window.present()

    def _on_view_menu_activate(self, widget):
        plugins_menu = self.xml.get_widget('plugins_view_menu')
        from mesk.plugin.interfaces import ViewMenuProvider
        menuitems = mesk.plugin.get_menuitems(ViewMenuProvider)
        if not menuitems:
            plugins_menu.hide()
        else:
            plugins_menu.show()
            submenu = gtk.Menu()
            plugins_menu.set_submenu(submenu)
            for item in menuitems:
                item.show()
                submenu.append(item)
            submenu.show()

    def _on_compact_menuitem_activate(self, widget):
        self.set_compact_mode(widget.get_active())

    def _on_jump_to_current_menuitem_activate(self, widget):
        self.display_current_playlist()

    def _on_logs_menuitem_activate(self, widget):
        if self._logs_window is None:
            import log_window
            self._logs_window = log_window.LogWindow()
            # Associate log handler with window textview
            for h in mesk.log.getLogger().handlers:
                if isinstance(h, mesk.log.TextBufferLogHandler):
                    buff = self._logs_window.log_textview.get_buffer()
                    h.set_text_buffer(buff)
                    break
        self._logs_window.show()

    def _on_about_menuitem_activate(self, widget):
        self.about_dialog = AboutDialog()
        self.about_dialog.dialog.set_transient_for(self.window)
        self.about_dialog.dialog.run()
        self.about_dialog.dialog.destroy()

    def _on_online_help_menuitem_activate(self, widget):
        mesk.utils.load_web_page('http://mesk.nicfit.net/')

    def _on_window_key_press_event(self, window, event):
        mesk.log.debug('Window key-press: %s' % str(event))

        # Control bindings
        if event.state & gtk.gdk.CONTROL_MASK:
            # CTRL+w: Close tab
            if (event.keyval == gtk.keysyms.w):
                self.remove_notebook_control(self.get_focused_control())
                return True
        # Alt bindings
        elif event.state & gtk.gdk.MOD1_MASK:
            # Alt+Right: Move right one tab
            if event.keyval == gtk.keysyms.Right:
                new = self._notebook.get_current_page() + 1
                if new >= self._notebook.get_n_pages():
                    new = 0
                self._notebook.set_current_page(new)
                return True
            # Alt+Left: Move left one tab
            elif event.keyval == gtk.keysyms.Left:
                new = self._notebook.get_current_page() - 1
                if new < 0:
                    new = self._notebook.get_n_pages() - 1
                self._notebook.set_current_page(new)
                return True

        return False

    def _on_audio_source_changed(self, audio_control, old, new):
        self._update_current_display(new[1])

    def _update_current_display(self, src):
        if src is None:
            self._marquee_label.set_markup('')
            self.window.set_title('Mesk')
            self._album_cover_control.clear()
            return

        title = src.meta_data.title
        artist = src.meta_data.artist
        album = src.meta_data.album
        year = src.meta_data.year

        marquee = ''
        if title:
            marquee += u'<span weight="bold">%s</span>' % \
                        mesk.gtk_utils.escape_pango_markup(title)
        if artist or album:
            marquee += '\n'
            if artist:
                marquee += u'%s' % mesk.gtk_utils.escape_pango_markup(artist)
            if album:
                #if artist:
                #    marquee += ' - '
                marquee += u'\n<i>%s</i>' % \
                            mesk.gtk_utils.escape_pango_markup(album)
                if year:
                    marquee += u' (%d)' % int(year)
        self._marquee_label.set_markup(marquee)

        # Update window title
        win_title = ''
        if artist and title:
            win_title = '%s - %s' % (artist, title)
        elif artist:
            win_title = artist
        elif title:
            win_title = title

        if win_title:
            win_title += ' - Mesk'
        else:
            win_title = 'Mesk'
        self.window.set_title(win_title)

    def _on_audio_source_tag_update(self, ctrl, src):
        self._update_current_display(src)

    def _uptate_open_menus(self):
        open_pl_menu = self.xml.get_widget('open_playlist_menuitem')
        pl_menu = open_pl_menu.get_submenu()
        open_device_menu = self.xml.get_widget('open_device_menuitem')
        device_menu = open_device_menu.get_submenu()

        # Clear open menus
        for menu in [pl_menu, device_menu]:
            for child in menu.get_children():
                menu.remove(child)

        # What controls are currently being shown
        shown_ctrls = set()
        for c in self._controls:
            if isinstance(c, CDROMControl):
                shown_ctrls.add(c.hal_udi)
            elif isinstance(c, PlaylistControl):
                shown_ctrls.add(c.name)

        # Add new playlist entries
        playlists = set(config.get_all_playlist_names())
        playlists = list(playlists.difference(shown_ctrls))
        if playlists:
            open_pl_menu.set_sensitive(True)
            playlists.sort()
            for pl in playlists:
                item = gtk.MenuItem(pl, use_underline=False)
                pl_menu.append(item)
                item.connect('activate',
                             self._on_playlist_open_menuitem_activate)
                item.show()
        else:
            open_pl_menu.set_sensitive(False)

        # Add new device entries for optical drives
        device_mgr = devices.get_mgr()
        cdroms = device_mgr.get_optical_devices()
        cd_devices = set(cdroms.keys())
        cd_devices = list(cd_devices.difference(shown_ctrls))
        if cd_devices:
            open_device_menu.set_sensitive(True)
            cd_devices.sort()
            for dev_udi in cd_devices:
                lbl = device_mgr.get_device_display_name(cdroms[dev_udi])
                item = gtk.ImageMenuItem(lbl)
                img = gtk.image_new_from_stock(gtk.STOCK_CDROM,
                                               gtk.ICON_SIZE_MENU)
                item.set_image(img)
                device_menu.append(item)
                item.connect('activate',
                             self._on_device_open_menuitem_activate,
                             dev_udi)
                item.show()
        else:
            open_device_menu.set_sensitive(False)

    def _on_device_open_menuitem_activate(self, widget, device_udi):
        c = self.add_control(CDROMControl, device_udi)

    # Callback for opening an existing playlist
    def _on_playlist_open_menuitem_activate(self, widget):
        pl_name = widget.get_children()[0].get_text()
        self.add_control(PlaylistControl, pl_name)

    # Callback for creating a new playlist
    def _on_playlist_new_menuitem_activate(self, widget):
        # Get a name via a dialog
        props_dialog = PlaylistPropertiesDialog()
        resp = props_dialog.run()
        if resp != gtk.RESPONSE_OK:
            return

        self.add_control(PlaylistControl, props_dialog.name)

    def _find_page_num_by_tab_label(self, tab_label):
        '''Find the page num of the tab label'''
        page_num = -1
        for i in xrange(self._notebook.get_n_pages()):
            page = self._notebook.get_nth_page(i)
            tab = self._notebook.get_tab_label(page)
            if tab == tab_label:
                page_num = i
                break
        return page_num


    def _get_tab_at_xy(self, x, y):
        '''Thanks to Gaim
        Return the tab under xy and
        if its nearer from left or right side of the tab
        '''
        page_num = -1
        to_right = False
        horiz = self._notebook.get_tab_pos() == gtk.POS_TOP or \
                self._notebook.get_tab_pos() == gtk.POS_BOTTOM
        for i in xrange(self._notebook.get_n_pages()):
            page = self._notebook.get_nth_page(i)
            tab = self._notebook.get_tab_label(page)
            tab_alloc = tab.get_allocation()
            if horiz:
                if (x >= tab_alloc.x and
                    (x <= (tab_alloc.x + tab_alloc.width))):
                    page_num = i
                    if x >= tab_alloc.x + (tab_alloc.width / 2.0):
                        to_right = True
                    break
            else:
                if (y >= tab_alloc.y and
                    (y <= (tab_alloc.y + tab_alloc.height))):
                    page_num = i

                    if y > tab_alloc.y + (tab_alloc.height / 2.0):
                        to_right = True
                    break
        return (page_num, to_right)

    def _media_changed(self, mgr, device):
        block_device = device.dev.GetProperty('block.device')
        status = devices.cdrom_disc_status(block_device)
        mesk.log.debug("MainWindow._media_changed: device=%s, status=%d" %
                       (block_device, status))

        if (status == devices.CD_STATUS_AUDIO and
            mesk.config.getboolean(mesk.CONFIG_UI, 'auto_open_devices')):
            # Autopen CD if not already open
            do_open = True
            for c in self._controls:
                if isinstance(c, CDROMControl) and device == c.device:
                    do_open = False
                    break
            if do_open:
                mesk.log.debug("Auto-adding CDROMControl %s" % block_device)
                self.add_control(CDROMControl, device.udi)
        elif status != devices.CD_STATUS_AUDIO:
            # Remove CD control if it exists
            for c in self._controls:
                if isinstance(c, CDROMControl) and device == c.device:
                    mesk.log.debug("Removing CDROMControl %s" % block_device)
                    self.remove_notebook_control(c)
                    break
