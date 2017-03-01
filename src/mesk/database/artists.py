#!/usr/bin/env python
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

class Artist(database.OrmObject):
    TABLE = sql.Table('artists', mesk_db.metadata,
                      sql.Column('id', sql.Integer, primary_key=True),
                      sql.Column('name', sql.Unicode(128), nullable=False,
                                 index=True),
                      sql.Column('name_prefix', sql.Unicode(10)),
                      sql.Column('fuzzy_name', sql.Unicode(128)),
                      sql.Column('date_added', sql.Date(), nullable=False),
                     )

    def __init__(self, audio_src=None, name=None):
        self.id = None

        if audio_src:
            name = audio_src.meta_data.artist
        assert(name)

        self.name, self.name_prefix = database.split_name_prefix(name)
        self.fuzzy_name = database.make_fuzzy_name(self.name)
        self.date_added = datetime.date.today()

    @staticmethod
    def init_table(session):
        Artist.TABLE.create()
        va = Artist(name=u'mesk:Various Artists')
        va.id = 0
        session.save(va)
        session.flush()


from . import albums
orm.mapper(Artist, Artist.TABLE,
           properties={'albums': orm.relation(albums.Album)})
