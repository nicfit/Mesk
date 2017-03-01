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
import gst

import mesk
import mesk.utils, mesk.uri
from mesk.i18n import _

# Test for mpeg support in gstreamer
try:
    gst.element_factory_make('mad')
except Exception, ex:
    raise mesk.audio.UnsupportedFormat('No mpeg (mp3) audio support')

import eyeD3

NAME = eyeD3.mp3.INFO['name']
MIME_TYPES = eyeD3.mp3.INFO['mime-types']
EXTENSIONS = eyeD3.mp3.INFO['extensions']

from source import AudioSource, AudioMetaData
class MpegAudioSource(AudioSource):
    def __init__(self, uri, meta_data=None):
        AudioSource.__init__(self, uri, meta_data)

        if meta_data is None:
            self.meta_data = MpegMetaData(self.uri)

        self.set_title_if_none()

        # Compute file size if necessary/possible
        if not self.meta_data.size_bytes and self.uri.scheme == 'file':
            try:
                self.meta_data.size_bytes = \
                    os.stat(mesk.uri.unescape(self.uri.path))[stat.ST_SIZE]
            except OSError, ex:
                raise IOError(str(ex))

    def get_native_tag(self):
        '''Returns the eyeD3.Tag for this source, or None'''
        if self.uri.scheme != 'file':
            return None

        uri_path = mesk.uri.unescape(self.uri.path)
        try:
            tag = eyeD3.id3.Tag()
            if tag.link(uri_path):
                return tag
        except eyeD3.id3.TagException, ex:
            mesk.log.warning('Error loading ID3 tag for \'%s\': %s' %
                             (uri_path, str(ex)))
            return None

    def get_cover_image(self):
        from eyeD3.id3.frames import ImageFrame

        # Images are loaded lazily
        if self.meta_data.has_images:
            tag = self.get_native_tag()
            if tag:
                imgs = tag.getImages()
                # Search for acceptable covers
                for img in tag.getImages():
                    # TODO: back cover support
                    for type in [ImageFrame.FRONT_COVER, ImageFrame.OTHER]:
                        if img.pictureType == type:
                            return (img.mimeType, img.imageData)
        return None


from eyeD3 import UnsupportedFormatException
class MpegMetaData(AudioMetaData):

    def __init__(self, uri=None):
        AudioMetaData.__init__(self)

        if not uri or uri.scheme != 'file':
            return
        uri_path = mesk.uri.unescape(uri.path)

        audio_file = None
        try:
            audio_file = eyeD3.mp3.Mp3AudioFile(uri_path)
        except (eyeD3.id3.TagException, UnsupportedFormatException), ex:
            mesk.log.warning('Error reading mpeg source for \'%s\': %s' %
                             (uri_path, str(ex)))
        else:
            self.time_secs = audio_file.audio_info.time_secs
            self.size_bytes = audio_file.audio_info.size_bytes
            tag = audio_file.tag
            if tag:
                self.title = tag.getTitle() or u''
                self.artist = tag.getArtist() or u''
                self.album = tag.getAlbum() or u''
                self.year = tag.getYear()
                (self.track_num, self.track_total) = tag.getTrackNum()
                self.has_images = len(tag.getImages()) > 0
                genre = tag.getGenre()
                if genre:
                    for g in genre.getName().split('|'):
                        self.genres.append(g)

                self.frozen = True

# The factory class for mpeg files
factory = MpegAudioSource

