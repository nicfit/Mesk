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
import os, re, traceback
import gobject, eyeD3
import sqlalchemy as sql
from sqlalchemy import orm

from .. import uri as mesk_uri
from .. import audio
from .. import log as mesk_log
from .. import config as mesk_config
from ..config import CONFIG_LIBRARY, MESK_DIR
from ..utils import DirScannerThread

from .. import MeskException
class DBWarning(Exception):
    '''An exception type for database related exceptions'''

class MusicDB(object):
    def __init__(self, db_uri=None):
        self._db_uri = db_uri or self._get_default_db_uri()
        echo = (True if mesk_log.getLogger().isEnabledFor(mesk_log.DEBUG)
                     else False)

        # Create engine and attempt to connect, in the case of sqlite the DB
        # file is opened or created, and a exception is thrown otherwise.
        self.db_engine = sql.create_engine(self._db_uri, echo=echo)
        self.db_engine.connect()

        self.metadata = sql.MetaData(self.db_engine)

        self._sync_thread = None
        self.__session = orm.create_session(bind=self.db_engine)

    def _get_default_db_uri(self):
        db_uri = mesk_config.get(CONFIG_LIBRARY, 'db')
        if not db_uri:
            # No DB URI, make a default based on profile
            db_uri = 'sqlite:///%s/library' % MESK_DIR
            if mesk_config.profile:
                db_uri += '-%s' % mesk_config.profile
            mesk_config.set(CONFIG_LIBRARY, 'db', db_uri)
        return db_uri

    def init(self):
        # Check for tables and create if needed
        from . import labels, artists, albums, tracks, info
        for clazz in [labels.Label,
                      artists.Artist, albums.Album,
                      tracks.Track,
                      tracks.TrackLabel,
                      info.Info]:
            tbl = clazz.TABLE
            mesk_log.debug("Checking for table %s..." % tbl)
            if not self.db_engine.has_table(tbl.name):
                mesk_log.debug("Creating table %s..." % tbl)
                clazz.init_table(self.__session)
            self.__session.flush()

        # TODO: Use info.version to determine if updates to schema are needed
        self.__session.clear()

    def sync(self, lib_dirs, exclude_dirs, user_status_cb, user_file_cb=None):
        if self._sync_thread is not None:
            mesk_log.debug("Ignoring sync request as one is already in "
                             "progress")
            return

        def status_cb(status):
            # This is NOT happening on the Gtk thread
            self._sync_thread = None
            self._sync_session = None
            if user_status_cb:
                user_status_cb(status)
            mesk_log.debug("SyncThread exit status: %s" % str(bool(status)))

        sync_session = orm.create_session(bind=self.db_engine)
        self._sync_thread = SyncThread(lib_dirs, exclude_dirs,
                                       status_cb, user_file_cb,
                                       sync_session)
        self._sync_thread.start()

    def sync_stop(self):
        if self._sync_thread is None:
            return
        self._sync_thread.stop()

## end MusicDB

