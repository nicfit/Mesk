# -*- coding: utf-8 -*-
################################################################################
#  Copyright (C) 2007  Travis Shirk <travis@pobox.com>
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
import os, threading
import datetime, tempfile, shutil

import gobject, gtk, gtk.gdk, gtk.glade
import pango

import mesk
import mesk.utils, mesk.gtk_utils, mesk.uri, mesk.playlist, mesk.audio
from mesk.i18n import _

class Exporter(object):
    def __init__(self, playlist):
        self.default_ext = None
        self.playlist = playlist

    def get_extensions(self):
        raise NotImplementedError

    def export(self, directory, name, progress_cb):
        raise NotImplementedError

    def get_options_widget(self, extension):
        return None


class PlaylistExportDialog(object):
    def __init__(self, playlist):
        self.playlist = playlist
        self.export_directory = None
        self.export_name = None
        self._curr_filename = None
        self._curr_ext = None
        self._curr_display_name = None
        self._curr_exporter = None
        self._curr_opts_widget = None

        xml = mesk.gtk_utils.get_glade('playlist_export_dialog',
                                       'playlist.glade')
        xml.signal_autoconnect(self)
        self.dialog = xml.get_widget('playlist_export_dialog')
        self.export_label = xml.get_widget('export_type_label')
        self.export_options_box = xml.get_widget('export_options_vbox')
        self.export_name_table = xml.get_widget('export_name_type_table')

        self.dir_chooser = xml.get_widget('export_dirchooser_button')
        export_dir = mesk.config.get(mesk.CONFIG_MAIN, 'export_dir')
        self.dir_chooser.set_filename(export_dir)

        self.close_button = xml.get_widget('close_button')
        self.ok_button = xml.get_widget('ok_button')
        self.ok_button.set_sensitive(False)

        liststore = gtk.ListStore(gobject.TYPE_STRING,    # extension
                                  gobject.TYPE_PYOBJECT,  # exporter obj
                                  gobject.TYPE_STRING,    # name
                                  gobject.TYPE_PYOBJECT,  # options widget
                                 )
        type_combo = xml.get_widget('export_type_combobox')
        type_combo.set_model(liststore)

        def is_row_sep(model, iter):
            return (model.get_value(iter, 1) == None)
        type_combo.set_row_separator_func(is_row_sep)

        for exporter in [PlaylistExporter(self.playlist),
                         ArchiveExporter(self.playlist)]:
            # Add a separator
            liststore.append([None, None, None, None])
            for ext, name, opts_widget in exporter.get_extensions():
                iter = liststore.append([ext, exporter, name, opts_widget])
                if ext == exporter.default_ext:
                    type_combo.set_active_iter(iter)

        xml.get_widget('export_name_entry').set_text(playlist.name)
        self._progress_bar = xml.get_widget('export_progressbar')
        self._progress_bar.set_fraction(0.0)

        # Used to shrink window when options are unexpanded
        self._initial_size = None

    def _on_dialog_delete_event(self, dialog, event):
        self.dialog.destroy()

    ## Shrink window when option expander is closed.
    def _on_options_expander_activate(self, expander):
        if self._initial_size is None:
            self._initial_size = self.dialog.get_size()

        if expander.get_expanded():
            self.dialog.set_size_request(*self._initial_size)
            self.dialog.resize(*self._initial_size)
        else:
            self.dialog.set_size_request(-1, -1)

    def _on_export_name_entry_changed(self, entry):
        self._curr_filename = entry.get_text()
        self.ok_button.set_sensitive(True if self._curr_filename else False)
        self._update_export_label()

    def _on_export_name_entry_insert_text(self, entry, new_text, new_text_len,
                                          position):
        # Don't allow '.'; the extension is chosen automatically
        if new_text == '.':
            entry.emit_stop_by_name('insert-text')

    def _on_export_type_combobox_changed(self, combobox):
        active = combobox.get_active_iter()
        (self._curr_ext,
         self._curr_exporter,
         self._curr_display_name,
         self._curr_opts_widget) = combobox.get_model().get(active, 0, 1, 2, 3)

        self._update_export_label()

        # Update options widget
        for child in self.export_options_box.get_children():
            self.export_options_box.remove(child)
        if self._curr_opts_widget:
            self.export_options_box.pack_start(self._curr_opts_widget)

    def _update_export_label(self):
        name = ''
        if self._curr_filename:
            name = ': %s' % self._curr_filename
            if not os.path.splitext(name)[1]:
                # No extension, add the default
                name += self._curr_ext
        self.export_label.set_markup(_('Export %s%s') %
                                     (self._curr_display_name, name))

    def show(self):
        self.dialog.show()

    def _export_thread(self, directory, name):
        def show_progress(fraction):
            gobject.idle_add(lambda: self._progress_bar.set_fraction(fraction))
        def set_sensitive(state):
            for widget in [self.export_name_table,
                           self.export_options_box,
                           self.ok_button,
                           self.close_button]:
                widget.set_sensitive(state)

        gobject.idle_add(lambda: set_sensitive(False))
        try:
            self._curr_exporter.export(directory, name, show_progress)
        except Exception, ex:
            def show_error():
                import traceback
                msg = _('Playlist export failed: %s') % str(ex)
                mesk.log.error("%s\n%s" % (msg, traceback.format_exc()))

                from dialogs import ErrorDialog
                d = ErrorDialog(self.dialog, markup='<b>%s</b>' % msg)
                d.run()
                d.destroy()
            gobject.idle_add(show_error)
        else:
            self.export_name = name
            self.export_directory = directory
            mesk.config.set(mesk.CONFIG_MAIN, 'export_dir', directory)
        finally:
            gobject.idle_add(lambda: set_sensitive(True))

    def _on_ok_button_clicked(self, button):
        def append_extension(name, ext):
            '''Add extension if none exists'''
            if not os.path.splitext(name)[1]:
                if ext[0] != '.':
                    name += '.'
                name += ext
            return name

        name = self._curr_filename
        directory = self.dir_chooser.get_filename()

        name = append_extension(name, self._curr_ext)
        if os.path.exists(os.path.join(directory, name)):
            # Confirm file overwrites
            from dialogs import ConfirmationDialog
            d = ConfirmationDialog(None, type=gtk.MESSAGE_WARNING)
            d.set_markup(_('Overwrite existing file \'%s\'?') %
                         os.path.join(directory, name))
            if not d.confirm():
                return

        self._thread = threading.Thread(target=self._export_thread,
                                        args=(directory, name))
        self._thread.start()

    def _on_close_button_clicked(self, button):
        self.dialog.destroy()


