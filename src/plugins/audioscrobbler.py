# -*- coding: utf-8 -*-
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
import os, sys, md5
import urllib, urllib2
import time, datetime
import threading
import pickle
import gtk, gtk.glade, gobject

import mesk
import mesk.plugin
from mesk.i18n import _
from mesk.plugin.plugin import PluginInfo, Plugin
from mesk.plugin.interfaces import AudioControlListener, ViewMenuProvider

# AudioScrobbler plugin vaiables
PROTOCOL_VERSION = '1.1'
APP              = 'mes'
VERSION          = '0.1'

HANDSHAKE_CODES  = ('UPTODATE', 'UPDATE', 'FAILED', 'BADUSER')
SUBMISSION_CODES = ('FAILED', 'BADAUTH', 'OK')
HANDSHAKE_URL = 'http://post.audioscrobbler.com/?hs=true&p=%s&c=%s&v=%s&u=%s'

NAME = 'audioscrobbler'
CONFIG_SECTION = NAME
MAX_SUBMIT = 10

class AudioscrobblerPlugin(Plugin, AudioControlListener, ViewMenuProvider):

    def __init__(self):
        Plugin.__init__(self, PLUGIN_INFO)

        self.user = ''
        self.passwd = ''
        self.submit_tracks = True
        self.md5_passwd = None
        self.last_handshake = None
        self.md5_challenge = None
        self.submit_url = None

        # Status label values
        self.status_state = 'Auth Required'
        self.status_submitted = 0
        self.status_queued = 0
        self.status_last_submit = 'None'
        self.status_labels = {}

        self.queue_lock = threading.Lock()
        self.queue = []
        profile = ''
        if mesk.config.profile:
            profile = '_%s' % mesk.config.profile
        self.queue_filename = mesk.MESK_DIR + os.sep + 'tmp' + os.sep + \
                              ('%s%s.queue' % (NAME, profile))

        self.may_submit = threading.Event()
        self.handshake_task = None
        self.submit_task = None

        if mesk.config.has_section(CONFIG_SECTION):
            self.user = mesk.config.get(CONFIG_SECTION, 'username')
            self.passwd = mesk.config.get(CONFIG_SECTION, 'password')
            self.queue_filename = mesk.config.get(CONFIG_SECTION, 'queue_file')
            self.submit_tracks = mesk.config.getboolean(CONFIG_SECTION,
                                                        'submit_tracks', True)
            self.md5_passwd = self.get_md5(self.passwd)
            self.handshake()
        else:
            mesk.config.add_section(CONFIG_SECTION)
            mesk.config.set(CONFIG_SECTION, 'username', self.user)
            mesk.config.set(CONFIG_SECTION, 'password', self.passwd)
            mesk.config.set(CONFIG_SECTION, 'submit_tracks', self.submit_tracks)
            mesk.config.set(CONFIG_SECTION, 'queue_file', self.queue_filename)

        q_dir = os.path.dirname(self.queue_filename)
        if os.path.exists(self.queue_filename):
            self.queue = pickle.load(open(self.queue_filename, 'r'))
            self.status_queued = len(self.queue)
            self.log.verbose('Loaded %d queued tracks' % self.status_queued)
        elif not os.path.exists(q_dir):
            # Create tmp dir for queue
            self.log.verbose('Creating queue file directory')
            os.makedirs(q_dir)

        self.bad_auth_dialog = None

    def shutdown(self):
        self.log.debug('Shutting down...')
        self._cancel_handshake()
        self._cancel_submit()

        # Save pending queue
        self.log.verbose('Saving %d queued tracks' % len(self.queue))
        pickle.dump(self.queue, open(self.queue_filename, 'w'))

    def is_configurable(self):
        return True

    def get_config_widget(self, parent):
        self.config_parent = parent
        from mesk.gtk_utils import default_linkbutton_callback
        self.config_glade = gtk.glade.XML('./plugins/plugins_gui.glade',
                                          'audioscrobbler_config_vbox', 'mesk')
        self.config_glade.signal_autoconnect(self)
        self.config_widget = \
            self.config_glade.get_widget('audioscrobbler_config_vbox')
        # Add linkbuttons since glade2 does not support them yet
        join_url = 'http://www.last.fm/signup.php'
        group_url = 'http://www.last.fm/group/Mesk%2BUsers/join/'
        join_button = gtk.LinkButton(join_url, 'Join Last.FM')
        join_button.connect('clicked', default_linkbutton_callback)
        group_button = gtk.LinkButton(group_url,
                                      'Join the Mesk Last.FM group')
        group_button.connect('clicked', default_linkbutton_callback)
        hbox = self.config_glade.get_widget('linkbutton_hbox')
        hbox.pack_start(join_button)
        hbox.pack_start(group_button)
        hbox.show_all()

        self.status_labels = {
            'state': self.config_glade.get_widget('state_label'),
            'submitted': self.config_glade.get_widget('submitted_label'),
            'queued': self.config_glade.get_widget('queued_label'),
            'last': self.config_glade.get_widget('last_submit_label'),
            }

        # Populate current config values
        self.config_glade.get_widget('username_entry').set_text(self.user)
        self.config_glade.get_widget('password_entry').set_text(self.passwd)
        self.config_glade.get_widget('password_verify_entry')\
                         .set_text(self.passwd)

        self._update_status()

        enabled_checkbutton = self.config_glade.get_widget('submit_checkbutton')
        enabled_checkbutton.set_active(self.submit_tracks)
        enabled_checkbutton.emit('toggled')

        return self.config_widget

    def _update_status(self, state=None, submit_count=None, queue_count=None,
                       last_submit=None):
        if state is not None:
            self.status_state = state
        if submit_count is not None:
            self.status_submitted = submit_count
        if queue_count is not None:
            self.status_queued = queue_count
        if last_submit is not None:
            self.status_last_submit = last_submit

        def idle_update():
            # This must always execute on the gui thread
            if not self.status_labels:
                return
            self.status_labels['state'].set_text(self.status_state)
            self.status_labels['submitted'].set_text(str(self.status_submitted))
            self.status_labels['queued'].set_text(str(self.status_queued))
            self.status_labels['last'].set_text(self.status_last_submit)
        gobject.idle_add(idle_update)

    def _on_enable_checkbutton_toggled(self, checkbutton):
        # Set all table children's sensitivity based on enabled state
        table = self.config_glade.get_widget('profile_info_table')
        for child in table.get_children():
            child.set_sensitive(checkbutton.get_active())

    def config_ok(self):
        username = self.config_glade.get_widget('username_entry').get_text()
        pw = self.config_glade.get_widget('password_entry').get_text()
        pw_verify = \
            self.config_glade.get_widget('password_verify_entry').get_text()
        active = self.config_glade.get_widget('submit_checkbutton').get_active()

        # Validate input
        if not username or not pw or not pw_verify:
            d = gtk.MessageDialog(self.config_parent, gtk.DIALOG_MODAL,
                                  type=gtk.MESSAGE_ERROR,
                                  buttons=gtk.BUTTONS_OK,
                                  message_format=_('Username and password '
                                                   'required'))
            d.run()
            d.destroy()
            return
        elif pw != pw_verify:
            d = gtk.MessageDialog(self.config_parent, gtk.DIALOG_MODAL,
                                  type=gtk.MESSAGE_ERROR,
                                  buttons=gtk.BUTTONS_OK,
                                  message_format=_('Passwords do not match'))
            d.run()
            d.destroy()
            return

        # Update state
        mesk.config.set(CONFIG_SECTION, 'username', username)
        mesk.config.set(CONFIG_SECTION, 'password', pw)
        mesk.config.set(CONFIG_SECTION, 'submit_tracks', active)
        self.user = username
        self.passwd = pw
        self.md5_passwd = self.get_md5(self.passwd)
        self.submit_tracks = active

        # Rehandshake with new creds
        self.handshake()

    def _on_dialog_close(self, dialog, response):
        self.bad_auth_dialog.destroy()
        self.bad_auth_dialog = None

    def get_md5(self, s):
        hash = md5.new()
        hash.update(s)
        return hash.hexdigest()

    def handshake(self, delay=0.1):
        # Cancel any pending
        self._cancel_handshake()

        self.may_submit.clear()
        self.md5_challenge, self.submit_url = None, None
        # Async handshake
        self.handshake_task = threading.Timer(delay, self._handshake)
        self.handshake_task.start()

    def _handshake(self):
        # Update user/passwd from config if necessary
        if not self.user or not self.passwd:
            self.user = mesk.config.get(CONFIG_SECTION, 'username', '')
            self.passwd = mesk.config.get(CONFIG_SECTION, 'password', '')
            self.md5_passwd = self.get_md5(self.passwd)
            if not self.user or not self.passwd:
                self.log.critical('Add a username and password to the '
                                  'audioscrobbler plugin preferences.')
                self._update_status(state=_('No username and/or password'))
                return

        # Open handshake URL
        hs_url = HANDSHAKE_URL % (PROTOCOL_VERSION, APP, VERSION, self.user)
        url_data = None
        try:
            self.log.debug('Handshake: %s' % hs_url)
            url_data = urllib2.urlopen(hs_url)
        except Exception, ex:
            retry = 10 # minutes
            self.log.warning('Handshake error, retry in %d minutes: %s' %
                             (retry, str(ex)))
            self._update_status(state=_('Cannot connect to Last.FM'))
            # Fatal failure, retry in 10 minutes
            self.handshake(retry * 60)
            return

        # Parse response
        try:
            response = url_data.read()
            url_data.close()
            response = response.split('\n')
            self.log.debug('Handshake response: %s' % str(response))
            response_head = response[0].split(' ', 1)
            response_code = response_head[0]
            response_extra = ''
            if len(response_head) == 2:
                response_extra = response_head[1]

            if response_code not in HANDSHAKE_CODES:
                self.log.warning('Malformed response: %s' % str(response))
                self._update_status(state=_('Last.FM error'))
                return

            # XXX: Workaround bug in server.
            #      See http://www.audioscrobbler.net/forum/21716/_/93936
            if response_code == 'BADUSER':
                while '' in response:
                    response.remove('')

            if response_code == 'FAILED' or response_code == 'BADUSER':
                interval = int(response[1].split()[1])
                self.log.warning(_('Handshake failure \'%s\', retrying in %d '
                                   'seconds: %s') % (response_code,
                                                     interval * 60,
                                                     response_extra))

                if response_code == 'BADUSER':
                    self._update_status(state=_('Invalid username'))
                else:
                    self._update_status(state=_('Authentication failed'))

                # Retry handshake in interval seconds
                self.handshake(interval * 60)
                return

            if response_code == 'UPDATE':
                self.log.info(_('Plugin update available here, please see %s') \
                              % response_extra)

            self.md5_challenge = response[1]
            self.submit_url = response[2]
            interval = int(response[3].split()[1])
        except IndexError, ex:
            self.log.warning('Invalid response: %s' % str(response))
            self._update_status(state=_('Last.FM error'))
            return

        self._update_status(state=_('Authenticated'))
        self.log.debug('Handshake success: %s' % self.md5_challenge)

        self.may_submit.set()
        # Flush anything queued
        self.submit(interval = interval * 60)

    def _submit_post(self, post_data):
        try:
            self.log.debug('Submitting to %s: %s' % (self.submit_url,
                                                     post_data))
            url_data = urllib2.urlopen(self.submit_url, post_data)
        except Exception, ex:
            self.log.warning(_('Submit error: %s') % str(ex))
            self._update_status(state=_('Cannot connect to Last.FM'))
            return False

        try:
            response = url_data.read().split('\n')
            url_data.close()
            self.log.debug('Submit response: %s' % response)
            response_head = response[0].split(' ', 1)
            response_code = response_head[0]
            response_extra = ''
            if len(response_head) == 2:
                response_extra = response_head[1]

            if response_code not in SUBMISSION_CODES:
                self.log.warning(_('Malformed response: %s') % str(response))
                self._update_status(state=_('Last.FM error'))
                return False

            interval = int(response[1].split()[1])
        except IndexError:
            self.log.warning(_('Invalid response: %s') % str(response))
            self._update_status(state=_('Last.FM error'))
            return False

        if response_code == 'FAILED':
            self.log.warning(_('Submit failure: %s') % (response_extra,))
            self._update_status(state=_('Last.FM error'))
            self.submit(interval = interval * 60)
            return False
        elif response_code== 'BADAUTH':
            self.log.warning(_('BADAUTH failure, hanshake required'))
            self._update_status(state=_('Authentication required'))
            self.handshake(interval * 60)
            return

        return True

    def _submit(self, audio_src):
        audio_src_data = self.get_submit_data(audio_src)

        self.queue_lock.acquire()

        if not self.may_submit.isSet():
            if audio_src_data:
                self.log.debug('Handshake required, queueing: %s' % \
                               str(audio_src_data))
                self._update_status(state=_('Authentication required'))
                self.queue.append(audio_src_data)
                self._update_status(queue_count=len(self.queue))
            self.queue_lock.release()
            return

        secret = self.get_md5(self.md5_passwd + self.md5_challenge)

        if audio_src_data:
            self.queue.append(audio_src_data)

        # Process queue
        done = (len(self.queue) == 0)
        while not done:
            submit_dict = {'u': self.user.encode('utf-8'),
                           's': secret}
            submit_count = min(MAX_SUBMIT, len(self.queue))
            for i in range(submit_count):
                queue_dict = self.queue[i]
                for name, value in queue_dict.items():
                    submit_dict[name % {'index': i}] = value
            submit_str = urllib.urlencode(submit_dict)

            if not self._submit_post(submit_str):
                done = True
                continue
            else:
                self.status_submitted += submit_count
                self.status_last_submit = time.asctime()

            self.queue = self.queue[submit_count:]
            if len(self.queue) == 0:
                done = True

        self.queue_lock.release()
        self.status_queued = len(self.queue)
        self._update_status()

    def _cancel_handshake(self):
        if self.handshake_task:
            self.handshake_task.cancel()
            self.handshake_task = None
    def _cancel_submit(self):
        if self.submit_task:
            self.submit_task.cancel()
            self.submit_task = None

    ## AudioControlListener interface ###
    def on_plugin_audio_play(self, audio_src): pass
    def on_plugin_audio_pause(self, audio_src): pass
    def on_plugin_audio_stop(self, audio_src):
        self._cancel_submit()
    def on_plugin_audio_seek(self, audio_src):
        self._cancel_submit()

    def on_plugin_source_started(self, audio_src):
        self.log.debug('on_plugin_source_started: %s' % \
                       os.path.basename(audio_src.uri.path))

        if self.submit_tracks:
            # Cancel any pending submits since source changed 
            self._cancel_submit()
            self.submit(audio_src)

    def on_plugin_source_ended(self, audio_src):
        self.log.debug('on_plugin_source_ended: %s' % \
                       os.path.basename(audio_src.uri.path))

    ## ViewMenuProvider interface ###
    def plugin_view_menu_items(self):
        item = gtk.ImageMenuItem(_('Open Last.FM User Page'))
        item.set_image(gtk.image_new_from_stock(gtk.STOCK_HOME,
                                                gtk.ICON_SIZE_MENU))
        def user_page_activate(widget):
            mesk.utils.load_web_page('http://www.last.fm/user/%s' %
                                     mesk.uri.escape_path(self.user))
        item.connect('activate', user_page_activate)
        return [item]

    def submit(self, audio_src = None, interval = 0.1):
        # The audio_src is optional to allow flushing the queue
        if audio_src:
            # Half the song or 240s, whichever is shorter
            src_len = audio_src.meta_data.time_secs
            if src_len < 30:
                self.log.info(_('Source length %s < 30s, skipping') % \
                              str(src_len))
                return
            interval = min(src_len / 2, 240)
        # Schedule submit task
        self.submit_task = threading.Timer(interval, self._submit,
                                           args=[audio_src])
        self.submit_task.start()

    def time_stamp(self):
        return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())

    def get_submit_data(self, audio_src):
        '''Returns a dictionary of name value pairs.  The %(index)d is
        meant to be replaced with % formatting'''
        if not audio_src:
            return None

        artist = audio_src.meta_data.artist
        title = audio_src.meta_data.title
        if not artist or not title:
            self.log.warning(_('Source %s is missing artist and/or title: ') % \
                             audio_src.uri.path)
            return None
        album = audio_src.meta_data.album

        post = {}
        post['a[%(index)d]'] = artist.encode('utf-8')
        post['t[%(index)d]'] = title.encode('utf-8')
        post['b[%(index)d]'] = album.encode('utf-8')
        post['m[%(index)d]'] = ''
        post['l[%(index)d]'] = str(audio_src.meta_data.time_secs)
        post['i[%(index)d]'] = self.time_stamp()

        return post

