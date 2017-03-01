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
from . import database

class Album(database.OrmObject):
    TABLE = sql.Table('albums', mesk_db.metadata,
                      sql.Column('id', sql.INT, primary_key=True),
                      sql.Column('artist_id', sql.INT,
                                 sql.ForeignKey('artists.id'), nullable=False),
                      sql.Column('title', sql.Unicode(128), nullable=False,
                                 index=True),
                      sql.Column('fuzzy_title', sql.Unicode(128),
                                 nullable=False),
                      sql.Column('year', sql.INT, nullable=False),
                      sql.Column('compilation', sql.BOOLEAN, nullable=False,
                                 default=False),
                      sql.Column('date_added', sql.Date(), nullable=False),
                      sql.UniqueConstraint('title', 'artist_id', 'year'),
                      )

    def __init__(self, artist_id, audio_src=None, title=None, year=None,
                 compilation=False):
        self.id = None
        self.artist_id = artist_id

        if audio_src:
            title = audio_src.meta_data.album
            year = audio_src.meta_data.year
        elif not title or year is None:
            assert(True)

        self.title = title
        self.fuzzy_title = database.make_fuzzy_name(self.title)
        self.year = int(year) if year is not None else 0
        self.compilation = compilation
        self.date_added = datetime.date.today()

    @staticmethod
    def init_table(session):
        Album.TABLE.create()

from . import tracks
orm.mapper(Album, Album.TABLE,
           properties={'tracks': orm.relation(tracks.Track)})
