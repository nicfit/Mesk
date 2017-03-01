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

class Info(database.OrmObject):
    TABLE = sql.Table('info', mesk_db.metadata,
                      sql.Column('version', sql.String(32), nullable=False),
                      sql.Column('sync_datetime', sql.TIMESTAMP,
                                 nullable=False, primary_key=True))

    @staticmethod
    def init_table(session):
        Info.TABLE.create()

orm.mapper(Info, Info.TABLE)
