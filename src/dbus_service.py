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
import gobject
import dbus, dbus.service, dbus.glib
import mesk
import config, playlist_control

INTERFACE = 'net.nicfit.mesk.MeskAppInterface'

def get_service_name(profile):
    return _append_profile('net.nicfit.mesk.MeskApp.', profile)
def get_object_path(profile):
    return _append_profile('/net/nicfit/mesk/MeskApp/', profile)

def is_service_running(profile):
    sbus = dbus.SessionBus()
    interface = dbus.Interface(sbus.get_object('org.freedesktop.DBus',
                                               '/org/freedesktop/DBus'),
                               'org.freedesktop.DBus')
    return get_service_name(profile) in interface.ListNames()

PROFILE_FILTER = ([chr(v) for v in range(ord('a'), ord('z') + 1)] +
                  [chr(v) for v in range(ord('A'), ord('Z') + 1)] +
                  ['_', '-'])
def _append_profile(prefix, profile):
    if not profile:
        profile = 'profile_default'
    else:
        # Make a safe dbus identifier name
        safe_profile = ''
        for c in profile:
            if c not in PROFILE_FILTER:
                safe_profile += '_'
            else:
                safe_profile += c
        profile = 'profile_%s' % safe_profile
    return prefix + profile

class MeskDbusService(dbus.service.Object):
    '''A dbus service object for Mesk'''

    def __init__(self, bus_name, profile, main_win):
        self._main_win = main_win
        self._profile = profile
        obj_path = get_object_path(self._profile)
        dbus.service.Object.__init__(self, bus_name, obj_path)

        self._audio_control = self._main_win._audio_control
        self._audio_control.connect('source-changed',
                                    self._on_audio_source_changed)
        self._audio_control.connect('tag-update',
                                    self._on_audio_source_tag_update)
        self.current_src = None

    @dbus.service.method(INTERFACE, in_signature='', out_signature='')
    def stop(self):
        self._audio_control.stop()

    @dbus.service.method(INTERFACE, in_signature='', out_signature='')
    def play(self):
        self._audio_control.play()

    @dbus.service.method(INTERFACE, in_signature='', out_signature='')
    def pause(self):
        self._audio_control.pause()

    @dbus.service.method(INTERFACE, in_signature='', out_signature='')
    def prev(self):
        self._audio_control.prev()

    @dbus.service.method(INTERFACE, in_signature='', out_signature='')
    def next(self):
        self._audio_control.next()

    @dbus.service.method(INTERFACE, in_signature='', out_signature='s')
    def get_state(self):
        if self._audio_control.is_playing():
            return 'playing'
        elif self._audio_control.is_paused():
            return 'paused'
        else:
            return 'stopped'

    @dbus.service.method(INTERFACE, in_signature='', out_signature='')
    def play_pause(self):
        if self._audio_control.is_playing():
            self._audio_control.pause()
        else:
            self._audio_control.play()

    @dbus.service.method(INTERFACE, in_signature='', out_signature='')
    def toggle_mute(self):
        self._audio_control.toggle_mute()

    @dbus.service.method(INTERFACE, in_signature='d', out_signature='')
    def vol_up(self, n):
        self._audio_control.set_volume(self._audio_control.get_volume() + n)

    @dbus.service.method(INTERFACE, in_signature='d', out_signature='')
    def vol_down(self, n):
        self._audio_control.set_volume(self._audio_control.get_volume() - n)

    @dbus.service.method(INTERFACE, in_signature='', out_signature='s')
    def get_current_uri(self):
        if self.current_src:
            return str(self.current_src.uri)
        else:
            return ''

    @dbus.service.method(INTERFACE, in_signature='', out_signature='s')
    def get_current_title(self):
        if self.current_src:
            return self.current_src.meta_data.title.encode('utf-8')
        else:
            return u''

    @dbus.service.method(INTERFACE, in_signature='', out_signature='s')
    def get_current_artist(self):
        if self.current_src:
            return self.current_src.meta_data.artist.encode('utf-8')
        else:
            return u''.encode('utf-8')

    @dbus.service.method(INTERFACE, in_signature='', out_signature='s')
    def get_current_album(self):
        if self.current_src:
            return self.current_src.meta_data.album.encode('utf-8')
        else:
            return u''.encode('utf-8')

    @dbus.service.method(INTERFACE, in_signature='', out_signature='i')
    def get_current_year(self):
        if self.current_src:
            return dbus.Int32(self.current_src.meta_data.year)
        else:
            return dbus.Int32(0)

    @dbus.service.method(INTERFACE, in_signature='', out_signature='i')
    def get_current_length(self):
        if self.current_src:
            return dbus.Int32(self.current_src.meta_data.time_secs)
        else:
            return dbus.Int32(0)

    @dbus.service.method(INTERFACE, in_signature='', out_signature='as')
    def list_playlists(self):
        return config.get_all_playlist_names()

    @dbus.service.method(INTERFACE, in_signature='', out_signature='s')
    def get_active_playlist(self):
        ctrl = self._get_active_playlist_ctrl()
        if ctrl:
            return ctrl.name
        else:
            return ''

    @dbus.service.method(INTERFACE, in_signature='s', out_signature='b')
    def set_active_playlist(self, name):
        open_playlists = \
          self._main_win.get_controls_by_type(playlist_control.PlaylistControl)
        for ctrl in open_playlists:
            if ctrl.name == name:
                self._main_win.set_active_control(ctrl)
                return dbus.Boolean(True)
        return dbus.Boolean(False)

    @dbus.service.method(INTERFACE, in_signature='s', out_signature='b')
    def enqueue(self, uri):
        pl_ctrl = self._select_playlist()
        if not pl_ctrl:
            return dbus.Boolean(False)

        pl_ctrl.add_uris([uri])
        return dbus.Boolean(True)

    @dbus.service.method(INTERFACE, in_signature='', out_signature='')
    def toggle_visible(self):
        if not self._main_win.is_visible():
            self._main_win.show()
        else:
            self._main_win.hide()

    @dbus.service.method(INTERFACE, in_signature='', out_signature='')
    def raise_window(self):
        # Seemingly, both of these calls are needed.
        self._main_win.present()
        self._main_win.show()

    def _get_active_playlist_ctrl(self):
        open_playlists = \
          self._main_win.get_controls_by_type(playlist_control.PlaylistControl)
        for ctrl in open_playlists:
            if ctrl.is_active():
                return ctrl
        return None

    def _select_playlist(self):
        '''This method is used to select a playlist for enqueueing URIs. It
        may return None'''
        active_pl = self._get_active_playlist_ctrl()
        if active_pl:
            return active_pl

        from playlist_control import PlaylistControl
        playlist_ctrls = self._main_win.get_controls_by_type(PlaylistControl)
        if playlist_ctrls:
            return playlist_ctrls[0]

        return None

    def _on_audio_source_changed(self, ctrl, old, new):
        if new is None:
            return
        self.current_src = new[1]

    def _on_audio_source_tag_update(self, ctrl, src):
        self.current_src = src
