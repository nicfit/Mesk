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
import gnomevfs

# URI helpers and gnomevfs insulation

class CddaURI(object):
    '''This is here because gnomevfs.URI is not extensible and does not like
    cdda:// schemes.'''
    def __init__(self, track_num):
        self.scheme = 'cdda'
        self.path = '%d' % track_num
        self.uri = '%s://%s' % (self.scheme, self.path)
    def __str__(self):
        return self.uri

def is_uri(uri):
    return isinstance(uri, gnomevfs.URI)

def make_uri(uri):
    if is_uri(uri):
        return uri.copy()
    else:
        uri = gnomevfs.URI(uri)
        return uri

def unescape(uri):
    return gnomevfs.unescape_string_for_display(str(uri))

def escape_path(path):
    return gnomevfs.escape_path_string(path)
def escape_host_path(host_path):
    return gnomevfs.escape_host_and_path_string(host_path)
def escape_slashes(s):
    return gnomevfs.escape_slashes(s)

def uri_to_filesys_path(uri):
    return unescape(uri.path)

