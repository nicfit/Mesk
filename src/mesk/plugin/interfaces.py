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
import mesk

class AudioControlListener(object):
    def __init__(self):
        pass

    def on_plugin_audio_play(self, audio_src):
        '''Called when the audio starts to play.'''
    def on_plugin_audio_pause(self, audio_src):
        '''Called when the audio pauses.'''
    def on_plugin_audio_stop(self, audio_src):
        '''Called when the audio stops.'''
    def on_plugin_audio_seek(self, audio_src):
        '''Called when the audio is seeked.'''
    def on_plugin_source_started(self, audio_src):
        '''Called when the audio source starts.'''
    def on_plugin_source_ended(self, audio_src):
        '''Called when the audio source ends.'''

class ViewMenuProvider(object):
    def __init__(self):
        pass

    def plugin_view_menu_items(self):
        '''Returns a list of gtk.MenuItem objects to add to the view menu.
        The plugin is responsible for handling the activate signal.  '''
        return []

class MetaDataSearch(object):
    # Search capablities; more added as needed
    CAP_ALBUM_ART = 0x01

    def __init__(self, caps):
        self._search_caps = caps

    def get_caps(self):
        return self._search_caps

    def plugin_metadata_search(self, artist, album, track):
        '''Performs a synchronous search for metadata.
        The return value should be a dict consisting of a CAP_*/data pairs.'''
