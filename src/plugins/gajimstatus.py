# -*- coding: utf-8 -*-
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
import os, locale
import threading
from commands import getstatusoutput

import gtk, gtk.glade, dbus

import mesk
import mesk.plugin
from mesk.i18n import _
from mesk.plugin.plugin import PluginInfo, Plugin
from mesk.plugin.interfaces import AudioControlListener

UPDATE_STATUS_STATES = ['chat', 'online', 'dnd']

DEFAULT_HEADER = u'♫:'
DEFAULT_FORMAT = DEFAULT_HEADER + u'%a - %t - %b (%y)'
MASTER_FORMAT = u'%(state)s%(info)s'

class GajimStatusPlugin(Plugin, AudioControlListener):
    def __init__(self):
        Plugin.__init__(self, PLUGIN_INFO)

        self.status_map = {}  # acct: (state, status_msg)
        self.update_task = None

        if not mesk.config.has_section(self.name):
            mesk.config.add_section(self.name)
            mesk.config.set(self.name, 'accounts', '')
            mesk.config.set(self.name, 'status_format', DEFAULT_FORMAT)
            return

        # Initialize status for all accounts listed in config
        for acct in mesk.config.getlist(self.name, 'accounts'):
            acct = acct.strip()
            if not acct:
                continue
            self.status_map[acct] = ('offline', None)

        # Load gajim service
        try:
            self.sbus = dbus.SessionBus()
        except:
            self.log.error("Cannot load DBus session bus")
            self.sbus = None
        self._gajim_svc = self._get_gajim_service()

    def _get_gajim_service(self):
        if self.sbus is None:
            return None

        self.log.debug('Looking up Gajim DBus service')

        try:
            obj = self.sbus.get_object('org.gajim.dbus',
                                       '/org/gajim/dbus/RemoteObject')
            gajim_svc = dbus.Interface(obj, 'org.gajim.dbus.RemoteInterface')
            return gajim_svc
        except dbus.DBusException, ex:
            # Gajim is not running
            self.log.verbose(str(ex))
            return None

    def shutdown(self):
        self.change_status(audio_src = None)

    def _update_status_map(self):
        for acct in self.status_map.keys():
            self.status_map[acct] = ('offline', None)
            self.log.verbose(_('Updating status for account %s') % acct)

            # Determine current status 
            status = self.gajim_remote('get_status', [acct])
            if status in [False, None]:
                return
            status = status.strip()

            if not status:
                self.log.verbose(_('Gajim and/or Dbus is not running'))
                continue

            self.status_map[acct] = (status, None)
            if status not in UPDATE_STATUS_STATES:
                continue

            # Load current status message
            status_msg = self.gajim_remote('get_status_message', [acct])
            if not status_msg:
                continue

            status_msg = '%(now_playing)s'
            self.status_map[acct] = (status, status_msg)

    def _get_now_playing_str(self, audio_src, state_str = ''):
        if audio_src:
           format = mesk.config.get(self.name, 'status_format', DEFAULT_FORMAT)
           # Replace UI vars with python substitution vars
           format = format.replace("%a", "%(artist)s")\
                          .replace("%t", "%(title)s")\
                          .replace("%b", "%(album)s")\
                          .replace("%y", "%(year)d")
           info = format % {'artist': audio_src.meta_data.artist,
                            'title': audio_src.meta_data.title,
                            'album': audio_src.meta_data.album,
                            'year': int(audio_src.meta_data.year or "0"),
                           }

           now_playing = MASTER_FORMAT % {'state': state_str,
                                          'info': info}
        else:
            now_playing = u''
        return now_playing

    # The delays are for rapid states changes, the previous task is cancelled
    def on_plugin_audio_play(self, audio_src):
        self.change_status(audio_src, interval = 2.5)
    def on_plugin_audio_pause(self, audio_src):
        self.change_status(audio_src, '[%s]' % _('paused'), interval = 2.5)
    def on_plugin_audio_stop(self, audio_src):
        self.change_status(None, interval = 2.5)

    def change_status(self, audio_src, state='', interval=0):
        if self.update_task:
            self.update_task.cancel()

        # Give it a few seconds, in case the song changes again
        self.update_task = threading.Timer(interval, self._change_status,
                                           args = [audio_src, state])
        self.update_task.start()

    def _change_status(self, audio_src, state=''):
        self._update_status_map()
        for acct in self.status_map.keys():
            status = self.status_map[acct][0]
            if status not in UPDATE_STATUS_STATES:
                continue
            status_msg = self._get_now_playing_str(audio_src, state)
            self.gajim_remote('change_status', [status, status_msg, acct])

    def gajim_remote(self, command, args=[]):
        self.log.debug("gajim_remote: %s, %s" % (command, str(args)))
        if self._gajim_svc is None:
            self._gajim_svc = self._get_gajim_service()
            if self._gajim_svc is None:
                return False

        args = [a.decode('utf-8') for a in args]
        args = [dbus.String(a) for a in args]

        method = self._gajim_svc.__getattr__(command)
        try:
            result = method(*args)
        except dbus.DBusException, ex:
            self.log.warn(str(ex))
            self._gajim_svc = None
            return None
        else:
            return result

    def is_configurable(self):
        return True

    def get_config_widget(self, parent):
        if self.config_glade:
            del self.config_glade

        WIDGET_NAME = 'gajimstatus_config_vbox'
        self.config_glade = gtk.glade.XML('./plugins/plugins_gui.glade',
                                          WIDGET_NAME, 'mesk')
        self.config_glade.signal_autoconnect(self)
        self.config_widget = self.config_glade.get_widget(WIDGET_NAME)

        vbox = self.config_glade.get_widget('accounts_vbox')
        # Remove current widgets
        children = vbox.get_children()
        for c in children:
            vbox.remove(c)

        # Check if gajim is running and list accounts if so
        output = self.gajim_remote('list_accounts')
        self.log.debug('Gajim list_accounts output: %s' % str(output))
        err_msg = None
        if output is None:
            err_msg = _('Gajim must be running in order to determine accounts.')
        elif output is False:
            err_msg = _('Unable to determine Gajim accounts.')

        if err_msg:
            vbox.add(gtk.Label(err_msg))
        else:
            # Add a checkbox for each account
            config_accts = mesk.config.getlist(self.name, 'accounts')
            for acct in output:
                check_button = gtk.CheckButton(label=acct, use_underline=False)
                check_button.set_active(acct in config_accts)
                vbox.add(check_button)
                check_button.show()

        format = mesk.config.get(self.name, 'status_format', DEFAULT_FORMAT)
        self.config_glade.get_widget('format_entry').set_text(format)

        return self.config_widget

    def config_ok(self):
        vbox = self.config_glade.get_widget('accounts_vbox')

        # Determine account states
        children = vbox.get_children()
        accts = []
        for c in children:
            if isinstance(c, gtk.CheckButton) and c.get_active():
                accts.append(c.get_label())

        # Update state
        mesk.config.set(self.name, 'accounts', accts)
        self.status_map = {}
        for a in accts:
            self.status_map[a] = ('offline', None)
        self._update_status_map()

        # Get format settings
        entry = self.config_glade.get_widget('format_entry')
        format = entry.get_text()
        mesk.config.set(self.name, 'status_format', format)

    def _on_restore_default_format_button_clicked(self, button):
        self.config_glade.get_widget('format_entry').set_text(DEFAULT_FORMAT)

