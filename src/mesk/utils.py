################################################################################
#  Copyright (C) 2006  Travis Shirk <travis@pobox.com>
#  Copyright (C) 2005  Nikos Kouremenos <nkour@jabber.org>
#  Copyright (C) 2005  Dimitur Kirov <dkirov@gmail.com>
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
import os, sys

from . import log as mesk_log
from .i18n import _

class MeskException(Exception):
    def __init__(self, primary_msg, secondary_msg=''):
        Exception.__init__(self, primary_msg)
        self.primary_msg = primary_msg
        self.secondary_msg = secondary_msg
    def __str__(self):
        return '%s: %s' % (self.primary_msg, self.secondary_msg)

## FIXME: These are in eyeD3 0.6.13, but using would mean that eyeD3 will
##        always be required, regardless of mp3 support. Also, eyeD3 does not
##        yet do i18n
# Time and memory string formatting
def format_track_time(curr, total = None):
    def time_tuple(ts):
        if ts is None or ts < 0:
            ts = 0
        hours = ts / 3600
        mins = (ts % 3600) / 60
        secs = (ts % 3600) % 60
        tstr = '%02d:%02d' % (mins, secs)
        if int(hours):
            tstr = '%02d:%s' % (hours, tstr)
        return (int(hours), int(mins), int(secs), tstr)

    hours, mins, secs, curr_str = time_tuple(curr)
    retval = curr_str
    if total:
        hours, mins, secs, total_str = time_tuple(total)
        retval += ' / %s' % total_str
    return retval

KB_BYTES = 1024
MB_BYTES = 1048576
GB_BYTES = 1073741824
KB_UNIT = _('KB')
MB_UNIT = _('MB')
GB_UNIT = _('GB')

def format_size(sz):
    unit = _('Bytes')
    if sz >= GB_BYTES:
        sz = float(sz) / float(GB_BYTES)
        unit = GB_UNIT
    elif sz >= MB_BYTES:
        sz = float(sz) / float(MB_BYTES)
        unit = MB_UNIT
    elif sz >= KB_BYTES:
        sz = float(sz) / float(KB_BYTES)
        unit = KB_UNIT
    return "%.2f %s" % (sz, unit)

def format_time_delta(td):
    days = td.days
    hours = td.seconds / 3600
    mins = (td.seconds % 3600) / 60
    secs = (td.seconds % 3600) % 60
    tstr = "%02d:%02d:%02d" % (hours, mins, secs)
    if days:
        tstr = "%d days %s" % (days, tstr)
    return tstr

def pad_string(label, width):
    side = -1
    while len(label) < width:
        if side < 0:
            label = ' %s' % label
        else:
            label = '%s ' % label
        side *= -1
    return label

# Version compares
def version_cmp(v1, v2):
    lhs = []
    rhs = []
    for i in range(max(len(v1), len(v2))):
        try:
            lhs.append(int(v1[i]))
        except IndexError:
            lhs.append(0)
        try:
            rhs.append(int(v2[i]))
        except IndexError:
            rhs.append(0)

    for i in range(len(lhs)):
        if lhs[i] > rhs[i]:
            return 1
        elif lhs[i] < rhs[i]:
            return -1
    return 0

def remove_credentials(uri):
    '''Removes any username and/or password from a uri.'''
    if uri.user_name or uri.password:
        # Remove username and password if they exist
        uri_copy = uri.copy()
        uri_copy.user_name = ''
        uri_copy.password = ''
        # Unfortunately, this leaves the delimiters
        uri_copy = uri.make_uri(str(uri_copy).replace(':@', ''))
        return uri_copy
    else:
        return uri

def load_web_page(url):
    import webbrowser
    url = str(url)
    try:
        webbrowser.open_new_tab(url)
    except AttributeError:
        # Python < 2.5
        webbrowser.open(url)


import threading
class Thread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self._lock = threading.Lock()
        self._stopped = False

    def stop(self):
        '''Cooperative thread shutdown.  Subclasses MUST react accordingly
        when self._stopped is True.'''
        self._lock.acquire()
        self._stopped = True
        self._lock.release()

class FileScanner(object):
    def __init__(self, root_dirs, exclude_dirs):
        self._root_dirs = root_dirs
        self._exclude_dirs = exclude_dirs

    def dirs(self):
        '''A generator method which walks root_dirs, excluding exclude_dirs as
        necessary, and yields a 2-tuple for each directory that contains files:
        (dirname, [file1, file2, ...])'''
        for root_dir in self._root_dirs:
            for (root, dirs, files) in os.walk(root_dir):
                if not root_dir:
                    continue
                if len(files) and root not in self._exclude_dirs:
                    files.sort()
                    yield (root, files)

    def files(self):
        '''A generator method which walks root_dirs, excluding exclude_dirs as
        necessary, and yields a filename with each call.'''
        for root_dir in self._root_dirs:
            # Walk all directories which are to be included
            for (root, dirs, files) in os.walk(root_dir):
                if not root_dir:
                    continue
                for f in files:
                    f = os.path.abspath(root + os.sep + f)
                    if os.path.dirname(f) not in self._exclude_dirs:
                        yield f

    def get_num_files(self):
        '''Note, this requires scanning the entire set of root_dirs, this value
        is not cached.'''
        return len([f for f in self.files()])

    def get_num_dirs(self):
        '''Note, this requires scanning the entire set of root_dirs, this value
        is not cached.'''
        return len([d for d in self.dirs()])

class DirScannerThread(Thread, FileScanner):
    (SCAN_CONT,
     SCAN_HALT) = range(2)

    def _handle_dir(self, dir_path, files):
        mesk_log.debug("DirScannerThread._handle_dir: " + dir_path)
        return self.SCAN_CONT

    (STATUS_COMPLETE,
     STATUS_INTERRUPTED,
     STATUS_HALTED,
     STATUS_ERROR) = range(4)

    def _handle_done(self, status):
        mesk_log.debug("DirScannerThread._handle_done, status=%d" % status)

    def __init__(self, root_dirs, exclude_dirs):
        Thread.__init__(self)
        FileScanner.__init__(self, root_dirs, exclude_dirs)

    def run(self):
        mesk_log.debug("DirScannerThread running ...")
        try:
            for dir, files in self.dirs():
                # Check for shutdown
                self._lock.acquire()
                if self._stopped:
                    self._lock.release()
                    self._handle_done(self.STATUS_INTERRUPTED)
                    return
                self._lock.release()

                if self._handle_dir(dir, files) == self.SCAN_HALT:
                    self._handle_done(self.STATUS_HALTED)
                    return
        except Exception, ex:
            mesk_log.error(str(ex))
            self._error = ex
            self._handle_done(self.STATUS_ERROR)
        else:
            self._handle_done(self.STATUS_COMPLETE)

        mesk_log.debug("DirScannerThread stopping ...")

## end SyncThread
