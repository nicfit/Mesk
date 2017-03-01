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
import os, sys, traceback
import mimetypes
mimetypes.init()

import mesk.utils, mesk.uri
from ..i18n import _

import pygst
pygst.require('0.10')
import gst

class UnsupportedFormat(Exception):
    '''Thrown when a audio format is not supported'''

def load(uri, meta_data=None):
    '''Given a URI, attempt to load an AudioSource.  If this cannot be done,
    a UnsupportedFormat exception, or other related error is thrown.'''
    if not mesk.uri.is_uri(uri):
        uri = mesk.uri.make_uri(uri)

    mt = mimetypes.guess_type(str(uri))[0]
    if not mt or not supported_mimetypes.has_key(mt):
        if uri.scheme == 'file':
            raise UnsupportedFormat(_('Unsupported audio format: %s') % \
                                    (mt or os.path.splitext(uri.path)[1]))
        # If this is a URL, let things be...
        import source
        src = source.AudioSource(uri, meta_data)
    else:
        factory = supported_mimetypes[mt]
        src = factory(uri, meta_data)
    return src

### Begin module initialization ###

# Mapping from mime types to factory classes for supported formats
supported_mimetypes = {}
# Mapping from file extensions to factory classes for supported formats
supported_extensions = {}

def is_supported_ext(ext):
    return ext in supported_extensions.keys()

def is_supported_mimetype(mt):
    return mt in supported_mimetypes.keys()

# Initialize audio format modules
modules = ['mpeg',
           'oggvorbis',
           'cdaudio',
          ]
for module in modules:
    try:
        module = __import__(module, globals(), locals(), [])
        for mt in module.MIME_TYPES:
            supported_mimetypes[mt] = module.factory
        for ext in module.EXTENSIONS:
            supported_extensions[ext] = module.factory
            # Check python mimetypes DB and add if necessary
            if mimetypes.guess_type(ext, strict=False)[0] is None:
                mimetypes.add_type(module.MIME_TYPES[0], ext, strict=False)
    except Exception, ex:
        mesk.log.warn(str(ex))
        if not isinstance(ex, UnsupportedFormat):
            mesk.log.warn(traceback.format_exc())
        continue

# Ensure that the audio layer supports at least one type of audio format
if not supported_mimetypes or not supported_extensions:
    print >> sys.stderr, 'No audio formats supported'
    sys.exit(1)
