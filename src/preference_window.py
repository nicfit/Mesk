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
import gobject, gtk, gtk.glade

import mesk
from mesk.i18n import _
from mesk.plugin import PluginMgr
import mesk.window

from dialogs import ErrorDialog

class PreferenceWindow(mesk.window.Window):
    LIBRARY_TAB = 0
    PLUGINS_TAB = 1

    def __init__(self):
        mesk.window.Window.__init__(self, 'preference_window',
                                    'preference_window.glade')
        self.prefs_notebook = self.xml.get_widget('pref_notebook')

        self._plugins_prefs = PluginPrefs(self.xml, self.window)
        self._library_prefs = LibraryPrefs(self.xml, self.window)

    def _on_close_button_clicked(self, button):
        self.hide()
## end PreferenceWindow

class LibraryPrefs(object):
    def __init__(self, glade_xml, window):
        self.xml = glade_xml
        self.window = window
        self.xml.signal_autoconnect(self)

        self.xml.get_widget('remove_libdir_button').set_sensitive(False)
        self._last_lib_add_dir = None
        self.xml.get_widget('remove_excludedir_button').set_sensitive(False)
        self._last_lib_exclude_dir = None

        self.MODEL_PATH = 0
        def init_path_view(view_name, col_title, dirs):
            model = gtk.ListStore(str)

            view = self.xml.get_widget(view_name)
            view.set_model(model)

            col = gtk.TreeViewColumn(col_title)
            txt_renderer = gtk.CellRendererText()
            col.pack_start(txt_renderer, True)
            col.add_attribute(txt_renderer, 'text', self.MODEL_PATH)
            view.append_column(col)

            # Populate paths
            for d in dirs:
                model.append([d])

            return view

        self.libdir_view = init_path_view('libdirs_treeview',
                                          _('Library Paths'),
                                          mesk.database.db.get_lib_dirs())
        self.excludedir_view = \
                init_path_view('excludedirs_treeview',
                               _('Exclude Paths'),
                               mesk.database.db.get_lib_exclude_dirs())

        self.sync_button = self.xml.get_widget('sync_button')
        have_one_dir = self.libdir_view.get_model().get_iter_first() is not None
        self.sync_button.set_sensitive(have_one_dir)

        self.sync_stop_button = self.xml.get_widget('sync_stop_button')
        self.sync_stop_button.set_sensitive(False)

        self.sync_progressbar = self.xml.get_widget('sync_progressbar')
        self.sync_status_label = self.xml.get_widget('sync_status_label')

    def _save_dir_state(self):
        # Lib dirs
        inc_dirs = []
        model = self.libdir_view.get_model()
        for row in model:
            inc_dirs.append(row[self.MODEL_PATH])
        mesk.database.db.set_lib_dirs(inc_dirs)

        self.sync_button.set_sensitive(model.get_iter_first() is not None)

        # Exclude dirs
        exc_dirs = []
        model = self.excludedir_view.get_model()
        for row in model:
            exc_dirs.append(row[self.MODEL_PATH])
        mesk.database.db.set_lib_exclude_dirs(exc_dirs)


    def _on_add_libdir_button_clicked(self, button):
        dir = self._add_path_helper(self._last_lib_add_dir or "$HOME",
                                    self.libdir_view.get_model())
        self._last_lib_add_dir = (dir or self._last_lib_add_dir)
    def _on_add_excludedir_button_clicked(self, button):
        dir = self._add_path_helper(self._last_lib_exclude_dir or "$HOME",
                                    self.excludedir_view.get_model())
        self._last_lib_exclude_dir = (dir or self._last_lib_exclude_dir)

    def _add_path_helper(self, start_dir, model):
        parent_dir = None

        d = gtk.FileChooserDialog(title=_('Select Directory'),
                                  parent=self.window,
                                  action=gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
                                  buttons=(gtk.STOCK_CANCEL,
                                           gtk.RESPONSE_CANCEL,
                                           gtk.STOCK_ADD, gtk.RESPONSE_OK))
        d.set_select_multiple(True)
        d.set_current_folder(os.path.expandvars(start_dir))
        resp = d.run()
        if resp == gtk.RESPONSE_OK:
            # Note, these URIs should already be escaped
            for uri in [mesk.uri.make_uri(u) for u in d.get_uris()]:
                path = mesk.uri.unescape(uri.path)
                model.append([path])
                if parent_dir is None:
                    parent_dir = path
                else:
                    # Multiple selections from within a dir
                    parent_dir = os.path.dirname(path)
            self._save_dir_state()

        d.destroy()
        return parent_dir

    def _on_remove_libdir_button_clicked(self, button):
        self._remove_path_helper(self.libdir_view)
    def _on_remove_excludedir_button_clicked(self, button):
        self._remove_path_helper(self.excludedir_view)

    def _remove_path_helper(self, view):
        if view.get_cursor()[0] is None:
            return

        row = view.get_cursor()[0][0]
        if row >= 0:
            model = view.get_model()
            model.remove(model.get_iter(row))
            self._save_dir_state()

    def _on_path_treeview_cursor_changed(self, treeview):
        row = treeview.get_cursor()[0][0]
        if row >= 0:
            if treeview == self.libdir_view:
                button = 'remove_libdir_button'
            else:
                button = 'remove_excludedir_button'
            self.xml.get_widget(button).set_sensitive(True)

    def _update_sync_progress(self, dir_path, total_count):
        self.sync_status_label.set_text(_('Scanning %s') % dir_path)
        self.sync_progressbar.set_text(_('%d of %d directories scanned') %
                                       (self._dir_count, total_count))
        percent = float(self._dir_count) / float(total_count)
        self.sync_progressbar.set_fraction(percent)

    def _complete_sync_progress(self, completed):
        if completed:
            self.sync_status_label.set_text('')
            self.sync_progressbar.set_fraction(1.0)

        self.sync_stop_button.set_sensitive(False)
        self.sync_button.set_sensitive(True)

    def _on_sync_button_clicked(self, button):
        self._dir_count = 0
        self.sync_button.set_sensitive(False)
        self.sync_stop_button.set_sensitive(True)
        self.sync_progressbar.set_fraction(0.0)
        self.sync_progressbar.set_text(_('Scanning directories ...'))
        mesk.gtk_utils.update_pending_events()

        # Note, these callbacks happen on the sync thread, not gtk
        def progress_cb(dir_path, dir_total):
            '''Called back for each file sync'd'''
            self._dir_count += 1
            gobject.idle_add(lambda: self._update_sync_progress(dir_path,
                                                                dir_total))
        def status_cb(status):
            '''Called back when the sync is canceled or complete'''
            completed = (status == mesk.utils.DirScannerThread.STATUS_COMPLETE)
            gobject.idle_add(lambda: self._complete_sync_progress(completed))

        mesk.database.db.sync(status_cb, progress_cb)

    def _on_sync_stop_button_clicked(self, button):
        mesk.database.db.sync_stop()

