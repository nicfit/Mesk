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
import sys, os.path, logging
import gobject
from logging import DEBUG, INFO, WARNING, ERROR, CRITICAL

from .info import APP_NAME

VERBOSE = 15
LEVEL2STRINGS = {DEBUG: "DEBUG",
                 VERBOSE: "VERBOSE",
                 INFO: "INFO",
                 WARNING: "WARNING",
                 ERROR: "ERROR",
                 CRITICAL: "CRITICAL"}
STRINGS2LEVELS = {}
for l in LEVEL2STRINGS:
    STRINGS2LEVELS[LEVEL2STRINGS[l]] = l
STRINGS2LEVELS["WARN"] = WARNING  # synonym

def init(config):
    '''Initialize mesk.log using the passed in config'''
    logging.addLevelName(VERBOSE, 'VERBOSE')

    logging.setLoggerClass(MeskLogger)
    set_logging_level(get_logging_level(config))

_all_loggers = {}
_level = WARNING
class MeskLogger(logging.Logger):
    def __init__(self, name):
        logging.Logger.__init__(self, name)

        self.console_handler = logging.StreamHandler()
        self.console_handler.setFormatter(ConsoleFormatter())
        self.addHandler(self.console_handler)

        self.tb_handler = TextBufferLogHandler()
        self.tb_handler.setFormatter(ConsoleFormatter())
        self.addHandler(self.tb_handler)

        global _level
        global _all_loggers
        if name != "mesk":
            self.setLevel(logging.getLogger('mesk').getEffectiveLevel())
        else:
            self.setLevel(_level)
        _all_loggers[name] = self

    def verbose(self, msg):
        '''Log a verbose message.'''
        self.log(VERBOSE, msg)

def debug(msg):
    '''Log a debug message.'''
    logging.getLogger('mesk').debug(msg)
def verbose(msg):
    '''Log a verbose message.'''
    logging.getLogger('mesk').log(VERBOSE, msg)
def info(msg):
    '''Log an info message.'''
    logging.getLogger('mesk').info(msg)
def warn(msg):
    '''Log a warning message.  See the warning function.'''
    warning(msg)
def warning(msg):
    '''Log a warning message.'''
    logging.getLogger('mesk').warning(msg)
def error(msg):
    '''Log an error message.'''
    logging.getLogger('mesk').error(msg)
def critical(msg):
    '''Log a critical message.'''
    logging.getLogger('mesk').critical(msg)

def getLogger(name=None):
    '''Get a logger by name.  If name is None the default logger (mesk) is
       returned.'''
    if not name:
        name = 'mesk'
    return logging.getLogger(name)

def get_logging_level(config=None):
    '''Returns a log level.  If config is None (the default) the current active
    level is returned.  Otherwise the value in the config is mapped to a
    level constant.'''
    if config is None:
        return logging.getLogger('mesk').getEffectiveLevel()
    else:
        l = config.get('mesk', 'log_level')
        return string_to_level(l)

def set_logging_level(level):
    '''Set the active log level.'''
    global _level
    _level = level
    for logger in _all_loggers.values():
        logger.setLevel(level)

def string_to_level(l):
    '''Maps a level string to one of the level contants defined in this
    module, or returns None when the string is not recognized.'''
    return STRINGS2LEVELS[l.upper()]

def level_to_string(l):
    return LEVEL2STRINGS[l]

class TextBufferLogHandler(logging.Handler):
    '''A logging Handler that sends logs to a TextBuffer.  All messages recv'd
    before this assocation are buffered'''
    def __init__(self):
        logging.Handler.__init__(self)
        self._text_buffer = None
        self._rec_buffer = []

    def set_text_buffer(self, tv):
        if self._text_buffer:
            return # Can be set once
        self._text_buffer = tv
        self.flush()

    def flush(self):
        if self._text_buffer is None:
            return

        for rec in self._rec_buffer:
            self.emit(rec)
        self._rec_buffer = []

    def emit(self, record):
        if self._text_buffer is None:
            self._rec_buffer.append(record)
            return

        # No idea what thread we're being called on so get on the event loop
        gobject.idle_add(lambda: self._text_buffer.insert(
                                           self._text_buffer.get_end_iter(),
                                           '%s\n' % self.format(record)))

class ConsoleFormatter(logging.Formatter):
    DEFAULT_FORMAT = '%(name)s: %(asctime)s [%(levelname)s]: %(message)s'
    def __init__(self):
        logging.Formatter.__init__(self, self.DEFAULT_FORMAT)
