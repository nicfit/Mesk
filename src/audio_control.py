################################################################################
#  Copyright (C) 2006-2007  Travis Shirk <travis@pobox.com>
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
import gtk, gtk.glade
import os, gobject

import mesk, mesk.audio
import gst

import mesk, mesk.audio, mesk.playlist, mesk.plugin
from mesk.plugin.interfaces import AudioControlListener
from mesk.i18n import _

import control
import mesk.gtk_utils

class AudioControl(control.Control):
    # States
    (STOP,
     PLAY,
     PAUSE) = range(3)

    # Internal clock interval
    TICK_MS = 500

    # Tooltip strings
    PLAY_TOOLTIP  = _('Play')
    PAUSE_TOOLTIP = _('Pause')

    # When set_playlist is called with None, this is used. MUST have something
    NULL_PLAYLIST = mesk.playlist.Playlist()

    def __init__(self, parent_xml, parent_win, playlist=None):
        control.Control.__init__(self)

        self._parent_xml = parent_xml
        self._parent_win = parent_win
        self._playlist = playlist
        self._current_audio_src = None
        self._last_src_started = None
        self._volume_button_tip = gtk.Tooltips()
        self._volume_scale_tip = gtk.Tooltips()

        # Volume slider window
        vol_xml = mesk.gtk_utils.get_glade('volume_slider_window',
                                           'audio_control.glade')
        vol_xml.signal_autoconnect(self)
        self._volume_window = vol_xml.get_widget('volume_slider_window')
        self._volume_scale = vol_xml.get_widget('volume_scale')
        self._volume_scale_ebox = vol_xml.get_widget('volume_scale_eventbox')

        self._state = self.STOP
        self._tick_stopped = True
        self._duration = gst.CLOCK_TIME_NONE

        # Set up volume widgets
        self._volume_ebox = parent_xml.get_widget('volume_eventbox')
        self._volume_togglebutton = parent_xml.get_widget('volume_togglebutton')
        self._volume_mute_img = None
        self._volume_low_img = None
        self._volume_medium_img = None
        self._volume_high_img = None

        # Control widgets
        self._prev_button = parent_xml.get_widget('prev_button')
        self._play_pause_button = parent_xml.get_widget('play_pause_button')
        self._stop_button = parent_xml.get_widget('stop_button')
        self._next_button = parent_xml.get_widget('next_button')

        self._track_time_label = parent_xml.get_widget('track_time_label')
        self._track_scale = parent_xml.get_widget('track_scale')
        self._track_scale.set_sensitive(False)
        self._track_scale_adj = gtk.Adjustment(value = 0.0, lower = 0.0,
                                               upper = 100.0,
                                               step_incr = 0.1, page_incr = 1.0,
                                               page_size = 1.0)
        self._track_scale.set_adjustment(self._track_scale_adj)

        # Play/Pause button images
        self._play_image = gtk.image_new_from_stock(gtk.STOCK_MEDIA_PLAY,
                                                    gtk.ICON_SIZE_BUTTON)
        self._pause_image = gtk.image_new_from_stock(gtk.STOCK_MEDIA_PAUSE,
                                                     gtk.ICON_SIZE_BUTTON)
        self._play_pause_state = self.PLAY
        self._play_pause_button.remove(self._play_pause_button.get_child())
        self._play_pause_button.add(self._play_image)
        self._play_image.show()

        # Define custom signals
        gobject.signal_new('play', AudioControl, gobject.SIGNAL_RUN_LAST,
                           gobject.TYPE_NONE, [])
        gobject.signal_new('pause', AudioControl, gobject.SIGNAL_RUN_LAST,
                           gobject.TYPE_NONE, [])
        gobject.signal_new('stopped', AudioControl, gobject.SIGNAL_RUN_LAST,
                           gobject.TYPE_NONE, [])
        gobject.signal_new('next', AudioControl, gobject.SIGNAL_RUN_LAST,
                           gobject.TYPE_NONE, [])
        gobject.signal_new('prev', AudioControl, gobject.SIGNAL_RUN_LAST,
                           gobject.TYPE_NONE, [])
        gobject.signal_new('source-changed', AudioControl,
                           gobject.SIGNAL_RUN_LAST,
                           gobject.TYPE_NONE,
                           [gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT])
        gobject.signal_new('error', AudioControl, gobject.SIGNAL_RUN_LAST,
                           gobject.TYPE_NONE, [gobject.TYPE_STRING,
                                               gobject.TYPE_PYOBJECT])
        # Callback takes: widget, audio_src
        gobject.signal_new('tag-update', AudioControl, gobject.SIGNAL_RUN_LAST,
                           gobject.TYPE_NONE, [gobject.TYPE_PYOBJECT])
        gobject.signal_new('playlist-reset', AudioControl,
                           gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, [])

        # Hook up audio control events
        self._prev_button.connect('clicked', self._on_prev_button_clicked)
        self._play_pause_button.connect('clicked',
                                        self._on_play_pause_button_clicked)
        self._stop_button.connect('clicked', self._on_stop_button_clicked)
        self._next_button.connect('clicked', self._on_next_button_clicked)

        self.set_widget_sensitivites()
        mesk.log.verbose(_('Gstreamer version %d.%d.%d audio control '
                           'initialized') % (gst.gst_version[0],
                                             gst.gst_version[1],
                                             gst.gst_version[2]))
        # Initialize Gstreamer player
        from mesk.gst_player import GStreamerPlayer
        self._gst_player = GStreamerPlayer()
        self._gst_player.connect_source_notify(self._on_gst_source_notify)
        self._gst_player.connect_message_bus(self._on_gst_message)

        # Set initial volume from config
        vol = mesk.config.getfloat(mesk.CONFIG_AUDIO, 'volume')
        vol = max(vol, 0.0)
        vol = min(vol, 1.0)
        self._unmute_volume = None
        self.set_volume(vol)

        self._parent_win.connect('configure-event',
                                 self._on_main_window_configure_event)
        self._parent_xml.signal_autoconnect(self)

        import urllib2
        self._http_creds = urllib2.HTTPPasswordMgr()

    def set_playlist(self, pl):
        if pl is None:
            self._playlist = self.NULL_PLAYLIST
        else:
            self._playlist = pl

        self.set_widget_sensitivites()
        curr = self._playlist.get_curr_index()
        if curr < 0 and len(self._playlist):
            self.enqueue_source(next=True, start_playing=False)
        elif len(self._playlist):
            self.enqueue_source(absolute=curr, start_playing=False)

    def set_widget_sensitivites(self):
        if not self._playlist or not len(self._playlist):
            # No playlist, nothing to do
            self._prev_button.set_sensitive(False)
            self._play_pause_button.set_sensitive(False)
            self._stop_button.set_sensitive(False)
            self._next_button.set_sensitive(False)
            self._track_scale.set_sensitive(False)
        else:
            self._play_pause_button.set_sensitive(True)

            if self.is_playing():
                self._stop_button.set_sensitive(True)
                self._track_scale.set_sensitive(True)
            elif self.is_stopped():
                self._stop_button.set_sensitive(False)
                self._track_scale.set_sensitive(False)

            # Next/previous buttons
            self._prev_button.set_sensitive(self._playlist.has_prev())
            self._next_button.set_sensitive(self._playlist.has_next())

    def _set_track_scale(self, pos, lower = None, upper = None):
        if lower is not None:
            self._track_scale_adj.lower = lower
        if upper is not None:
            self._track_scale_adj.upper = upper
        self._track_scale_adj.value = pos

    def is_playing(self):
        return self._state == self.PLAY
    def is_paused(self):
        return self._state == self.PAUSE
    def is_stopped(self):
        return self._state == self.STOP

    def play(self):
        if self.is_playing():
            return

        self._adjusting_scale_timeout_id = None
        self._scale_mouse_event = False
        self._set_play_pause_state(self.PAUSE)

        self._gst_error_set = False
        self._state = self.PLAY
        self._gst_player.play()

        if self._gst_error_set:
            self._gst_error_set = False
            return

        self._start_play_tick()

        self.emit('play')
        mesk.plugin.emit(AudioControlListener, 'on_plugin_audio_play',
                         self._current_audio_src)
        if self._last_src_started is None:
            self._last_src_started = self._current_audio_src
            mesk.plugin.emit(AudioControlListener, 'on_plugin_source_started',
                             self._current_audio_src)

    def pause(self):
        if self.is_paused():
            return

        self._set_play_pause_state(self.PLAY)
        self._stop_play_tick()
        self._state = self.PAUSE
        self._gst_player.pause()

        self.emit('pause')
        mesk.plugin.emit(AudioControlListener, 'on_plugin_audio_pause',
                         self._current_audio_src)

    def stop(self):
        if self.is_stopped():
            return

        self._set_play_pause_state(self.PLAY)
        self._state = self.STOP
        self._gst_player.stop()
        self._stop_play_tick()
        self._set_track_scale(0.0)

        self.emit('stopped')
        self._last_src_started = None
        mesk.plugin.emit(AudioControlListener, 'on_plugin_audio_stop',
                         self._current_audio_src)

    def seek(self, location):
        '''location is the position to seek to in nanoseconds'''
        mesk.plugin.emit(AudioControlListener, 'on_plugin_audio_seek',
                         self._current_audio_src)
        unpause = False
        if self.is_playing():
            self.pause()
            unpause = True

        self._gst_player.seek(location)

        if unpause:
            self.play()

    def next(self, play=None):
        is_playing = self.is_playing() or self.is_paused()
        if is_playing:
            self.stop()
        self.enqueue_source(next=True, start_playing=(is_playing or play))
        self.set_widget_sensitivites()
        self.emit('next')

    def prev(self):
        is_playing = self.is_playing() or self.is_paused()
        if is_playing:
            self.stop()
        self.enqueue_source(prev=True, start_playing=is_playing)
        self.set_widget_sensitivites()
        self.emit('prev')

    def get_position(self):
        return (self._gst_player.get_position(),
                self._gst_player.get_duration())

    def get_volume(self):
        return self._gst_player.get_volume()

    def set_volume(self, vol):
        '''Volume is value between 0.0 and 1.0'''
        self._gst_player.set_volume(vol)

        self._set_volume_image()
        self._volume_scale.set_value(vol)
        tip_str = _('Volume %d%%') % int(vol * 100.0)
        self._volume_button_tip.set_tip(self._volume_ebox, tip_str)
        self._volume_scale_tip.set_tip(self._volume_scale_ebox, tip_str)

        # Update config
        mesk.config.set(mesk.CONFIG_AUDIO, 'volume', str(vol))

    def _set_play_pause_state(self, state):
        assert(state == self.PLAY or state == self.PAUSE)

        def update_pp_button():
            self._play_pause_button.remove(self._play_pause_button.get_child())
            if state == self.PAUSE:
                self._play_pause_state = self.PAUSE
                old_image = self._play_image
                new_image = self._pause_image
                new_tip = self.PAUSE_TOOLTIP
            else:
                self._play_pause_state = self.PLAY
                old_image = self._pause_image
                new_image = self._play_image
                new_tip = self.PLAY_TOOLTIP
            old_image.hide()
            self._play_pause_button.add(new_image)
            new_image.show()

            tips = gtk.tooltips_data_get(self._play_pause_button)[0]
            tips.set_tip(self._play_pause_button, new_tip)

        # Doing the button updates from this method would often lead to a 
        # blank button laggy (no image) update
        gobject.timeout_add(250, update_pp_button)


    def enqueue_source(self, args=None, **keywords):
        '''
        args is a dictionary supporting the following keys:
        Mutally exclusive:
        next: increment playlst (bool)
        prev: decrement playlist (bool)
        absolute: absolute list position (int)

        start_playing:  start playing the enqueued source (bool)

        Note, keyword arguments may be used in place of the args dict.
        '''

        if not args:
            args = keywords

        mesk.log.debug('AudioControl.enqueue_source: %s' % str(args))
        def arg_value(key):
            try:
                return args[key]
            except:
                return None

        if self._playlist is None:
            return

        self.stop()

        # Determine previous source
        old = self._playlist.get_curr_index()
        if old is None:
            old = -1
        elif old == -1:
            old = 0
        old_src = None
        if old is not None:
            try:
                old_src = self._playlist[old]
            except IndexError:
                pass

        # Determine new source
        src = None
        if arg_value('next'):
            src = self._playlist.get_next()
        elif arg_value('prev'):
            src = self._playlist.get_prev()
        elif arg_value('absolute') is not None:
            i = arg_value('absolute')
            try:
                src = self._playlist[i]
            except IndexError:
                i = 0
                src = self._playlist[0]
            self._playlist.set_curr_index(i)

        new = self._playlist.get_curr_index()
        if new is None or new < 0:
            new = -1

        self._last_src_started = None
        if src:
            try:
                self._set_source(src)
            except Exception, ex:
                mesk.log.error('enqueue_source error: %s' % str(ex))
                self.emit('error', ex, src)
                return

            if arg_value('start_playing'):
                self.play()
        else:
            # Emitting before reset allows listener to capture pre-reset state
            self.emit('playlist-reset')
            self._playlist.reset()
        self.emit('source-changed', (old, old_src), (new, src))

    def _set_source(self, src):
        mesk.log.debug("AudioControl._set_source %s %s" % (str(src),
                                                           str(src.uri)))
        if src and src.uri.scheme.startswith('http'):
            base_uri = os.path.dirname(str(src.uri))

            # Test http access to the URI
            import gnomevfs
            done = False
            while not done:
                try:
                    info = gnomevfs.get_file_info(src.uri)
                    done = True
                except gnomevfs.AccessDeniedError, ex:
                    # See if we have credentials cached
                    (user, pw) = self._http_creds.find_user_password('mesk',
                                                                     base_uri)
                    if not user or not pw:
                        # Handle HTTP auth
                        (resp, user, pw) = self._handle_http_auth(src.uri)
                        if resp != 0:
                            raise ex

                    # Set credentials
                    src.uri.user_name = user
                    src.uri.password = pw
                    # Try again with new creds ....
                except (gnomevfs.GenericError, gnomevfs.NotSupportedError), ex:
                    # gnomevfs does not like streams, hope for the best..
                    done = True

            if src.uri.user_name and src.uri.password:
                # Cache credentials
                self._http_creds.add_password('mesk', base_uri,
                                              src.uri.user_name,
                                              src.uri.password)

        # Initialize sink with fresh source
        self._set_track_scale(0.0)
        if src:
            self._gst_player.set_source_uri(src.uri)
        else:
            self._gst_player.set_source_uri(None)
        self._current_audio_src = src

    def _handle_http_auth(self, uri):
        auth_xml = mesk.gtk_utils.get_glade('http_auth_dialog',
                                            'audio_control.glade')
        auth_dialog = auth_xml.get_widget('http_auth_dialog')
        auth_xml.get_widget('url_label').set_text(str(uri))

        username = ''
        passwd = ''
        resp = auth_dialog.run()
        if resp == 0:
            username = auth_xml.get_widget('username_entry').get_text()
            passwd = auth_xml.get_widget('password_entry').get_text()

        auth_dialog.destroy()
        return (resp, username, passwd)

    ### Button event handlers ###
    def _on_play_pause_button_clicked(self, button):
        if self._play_pause_state == self.PLAY:
            self.play()
        else:
            self.pause()

    def _on_stop_button_clicked(self, button):
        self.stop()

    def _on_prev_button_clicked(self, button):
        self.prev()

    def _on_next_button_clicked(self, button):
        self.next()

    ### Gstreamer callbacks ###
    def _on_gst_source_notify(self, bin, pspec):
        src_elem = bin.get_property('source')

        # If the source is CD audio, make sure to point Gstreamer to the
        # correct device
        from mesk.audio.cdaudio import CDAudioSource
        if (src_elem and ('device' in dir(src_elem.props)) and
                isinstance(self._current_audio_src, CDAudioSource)):
            src_elem.set_property('device',
                                  self._current_audio_src.block_device)

    def _on_gst_message(self, bus, message):
        if message.type == gst.MESSAGE_STATE_CHANGED:
            self.set_widget_sensitivites()
        elif message.type == gst.MESSAGE_EOS:
            gobject.idle_add(mesk.plugin.emit, AudioControlListener,
                             'on_plugin_source_ended', self._current_audio_src)
            delay = mesk.config.getint(mesk.CONFIG_AUDIO, 'gst_delay')
            gobject.timeout_add(delay, self.enqueue_source,
                                {'next': True, 'start_playing': True})
        elif message.type == gst.MESSAGE_TAG:
            mesk.log.debug('Gstreamer MESSAGE_TAG: %s' % str(message))
            if not self._current_audio_src.meta_data.frozen:
                self._update_meta_data(self._current_audio_src,
                                       message.parse_tag())
        elif message.type == gst.MESSAGE_ERROR:
            self._gst_error_set = True
            error, debug = message.parse_error()

            self._set_play_pause_state(self.PLAY)
            mesk.log.error('Gstreamer error: {bus: %s}: %s\n%s' % \
                           (str(bus), str(error), str(debug)))
            self.emit('error', error, self._current_audio_src)

    def _update_meta_data(self, src, taglist):
        '''Possible keys:
        ['title', 'artist', 'album', 'date', 'track-count', 'track-number',
         'genre', 'duration']
        ['layer', 'mode', 'emphasis', 'audio-codec', 'bitrate']
        '''
        def get_tag_data(key):
            data = taglist[key]
            if type(data) is list:
                return data[0]
            elif not data:
                return ''
            else:
                return data

        changed = False
        keys = taglist.keys()
        if 'title' in keys:
            src.meta_data.title = unicode(get_tag_data('title'), 'utf-8')
        if 'artist' in keys:
            src.meta_data.artist = unicode(get_tag_data('artist'), 'utf-8')
        if 'album' in keys:
            src.meta_data.album = unicode(get_tag_data('album'), 'utf-8')
        if 'date' in keys:
            src.meta_data.year = unicode(str(get_tag_data('date').year),
                                         'utf-8')
        if 'track-number' in keys:
            src.meta_data.track_num = int(get_tag_data('track-number'))
        if 'track-count' in keys:
            src.meta_data.track_total = int(get_tag_data('track-count'))
        if 'duration' in keys:
            src.meta_data.time_secs = int(get_tag_data('duration')) / gst.SECOND
        self.emit('tag-update', src)

    ### Timer methods ###
    def _start_play_tick(self):
        self._tick_stopped = False
        gobject.timeout_add(self.TICK_MS, self._tick)

    def _stop_play_tick(self):
        self._tick_stopped = True

    def _tick(self):
        # Update the track position slider.
        position, self._duration = self.get_position()
        if position != gst.CLOCK_TIME_NONE:
            if self._duration:
                value = position * 100.0 / self._duration
            else:
                value = 0
            self._set_track_scale(value)

        return not self._tick_stopped

    ### Track scale events ###
    def _on_track_scale_button_press_event(self, event, arg):
        if self.is_playing():
            self.pause()
        self._scale_mouse_event = True
    def _on_track_scale_button_release_event(self, event, arg):
        self._scale_mouse_event = False
        self.play()
    def _on_track_scale_adjust_bounds(self, scale, value):
        if self.is_playing():
            self.pause()

        # We've scheduled the resume, but got another event so reset
        if self._adjusting_scale_timeout_id:
            gobject.source_remove(self._adjusting_scale_timeout_id)

        # Value is a percentage of the total
        self.seek(value * self._duration / 100)
        if not self._scale_mouse_event:
            # Schedule resuming play, it's not done now in case another
            # adjustment occurs in the near future, unless the mouse is
            # being used the button release schedules play
            self._adjusting_scale_timeout_id = \
                    gobject.timeout_add(450, lambda: self.play())

    def _on_track_scale_value_changed(self, scale):
        if self._duration != gst.CLOCK_TIME_NONE:
            # Keep time label in sync with scale
            p = scale.get_value() * self._duration / 100
            # _duration not used, it fluctuates and the label total should
            # be static
            d = self._current_audio_src.meta_data.time_secs
        else:
            p = d = 0
        label = mesk.utils.format_track_time(p / gst.SECOND, d)
        self._track_time_label.set_markup('<i>%s</i>' % label)

    def _set_volume_image(self):
        old_img = self._volume_togglebutton.get_child()
        if old_img:
            self._volume_togglebutton.remove(old_img)

        val = int(self._gst_player.get_volume() * 100.0)
        if val == 0:
            if not self._volume_mute_img:
                img = gtk.Image()
                img.set_from_file('data/images/audio-volume-muted.png')
                self._volume_mute_img = img
            new_img = self._volume_mute_img
        elif val <= 35:
            if not self._volume_low_img:
                img = gtk.Image()
                img.set_from_file('data/images/audio-volume-low.png')
                self._volume_low_img = img
            new_img = self._volume_low_img
        elif val <= 68:
            if not self._volume_medium_img:
                img = gtk.Image()
                img.set_from_file('data/images/audio-volume-medium.png')
                self._volume_medium_img = img
            new_img = self._volume_medium_img
        else:
            if not self._volume_high_img:
                img = gtk.Image()
                img.set_from_file('data/images/audio-volume-high.png')
                self._volume_high_img = img
            new_img = self._volume_high_img

        self._volume_togglebutton.add(new_img)
        new_img.show()

    ### Volume events ###
    def _on_volume_togglebutton_scroll_event(self, widget, event):
        curr_vol = self._gst_player.get_volume()

        FACTOR = 0.04
        if event.direction == gtk.gdk.SCROLL_UP:
            new_vol = curr_vol + FACTOR
        elif event.direction == gtk.gdk.SCROLL_DOWN:
            new_vol = curr_vol - FACTOR
        else:
            return

        # Coerce vol to an acceptable range
        if new_vol < 0.0:
            new_vol = 0.0
        elif new_vol > 1.0:
            new_vol = 1.0

        self.set_volume(new_vol)

    def _on_volume_togglebutton_toggled(self, button):
        # Show or hide the volume scale window
        if button.get_active():
            self._volume_button_tip.disable()
            self._volume_scale_tip.enable()

            # Volume window position is in line with wutton, but below it
            x0, y0 = self._volume_ebox.window.get_origin()
            self._volume_window.move(x0,
                                     y0 + self._volume_ebox.allocation.height)
            # Make the volume window as wide as the volume button
            ebox_sz = self._volume_ebox.size_request()
            win_sz = self._volume_window.size_request()
            self._volume_window.set_size_request(ebox_sz[0], win_sz[1])
            self._volume_window.show()
            self._volume_scale.grab_focus()
        else:
            self._volume_scale_tip.disable()
            self._volume_button_tip.enable()
            self._volume_window.hide()

    def _on_volume_togglebutton_button_press_event(self, button, event):
        if event.button == 3:
            popup_xml = mesk.gtk_utils.get_glade('volume_button_menu',
                                                 'audio_control.glade')
            popup_xml.signal_autoconnect(self)
            popup = popup_xml.get_widget('volume_button_menu')

            # Make mute menuitem label depend on current state
            for c in popup.get_children():
                if c.get_name() == 'mute_menuitem':
                    mute = (self._gst_player.get_volume() > 0.0)
                    for subc in c.get_children():
                        if isinstance(subc, gtk.Label):
                            if mute:
                                subc.set_text(_('Mute Volume'))
                            else:
                                subc.set_text(_('Restore Volume'))
                        elif isinstance(subc, gtk.Image):
                            if mute:
                                subc.set_from_stock(gtk.STOCK_NO,
                                                    gtk.ICON_SIZE_MENU)
                            else:
                                subc.set_from_stock(gtk.STOCK_YES,
                                                    gtk.ICON_SIZE_MENU)
                    break

            popup.popup(None, None, None, event.button, event.time)
            return True
        elif event.type == gtk.gdk._2BUTTON_PRESS:
            self._open_mixer()
            return True
        return False

    def _on_main_window_configure_event(self, window, event):
        if self._volume_togglebutton.get_active():
            # The first stab at this I hid the volume window as soon as
            # the top-level moved (self._volume_togglebutton.set_active(False))
            # but emitting toggled makes the volume window follow the main
            # window, which is definitely cooler (but laggy somethimes)
            self._volume_togglebutton.toggled()

    def _on_volume_scale_value_changed(self, scale):
        self.set_volume(scale.get_value())

    def toggle_mute(self):
        curr_vol = self._gst_player.get_volume()
        if curr_vol <= 0:
            # We are currently muted, treat as an "unmute"
            if not self._unmute_volume:
                self._unmute_volume = 0.5
            self.set_volume(self._unmute_volume)
            self._unmute_volume = None
        else:
            self._unmute_volume = curr_vol
            self.set_volume(0.0)

    ### Volume menu handlers ###
    def _on_mute_menuitem_activate(self, menuitem):
        self.toggle_mute()

    def _on_25_percent_menuitem_activate(self, menuitem):
        self.set_volume(0.25)
    def _on_50_percent_menuitem_activate(self, menuitem):
        self.set_volume(0.50)
    def _on_75_percent_menuitem_activate(self, menuitem):
        self.set_volume(0.75)
    def _on_100_percent_menuitem_activate(self, menuitem):
        self.set_volume(1.0)
    def _on_open_mixer_menuitem_activate(self, menuitem):
        self._open_mixer()

    def _open_mixer(self):
        mixer = mesk.config.get(mesk.CONFIG_AUDIO, 'mixer_command')
        mesk.log.info('Running mixer: ' + mixer)
        pid = os.spawnlp(os.P_NOWAIT, mixer)
