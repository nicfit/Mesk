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
import os, sys, md5
import urllib, urllib2
import time, datetime
import threading
import pickle
import gtk, gtk.glade, gobject

import mesk
import mesk.plugin
from mesk.i18n import _
from mesk.plugin.plugin import PluginInfo, Plugin
from mesk.plugin.interfaces import AudioControlListener, ViewMenuProvider

NAME = 'lyrics'
CONFIG_SECTION = NAME

class LyricsPlugin(Plugin, ViewMenuProvider, AudioControlListener):
    QUERY = '"%s"+"%s"+lyrics'

    def __init__(self):
        Plugin.__init__(self, PLUGIN_INFO)
        self._current_src = None

    def shutdown(self):
        self.log.debug('Shutting down...')

    ## ViewMenuProvider interface ###
    def plugin_view_menu_items(self):
        item = gtk.ImageMenuItem(_('Lyrics Search'))
        item.set_image(gtk.image_new_from_stock(gtk.STOCK_JUMP_TO,
                                                gtk.ICON_SIZE_MENU))
        item.connect('activate', self._on_search_menu_activate)
        if not self._current_src:
            item.set_sensitive(False)
        return [item]

    def _on_search_menu_activate(self, widget):
        if not self._current_src:
            return
        query = self.QUERY % (self._current_src.meta_data.artist,
                              self._current_src.meta_data.title)
        query = mesk.uri.escape_path(query)
        url = "http://google.com/search?hl=en&q=%s" % query
        self.log.debug("Lyrics search: %s" % url)
        mesk.utils.load_web_page(url)

    ## AudioControlListener interface ###
    def on_plugin_audio_play(self, audio_src):
        self._current_src = audio_src
    def on_plugin_source_started(self, audio_src):
        self._current_src = self._current_src
    def on_plugin_audio_stop(self, audio_src):
        self._current_src = None
    def on_plugin_source_ended(self, audio_src):
        self._current_src = None

XPM = mesk.plugin.plugin.DEFAULT_PLUGIN_XPM

## Required for plugins ##
PLUGIN_INFO = PluginInfo(name=NAME,
                         desc=_('Performs a Google search for the lyrics to the'
                                ' currently playing song.'),
                         author='Travis Shirk <travis@pobox.com>',
                         url='http://mesk.nicfit.net/',
                         copyright='Copyright © 2007 Travis Shirk',
                         clazz=LyricsPlugin,
                         xpm=XPM, display_name='Lyrics Search (google)')
