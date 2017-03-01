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
import os, stat
import mesk.log, mesk.audio, mesk.utils

NAME = 'Spiff-XML'
EXTENSIONS = ['.xspf']
MIME_TYPES = ['application/xspf+xml']
import mimetypes
mimetypes.add_type(MIME_TYPES[0], EXTENSIONS[0])

XSPF_NS = 'http://xspf.org/ns/0/'
MESK_NS = 'http://mesk.nicfit.net'
META_YEAR = '%s/playlist/year' % MESK_NS

EMPTY_PLAYLIST = """<?xml version="1.0" encoding="UTF-8"?>
<playlist version="1" xmlns="http://xspf.org/ns/0/">
  <trackList/>
</playlist>
"""

def load(pl_file, pl):
    import xml.dom, xml.dom.minidom, xml.parsers.expat
    # Check to see if playlist is an empty file, and create a stub if necessary
    if os.stat(pl_file.name)[stat.ST_SIZE] == 0:
        pl_dom = xml.dom.minidom.parseString(EMPTY_PLAYLIST)
    else:
        pl_dom = xml.dom.minidom.parse(pl_file.name)

    parent_path = os.path.dirname(pl_file.name)
    pl_queue = []
    pl_current = -1
    same_version = False
    pl_elem = pl_dom.getElementsByTagNameNS(XSPF_NS, 'playlist')[0]

    if pl_elem.getElementsByTagNameNS(XSPF_NS, 'title'):
        elem = pl_elem.getElementsByTagNameNS(XSPF_NS, 'title')[0]
        pl.name = _get_elem_text(elem)

    if pl_elem.getElementsByTagNameNS(XSPF_NS, 'annotation'):
        elem = pl_elem.getElementsByTagNameNS(XSPF_NS, 'annotation')[0]
        pl.annotation = _get_elem_text(elem)

    mesk_state_elem = None
    for ext_elem in pl_elem.getElementsByTagNameNS(XSPF_NS, 'extension'):
        if ext_elem.getAttribute('application') == MESK_NS:
            mesk_state_elem = ext_elem

            # Mesk version
            mesk_elems = ext_elem.getElementsByTagNameNS(MESK_NS, 'version')
            if mesk_elems:
                if _get_elem_text(mesk_elems[0]) == mesk.info.APP_VERSION:
                    same_version = True
            # Shuffle, repeat, etc. booleans.  
            pl.set_shuffle(bool(ext_elem.getElementsByTagNameNS(MESK_NS,
                                                                'shuffle')))
            pl.set_repeat(bool(ext_elem.getElementsByTagNameNS(MESK_NS,
                                                               'repeat')))
            # Select dirs when true, files when false
            pl.dir_select = bool(ext_elem.getElementsByTagNameNS(MESK_NS,
                                                                 'dir-select'))
            # Directory to start when adding files
            mesk_elems = ext_elem.getElementsByTagNameNS(MESK_NS, 'browse-dir')
            if mesk_elems:
                pl.browse_dir = _get_elem_text(mesk_elems[0])

            # Playlist queue indexes, MUST be set after the playlist is filled
            mesk_elems = ext_elem.getElementsByTagNameNS(MESK_NS, 'queue')
            if mesk_elems:
                for index in ext_elem.getElementsByTagNameNS(MESK_NS, 'index'):
                    pl_queue.append(int(_get_elem_text(index)))

            # Read-only property
            pl.read_only = bool(ext_elem.getElementsByTagNameNS(MESK_NS,
                                                                'read-only'))
            # Current index, this MUST be set after the playlist is filled
            mesk_elems = ext_elem.getElementsByTagNameNS(MESK_NS, 'current')
            if mesk_elems:
                pl_current = int(_get_elem_text(mesk_elems[0]))

            break

    list_elem = pl_elem.getElementsByTagName('trackList')[0]
    for track_elem in list_elem.getElementsByTagName('track'):
        location_elems = track_elem.getElementsByTagName('location')
        if not location_elems:
            mesk.log.warn('<location/> URI required in XSPF playlist tracks')
            continue
        location = _get_elem_text(location_elems[0])
        location_uri = mesk.uri.make_uri(location)

        meta_data = None
        # Not loading metadata from the files is much faster, but only do
        # so when the same version of Mesk wrote the playlist.
        if same_version:
            meta_data = mesk.audio.source.AudioMetaData()
            for elem in track_elem.childNodes:
                if elem.nodeType == elem.ELEMENT_NODE:
                    if elem.tagName == 'title':
                        meta_data.title = _get_elem_text(elem)
                    elif elem.tagName == 'creator':
                        meta_data.artist = _get_elem_text(elem)
                    elif elem.tagName == 'album':
                        meta_data.album = _get_elem_text(elem)
                    elif elem.tagName == 'duration':
                        meta_data.time_secs = int(_get_elem_text(elem)) / 1000
                    elif elem.tagName == 'trackNum':
                        meta_data.track_num = int(_get_elem_text(elem))
                    elif (elem.tagName == 'meta' and
                          elem.getAttribute('rel') == META_YEAR):
                        meta_data.year = _get_elem_text(elem)

        # Handle relative paths if necessary
        if (location_uri.is_local and not os.path.isabs(location_uri.path)):
            location_uri = mesk.uri.make_uri('file://%s/%s' %
                                             (parent_path, location_uri.path))

        if meta_data and not meta_data.title:
            meta_data.title = mesk.uri.unescape(str(location_uri))

        try:
            src = mesk.audio.load(location_uri, meta_data)
        except Exception, ex:
            msg = str(ex)
            if not isinstance(ex, IOError):
                import traceback
                msg += "\n%s" % traceback.format_exc()

            # Loading failed, but leave it on the playlist as a "dead" file.
            mesk.log.warn(msg)
            if meta_data is None:
                meta_data = mesk.audio.source.AudioMetaData()
            src = mesk.audio.source.AudioSource(location, meta_data)

        src.set_title_if_none()
        pl.append(src)

    # The following props MUST be set after the playlist is populated
    if pl_queue:
        pl.set_queue(pl_queue)
    try:
        pl.set_curr_index(pl_current)
    except IndexError:
        pass

