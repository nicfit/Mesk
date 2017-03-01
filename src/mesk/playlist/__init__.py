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
import os.path, traceback, random

import mesk.audio.source
import mesk.utils, mesk.uri, mesk.log

# Mapping from mime types to the respective module
supported_mimetypes = {}
# Mapping from file extensions to the respective module
supported_extensions = {}

# Initialize audio format modules
modules = ['m3u',
           'xspf',
           'pls',
          ]
for module in modules:
    try:
        module = __import__(module, globals(), locals(), [])
        for mt in module.MIME_TYPES:
            supported_mimetypes[mt] = module
        for ext in module.EXTENSIONS:
            supported_extensions[ext] = module
    except:
        mesk.log.warn(traceback.format_exc())
        continue

def load(uri, name=None):
    if not mesk.uri.is_uri(uri):
        uri = mesk.uri.make_uri(uri)

    pl = Playlist(name)
    pl_path = mesk.uri.unescape(uri.path)
    pl_ext = os.path.splitext(pl_path)[1]

    if uri.scheme == 'file':
        if pl_ext not in supported_extensions:
            raise TypeError('Unsupported playlist type: %s' % pl_ext)
        elif not os.path.exists(pl_path):
            # Create empty playlist
            fp = file(pl_path, 'w')
            fp.close()
            return pl

        fp = file(pl_path, 'r')
        supported_extensions[pl_ext].load(fp, pl)
        fp.close()
    else:
        # Remote playlist, fetch it and add it's contents
        import urllib2
        mesk.log.debug('Fetching %s' % str(uri))
        fp = urllib2.urlopen(str(uri))
        if not pl_ext:
            # Fallback on m3u
            pl_ext = '.m3u'
        supported_extensions[pl_ext].load(fp, pl)
        fp.close()

    return pl

class Playlist(object):
    def __init__(self, name=None):
        self.name = name
        self.annotation = u''

        # AudioSource objects managed my this playlist and the index of the
        # "current" (the last index returned from get_next/get_prev) source
        self._sources = []
        self._curr_idx = -1

        self._repeat = False
        self._shuffle = False
        self._shuffle_history = []

        # Queued indexes where the beginning of the list is the next source
        self._queue = []

        self.browse_dir = None
        self.dir_select = False
        self.read_only = False # Read only is not enforced in this class

    def insert(self, idx, audio_src):
        # Update current index
        if idx <= self._curr_idx:
            self._curr_idx += 1

        # Update queue indexes
        for j in range(len(self._queue)):
            if idx <= self._queue[j]:
                self._queue[j] += 1
        # Update shuffle history indexes
        if self._shuffle and self._shuffle_history:
            for j in range(len(self._shuffle_history)):
                if idx <= self._shuffle_history[j]:
                    self._shuffle_history[j] += 1

        # Add AudioSource and reset if needed
        self._sources.insert(idx, audio_src)
        if self.get_length() == 1:
            self.reset()

    def insert_after(self, idx, audio_src):
        self.insert(idx + 1, audio_src)
    def append(self, audio_src):
        self.insert(self.get_length(), audio_src)
    def prepend(self, audio_src):
        self.insert(0, audio_src)

    def clear(self):
        self._sources = []
        self.reset()

    def remove(self, idx):
        # Update current index
        if idx < self._curr_idx:
            self._curr_idx -= 1
        # Update queue indexes
        if idx in self._queue:
            self._queue.remove(idx)
        for i in range(len(self._queue)):
            if idx < self._queue[i]:
                self._queue[i] -= 1
        # Update shuffle history indexes
        if self._shuffle and self._shuffle_history:
            if idx in self._shuffle_history:
                self._shuffle_history.remove(idx)
            for j in range(len(self._shuffle_history)):
                if idx < self._shuffle_history[j]:
                    self._shuffle_history[j] -= 1

        # Update list
        del self._sources[idx]
        if self.get_length() == 0:
            self.reset()

    def set_repeat(self, state):
        self._repeat = state
    def is_repeating(self):
        return self._repeat

    def is_shuffled(self):
        return self._shuffle
    def set_shuffle(self, state):
        self._shuffle = state
        self._shuffle_history = []

    def reset(self, start_idx = None):
        random.seed(None)

        self._queue = []
        self._shuffle_history = []

        # Update next index
        if start_idx is not None:
            self.set_curr_index(start_idx)
        else:
            self._curr_idx = -1

    def get_curr_index(self):
        return self._curr_idx

    def set_curr_index(self, idx):
        if idx < -1:
            idx = -1
        if idx == -1 and len(self):
            idx = 0
        self._curr_idx = idx

    def has_next(self):
        if self._repeat or self._queue:
            return True
        elif self._shuffle:
            return len(self._shuffle_history) <= len(self._sources)
        else:
            return (self._curr_idx + 1) < self.get_length()

    def has_prev(self):
        if self._shuffle:
            return len(self._shuffle_history) > 0
        else:
            return self._repeat or self._curr_idx > 0

    def get_next(self):
        if not self.get_length():
            return None

        if self._queue:
            next = self._queue.pop(0)
            self._curr_idx = next
            next = self._sources[next]
        elif self._shuffle:
            all = set(range(self.get_length()))
            history = set(self._shuffle_history)
            choices = list(all.difference(history))
            if not choices and self._repeat:
                self.reset()
                return self.get_next()
            elif not choices:
                next = None
            else:
                next = random.choice(choices)
                self._shuffle_history.append(next)
                self._curr_idx = next
                next = self._sources[next]
        else:
            next = self._curr_idx + 1
            if next < self.get_length():
                self._curr_idx = next
                next = self._sources[next]
            elif self._repeat:
                self.reset()
                return self.get_next()
            else:
                next = None

        return next

    def get_prev(self):
        if not self.get_length():
            return None

        if self._shuffle:
            if not self._shuffle_history:
                prev = None
            else:
                prev_idx = self._shuffle_history.pop()
                if prev_idx == self._curr_idx and self._shuffle_history:
                    prev_idx = self._shuffle_history.pop()
                self._curr_idx = prev_idx
                prev = self._sources[prev_idx]
        else:
            prev = self._curr_idx - 1
            if prev >= 0:
                self._curr_idx = prev
                prev = self._sources[prev]
            elif self._repeat:
                self._curr_idx = prev = self.get_length() - 1
                prev = self._sources[prev]
            else:
                prev = None

        return prev

    def has_queue(self):
        return bool(self._queue)

    def get_queue(self):
        '''Returns a copy of the queue'''
        return list(self._queue)

    def set_queue(self, q):
        '''A list of integer indexes'''
        self._queue = list(q)

    def enqueue(self, idx, pos=-1):
        if idx in self._queue:
            self._queue.remove(idx)

        if pos < 0:
            self._queue.append(idx)
        else:
            self._queue.insert(pos, idx)

    def dequeue(self, idx):
        self._queue.remove(idx)

    def get_length(self):
        return len(self._sources)

    def index(self, src):
        return self._sources.index(src)

    def __len__(self):
        return self.get_length()

    def __iter__(self):
        return self._sources.__iter__()

    def __getitem__(self, i):
        return self._sources[i]

def is_supported_ext(ext):
    return ext in supported_extensions.keys()

def is_supported_mimetype(mt):
    return mt in supported_mimetypes.keys()