XPM = [
"46 48 721 2",
"  	c None",
". 	c #000000",
"+ 	c #010000",
"@ 	c #010100",
"# 	c #020201",
"$ 	c #060503",
"% 	c #16140B",
"& 	c #2A2413",
"* 	c #362E18",
"= 	c #383018",
"- 	c #302814",
"; 	c #1F1A0C",
"> 	c #0D0B05",
", 	c #040301",
"' 	c #010101",
") 	c #030201",
"! 	c #0F0E08",
"~ 	c #39331D",
"{ 	c #716539",
"] 	c #9E8B4C",
"^ 	c #B49C53",
"/ 	c #BEA454",
"( 	c #C0A452",
"_ 	c #B79B4A",
": 	c #A68B41",
"< 	c #887133",
"[ 	c #57481F",
"} 	c #1B170A",
"| 	c #050502",
"1 	c #040402",
"2 	c #2C2818",
"3 	c #897A48",
"4 	c #C8B267",
"5 	c #E0C66F",
"6 	c #E9CC6F",
"7 	c #E9CA6B",
"8 	c #E7C867",
"9 	c #E6C563",
"0 	c #E5C25D",
"a 	c #E3BF59",
"b 	c #DEB953",
"c 	c #D0AC49",
"d 	c #A48636",
"e 	c #51421A",
"f 	c #120E06",
"g 	c #020200",
"h 	c #030302",
"i 	c #14120B",
"j 	c #595030",
"k 	c #CAB66D",
"l 	c #EDD47E",
"m 	c #ECD27A",
"n 	c #EBCF75",
"o 	c #EACD70",
"p 	c #E4BF58",
"q 	c #E2BD54",
"r 	c #E1BA50",
"s 	c #E0B74A",
"t 	c #D4AB42",
"u 	c #8F732B",
"v 	c #2E250D",
"w 	c #060401",
"x 	c #18160D",
"y 	c #6D623B",
"z 	c #CFBA70",
"A 	c #EDD57F",
"B 	c #EED47E",
"C 	c #E7C767",
"D 	c #E6C463",
"E 	c #DFB445",
"F 	c #D9AE40",
"G 	c #9B7B2B",
"H 	c #2D240C",
"I 	c #060501",
"J 	c #0D0C07",
"K 	c #645A36",
"L 	c #CFBA71",
"M 	c #EDD683",
"N 	c #EED682",
"O 	c #EACD6F",
"P 	c #E1BA4F",
"Q 	c #DDB240",
"R 	c #D6AA3A",
"S 	c #896C23",
"T 	c #231B08",
"U 	c #020101",
"V 	c #36311D",
"W 	c #C1AE69",
"X 	c #EED889",
"Y 	c #F0DB90",
"Z 	c #EFD887",
"` 	c #DCAF3B",
" .	c #C89E32",
"..	c #665018",
"+.	c #0E0C03",
"@.	c #0F0D08",
"#.	c #807345",
"$.	c #EFD98A",
"%.	c #F2DFA0",
"&.	c #F2DF9E",
"*.	c #E9CA6A",
"=.	c #E7C766",
"-.	c #E6C462",
";.	c #DBAC37",
">.	c #AA8428",
",.	c #34280C",
"'.	c #1D1A10",
").	c #B3A262",
"!.	c #F1DD97",
"~.	c #F4E4AF",
"{.	c #F2E1A3",
"].	c #EFD989",
"^.	c #DDB23F",
"/.	c #C99D2F",
"(.	c #5B4714",
"_.	c #070502",
":.	c #292516",
"<.	c #CDB970",
"[.	c #F2E09F",
"}.	c #F6E7BA",
"|.	c #F3E2A7",
"1.	c #EFD885",
"2.	c #ECD279",
"3.	c #E9C96A",
"4.	c #E5C25C",
"5.	c #E1B94F",
"6.	c #E0B749",
"7.	c #DBAC36",
"8.	c #D7A831",
"9.	c #775C1A",
"0.	c #0F0B03",
"a.	c #020202",
"b.	c #D3BE74",
"c.	c #F6EAC1",
"d.	c #F4E3AC",
"e.	c #EED783",
"f.	c #EBCF74",
"g.	c #DFB444",
"h.	c #DAAA32",
"i.	c #87681D",
"j.	c #161004",
"k.	c #242013",
"l.	c #C4B16B",
"m.	c #F2DF9F",
"n.	c #F7EBC5",
"o.	c #F4E6B3",
"p.	c #EED784",
"q.	c #EACC6F",
"r.	c #E4C25C",
"s.	c #E2BC54",
"t.	c #DCAF3A",
"u.	c #DAA932",
"v.	c #896A1E",
"w.	c #161104",
"x.	c #17140C",
"y.	c #9F8E56",
"z.	c #F6EBC3",
"A.	c #F6E9BD",
"B.	c #E3BF58",
"C.	c #E2BC53",
"D.	c #D8A831",
"E.	c #7B5E1B",
"F.	c #100C03",
"G.	c #0A0905",
"H.	c #685D38",
"I.	c #E8D389",
"J.	c #F6E9BC",
"K.	c #F7ECC6",
"L.	c #F0DC94",
"M.	c #EED47D",
"N.	c #E3BF57",
"O.	c #DCAE3A",
"P.	c #CB9E2E",
"Q.	c #5F4A15",
"R.	c #080602",
"S.	c #332E1B",
"T.	c #C0AE6C",
"U.	c #F3E3AA",
"V.	c #F7EDCB",
"W.	c #F2E1A5",
"X.	c #EED57E",
"Y.	c #EACC6E",
"Z.	c #DAAB36",
"`.	c #AE8728",
" +	c #3A2C0D",
".+	c #0B0B06",
"++	c #665C37",
"@+	c #D6C380",
"#+	c #F4E6B8",
"$+	c #F5E7B8",
"%+	c #EFD888",
"&+	c #E1B94E",
"*+	c #DDB13F",
"=+	c #C99D32",
"-+	c #6C5419",
";+	c #110D04",
">+	c #060101",
",+	c #231F12",
"'+	c #897B4C",
")+	c #DFCC8B",
"!+	c #F4E5B2",
"~+	c #F0DD98",
"{+	c #EDD27A",
"]+	c #E9C969",
"^+	c #E7C765",
"/+	c #D4A838",
"(+	c #8D6E23",
"_+	c #2A200A",
":+	c #0A0301",
"<+	c #1B0000",
"[+	c #0D0402",
"}+	c #312B1A",
"|+	c #9A8B55",
"1+	c #E8D591",
"2+	c #F1DE9C",
"3+	c #EDD481",
"4+	c #E6C461",
"5+	c #E4C15C",
"6+	c #E3BE57",
"7+	c #E1BC53",
"8+	c #DAAE3E",
"9+	c #A6832C",
"0+	c #362B0E",
"a+	c #0D0502",
"b+	c #2D0000",
"c+	c #2B0505",
"d+	c #1C0F11",
"e+	c #0D0E0D",
"f+	c #37321F",
"g+	c #B4A364",
"h+	c #EDD88D",
"i+	c #EDD585",
"j+	c #E0B94E",
"k+	c #E0B748",
"l+	c #DDB344",
"m+	c #BA9435",
"n+	c #4C3C15",
"o+	c #0C0D08",
"p+	c #1A1613",
"q+	c #2A0C0A",
"r+	c #2D0201",
"s+	c #2D0101",
"t+	c #2D0506",
"u+	c #2F1518",
"v+	c #323239",
"w+	c #31464F",
"x+	c #1F3238",
"y+	c #0B0F0F",
"z+	c #4C4429",
"A+	c #C7B26A",
"B+	c #EBD27C",
"C+	c #E4C15B",
"D+	c #DFB648",
"E+	c #C6A03D",
"F+	c #624F1D",
"G+	c #100F09",
"H+	c #1D322D",
"I+	c #385B4F",
"J+	c #3B4F44",
"K+	c #352B24",
"L+	c #2F0C0B",
"M+	c #2D0202",
"N+	c #2E0B0D",
"O+	c #31252B",
"P+	c #34424D",
"Q+	c #365765",
"R+	c #375D69",
"S+	c #30515B",
"T+	c #17272C",
"U+	c #19180F",
"V+	c #857645",
"W+	c #DFC671",
"X+	c #EBCE73",
"Y+	c #D9B146",
"Z+	c #93772E",
"`+	c #27200D",
" @	c #131F1C",
".@	c #355D52",
"+@	c #427565",
"@@	c #437665",
"#@	c #406556",
"$@	c #3A4237",
"%@	c #321C17",
"&@	c #2E0504",
"*@	c #2E0E11",
"=@	c #32303A",
"-@	c #354D5B",
";@	c #365968",
">@	c #375C6A",
",@	c #375D6A",
"'@	c #375C67",
")@	c #2A464D",
"!@	c #0E1413",
"~@	c #473F24",
"{@	c #C1AA61",
"]@	c #E7C665",
"^@	c #E6C361",
"/@	c #C9A441",
"(@	c #5A491C",
"_@	c #11130C",
":@	c #27443C",
"<@	c #407163",
"[@	c #437667",
"}@	c #447866",
"|@	c #447966",
"1@	c #43715F",
"2@	c #3E5647",
"3@	c #352821",
"4@	c #2E0605",
"5@	c #2E0D11",
"6@	c #32343F",
"7@	c #355364",
"8@	c #365969",
"9@	c #365B6A",
"0@	c #385E69",
"a@	c #345760",
"b@	c #17282B",
"c@	c #221E11",
"d@	c #9C8A4F",
"e@	c #E6CA70",
"f@	c #E3BE56",
"g@	c #E1BC52",
"h@	c #DFB94D",
"i@	c #AE8E39",
"j@	c #312810",
"k@	c #355E53",
"l@	c #427567",
"m@	c #457A66",
"n@	c #447863",
"o@	c #416352",
"p@	c #362B23",
"q@	c #2D0102",
"r@	c #2E1014",
"s@	c #313845",
"t@	c #355567",
"u@	c #35586A",
"v@	c #36596A",
"w@	c #385F69",
"x@	c #385E68",
"y@	c #233B40",
"z@	c #14140F",
"A@	c #77693B",
"B@	c #DCC16B",
"C@	c #EACC6D",
"D@	c #DEB84D",
"E@	c #89702D",
"F@	c #1D1A0C",
"G@	c #1E352F",
"H@	c #3E6D61",
"I@	c #457C66",
"J@	c #467D66",
"K@	c #426B57",
"L@	c #373027",
"M@	c #2F0706",
"N@	c #2E0A0D",
"O@	c #31313E",
"P@	c #345164",
"Q@	c #35576A",
"R@	c #395F69",
"S@	c #284349",
"T@	c #121613",
"U@	c #615631",
"V@	c #D6BC68",
"W@	c #E7C664",
"X@	c #DDB74C",
"Y@	c #735D26",
"Z@	c #17170E",
"`@	c #243E38",
" #	c #407063",
".#	c #467D65",
"+#	c #416350",
"@#	c #35271E",
"##	c #2E0403",
"$#	c #2D0203",
"%#	c #30242F",
"&#	c #334D61",
"*#	c #34566B",
"=#	c #396069",
"-#	c #2B484F",
";#	c #121917",
">#	c #4E4527",
",#	c #CFB665",
"'#	c #E9C868",
")#	c #DCB54B",
"!#	c #5F4E1F",
"~#	c #12160F",
"{#	c #28463F",
"]#	c #407164",
"^#	c #467E66",
"/#	c #467B63",
"(#	c #3F5845",
"_#	c #321612",
":#	c #2D0100",
"<#	c #2E0E12",
"[#	c #324559",
"}#	c #33546A",
"|#	c #385E6A",
"1#	c #3D626D",
"2#	c #3C626C",
"3#	c #2F5057",
"4#	c #121D1F",
"5#	c #2F2918",
"6#	c #A28F51",
"7#	c #C9B163",
"8#	c #C2A95F",
"9#	c #BCA359",
"0#	c #B99F55",
"a#	c #BCA153",
"b#	c #C1A350",
"c#	c #C6A54C",
"d#	c #B2933F",
"e#	c #3B3014",
"f#	c #0F1814",
"g#	c #2E5149",
"h#	c #417265",
"i#	c #477E66",
"j#	c #467960",
"k#	c #3A3E31",
"l#	c #2D0405",
"m#	c #302D3C",
"n#	c #33536B",
"o#	c #33546B",
"p#	c #3F6470",
"q#	c #4B6D77",
"r#	c #3F656E",
"s#	c #365B63",
"t#	c #24393D",
"u#	c #1F2220",
"v#	c #393526",
"w#	c #423C29",
"x#	c #3A3524",
"y#	c #343020",
"z#	c #322E1F",
"A#	c #36301F",
"B#	c #3C3522",
"C#	c #443C25",
"D#	c #403825",
"E#	c #1C1D18",
"F#	c #1E332E",
"G#	c #3A655B",
"H#	c #427367",
"I#	c #488065",
"J#	c #45735A",
"K#	c #321813",
"L#	c #2E1015",
"M#	c #324459",
"N#	c #3A5F6D",
"O#	c #4F707C",
"P#	c #55757E",
"Q#	c #3E646D",
"R#	c #395F68",
"S#	c #355257",
"T#	c #2A3234",
"U#	c #1C1C1C",
"V#	c #171717",
"W#	c #181818",
"X#	c #1F1F1F",
"Y#	c #293734",
"Z#	c #365A53",
"`#	c #407065",
" $	c #427467",
".$	c #3A4032",
"+$	c #2F242F",
"@$	c #334D65",
"#$	c #456774",
"$$	c #65818B",
"%$	c #56767F",
"&$	c #3D626C",
"*$	c #39585E",
"=$	c #2E373A",
"-$	c #1B1B1C",
";$	c #141414",
">$	c #151515",
",$	c #161616",
"'$	c #202020",
")$	c #354A46",
"!$	c #3F6A61",
"~$	c #488165",
"{$	c #42664F",
"]$	c #300F0B",
"^$	c #2D0508",
"/$	c #303444",
"($	c #33516A",
"_$	c #3A5E6D",
":$	c #5A7884",
"<$	c #738C96",
"[$	c #52737C",
"}$	c #3B616B",
"|$	c #2F393A",
"1$	c #222222",
"2$	c #1D1D1D",
"3$	c #1A1A1A",
"4$	c #191919",
"5$	c #1B1B1B",
"6$	c #1E1E1E",
"7$	c #242625",
"8$	c #374C48",
"9$	c #406B62",
"0$	c #46755A",
"a$	c #35231B",
"b$	c #2E0C10",
"c$	c #303748",
"d$	c #32485E",
"e$	c #32495E",
"f$	c #334A5E",
"g$	c #334B5E",
"h$	c #344D5D",
"i$	c #355262",
"j$	c #365A6A",
"k$	c #446775",
"l$	c #79929C",
"m$	c #758F98",
"n$	c #4D6F79",
"o$	c #3A5F69",
"p$	c #396068",
"q$	c #38575C",
"r$	c #2B3537",
"s$	c #161818",
"t$	c #0D0E0E",
"u$	c #0A0A0A",
"v$	c #080808",
"w$	c #090909",
"x$	c #0C0C0C",
"y$	c #0F1010",
"z$	c #1A1D1D",
"A$	c #354B46",
"B$	c #406C62",
"C$	c #447561",
"D$	c #436E5A",
"E$	c #436E59",
"F$	c #446E59",
"G$	c #446F58",
"H$	c #457158",
"I$	c #446C54",
"J$	c #383529",
"K$	c #2D0406",
"L$	c #2E1116",
"M$	c #2F151B",
"N$	c #2F161B",
"O$	c #2F171C",
"P$	c #32313B",
"Q$	c #395969",
"R$	c #577583",
"S$	c #899EA7",
"T$	c #738D96",
"U$	c #4A6C76",
"V$	c #3A5E65",
"W$	c #365256",
"X$	c #2F4244",
"Y$	c #213031",
"Z$	c #142021",
"`$	c #0F1A1A",
" %	c #0E1918",
".%	c #121E1D",
"+%	c #1D2A29",
"@%	c #293A39",
"#%	c #334A47",
"$%	c #3D635B",
"%%	c #407066",
"&%	c #3E5949",
"*%	c #342720",
"=%	c #331E18",
"-%	c #331D18",
";%	c #331D16",
">%	c #30100C",
",%	c #312E36",
"'%	c #3E5F6F",
")%	c #718A96",
"!%	c #8EA2AB",
"~%	c #718B94",
"{%	c #486B75",
"]%	c #3A6169",
"^%	c #3A6167",
"/%	c #3A6065",
"(%	c #385D60",
"_%	c #355A5B",
":%	c #325656",
"<%	c #315554",
"[%	c #355B59",
"}%	c #39615E",
"|%	c #3D6662",
"1%	c #3F6A64",
"2%	c #406F66",
"3%	c #417167",
"4%	c #3E5849",
"5%	c #311511",
"6%	c #2E080A",
"7%	c #333B46",
"8%	c #466676",
"9%	c #869BA6",
"0%	c #91A4AD",
"a%	c #6F8993",
"b%	c #466974",
"c%	c #3A6369",
"d%	c #3B6469",
"e%	c #3B6569",
"f%	c #3C6668",
"g%	c #3C6767",
"h%	c #3C6867",
"i%	c #3E6B68",
"j%	c #3E6C68",
"k%	c #3F6D68",
"l%	c #406F67",
"m%	c #407067",
"n%	c #416654",
"o%	c #33201B",
"p%	c #374D5C",
"q%	c #587584",
"r%	c #95A7B1",
"s%	c #91A5AE",
"t%	c #6D8892",
"u%	c #446973",
"v%	c #3D6868",
"w%	c #3D6968",
"x%	c #3F6E68",
"y%	c #447662",
"z%	c #363229",
"A%	c #2D0302",
"B%	c #2F151A",
"C%	c #6A8390",
"D%	c #9EAEB8",
"E%	c #91A4AE",
"F%	c #6C8791",
"G%	c #446872",
"H%	c #457B66",
"I%	c #3A4135",
"J%	c #302026",
"K%	c #3C5E6E",
"L%	c #788F9B",
"M%	c #A5B4BD",
"N%	c #3D4F41",
"O%	c #2F0B09",
"P%	c #2E0405",
"Q%	c #322C35",
"R%	c #416373",
"S%	c #869BA5",
"T%	c #A9B8C0",
"U%	c #6D8792",
"V%	c #446873",
"W%	c #40604F",
"X%	c #30100D",
"Y%	c #2E0607",
"Z%	c #323A47",
"`%	c #4B6B7A",
" &	c #93A6B0",
".&	c #ABB9C1",
"+&	c #92A5AE",
"@&	c #6E8992",
"#&	c #456973",
"$&	c #447560",
"%&	c #321814",
"&&	c #2E0709",
"*&	c #344352",
"=&	c #547281",
"-&	c #9EAEB7",
";&	c #708B94",
">&	c #457B64",
",&	c #2E0A0C",
"'&	c #354B5B",
")&	c #5E7988",
"!&	c #A9B7BF",
"~&	c #467C66",
"{&	c #352A22",
"]&	c #2E0F13",
"^&	c #364E5F",
"/&	c #67818F",
"(&	c #B3C0C7",
"_&	c #3A606A",
":&	c #37332A",
"<&	c #2E1519",
"[&	c #355061",
"}&	c #5D7987",
"|&	c #93A6AF",
"1&	c #8A9EA8",
"2&	c #79919C",
"3&	c #66828C",
"4&	c #3B606A",
"5&	c #393D32",
"6&	c #2F1317",
"7&	c #33404E",
"8&	c #364856",
"9&	c #394B58",
"0&	c #394C58",
"a&	c #384C57",
"b&	c #384D56",
"c&	c #374C54",
"d&	c #364C53",
"e&	c #374C53",
"f&	c #374D53",
"g&	c #374E53",
"h&	c #384F53",
"i&	c #385053",
"j&	c #395152",
"k&	c #395252",
"l&	c #3A5452",
"m&	c #3A5551",
"n&	c #3B5551",
"o&	c #3C5650",
"p&	c #3C5750",
"q&	c #3D5850",
"r&	c #3D5950",
"s&	c #3D5A50",
"t&	c #3E5B4F",
"u&	c #3F5C4F",
"v&	c #3F5D4E",
"w&	c #3F5E4E",
"x&	c #3F5F4E",
"y&	c #40604E",
"z&	c #2F1216",
"A&	c #2F1316",
"B&	c #2F1315",
"C&	c #2F1415",
"D&	c #301415",
"E&	c #301414",
"F&	c #301514",
"G&	c #301513",
"H&	c #311513",
"I&	c #311512",
"J&	c #311612",
"K&	c #311611",
"L&	c #2F0D0A",
"                                      . + @ @ @ +                                           ",
"                                  # $ % & * = - ; > , '                                     ",
"                            . ) ! ~ { ] ^ / ( _ : < [ } | @                                 ",
"                          @ 1 2 3 4 5 6 7 8 9 0 a b c d e f g                               ",
"                        h i j k l m n o 7 8 9 0 p q r s t u v w                             ",
"                      # x y z A B m n o 7 C D 0 p q r s E F G H I                           ",
"                    . J K L M N B m n O 7 C D 0 p q P s E Q R S T )                         ",
"                    U V W X Y Z B m n O 7 C D 0 p q P s E Q `  ...+.                        ",
"                  . @.#.$.%.&.$.B m n O *.=.-.0 p q P s E Q ` ;.>.,.#                       ",
"                  . '.).!.~.{.].B m n O *.=.-.0 p q P s E ^.` ;./.(._.                      ",
"                  # :.<.[.}.|.1.B 2.n O 3.=.-.4.p q 5.6.E ^.` 7.8.9.0.                      ",
"                  a.2 b.{.c.d.e.B 2.f.O 3.=.-.4.p q 5.6.g.^.` 7.h.i.j..                     ",
"                  ' k.l.m.n.o.p.B 2.f.q.3.=.-.r.p s.5.6.g.^.t.7.u.v.w..                     ",
"                  . x.y.!.z.A.].B 2.f.q.3.=.-.r.B.C.5.6.g.^.t.7.D.E.F.                      ",
"                  . G.H.I.J.K.L.M.2.f.q.3.=.-.r.N.C.5.6.g.^.O.7.P.Q.R.                      ",
"                    ' S.T.U.V.W.X.2.f.Y.3.=.-.r.N.C.5.6.g.^.O.Z.`. +)                       ",
"                      .+++@+#+$+%+2.f.Y.3.=.-.r.N.C.&+6.g.*+O.=+-+;+.                       ",
"                      >+,+'+)+!+~+{+f.Y.]+^+-.r.N.C.&+6.g.*+/+(+_+:+                        ",
"                      <+[+}+|+1+2+3+f.Y.]+^+4+5+6+7+&+6.g.8+9+0+a+<+                        ",
"                  b+b+c+d+e+f+g+h+i+n Y.]+^+4+5+6+7+j+k+l+m+n+o+p+q+r+b+                    ",
"                s+t+u+v+w+x+y+z+A+B+n Y.]+^+4+C+6+7+j+D+E+F+G+H+I+J+K+L+M+b+                ",
"            b+s+N+O+P+Q+R+S+T+U+V+W+X+Y.]+^+4+C+6+7+j+Y+Z+`+ @.@+@@@#@$@%@&@b+              ",
"          b+s+*@=@-@;@>@,@'@)@!@~@{@X+Y.]+]@^@C+6+7+j+/@(@_@:@<@[@}@|@1@2@3@4@b+            ",
"        b+s+5@6@7@8@9@>@,@0@a@b@c@d@e@Y.]+]@^@C+f@g@h@i@j@ @k@l@[@}@|@m@n@o@p@&@b+          ",
"      b+q@r@s@t@u@v@9@>@,@w@x@y@z@A@B@C@]+]@^@C+f@g@D@E@F@G@H@l@[@}@|@m@I@J@K@L@M@b+        ",
"      b+N@O@P@Q@u@v@9@>@,@w@R@S@T@U@V@C@]+W@^@C+f@g@X@Y@Z@`@ #l@[@}@|@m@I@J@.#+#@###b+      ",
"    b+$#%#&#*#Q@u@v@9@>@,@w@=#-#;#>#,#C@'#W@^@C+f@g@)#!#~#{#]#l@[@}@|@m@I@J@^#/#(#_#:#      ",
"    s+<#[#}#*#Q@u@v@9@>@|#1#2#3#4#5#6#7#8#9#0#a#b#c#d#e#f#g#h#l@[@}@|@m@I@J@^#i#j#k###b+    ",
"  b+l#m#n#o#*#Q@u@v@9@>@p#q#r#s#t#u#v#w#x#y#z#A#B#C#D#E#F#G#H#l@[@}@|@m@I@J@^#i#I#J#K#s+    ",
"  s+L#M#n#o#*#Q@u@v@9@N#O#P#Q#R#S#T#U#V#V#W#W#W#W#W#X#Y#Z#`# $l@[@}@|@m@I@J@^#i#I#I#.$##b+  ",
"b+M++$@$n#o#*#Q@u@v@9@#$$$%$&$=#*$=$-$;$>$,$,$>$>$>$'$)$!$H# $l@[@}@|@m@I@J@^#i#I#~${$]$b+  ",
"b+^$/$($n#o#*#Q@u@v@_$:$<$[$}$=#*$|$1$2$3$4$4$3$5$6$7$8$9$H# $l@[@}@|@m@I@J@^#i#I#~$0$a$s+  ",
"b+b$c$d$e$f$g$h$i$j$k$l$m$n$o$p$q$r$s$t$u$v$v$w$x$y$z$A$B$H# $l@[@}@|@m@C$D$E$F$G$H$I$J$r+  ",
"b+K$L$M$M$N$N$O$P$Q$R$S$T$U$R@=#V$W$X$Y$Z$`$ %.%+%@%#%$%%%H# $l@[@}@|@m@&%*%=%-%-%=%;%>%b+b+",
"b+b+s+q@q@q@q@t+,%'%)%!%~%{%R@=#]%^%/%(%_%:%<%[%}%|%1%2%3%H# $l@[@}@|@m@4%5%M+s+s+s+s+:#b+b+",
"            b+6%7%8%9%0%a%b%R@=#]%c%d%e%f%g%h%i%j%k%l%m%3%H# $l@[@}@|@m@n%o%s+              ",
"            b+*@p%q%r%s%t%u%R@=#]%c%d%e%f%v%w%i%j%x%l%m%3%H# $l@[@}@|@m@y%z%A%b+            ",
"            s+B%Q$C%D%E%F%G%R@=#]%c%d%e%f%v%w%i%j%x%l%m%3%H# $l@[@}@|@m@H%I%4@b+            ",
"          b+M+J%K%L%M%E%F%G%R@=#]%c%d%e%f%v%w%i%j%x%l%m%3%H# $l@[@}@|@m@I@N%O%b+            ",
"          b+P%Q%R%S%T%E%U%V%R@=#]%c%d%e%f%v%w%i%j%x%l%m%3%H# $l@[@}@|@m@I@W%X%b+            ",
"          b+Y%Z%`% &.&+&@&#&R@=#]%c%d%e%f%v%w%i%j%x%l%m%3%H# $l@[@}@|@m@I@$&%&b+            ",
"          b+&&*&=&-&.&+&;&{%R@=#]%c%d%e%f%v%w%i%j%x%l%m%3%H# $l@[@}@|@m@I@>&o%s+            ",
"          b+,&'&)&!&.&+&T$U$R@=#]%c%d%e%f%v%w%i%j%x%l%m%3%H# $l@[@}@|@m@I@~&{&M+b+          ",
"          s+]&^&/&(&.&+&m$n$_&=#]%c%d%e%f%v%w%i%j%x%l%m%3%H# $l@[@}@|@m@I@J@:&##b+          ",
"          s+<&[&}&|&1&2&3&q#4&=#]%c%d%e%f%v%w%i%j%x%l%m%3%H# $l@[@}@|@m@I@J@5&&@b+          ",
"          s+6&7&8&9&0&a&b&c&d&e&f&g&h&i&j&j&k&l&m&n&o&p&q&r&s&s&t&u&v&w&x&y&:&&@b+          ",
"          b+Y%L#z&z&z&A&A&A&A&A&B&B&C&D&E&E&F&F&G&G&H&H&H&H&H&I&I&J&J&J&J&K&L&s+b+          ",
"          b+b+b+b+b+b+b+b+b+b+b+b+b+b+b+b+b+b+b+b+b+b+b+b+b+b+b+b+b+b+b+b+b+b+b+b+          "
]

## Required for plugins ##
PLUGIN_INFO = PluginInfo(name='gajimstatus',
                         desc=_('Uses Gajim (a Jabber/XMPP instant '
                                'message client) to update your status '
                                'message with currently playing song info.'),
                         author='Travis Shirk <travis@pobox.com>',
                         url='http://mesk.nicfit.net/',
                         copyright='Copyright © 2006-2007 Travis Shirk',
                         clazz=GajimStatusPlugin,
                         xpm=XPM, display_name='Gajim Status')

