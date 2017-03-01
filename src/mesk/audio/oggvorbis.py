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
import sys, os, stat
import gst, ogg.vorbis

import eyeD3

import mesk
import mesk.utils, mesk.uri
from mesk.i18n import _

# Test for the ability to play oggvorbis
try:
    gst.element_factory_make('vorbisdec')
    from ogg.vorbis import VorbisFile, VorbisError
except Exception, ex:
    from mesk.audio import UnsupportedFormat
    raise UnsupportedFormat('No Ogg Vorbis audio support')
    raise Exception('No Ogg Vorbis audio support')

NAME = eyeD3.ogg.INFO['name']
MIME_TYPES = eyeD3.ogg.INFO['mime-types']
EXTENSIONS = eyeD3.ogg.INFO['extensions']

from source import AudioSource, AudioMetaData
class OggAudioSource(AudioSource):
    def __init__(self, uri, meta_data=None):
        AudioSource.__init__(self, uri, meta_data)

        if meta_data is None:
            self.meta_data = OggMetaData(self.uri)

        self.set_title_if_none()

        # Compute file size if necessary/possible
        if not self.meta_data.size_bytes and self.uri.scheme == 'file':
            self.meta_data.size_bytes = \
                os.stat(mesk.uri.unescape(self.uri.path))[stat.ST_SIZE]

    def get_native_tag(self):
        '''Returns the VorbisComment object, if any'''
        if self.uri.scheme != 'file':
            return None
        try:
            tag = VorbisFile(self.uri.path)
            if tag.comment():
                return tag.comment()
        except VorbisError, ex:
            return None

class OggMetaData(AudioMetaData):
    def __init__(self, uri=None):
        AudioMetaData.__init__(self)

        if not uri or uri.scheme != 'file':
            return
        uri_path = mesk.uri.unescape(uri.path)

        audio_file = None
        try:
            audio_file = VorbisFile(uri_path)
        except (VorbisError), ex:
            mesk.log.warning('Error reading ogg/vorbis source for \'%s\': %s' %
                             (uri_path, str(ex)))
        else:
            self.time_secs = int(audio_file.time_total(0))
            self.size_bytes = os.stat(uri_path)[stat.ST_SIZE]

            tag = audio_file.comment()
            if tag:
                for key, value in tag.items():
                    if key.lower() == 'title':
                        self.title = value
                    elif key.lower() == 'artist':
                        self.artist = value
                    elif key.lower() == 'album':
                        self.album = value
                    elif key.lower() == 'date':
                        self.year = value
                    elif key.lower() == 'tracknumber':
                        values = value.split('/')
                        if values:
                            self.track_num = int(values[0])
                            if len(values) > 1:
                                self.track_total = int(values[1])
                    elif key.lower() == 'genre':
                        # FIXME: Needs testing...
                        genres = value
                        if genres:
                            for g in genres.split('|'):
                                self.genres.append(g)

                self.frozen = True

# Factory class for Ogg Vorbis files
factory = OggAudioSource