def save(fp, pl, relative_paths=False):
    import xml.sax.saxutils as saxutils
    def pad(n):
        return ' ' * n

    # We are only serializing pl, so building a DOM would just waste time.
    fp.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    fp.write('<playlist xmlns="http://xspf.org/ns/0/" '
             'xmlns:mesk="%s" version="1">\n' % MESK_NS)

    # Playlist and Mesk metadata
    indent = 2
    fp.write(pad(indent) + '<title>%s</title>\n' % saxutils.escape(pl.name))
    if pl.annotation:
        fp.write(pad(indent) + '<annotation>%s</annotation>\n' %
                               saxutils.escape(pl.annotation))
    fp.write(pad(indent) +
             '<info>Made with Mesk - http://mesk.nicfit.net/</info>\n')
    fp.write(pad(indent) + '<extension application="%s">\n' % MESK_NS)
    indent += 2
    fp.write(pad(indent) + '<mesk:version>%s</mesk:version>\n' %
                           mesk.info.APP_VERSION)
    fp.write(pad(indent) + '<mesk:current>%d</mesk:current>\n' %
                           pl.get_curr_index())
    if pl.is_shuffled():
        fp.write(pad(indent) + '<mesk:shuffle/>\n')
    if pl.is_repeating():
        fp.write(pad(indent) + '<mesk:repeat/>\n')
    if pl.dir_select:
        fp.write(pad(indent) + '<mesk:dir-select/>\n')
    if pl.browse_dir:
        fp.write(pad(indent) + '<mesk:browse-dir>%s</mesk:browse-dir>\n' %
                               saxutils.escape(pl.browse_dir))
    if pl.has_queue():
        fp.write(pad(indent) + '<mesk:queue>\n')
        indent += 2
        for i in pl.get_queue():
            fp.write(pad(indent) + '<mesk:index>%d</mesk:index>\n' % i)
        indent -= 2
        fp.write(pad(indent) + '</mesk:queue>\n')

    if pl.read_only:
        fp.write(pad(indent) + '<mesk:read-only/>\n')

    indent -= 2
    fp.write(pad(indent) + '</extension>\n')

    # Playlist tracks
    fp.write(pad(indent) + '<trackList>\n')
    indent += 2
    for s in pl:
        fp.write(pad(indent) + '<track>\n')
        indent += 2

        uri = mesk.utils.remove_credentials(s.uri)
        if uri.is_local and relative_paths:
            uri = 'file:%s' % os.path.basename(uri.path)
        fp.write(pad(indent) + '<location>%s</location>\n' %
                               saxutils.escape(str(uri)))

        if s.meta_data.time_secs:
            fp.write(pad(indent) + '<duration>%d</duration>\n' %
                                   (s.meta_data.time_secs * 1000))
        if s.meta_data.title:
            t = saxutils.escape(s.meta_data.title.encode('utf-8'))
            fp.write(pad(indent) + '<title>%s</title>\n' % t)
        if s.meta_data.artist:
            a = saxutils.escape(s.meta_data.artist.encode('utf-8'))
            fp.write(pad(indent) + '<creator>%s</creator>\n' % a)
        if s.meta_data.album:
            a = saxutils.escape(s.meta_data.album.encode('utf-8'))
            fp.write(pad(indent) + '<album>%s</album>\n' % a)
        if s.meta_data.track_num is not None:
            fp.write(pad(indent) +
                     '<trackNum>%d</trackNum>\n' % s.meta_data.track_num)
        if s.meta_data.year is not None:
            fp.write(pad(indent) + '<meta rel="%s">%d</meta>\n' %
                                   (META_YEAR, int(s.meta_data.year)))

        indent -= 2
        fp.write(pad(indent) + '</track>\n')

    indent -= 2
    fp.write(pad(indent) + '</trackList>\n')
    fp.write('</playlist>\n')

def _get_elem_text(elem):
    nodelist = elem.childNodes
    txt = u''
    for node in nodelist:
        if node.nodeType == node.TEXT_NODE:
            txt = txt + node.data
    return txt
