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
import sys, os

# Load config object with module level access
from config import *
config = Config(OPTIONS)

# Make starting mesk dirs if needed
if not os.path.isdir(MESK_DIR):
    os.mkdir(MESK_DIR, 0751)
    os.mkdir(DEFAULT_PLAYLISTS_DIR, 0751)
    os.mkdir(DEFAULT_PLUGINS_DIR, 0751)

import mesk.log
from .utils import MeskException
