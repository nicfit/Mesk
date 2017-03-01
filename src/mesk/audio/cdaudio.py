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
import mesk, mesk.uri
from mesk.i18n import _
from .source import AudioSource, AudioMetaData

NAME = 'CD Audio'
MIME_TYPES = ['audio/cdda']
EXTENSIONS = []

class CDAudioSource(AudioSource):
    def __init__(self, device, track_num, meta_data=None):
        # gnomevfs does not like cdda:// uris, workaround
        AudioSource.__init__(self, "file://dummy", meta_data)
        self.uri = mesk.uri.CddaURI(track_num)

        self.block_device = device
        if not meta_data:
            self.meta_data = AudioMetaData()

        # Use URI if we don't have a title
        if not self.meta_data.title:
            self.meta_data.title = unicode(_('Track #%d') % track_num)

factory = CDAudioSource
