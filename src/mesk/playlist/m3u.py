################################################################################
#  Copyright (C) 2006-2007  Travis Shirk <travis@pobox.com>
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

import mesk.log
import mesk.audio
import mesk.utils

NAME = 'Extended M3U'
EXTENSIONS = ['.m3u']
MIME_TYPES = ['audio/x-mpegurl']

def load(pl_file, pl):
    '''Load an m3u into playlist pl.  pl_file must support readlines()'''

    meta_time = 0
    meta_title = u''
    meta_artist = u''
    parent_path = os.path.dirname(pl_file.name)

    for line in pl_file.readlines():
        line = line.strip()
        if not line:
            continue

        if line.startswith('#EXTINF:'):
            # Handle extended m3u metadata
            line = line[len('#EXTINF:'):]
            pair = line.split(',')
            if len(pair) == 2:
                time,title = pair
                meta_time = int(time)
                # Split artist and title if it looks like that format
                if ' - ' in title >= 0:
                    meta_artist, meta_title = title.split(' - ', 1)
                else:
                    meta_title = title
            continue
        elif line[0] == '#':
            continue

        uri = mesk.uri.make_uri(line)
        if not meta_title:
            # No title set so use the uri/path, whatever
            meta_title = mesk.uri.unescape(str(uri))

        # Handle relative paths
        if (uri.is_local and not os.path.isabs(uri.path)):
            uri = mesk.uri.make_uri('file:%s/%s' % (parent_path, uri.path))

        try:
            src = mesk.audio.load(uri)
        except Exception, ex:
            mesk.log.warn(str(ex))
            # Loaing failed, but add it as a "dead" file
            src = mesk.audio.source.AudioSource(line, None)
            src.meta_data = mesk.audio.source.AudioMetaData()

        # Use metadata from playlist if not set from load
        if ((not src.meta_data.frozen) and (meta_time is not None) and
            meta_title):
            src.meta_data.time_secs = meta_time
            src.meta_data.title = meta_title
            src.meta_data.artist = meta_artist
        pl.append(src)

        # Reset
        meta_time = 0
        meta_title = u''
        meta_artist = u''

def save(fp, pl, relative_paths=False):
    fp.write('#EXTM3U\n')
    for src in pl:
        time = src.meta_data.time_secs or 0
        info = src.meta_data.title or u''
        if src.meta_data.artist:
            info = '%s - %s' % (src.meta_data.artist, info)

        fp.write('#EXTINF:%d,%s\n' % (time, info.encode('utf-8')))
        if src.uri.is_local:
            path = (os.path.basename(src.uri.path) if relative_paths
                                                   else src.uri.path)
            fp.write(mesk.uri.unescape(path))
        else:
            uri = mesk.utils.remove_credentials(src.uri)
            fp.write(str(uri))
        fp.write('\n')