XPM = [
"144 27 256 2",
"  	c None",
". 	c #D1637F",
"+ 	c #CF002E",
"@ 	c #DCA5B1",
"# 	c #D00B40",
"$ 	c #CE325A",
"% 	c #D26C85",
"& 	c #DD92A5",
"* 	c #CD0035",
"= 	c #DA486E",
"- 	c #D20034",
"; 	c #F2F1F0",
"> 	c #D45C7C",
", 	c #CC1343",
"' 	c #FCFDFD",
") 	c #EEF1EF",
"! 	c #E6C4CB",
"~ 	c #EEDADE",
"{ 	c #D24C6E",
"] 	c #F7FAF9",
"^ 	c #E9DBDD",
"/ 	c #D10A3D",
"( 	c #D9718C",
"_ 	c #D38A9B",
": 	c #D1002D",
"< 	c #E4A4B4",
"[ 	c #D20032",
"} 	c #F7F4F5",
"| 	c #D02352",
"1 	c #EAEDEA",
"2 	c #FBFAFA",
"3 	c #D68599",
"4 	c #E59BAE",
"5 	c #D5456A",
"6 	c #D1002C",
"7 	c #E1ADBA",
"8 	c #CD2F55",
"9 	c #EBCED5",
"0 	c #DE9AAB",
"a 	c #DC6D8A",
"b 	c #E3B2BE",
"c 	c #D20038",
"d 	c #D22955",
"e 	c #E6ADBB",
"f 	c #F2DDE2",
"g 	c #E6B5C1",
"h 	c #CE0A3D",
"i 	c #E28BA2",
"j 	c #CE214F",
"k 	c #CD063A",
"l 	c #EEE2E5",
"m 	c #E5DEDE",
"n 	c #DF8199",
"o 	c #CC0A3A",
"p 	c #ECCAD3",
"q 	c #F1EBEC",
"r 	c #CF2652",
"s 	c #D1002F",
"t 	c #D25172",
"u 	c #DE7591",
"v 	c #D00032",
"w 	c #FBFFFF",
"x 	c #EAC9D1",
"y 	c #D26A85",
"z 	c #D33D65",
"A 	c #D46581",
"B 	c #DB8EA0",
"C 	c #E195A8",
"D 	c #E1ABB8",
"E 	c #D25776",
"F 	c #F7F8F7",
"G 	c #F6EFF1",
"H 	c #F1EEEE",
"I 	c #F5EAEC",
"J 	c #D8768F",
"K 	c #CF365E",
"L 	c #D4778D",
"M 	c #EBE0E2",
"N 	c #EFD4DB",
"O 	c #D0002F",
"P 	c #EAD2D6",
"Q 	c #CE0032",
"R 	c #CE1B49",
"S 	c #C91745",
"T 	c #CF3B62",
"U 	c #D06982",
"V 	c #D2002E",
"W 	c #D10025",
"X 	c #CC1C4A",
"Y 	c #D10029",
"Z 	c #FAFDFD",
"` 	c #D01042",
" .	c #F7F2F3",
"..	c #EEE6E7",
"+.	c #EDE1E2",
"@.	c #EFB9C7",
"#.	c #E6BCC7",
"$.	c #CD1F4C",
"%.	c #D30032",
"&.	c #CE0C3D",
"*.	c #CD6D83",
"=.	c #CD0032",
"-.	c #DD3D68",
";.	c #D0053A",
">.	c #D3002C",
",.	c #D30F3C",
"'.	c #DD406B",
").	c #F4BFCD",
"!.	c #E87F9C",
"~.	c #EB8FA8",
"{.	c #E36084",
"].	c #E05077",
"^.	c #DA305E",
"/.	c #D51045",
"(.	c #E67090",
"_.	c #FCEFF3",
":.	c #D20036",
"<.	c #D82052",
"[.	c #F7D0DB",
"}.	c #F1AFC1",
"|.	c #FCF0F3",
"1.	c #F4C0CE",
"2.	c #E9809C",
"3.	c #FEFFFF",
"4.	c #FDFFFF",
"5.	c #D20037",
"6.	c #EE9FB4",
"7.	c #F7CFDA",
"8.	c #F1B0C2",
"9.	c #F9DFE6",
"0.	c #FAE0E7",
"a.	c #EEA0B5",
"b.	c #FCFFFF",
"c.	c #EB90A9",
"d.	c #D30036",
"e.	c #D30037",
"f.	c #D66A86",
"g.	c #C63157",
"h.	c #DD7A94",
"i.	c #DBA1AF",
"j.	c #F2F4F3",
"k.	c #DE97A9",
"l.	c #FEFEFE",
"m.	c #D2003A",
"n.	c #EFE9EA",
"o.	c #F5F2F2",
"p.	c #EBE5E5",
"q.	c #E7ABBA",
"r.	c #D4345B",
"s.	c #CF8292",
"t.	c #F9FFFF",
"u.	c #D95A77",
"v.	c #D0345D",
"w.	c #D86E89",
"x.	c #CB1B4A",
"y.	c #E397AC",
"z.	c #DA7F97",
"A.	c #F0E8E9",
"B.	c #D48093",
"C.	c #F2E2E6",
"D.	c #DFABB7",
"E.	c #F1E6E8",
"F.	c #D01847",
"G.	c #D8889C",
"H.	c #D5C9C9",
"I.	c #F9F1F3",
"J.	c #F9F5F7",
"K.	c #F0D5DC",
"L.	c #E3A8B7",
"M.	c #E0A4B3",
"N.	c #F5E8EB",
"O.	c #FAF7F8",
"P.	c #C55971",
"Q.	c #EFEAEC",
"R.	c #EFECED",
"S.	c #D23560",
"T.	c #CE1847",
"U.	c #D40F3D",
"V.	c #C72F55",
"W.	c #CD0334",
"X.	c #CF2E58",
"Y.	c #D01747",
"Z.	c #EACAD2",
"`.	c #D00937",
" +	c #E5D6D8",
".+	c #D85678",
"++	c #D10033",
"@+	c #CF0237",
"#+	c #EADEE0",
"$+	c #D2B3B7",
"%+	c #D0BBBE",
"&+	c #F7F7F7",
"*+	c #D07087",
"=+	c #D5788E",
"-+	c #ECE3E4",
";+	c #CE0537",
">+	c #D00D41",
",+	c #E87C99",
"'+	c #E47995",
")+	c #F8FDFD",
"!+	c #CF466A",
"~+	c #F9FEFD",
"{+	c #DE446D",
"]+	c #E9C6CF",
"^+	c #E8C8CF",
"/+	c #FCFFFE",
"(+	c #FDFEFE",
"_+	c #E9D8DB",
":+	c #D1204D",
"<+	c #F2F7F5",
"[+	c #D25374",
"}+	c #D65774",
"|+	c #F6FFFF",
"1+	c #D991A3",
"2+	c #D896A5",
"3+	c #FAEFF2",
"4+	c #F5F7F6",
"5+	c #D32D57",
"6+	c #D591A2",
"7+	c #CF083B",
"8+	c #D79EAD",
"9+	c #CD7087",
"0+	c #CC7F8F",
"a+	c #CF3059",
"b+	c #D3365A",
"c+	c #D33A60",
"d+	c #D13C63",
"e+	c #E2D6D7",
"f+	c #D43A63",
"g+	c #D43F65",
"h+	c #DDCDCF",
"i+	c #D86985",
"j+	c #ECD3D9",
"k+	c #DFB1BA",
"l+	c #ECD8DC",
"m+	c #D85E7E",
"n+	c #CA1C4A",
"o+	c #DC5277",
"p+	c #E5D9DB",
"q+	c #E9829E",
"r+	c #CD0030",
"s+	c #DBBAC1",
"t+	c #FDFEFD",
"u+	c #EFCED7",
"v+	c #E9CBD2",
"w+	c #FAFCFB",
"x+	c #D10138",
"y+	c #D20239",
"z+	c #ECE8E8",
"A+	c #E9BFCA",
"B+	c #DF9CAD",
"C+	c #D50F45",
"D+	c #D06F87",
"E+	c #D3002F",
"F+	c #FFFFFF",
"G+	c #D20039",
"                F+F+F+F+F+F+F+F+F+F+F+(+1 %+*.U D+D+D+D+D+D+D+D+% 9+H.4+F+F+F+F+F+F+) $+*.D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+D+*+J '+! q '                 ",
"              F+F+F+F+F+F+F+F+F+F+F+F+F+F+J.& 7+W E+E+E+E+E+E+>.6 i 2 F+F+F+F+F+F+F+F+3+.+W E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+E+V - c >+s.#+'             ",
"          F+F+F+F+F+F+F+F+F+F+F+F+F+F+F+F+F+F+p+$ s G+G+G+G+c O & F+F+F+F+F+w b.F+F+F+F+o.z [ G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+c :.%.7+_ ;           ",
"        F+F+F+F+F+F+b.H ! @ z.1+D P } 3.F+F+F+F+n.K [ G+G+G+[ T ] F+F+F+C.k.U % L. .F+F+F+^+;.5.G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+e.E+r q F+      ",
"      F+F+F+F+F+F+! E $.@+=.+ Q * ;.r 3 ; F+F+F+F+H 5+[ G+c Q D F+F+F+v+$.+ V : =.a+N w M.b+y+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+[ $.l       ",
"    F+F+F+F+F+3.n ;+: - 5.c G+c c 5.- + 8 g F+F+F+F+b * c 5.7+P F+F+4.f.Y c G+G+c V v.{ * [ G+G+G+G+G+G+G+G+G+G+G+G+2.2.2.{.G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+<.{.G+G+<.{.G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+%.j G     ",
"  F+F+F+F+F+b.u O :.G+G+G+G+G+G+G+G+G+G+V &.x F+F+F+)+t V :.# -+F+F+' d+[ G+G+G+G+m.- s c G+G+G+G+G+G+G+G+G+G+G+G+G+F+'.{.0.].G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+'.1.G+G+'.1.G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+%.> '   ",
"  F+F+F+F+F+i.Q :.G+G+G+G+G+G+G+G+G+G+G+G+++| n.F+F+F+x @+- >+-+F+F+' f+V G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+F+G+G+a.(.2.0.0.2.a.(.].|.G+1.-.[.1.[./.F+|.q+0.[.[.G+[.[.|.1.G+G+'.|.0.|.{.[.].G+|.<.G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+c v l+  ",
"F+F+F+F+F+9 ` - G+G+G+G+G+G+G+G+G+G+G+G+G+G+s . Z F+F+Z > s ;.x F+F+F+0 r+[ c G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+F+1.|.[.<.F+/./.F+].8.c.|.'.|.(.1.'.8.(.F+^.c.c.'.0.(.[.G+].1.G+G+'.0./.^.|.{.a.].1.G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+v 5 2 ",
"F+F+F+F+3.E : G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+5.* ]+F+F+F+A+v + 2+3.F+F+t.8+8 =.: - G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+F+G+G+G+<.0.G+G+F+G+|.[.2.1.a.2.1.2.a.{.F+G+8.8.2.8.,+a.G+'.1.G+G+'.[.G+/.F+/.|.8.{.G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+c - ~ ",
"F+F+F+F+1 x.d.G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+: A w F+F+} T V V.q F+F+F+F+<+@ }+F.+ s :.G+G+G+G+G+G+G+G+G+G+G+G+G+G+F+G+G+G+G+[.8.8.1.G+8.[.^.F+].<.|.2.[.'.F+G+{.[.2.0.-.|.c.[.1.G+G+'.F+c.8.1.G+a.|.G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+O g ",
"F+F+F+F+i.=.c G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+:.h ~ F+F+F+D.Q s . ] F+F+F+F+F+4.A.& { , O :.G+G+G+G+G+G+G+G+G+G+G+G+'.G+G+G+G+/.{.{./.G+<.^.G+'.G+G+<.2.^.G+2.G+G+'.(.^.G+<.2.].^.G+G+/.'.(.{./.G+{.a.G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+%.3 ",
"F+F+F+3.a 6 G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+O G.3.F+F+q j - Q [+K.F+F+F+F+F+F+F+b.^ A / [ G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+2.|.<.G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+:.o+",
"F+F+F+b.% : G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+- n+z+F+F+F+k.v c s / L ..3.F+F+F+F+F+F+4.N g+: G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+++= ",
"F+F+F+4.w.: G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G++ C F+F+F+f / :.G+:.O Y.u.e &+F+F+F+F+F+F+; z [ G+G+G+G+G+G+G+G+G+G+{.).].G+G+G+G+G+G+G+G+G+G+G+G+).^.{.).G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+).^.G+G+G+G+).^.G+G+G+G+~.~.G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+++{+",
"F+F+F+F+h.+ G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+s 5 3.F+F+/+t V G+G+G+- : v d J  +b.F+F+F+F+l+h :.G+G+G+G+G+G+G+G+G+7.F+}.G+G+G+G+G+G+G+G+G+G+G+G+F+'.'.!.G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+F+'.G+G+G+G+F+'.G+G+G+G+).).G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+%.( ",
"F+F+F+F+h+k 5.G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+e.o e+F+F+F+s+W.e.G+G+G+G+c - : h t 9 F+F+F+b.y : G+G+G+G+G+G+G+G+^.F+}.F+<.G+~.~.G+^.).^./.6.).!.F+'.{.).G+/.~.).~./.G+].).).(.G+G+].).}.].G+~.(.6.{./.~.).~./.G+F+~.}.}.^.G+F+~.}.}.^.G+).).G+^.}.).{.G+{.~.!.~.G+G+G+G+G+G+G+G+G+G+G+G+V k.",
"F+F+F+F+F v.[ G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+- - m.O > 3.F+F+] S.[ G+G+G+G+G+G+G+5.6 x.p F+F+F+q.v G+G+G+G+G+G+G+G+~._./.F+(.G+).).G+'.F+'.6._.].~.F+'.!.F+G+6.9.'.9.6.^.F+!.].9.{.].F+(.(.F+^.).F+~.'.6.9.'.9.6.G+F+7.'.7._.G+F+7.'.7._.G+).).<._.(.]._.{.!.F+}.{.G+G+G+G+G+G+G+G+G+G+G+G+++p ",
"F+F+F+F+F+C + c G+G+G+G+G+G+G+G+G+G+G+G+G+G+- | r d.d.S m F+F+F+@ Q c G+G+G+G+G+G+G+G+Y u F+F+F+@.x+5.G+G+G+G+G+G+G+_.}.'.7.7.G+).).G+'.F+'.F+!.G+G+F+'.!.F+G+F+!.G+!.F+<._.9.~.{.G+).).G+G+'.<.).~.G+G+F+!.G+!.F+G+F+'.G+'.F+'.F+'.G+'.F+'.).).!.F+).)._.).!.7.G+G+G+G+G+G+G+G+G+G+G+G+G+- >+} ",
"  F+F+F+F+w+{ : G+G+G+G+G+G+G+G+G+G+G+G+G+d.* ! B++ G+: f.F+F+F+F | - G+G+G+G+G+G+G+G+: w.3.F+F+_+h :.G+G+G+G+G+G+].F+F+F+F+F+^.).).G+'.F+'._.6.G+/.F+'.!.F+G+_.~.G+~._.G+/.'.~._.6.}.7.G+G+!.^.).!.G+G+_.~.G+~._.G+F+].G+].F+^.F+].G+].F+^.).).(.F+].'.(.{.!.).G+G+G+G+G+G+G+G+G+G+G+G+G+: i (+",
"  F+F+F+F+F+-+8 O G+G+G+G+G+G+G+G+G+G+G+:.r+_ 4.o.| - - $.) F+F+F+B 6 G+G+G+G+G+G+G+G++ n F+F+F+@.x+5.G+G+G+G+G+G+}.9.G+G+/.F+~.6.F+~.).F+'.!.F+~.).F+'.!.F+G+!._.!._.~.<.F+(.].9.}.'._.6.}._.<.).!.G+G+!._.!._.~.G+F+9.!._.7.G+F+9.!._.7.G+).)./._.}.~._.'.!.).G+G+G+G+G+G+G+G+G+G+G+G+- T.I.  ",
"    F+F+F+F+F+m a+: :.G+G+G+G+G+G+G+c ++Q % ~+F+3.J : c =.6+F+F+F+ .v.s G+G+G+G+G+G+- k x F+F+F+< Q G+G+G+G+G+G+G+!.].G+G+G+{.(./.(.(.^.!.<.G+{.!.'.'./.'.!.G+G+].!.].G+G+].}.).~./.G+<.!.(.<.G+{.'.G+G+G+].!.].G+G+!.^.(.(./.G+!.^.(.(./.G+{.{.G+/.(.!.^.G+'.{.G+G+G+G+G+G+G+G+G+G+G+:.W.#.F+  ",
"      F+F+F+F+F+N.B.&.+ E+:.:.:.:.s Q d g b.F+F+F+..X - - R A.F+F+F+p.r Y %.5.5.%.6 h 7 4.F+F+O.z ++G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+:.s L.3.    ",
"        F+F+F+F+F+4.l+B P.` # # ` . e G F+F+F+F+4.B `.c G+: m+4.F+F+F+f L g./ / g.=+j+F+F+F+F+#.v c G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+- - y.(+      ",
"        F+F+F+F+F+F+F+F+|+E.M +.I w F+F+F+F+F+4.h.o d.G+G+d.&.Z.F+F+F+F+4.j.+.+.j.4.F+F+F+F+) K [ G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+e.%./ 7 t+        ",
"            F+F+F+F+F+F+F+F+F+F+F+F+F+F+F+F+R.U v :.G+G+G+G+- :+u+F+F+F+F+F+F+F+F+F+F+F+F+Q.!+s G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+G+d.- %.%.h 0+l 3.          ",
"                F+F+F+F+F+F+F+F+F+F+F+F+N.4 r.,.C+C+C+C+C+C+C+U.5+4 } F+F+F+F+F+F+F+F+] b c+,.C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+C+X.g+i+k+M '               "
]

## Required for plugins ##
PLUGIN_INFO = PluginInfo(name=NAME,
                         desc=_('Submits played song information to last.fm'),
                         author='Travis Shirk <travis@pobox.com>',
                         url='http://mesk.nicfit.net/',
                         copyright='Copyright © 2006-2007 Travis Shirk',
                         clazz=AudioscrobblerPlugin,
                         xpm=XPM, display_name='Audioscrobbler (last.fm)')
