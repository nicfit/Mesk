################################################################################
#  Copyright (C) 2003-2004 Vincent Hanquez <tab@snarc.org>
#  Copyright (C) 2003-2006 Yann Le Boulanger <asterix@lagaule.org>
#  Copyright (C) 2006 Nikos Kouremenos <kourem@gmail.com>
#  Copyright (C) 2006 Travis Shirk <travis@pobox.com>
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

### NOTE: Thanks to the Gajim <http://gajim.org/> project for this code

import os, sys

# WRT install environment, the dir containing lang mesk i18n files (dir/mesk)
DIR = '../../share/locale'
DIR = os.path.abspath(os.getcwd() + os.sep + DIR)

import locale, gettext
_translation = None
try:
    # set '' so each part of the locale that should be modified is set
    # according to the environment variables
    locale.setlocale(locale.LC_ALL, '')
    _translation = gettext.translation('mesk', DIR)
except Exception, ex:
    _translation = gettext.NullTranslations()

def _(s):
    if s == '':
        return s
    return _translation.ugettext(s)

def Q_(s):
    # Qualified translatable strings
    # Some strings are too ambiguous to be easily translated.
    # so we must use as:
    # s = Q_('?vcard:Unknown')
    # widget.set_text(s)
    # Q_() removes the ?vcard: 
    # but gettext while parsing the file detects ?vcard:Unknown as a whole
    # string.
    # translator can either put the ?vcard: part or no (easier for him/her to
    # no) nothing fails
    s = _(s)
    if s[0] == '?':
        s = s[s.find(':')+1:] # remove ?abc: part
    return s

def ngettext(s_sing, s_plural, n, replace_sing = None, replace_plural = None):
    '''use as:
    i18n.ngettext('leave room %s', 'leave rooms %s', len(rooms), 'a', 'a, b, c')
    in other words this is a hack to ngettext() to support %s %d etc..
    '''
    text = _translation.ungettext(s_sing, s_plural, n)
    if n == 1 and replace_sing is not None:
        text = text % replace_sing
    elif n > 1 and replace_plural is not None:
        text = text % replace_plural
    return text
