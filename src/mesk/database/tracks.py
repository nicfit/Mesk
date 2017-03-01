# -*- coding: utf-8 -*-
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
import datetime
import sqlalchemy as sql
from sqlalchemy import orm

from . import db as mesk_db
from .database import make_fuzzy_name, split_name_prefix, OrmObject
from . import labels

class Track(OrmObject):
    TABLE = sql.Table('tracks', mesk_db.metadata,
                      sql.Column('id', sql.INT, primary_key=True),
                      sql.Column('artist_id', sql.INT,
                                 sql.ForeignKey('artists.id'), nullable=False),
                      sql.Column('album_id', sql.INT,
                                 sql.ForeignKey('albums.id'), nullable=True),
                      sql.Column('title', sql.Unicode(128), nullable=False,
                                 index=True),
                      sql.Column('fs_uri', sql.String(512), nullable=False,
                                 unique=True, index=True),
                      sql.Column('date_added', sql.Date(), nullable=False),
                      sql.Column('track_num', sql.SmallInteger),
                      sql.Column('track_total', sql.SmallInteger),
                      sql.Column('time_secs', sql.Integer),
                      sql.Column('size_bytes', sql.Integer, nullable=False),
                     )

    def __init__(self, artist_id, album_id, title=None, audio_src=None,
                 fs_uri=None):
        '''Constructor'''
        self.id = None
        self.artist_id = artist_id
        self.album_id = album_id
        self.title = title or u''
        self.date_added = datetime.date.today()

        if audio_src:
            self.fs_uri = str(audio_src.uri)
            self.title = audio_src.meta_data.title
            self.track_num = audio_src.meta_data.track_num
            self.track_total = audio_src.meta_data.track_total
            self.time_secs = audio_src.meta_data.time_secs
            self.size_bytes = audio_src.meta_data.size_bytes
        else:
            if fs_uri:
                self.fs_uri = str(fs_uri)
            if title:
                self.title = title

    @staticmethod
    def init_table(session):
        Track.TABLE.create()

class TrackLabel(OrmObject):
    TABLE = sql.Table('track_labels', mesk_db.metadata,
                      sql.Column('track_id', sql.Integer,
                                 sql.ForeignKey('tracks.id'), nullable=False),
                      sql.Column('label_id', sql.Integer,
                                 sql.ForeignKey('labels.id'), nullable=False),
                     )

    def __init__(self, track_id, label_id):
        assert(track_id is not None)
        assert(label_id is not None)
        self.track_id = track_id
        self.label_id = label_id

    @staticmethod
    def init_table(session):
        TrackLabel.TABLE.create()

# Table relations
orm.mapper(Track, Track.TABLE,
           properties={'labels': orm.relation(TrackLabel)})

orm.mapper(TrackLabel, TrackLabel.TABLE,
           primary_key=[TrackLabel.TABLE.c.track_id,
                        TrackLabel.TABLE.c.label_id],
           properties={'track': orm.relation(Track),
                       'label': orm.relation(labels.Label)})