class SyncThread(DirScannerThread):
    def __init__(self, root_dirs, excl_dirs, status_cb, progress_cb,
                 db_session):
        '''The callback arg is called when syncing is complete or canceled.'''
        DirScannerThread.__init__(self, root_dirs, excl_dirs)

        self._status_cb = status_cb
        self._progress_cb = progress_cb
        self._log = mesk_log.getLogger("mesk-sync")
        self._status = None
        self._file_count = 0
        self._db_session = db_session
        self._num_dirs = 0
        self._dir_count = 0

        from .artists import Artist
        query = self._db_session.query(Artist)
        self._various_artists = query.get(0)
        assert(self._various_artists)

    def _sync_file(self, audio_src):
        from .tracks import Track
        self._log.debug("sync'ing : " + str(audio_src.uri))

        uri_str = str(audio_src.uri)
        track = self._db_session.query(Track).filter_by(fs_uri=uri_str).first()
        if not track:
            self._log.debug("URI not found in database: %s" % uri_str)
            self._sync_add(audio_src)
            self._db_session.flush()
            self._log.debug('%s - added' % uri_str)

        # TODO: Updates, moved files, etc.

    def _sync_add(self, audio_src):
        # Check for artist
        from .artists import Artist
        from .albums import Album
        from .tracks import Track, TrackLabel
        from .labels import Label

        audio_src_dir = \
            os.path.dirname(mesk_uri.uri_to_filesys_path(audio_src.uri))

        # Handle artists table
        (artist_name,
         artist_prefix) = split_name_prefix(audio_src.meta_data.artist)
        if not artist_name:
            raise DBWarning('No artist name for %s' % str(audio_src.uri))

        query = self._db_session.query(Artist)
        # FIXME: Artists can have the same name
        artist = query.filter_by(name=artist_name,
                                 name_prefix=artist_prefix).first()
        if not artist:
            artist = Artist(audio_src)
            self._db_session.save(artist)
            self._db_session.flush()
            self._log.debug("Artist added: %s" % str(artist))
        else:
            self._log.debug("Artist found: %s" % str(artist))

        if audio_src.meta_data.album:
            # Handle albums table
            query = self._db_session.query(Album)
            album = None
            albums = query.filter_by(title=audio_src.meta_data.album,
                                     year=audio_src.meta_data.year)
            if albums:
                # Look for an album by this name with the same artist
                for a in albums:
                    if a.artist_id == artist.id:
                        self._log.debug("Album found: %s" % str(album))
                        album = a
                        break

                if not album:
                    # No matches on artist.. is this a comp?
                    for a in albums:
                        album = None
                        track_uri = mesk_uri.make_uri(a.tracks[0].fs_uri)
                        track_path = mesk_uri.unescape(track_uri.path)

                        if audio_src_dir == os.path.dirname(track_path):
                            # Both the first track of a and the new file are
                            # in the same directory, call it a comp
                            album = a
                            if not a.compilation:
                                self._log.debug('Setting compilation bit on %s'
                                                % str(a))
                                a.compilation = True
                                a.artist_id = self._various_artists.id
                                # FIXME: Throwing exception
                                self._db_session.save(a)
                                self._db_session.flush()
                                break
                            else:
                                assert(a.artist_id == self._various_artists.id)

            if not albums or not album:
                # Add the album
                album = Album(artist.id, audio_src)
                self._db_session.save(album)
                self._log.debug("Album added: %s" % str(album))

            self._db_session.flush()
        else:
            # No album names infers a single, album_id is None
            self._log.debug('No album name for %s, marking as a single' %
                            str(audio_src.uri))
            album = None

        # Add track
        album_id = album.id if album else None
        track = Track(artist.id, album_id, audio_src=audio_src)
        self._db_session.save(track)
        self._db_session.flush()
        self._log.debug("Track added: %s" % str(track))

        # Genres go in as labels
        for g in audio_src.meta_data.genres:
            query = self._db_session.query(Label)
            label = query.filter_by(name=g).first()
            if not label:
                # Add label
                label = Label(g)
                self._db_session.save(label)
                self._db_session.flush()
                self._log.debug("Label added: %s" % g)

            # Set relation between track and genre
            label_relation = TrackLabel(track.id, label.id)
            self._db_session.save(label_relation)
            self._db_session.flush()
            self._log.debug("Track %d mapped to label %d" % (track.id,
                                                             label.id))

    def _handle_dir(self, dir_path, files):
        self._dir_count += 1
        for filename in files:
            if not audio.is_supported_ext(os.path.splitext(filename)[1]):
                self._log.debug("NOT sync'ing : " + filename)
                continue

            filename = os.path.join(dir_path, filename)
            # Update the database
            try:
                uri = mesk_uri.make_uri(mesk_uri.escape_path(filename))
                audio_src = audio.load(uri)
                self._sync_file(audio_src)
            except DBWarning, ex:
                self._log.warn('sync warning: %s' % str(ex))
            except Exception, ex:
                self._log.error("sync error [%s]: %s\n%s" %
                                (str(uri), str(ex), traceback.format_exc()))
            else:
                self._file_count += 1

        # Per dir callback
        if self._progress_cb:
            self._progress_cb(dir_path, self._num_dirs)

        return self.SCAN_CONT

    def _handle_done(self, status):
        self._status = status
        self._log.debug("sync done, status=%d" % status)

    def run(self):
        # Debugging sync time
        import time
        t1 = time.time()

        self._num_dirs = self.get_num_dirs()
        DirScannerThread.run(self)

        # Debugging sync time
        t2 = time.time()
        t = t2 - t1
        self._log.verbose("%d files sync'd in %fs (%f / file)" %
                          (self._file_count, t, t / float(self._file_count)))

        # Invoke user status callback
        if self._status_cb:
            self._status_cb(self._status)

## end SyncThread

class OrmObject(object):
    def __init__(self, **kw):
        for key in kw:
            if key in self.c:
                setattr(self, key, kw[key])
            else:
                raise AttributeError('Cannot set attribute which is' +
                                     'not column in mapped table: %s' % (key,))

    def __repr__(self):
        atts = []
        for key in self.c.keys():
            if key in self.__dict__:
                default = self.c.get(key).default
                if not (hasattr(default, 'arg') and
                        getattr(default, 'arg') == getattr(self, key)):
                    atts.append( (key, getattr(self, key)) )

        return (self.__class__.__name__ +
                '(' + ', '.join(x[0] + '=' + repr(x[1]) for x in atts) + ')')

def make_fuzzy_name(s):
    assert(isinstance(s, unicode))
    return unicode(re.compile("[^\w]", re.UNICODE).subn(u'', s)[0].lower())

def split_name_prefix(s):
    '''Given a name string (e.g., The Ramones) returns a tuple thusly:
    (unprefixed_name, prefix) where prefix may be None'''
    assert(isinstance(s, unicode))
    s_lower = s.lower()
    for prefix_lower, prefix in [('the ', 'The ')]:
        if s_lower.startswith(prefix_lower):
            return (s[len(prefix_lower):], prefix.rstrip())
    return (s, None)

