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
import sqlalchemy as sql
from sqlalchemy import orm

from . import db as mesk_db
from . import database

class Genre(database.OrmObject):
    TABLE = sql.Table('genres', mesk_db.metadata,
                      sql.Column('id', sql.Integer, primary_key=True),
                      sql.Column('name', sql.String(64), nullable=False))

    def __repr__(self):
        return "%s(%r,%r)" % (self.__class__.__name__,
                              self.id, self.name)

    def __init__(self, name, id=None):
        assert(name)
        self.id = id
        self.name = name

    @staticmethod
    def init_table(session):
        Genre.TABLE.create()

        import eyeD3.id3
        id = 0
        for g in eyeD3.id3.genres:
            if g != 'Unknown':
                session.save(Genre(g, id))
            else:
                break
            id += 1
        session.save(Genre(g, 255))
        session.flush()

orm.mapper(Genre, Genre.TABLE)
