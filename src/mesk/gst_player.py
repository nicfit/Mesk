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
import gobject

from . import MeskException
from . import log as mesk_log
from . import config as mesk_config
from .config import (CONFIG_AUDIO, GST_AUTO_SINK, GST_GCONF,
                     GST_ALSA, GST_ESD, GST_OSS)
import gst

class GStreamerPlayer(object):

    def __init__(self):
        (self._sink_name, self._sink) = self._init_sink()
        if not self._sink:
            raise MeskException('Unable to locate a valid Gstreamer sync')

        self._playbin = None
        self._init_pipeline()

    def set_source_uri(self, uri):
        uri = uri or ''
        self._playbin.set_property('uri', str(uri))

    def play(self):
        self._playbin.set_state(gst.STATE_PLAYING)

    def pause(self):
        self._playbin.set_state(gst.STATE_PAUSED)

    def stop(self):
        self._playbin.set_state(gst.STATE_NULL)
        self._playbin.set_state(gst.STATE_READY)

    def get_position(self):
        try:
            position, format = self._playbin.query_position(gst.FORMAT_TIME)
        except:
            position = gst.CLOCK_TIME_NONE
        return position

    def get_duration(self):
        try:
            duration, format = self._playbin.query_duration(gst.FORMAT_TIME)
        except:
            duration = gst.CLOCK_TIME_NONE
        return duration

    def seek(self, location):
        event = gst.event_new_seek(1.0, gst.FORMAT_TIME,
                                   gst.SEEK_FLAG_FLUSH | gst.SEEK_FLAG_ACCURATE,
                                   gst.SEEK_TYPE_SET, location,
                                   gst.SEEK_TYPE_NONE, 0)
        if self._playbin.send_event(event):
            mesk_log.debug('Seeking to location %r' % location)
            self._playbin.set_new_stream_time(0L)
            return True
        else:
            mesk_log.error('Seeking to location %r failed' % location)
            return False

    def set_volume(self, vol):
        '''Set the percent volume, where 0.0 <= volume <= 1.0'''
        if vol < 0.0:
            vol = 0.0
        elif vol > 1.0:
            vol = 1.0
        elif vol == self.get_volume():
            return
        self._playbin.set_property('volume', vol)

    def get_volume(self):
        '''Get the percent volume, where 0.0 <= volume <= 1.0'''
        return self._playbin.get_property('volume')

    def connect_source_notify(self, cb):
        self._playbin.connect('notify::source', cb)

    def connect_message_bus(self, cb):
        self._playbin.get_bus().connect('message', cb)

    def _init_sink(self):
        config_sink = mesk_config.get(CONFIG_AUDIO, 'gst_sink')
        if not config_sink:
            config_sink = GST_AUTO_SINK

        name = audio_sink = None
        # Try and locate the preferred sink, and falback from best to worst, IMO
        for sink in [config_sink, GST_GCONF, GST_AUTO_SINK,
                     GST_ALSA, GST_OSS, GST_ESD]:
            try:
                mesk_log.debug('Trying gst sink: %s' % sink)
                audio_sink = gst.parse_launch(sink)
                name = sink
                break
            except gobject.GError, ex:
                mesk_log.warn('Missing gst sink: %s' % str(ex))
        mesk_log.verbose('Gstreamer sink: %s' % name)
        return (name, audio_sink)

    def _init_pipeline(self):
        if self._playbin:
            # Cleanup existing bin
            self._playbin.set_state(gst.STATE_NULL)
            del self._playbin

        self._playbin = gst.element_factory_make('playbin', 'player')
        self._playbin.set_property('audio-sink', self._sink)
        self._playbin.set_property('video-sink', None)

        bus = self._playbin.get_bus()
        bus.add_signal_watch()

        self._playbin.set_state(gst.STATE_READY)

