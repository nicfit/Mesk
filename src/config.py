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
import os, string

import mesk
import mesk.uri
from mesk.i18n import _

def get_all_playlist_names():
    playlists = []
    for section in mesk.config.sections():
        if section.startswith(mesk.CONFIG_PLAYLIST + '.'):
            name = section.split('.', 1)[1]
            playlists.append(name)
    return playlists

class PlaylistConfig:
    name = ''
    uri = None

    def __init__(self, name):
        self.set_name(name)

        if (mesk.config.has_section(self._section) and
            mesk.config.has_option(self._section, 'uri') and
            mesk.config.get(self._section, 'uri')):
            # Initialize from config
            self.uri = mesk.uri.make_uri(mesk.config.get(self._section, 'uri'))
        else:
            if not mesk.config.has_section(self._section):
                mesk.config.add_section(self._section)
            pl_dir = mesk.config.get(mesk.CONFIG_MAIN, 'playlist_dir')
            import tempfile
            (fd, path) = tempfile.mkstemp('.xspf', 'playlist-', pl_dir)
            os.close(fd)
            self.uri = mesk.uri.make_uri('file://%s' %
                                         mesk.uri.escape_path(path))

    def update(self):
        mesk.config.set(self._section, 'uri', str(self.uri))

    def set_name(self, name):
        self._section = None
        if name == self.name or not name:
            return

        old_name = self.name
        self.name = name
        old_section = mesk.CONFIG_PLAYLIST + '.' + old_name
        self._section = mesk.CONFIG_PLAYLIST + '.' + self.name

        # Convert config if necessary
        if (not mesk.config.has_section(self._section) and
                mesk.config.has_section(old_section)):
            mesk.config.add_section(self._section)
            for nv in mesk.config.items(old_section):
                mesk.config.set(self._section, nv[0], nv[1])
            mesk.config.remove_section(old_section)

    def delete(self):
        mesk.config.remove_section(self._section)
