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
import os

import mesk
import mesk.utils

NAME = 'PLSv2'
EXTENSIONS = ['.pls']
MIME_TYPES = ['audio/x-scpls']
import mimetypes
mimetypes.add_type(MIME_TYPES[0], EXTENSIONS[0])

def load(pl_file, pl):
    parent_path = os.path.dirname(pl_file.name)

    import ConfigParser
    parser = ConfigParser.RawConfigParser()
    parser.readfp(pl_file)
    SECT = 'playlist'

    count = 1
    total = parser.getint(SECT, 'NumberOfEntries')
    while count <= total:
        entry = {}
        for key in ['File', 'Title', 'Length']:
            entry[key] = None
            try:
                entry[key] = parser.get(SECT, '%s%d' % (key, count))
            except:
                if key is 'File':
                    raise
        count += 1

        meta_data = mesk.audio.source.AudioMetaData()
        meta_data.title = unicode(entry['Title'] or entry['File'])
        meta_data.time_secs = int(entry['Length'] or 0)

        uri = mesk.uri.make_uri(entry['File'])
        if (uri.scheme == 'file' and not os.path.isabs(uri.path)):
            uri = mesk.uri.make_uri('file://%s/%s' % (parent_path, uri.path))

        try:
            src = mesk.audio.load(uri, meta_data)
        except Exception, ex:
            # Loading failed, but leave it on the playlist as a "dead" file.
            mesk.log.warn(str(ex))
            src = mesk.audio.source.AudioSource(entry['File'], meta_data)
        pl.append(src)

def save(fp, pl, relative_paths=False):
    fp.write('[playlist]\n')
    fp.write('Version=2\n')
    total = pl.get_length()
    fp.write('NumberOfEntries=%d\n' % total)

    count = 1
    for src in pl:
        path = ''
        if src.uri.scheme == 'file':
            if relative_paths:
                path = mesk.uri.unescape(os.path.basename(src.uri.path))
            else:
                path = mesk.uri.unescape(src.uri.path)
        else:
            path = str(mesk.utils.remove_credentials(src.uri))
        fp.write('File%d=%s\n' % (count, path))

        fp.write('Title%d=%s\n' % (count, src.meta_data.title or ''))
        fp.write('Length%d=%d\n' % (count, src.meta_data.time_secs or 0))

        count += 1