class PlaylistExporter(Exporter):
    def __init__(self, playlist):
        Exporter.__init__(self, playlist)
        self.default_ext = ".xspf"

        xml = mesk.gtk_utils.get_glade('playlist_options_vbox',
                                       'playlist.glade')
        xml.signal_autoconnect(self)
        self.options_widget = xml.get_widget('playlist_options_vbox')
        xml.get_widget('absolute_paths_radiobutton').set_active(True)
        self.option_relative_paths = False

    def _on_absolute_paths_radiobutton_toggled(self, radiobutton):
        self.option_relative_paths = not radiobutton.get_active()

    def get_extensions(self):
        extenstions = mesk.playlist.supported_extensions.keys()
        extenstions.sort()
        retval = []
        for ext in extenstions:
            retval.append((ext,
                           mesk.playlist.supported_extensions[ext].NAME,
                           self.options_widget))
        return retval

    def get_options_widget(self, extenstion):
        return self.options_widget

    def export(self, directory, filename, progress_cb):
        progress_cb(0.0)
        path = os.path.join(directory, filename)
        ext = os.path.splitext(filename)[1]
        pl_module = mesk.playlist.supported_extensions[ext]

        mesk.log.debug('Exporting %s, module: %s' % (path, pl_module))
        pl_file = file(path, 'wb+')
        pl_module.save(pl_file, self.playlist,
                       relative_paths=self.option_relative_paths)
        pl_file.close()
        progress_cb(1.0)