## end LibraryPrefs

class PluginPrefs(object):
    def __init__(self, glade_xml, window):
        self.xml = glade_xml
        self.xml.signal_autoconnect(self)
        self.window = window

        self._plugins = list(mesk.plugin.get_manager().get_all_plugins())
        self._plugins.sort(cmp=lambda x,y: cmp(x['DISPLAY_NAME'],
                                               y['DISPLAY_NAME']))
        if not self._plugins:
           # No plugins to show.
           self.prefs_notebook.remove_page(self.PLUGINS_TAB)
           return

        self.plugins_notebook = self.xml.get_widget('plugins_notebook')
        self.plugins_notebook.set_show_tabs(False)
        self.plugin_config_container = self.xml.get_widget('plugin_config_vbox')

        # Plugin info widgets
        self._name_label = self.xml.get_widget('name_label')
        self._desc_label = self.xml.get_widget('description_label')
        self._author_label = self.xml.get_widget('author_label')
        self._copyright_label = self.xml.get_widget('copyright_label')
        self._plugin_image = self.xml.get_widget('plugin_image')
        self._config_button = self.xml.get_widget('plugin_config_button')
        self._config_button.set_sensitive(False)

        self._url_linkbutton = gtk.LinkButton('')
        from mesk.gtk_utils import default_linkbutton_callback
        self._url_linkbutton.connect('clicked', default_linkbutton_callback)

        # Create plugins list and model
        (self.MODEL_ENABLED,
         self.MODEL_NAME) = range(2)
        plugins_model = gtk.ListStore(int, # Enabled
                                      str, # Plugin name
                                     )

        plugins_view = self.xml.get_widget('plugins_treeview')
        plugins_view.set_model(plugins_model)

        col = gtk.TreeViewColumn(_('Plugin'))
        txt_renderer = gtk.CellRendererText()
        col.pack_start(txt_renderer, True)
        col.add_attribute(txt_renderer, 'text', 1)
        plugins_view.append_column(col)

        col = gtk.TreeViewColumn(_('Enabled'))
        toggle_renderer = gtk.CellRendererToggle()
        toggle_renderer.set_property('activatable', True)
        toggle_renderer.connect('toggled', self._on_plugin_toggled,
                                plugins_model)
        col.pack_start(toggle_renderer, True)
        col.add_attribute(toggle_renderer, 'active', 0)
        plugins_view.append_column(col)

        # Populate plugins list
        active_plugins = mesk.plugin.get_manager().get_active_plugins()
        active_names = []
        for plugin in active_plugins:
            active_names.append(plugin.name)

        for plugin in self._plugins:
            plugins_model.append([plugin['NAME'] in active_names,
                                  plugin['DISPLAY_NAME']])
            # Create a Pixbuf from the xpm data
            pixbuf = gtk.gdk.pixbuf_new_from_xpm_data(plugin['XPM'])
            plugin['PIXBUF'] = pixbuf
            # Save some memory
            plugin['XPM'] = ''

        plugins_view.set_cursor(0)
        self._plugins_view = plugins_view

    def _on_plugins_treeview_cursor_changed(self, treeview):
        # Update info panel for the selected plugin
        row = treeview.get_cursor()[0][0]
        plugin = self._plugins[row]

        # Update plugin info
        self._name_label.set_markup('<big><b>%s</b></big>' %
                                    plugin['DISPLAY_NAME'])
        self._plugin_image.set_from_pixbuf(plugin['PIXBUF'])
        self._desc_label.set_text(plugin['DESCRIPTION'])
        self._author_label.set_text(plugin['AUTHOR'])
        self._copyright_label.set_text(plugin['COPYRIGHT'])

        self._url_linkbutton.set_label(plugin['URL'])
        self._url_linkbutton.set_uri(plugin['URL'])

        # Show/hide configure button
        is_active = treeview.get_model()[row][self.MODEL_ENABLED]
        mgr = mesk.plugin.get_manager()
        selected_plugin = self._plugins[row]
        plugin = mesk.plugin.get_manager().get_plugin(selected_plugin['NAME'])
        if is_active and plugin.is_configurable():
            self._config_button.set_sensitive(True)
        else:
            self._config_button.set_sensitive(False)

    def _on_plugin_toggled(self, cell, path, model):
        new_state = not model[path][0]
        path = int(path)
        plugin_name = self._plugins[path]['NAME']

        plugin_mgr = mesk.plugin.get_manager()
        state_str = ''
        try:
            if new_state:
                state_str = _('Plugin activation error')
                plugin_mgr.activate_plugin(plugin_name)
            else:
                state_str = _('Plugin deactivation error')
                plugin_mgr.deactivate_plugin(plugin_name)
            # Update model
            model[path][0] = new_state
        except Exception, ex:
            d = ErrorDialog(self.window)
            d.set_markup('<b>%s</b>' % state_str)
            d.format_secondary_text(str(ex))
            d.run()
            d.destroy()

    def _on_plugin_config_button_clicked(self, button):
        selected_row = self._plugins_view.get_cursor()[0][0]
        selected_plugin = self._plugins[selected_row]
        plugin = mesk.plugin.get_manager().get_plugin(selected_plugin['NAME'])

        self.config_widget = plugin.get_config_widget(self.window)
        self.plugin_config_container.pack_start(self.config_widget)
        self.plugin_config_container.show_all()
        self._plugins_view.set_sensitive(False)
        self.plugins_notebook.set_current_page(1)
        self.config_plugin = plugin

    def _config_action(self, action):
        '''A helper for the config ok/cancel buttons'''
        action()

        self.plugin_config_container.remove(self.config_widget)
        self.config_widget.destroy()
        self.config_widget = None
        del self.config_widget
        self.config_plugin = None

        self.plugins_notebook.set_current_page(0)
        self._plugins_view.set_sensitive(True)

    def _on_plugin_config_cancel_button_clicked(self, button):
        self._config_action(self.config_plugin.config_cancel)
    def _on_plugin_config_ok_button_clicked(self, button):
        self._config_action(self.config_plugin.config_ok)
## end PluginPrefs
