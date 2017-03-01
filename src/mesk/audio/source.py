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

import mesk, mesk.uri
from mesk.i18n import _

class UnsupportedScheme(Exception):
    '''Thrown when a URI scheme is not supported'''

class AudioMetaData:

    def __init__(self):
       self.time_secs = None
       self.size_bytes = None
       self.title = u''
       self.artist = u''
       self.album = u''
       self.year = None
       self.track_num, track_total = (None, None)
       self.genres = []

       # Use to freeze the state from being updated
       self.frozen = False
       # True when the meta data includes images.  
       self.has_images = False

class AudioSource:
    def __init__(self, uri, meta_data=None):
        self.uri = mesk.uri.make_uri(uri)
        self.meta_data = meta_data if meta_data else AudioMetaData()

    def get_native_tag(self):
        return None

    def get_cover_image(self):
        '''Return None, or a 2-tuple of the form (mimetype, imgdata)'''
        return None

    def set_title_if_none(self):
        # Use URI if we don't have a title
        if not self.meta_data.title:
            if self.uri.scheme in ['file']:
                title = mesk.uri.unescape(self.uri.path)
            else:
                title = mesk.uri.unescape(str(self.uri))
            self.meta_data.title = unicode(title)