class ArchiveExporter(Exporter):
    def __init__(self, playlist):
        Exporter.__init__(self, playlist)
        self._save_playlist_modules = {}
        self._rename_files = False

        xml = mesk.gtk_utils.get_glade('archive_options_vbox',
                                       'playlist.glade')
        xml.signal_autoconnect(self)
        self.options_widget = xml.get_widget('archive_options_vbox')

        xml.get_widget('archive_dir_entry').set_text(playlist.name)

        # Add checkboxes for additional archive options.
        vbox = xml.get_widget('add_to_archive_vbox')
        for module in mesk.playlist.supported_extensions.values():
            cb = gtk.CheckButton('%s (%s) playlist' % (module.NAME,
                                                       module.EXTENSIONS[0]))
            vbox.pack_start(cb)
            cb.connect('toggled', self._on_playlist_toggled, module)
            cb.show()

        self.archivers = {
                '.tar':  (self._tarfile, 'Tarfile'),
                '.tgz':  (self._tarfile, 'Tarball (Gzip)'),
                '.tbz2': (self._tarfile, 'Tarball (bzip2)'),
                '.zip':  (self._zipfile, 'Zipfile'),
            }

    def _on_playlist_toggled(self, togglebutton, module):
        if togglebutton.get_active():
            self._save_playlist_modules[module.NAME] = module
        else:
            if self._save_playlist_modules.has_key(module.NAME):
                del self._save_playlist_modules[module.NAME]

    def _on_archive_dir_entry_changed(self, entry):
        self._archive_topdir = entry.get_text()

    def _on_rename_files_checkbutton_toggled(self, togglebutton):
        self._rename_files = togglebutton.get_active()

    def _show_warn_dialog(self, uri):
        from dialogs import WarningDialog
        d = WarningDialog(None)
        msg = (_("Playlist entry '%s' will be omitted from the archive since "
                 "it is not a local file") % mesk.uri.unescape(str(uri)))
        d.set_markup(msg)
        d.run()
        d.destroy()

    def get_extensions(self):
        retval = []
        extensions = self.archivers.keys()
        extensions.sort()
        for ext in extensions:
            retval.append((ext, self.archivers[ext][1], self.options_widget))
        return retval

    def _files_to_archive_names(self, parent_dir, file_list):
        basenames = [os.path.basename(f) for f in file_list]
        sorted_names = list(basenames)
        sorted_names.sort()
        need_sort = sorted_names != basenames

        retval = []
        count = 1
        max_width = max(len(str(len(file_list))), 2)
        for f in file_list:
            arc_name = os.path.basename(f)
            if need_sort and self._rename_files:
                zero_pad = "0" * (max_width - len(str(count)))
                arc_name = "%s%d - %s" % (zero_pad, count, arc_name)
            arc_name = os.path.join(parent_dir, arc_name)
            retval.append(tuple((f, arc_name)))
            count += 1

        return retval

    def _zipfile(self, path, additional_files, progress_cb):
        import zipfile, datetime
        archive = zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED)
        parent_dir = self._archive_topdir.encode('utf-8')

        progress_cb(0.0)
        pl_files = []
        for source in self.playlist:
            if source.uri.scheme == "file":
                path = mesk.uri.uri_to_filesys_path(source.uri)
                pl_files.append(path)
            else:
                self._show_warn_dialog(source.uri)

        pl_files = self._files_to_archive_names(parent_dir, pl_files)
        total = float(len(pl_files) + len(additional_files))
        count = 0

        for fpath, arc_name in pl_files:
            archive.write(fpath, arc_name)
            count += 1
            progress_cb(count / total)

        for fname, arc_name in additional_files:
            archive.write(fname, "%s/%s" % (parent_dir,
                                            arc_name.encode('utf-8')))
            count += 1
            progress_cb(count / total)

        archive.close()
        progress_cb(1.0)

    def _tarfile(self, path, additional_files, progress_cb):
        import tarfile, time
        mode = 'w:'
        ext = os.path.splitext(path)[1]
        if ext == '.tgz':
            mode += 'gz'
        elif ext == '.tbz2':
            mode += 'bz2'

        progress_cb(0.0)
        archive = tarfile.open(path, mode)

        parent_dir = tarfile.TarInfo(self._archive_topdir.encode('utf-8'))
        parent_dir.type = tarfile.DIRTYPE
        parent_dir.mtime = int(time.time())
        parent_dir.mode = int('755', 8)
        archive.addfile(parent_dir)

        pl_files = []
        for source in self.playlist:
            if source.uri.scheme == "file":
                path = mesk.uri.uri_to_filesys_path(source.uri)
                pl_files.append(path)
            else:
                self._show_warn_dialog(source.uri)

        pl_files = self._files_to_archive_names(parent_dir.name, pl_files)
        total = float(len(pl_files) + len(additional_files))
        count = 0

        for fpath, arc_name in pl_files:
            archive.add(fpath, arc_name)
            count += 1
            progress_cb(count / total)

        for fname, arc_name in additional_files:
            arc_name = self._files_to_archive_names(parent_dir.name,
                                                    [arc_name])[0][1]
            archive.add(fname, arc_name.encode('utf-8'))
            count += 1
            progress_cb(count / total)

        archive.close()
        progress_cb(1.0)

    def export(self, directory, filename, progress_cb):
        ext = os.path.splitext(filename)[1]
        archive_func = self.archivers[ext][0]

        # Generate additional playlists if requested
        additional_files = []
        for pl_module in self._save_playlist_modules.values():
            tmp, tmp_file = tempfile.mkstemp()
            os.close(tmp)
            os.chmod(tmp_file, 0644)
            tmp = file(tmp_file, "wb+")
            pl_module.save(tmp, self.playlist, relative_paths=True)
            tmp.close()
            pl_name = "%s%s" % (self.playlist.name, pl_module.EXTENSIONS[0])
            additional_files.append((tmp_file, pl_name))

        archive_func(os.path.join(directory, filename), additional_files,
                     progress_cb)

        for (tmp_file, _) in additional_files:
            # Cleanup temporaries
            os.remove(tmp_file)


