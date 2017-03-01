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
import os, ConfigParser

from .i18n import _

from .info import APP_NAME
from .info import APP_VERSION
from .info import APP_MAINTAINER

## Module constants ##
MESK_DIR = os.path.expandvars('${HOME}/.%s' % APP_NAME.lower())
DEFAULT_PLAYLISTS_DIR = "%s/playlists" % (MESK_DIR)
DEFAULT_PLUGINS_DIR = "%s/plugins" % (MESK_DIR)

# Config sections
CONFIG_MAIN     = 'mesk'
CONFIG_UI       = 'ui'
CONFIG_AUDIO    = 'audio'
CONFIG_PLAYLIST = 'playlist'
CONFIG_LIBRARY  = 'library'

# GST sinks
GST_ALSA      = 'alsasink'
GST_OSS       = 'osssink'
GST_ESD       = 'esdsink'
GST_GCONF     = 'gconfaudiosink'
GST_AUTO_SINK = 'autoaudiosink'

DEFAULT_PLAYLIST_NAME = _('Playlist')

# Program options
# section: {opt_name: [type, default, help_string]}
OPTIONS = {
    CONFIG_MAIN: {
    'version': [str, APP_VERSION, _('Application version')],
    'playlist_dir': [str, DEFAULT_PLAYLISTS_DIR,
                     _('The directory containing playlists.')],
    'active_playlist': [str, '',
                  _('The foreground playlist that has audio control.')],
    'playlists': [str, DEFAULT_PLAYLIST_NAME,
                  _('A list of playlists to open on startup.')],
    'log_level': [str, 'INFO',
                  _('Logging level. May be CRITICAL, ERROR, WARNING, INFO, '
                    'VERBOSE, or DEBUG')],
    'confirm_quit': [bool, True,
                     _('Show confirmation dialog before quitting the '
                       'application.')],
    'plugins_dir': [str, DEFAULT_PLUGINS_DIR,
                    _('The directory containing user installed plugins')],
    'plugins': [str, '', _('A list of plugins (separated by \';\') to activate '
                           'on startup.')],
    'export_dir': [str, os.path.expandvars("$HOME"),
                   _('The last export directory.')],
    },

    CONFIG_UI: {
    'compact_state': [bool, False, _('Start in compact view mode')],
    'window_hide_on_close': [bool, True,
                             _('If True, the main window is hidded instead of '
                               'closed when the window close button is '
                               'clicked.')],
    'main_window_width': [int, 435, _('Main window width.')],
    'main_window_height': [int, 560, _('Main window height.')],
    'main_window_pos_x': [int, -1, _('Main window x origin.')],
    'main_window_pos_y': [int, -1, _('Main window y origin.')],
    'compact_main_window_pos_x': [int, -1,
                                  _('Main window x origin in compact mode.')],
    'compact_main_window_pos_y': [int, -1,
                                  _('Main window y origin in compact mode.')],
    'show_tab_close_button': [bool, False,
                              _('Display a close button on each tab.')],
    'show_tip_window_on_startup': [bool, True,
                                   _('Show tips window each time Mesk is '
                                     'started.')],
    'last_tip_displayed': [int, -1,
                           _('The last tip displayed in the tips window.')],
    'auto_open_devices': [bool, True,
                          _('Automatically open devices (cdroms, etc.)')],

    },

    CONFIG_AUDIO: {
    'gst_sink': [str, GST_ALSA,
                 _("GStreamer output sink. May be %s (default), %s, '%s',"
                   "'%s', or '%s'") % (GST_AUTO_SINK, GST_GCONF, GST_ALSA,
                                       GST_OSS, GST_ESD)],
    'gst_delay': [int, 1000,
                  _('Number of milliseconds to pause between tracks')],
    'volume': [float, 1.0,
               _('Volume level is a value between 0.0 and 1.0')],
    'mixer_command': [str, 'gnome-volume-control',
                      _('The volume level mixing program. The PATH environment '
                        'variable is used to locate commands that do not '
                        'contain a path.')],
    },

    CONFIG_PLAYLIST + '.' + DEFAULT_PLAYLIST_NAME: {
    'uri': [str, '', _('Playlist (file) location')],
    },

    CONFIG_LIBRARY: {
    'db': [str, '', _('Database (sqlite) path URI')],
    'lib_dirs': [str, '',
                 _('Tab delimited list of directories included in the '
                   'library.')],
    'exclude_dirs': [str, '',
                     _('Tab delimited list of directories to exclude from the '
                       'library.')],
    },
}

class ConfigException(Exception):
    '''Config exception'''

class Config(ConfigParser.RawConfigParser):

    (OPT_TYPE,
     OPT_DEFAULT,
     OPT_HELP) = range(3)

    def __init__(self, options):
        # Using RawConfigParser so that values containing '%' don't get
        # interpolated and throw errors when there is no value defined
        ConfigParser.RawConfigParser.__init__(self, None)

        self.profile = None
        self.__options = options

        # Initialize from schema
        for section in self.__options:
            self.add_section(section)
            options = self.__options[section]
            for opt in options:
                opt_type = options[opt][self.OPT_TYPE]
                if opt_type is unicode:
                    opt_val = options[opt][self.OPT_DEFAULT].encode('utf-8')
                else:
                    opt_val = str(options[opt][self.OPT_DEFAULT])
                self.set(section, opt, opt_val)

    def load(self, config_file, profile):
        self.profile = profile
        file_config = ConfigParser.ConfigParser()
        file_config.readfp(file(config_file, 'r'))

        # Add any config that is not in the default options
        for sect in file_config.sections():
            if not self.has_section(sect):
                self.add_section(sect)
            for opt in file_config.options(sect):
                val = file_config.get(sect, opt)
                self.set(sect, opt, val)

    def save(self, config_file):
        fp = file(config_file, 'w')
        ConfigParser.RawConfigParser.write(self, fp)
        fp.close()
        # Ensure security
        os.chmod(config_file, 0600)

    def get(self, section, option, default=''):
        try:
            val = ConfigParser.RawConfigParser.get(self, section, option)
        except ConfigParser.NoOptionError:
            val = default
        return val

    def getboolean(self, section, option, default=False):
        try:
            val = ConfigParser.RawConfigParser.getboolean(self, section, option)
        except ConfigParser.NoOptionError:
            val = default
        return val

    def getint(self, section, option, default=None):
        try:
            val = ConfigParser.RawConfigParser.getint(self, section, option)
        except ConfigParser.NoOptionError:
            val = default
        return val

    def getfloat(self, section, option, default=None):
        try:
            val = ConfigParser.RawConfigParser.getfloat(self, section, option)
        except ConfigParser.NoOptionError:
            val = default
        return val

    def getlist(self, section, option, default=[], list_delim=';'):
        retlist = []
        try:
            val = self.get(section, option)
            for item in val.split(list_delim):
                item = item.strip()
                if not item:
                    continue
                retlist.append(item)
        except ConfigParser.NoOptionError:
            retlist = default
        return retlist

    def set(self, section, option, value, list_delim=';'):
        if isinstance(value, unicode):
            str_val = value.encode('utf-8')
        elif isinstance(value, list):
            str_val = ''
            for item in value:
                str_val += str(item) + list_delim
            # Remove trailing delimiter
            str_val = str_val[:-1]
        else:
            str_val = value

        ConfigParser.RawConfigParser.set(self, section, option, str_val)

    ### Overridden ###
    def read(self, filenames):
        raise ConfigException('Use the load method instead')
    def readfp(self, fp, filename):
        raise ConfigException('Use the load method instead')
    def write(self, fp):
        raise ConfigException('Use the save method instead')
