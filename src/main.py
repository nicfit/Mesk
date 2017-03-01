#!/usr/bin/env python
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

# XXX: Take care when importing, else gst could be imported too early and would
#      mess up --gst-help support
import locale

class RemoteControlException(Exception):
    pass

class MeskApp:
    def __init__(self):
        '''Constructor'''

        # Workaround gst intercepting --help by ensuring gst is not imported
        # at this point.
        def handle_gst_option():
            import gst # This should not return
            assert(False)
            sys.exit(1)

        try:
            if gst.gst_version:
                raise Exception('!!!BUG!!!: gst imported to soon.')
        except NameError:
            # This is the happy path
            if '--gst-help' in sys.argv:
                # Make gst see --help, so that it does its thing
                sys.argv.append('--help')
                handle_gst_option() # This will not return
            else:
                # Any gst options are parsed during the import.
                for opt in sys.argv:
                    if opt.startswith('--gst-'):
                        handle_gst_option() # This will not return

        gtk.window_set_auto_startup_notification(False)

        # Parse command line
        self.cmd_line = OptionParser()
        (self.opts, args, self.remote_opts) = self.cmd_line.parse_args()
        # Add any command line args as --enqueue remote opts
        for a in args:
            self.remote_opts.append(('--enqueue', a))
        # The profile is used for the GUI and to select a DBus service instance
        self.profile = self.opts.profile

    def _run_remote_commands(self, interface):
        for cmd, arg in self.remote_opts:
            self._remote_control(interface, cmd, arg)

    def run(self):
        import mesk
        self._init()

        if not mesk.info.DISABLE_DBUS_SUPPORT:
            mesk.log.debug('Testing for existing instance; profile \'%s\'' %
                           self.profile)
            import dbus_service
            mesk_running = dbus_service.is_service_running(self.profile)
            if mesk_running and not self.remote_opts:
                mesk.log.debug('mesk is running but no remote commands')
                raise mesk.MeskException(
                    _('Mesk is already running'),
                    _('Another instance of Mesk is using the profile \'%s\'. '
                      'Try again with a different profile name '
                      '(-p/--profile)') % self.profile)
            elif mesk_running:
                mesk.log.debug('mesk is running, execting remote commands')
                # Mesk is running and we have some remote control options, 
                # so execute the commands on the remote service and exit
                import dbus
                import dbus_service  # This is a local module
                obj_path = dbus_service.get_object_path(self.profile)
                service = dbus_service.get_service_name(self.profile)
                session_bus = dbus.SessionBus()
                obj = session_bus.get_object(service, obj_path)

                mesk_dbus = dbus.Interface(obj, dbus_service.INTERFACE)
                self._run_remote_commands(mesk_dbus)
                return
        elif self.remote_opts:
            raise RemoteControlException('Remote control disabled')


        # Gnome session management
        try:
            import gnome.ui
        except ImportError:
            mesk.log.info('Session management disabled (gnome.ui not found)')
        else:
            mesk.log.debug('Enabling Gnome session management')
            gnome.program_init(mesk.info.APP_NAME.lower(),
                               mesk.info.APP_VERSION)
            cli = gnome.ui.master_client()
            cli.connect('die', lambda: gtk.main_quit())
            argv = ['mesk'] + sys.argv[1:]
            try:
                cli.set_restart_command(argv)
            except TypeError:
                # Fedora systems have a broken gnome-python wrapper for this
                # function.  Credits to Quod Libet:
                # http://www.sacredchao.net/quodlibet/ticket/591
                cli.set_restart_command(len(argv), argv)

        # Initialize DB
        try:
            import mesk.database
        except Exception, ex:
            raise mesk.MeskException('Music Library Error',
                                     traceback.format_exc())
        # FIXME
        print mesk.database.db

        # Main window
        from main_window import MainWindow
        self.main_window = MainWindow(self.profile)
        self.main_window.show()
        gtk.gdk.notify_startup_complete()

        # Handle any remote commands we have (once th main loop has started)
        gobject.idle_add(self._run_remote_commands, self.main_window.mesk_dbus)
        try:
            # Main loop
            gtk.main()
        except KeyboardInterrupt:
            mesk.log.debug("Interrupted")
            self.main_window.quit()

        # Shutdown
        mesk.config.save(self.config_file)

    def _init(self):
        # Load configuration
        if self.profile:
            self.config_file = '%s/config.%s' % (mesk.MESK_DIR,
                                                 self.opts.profile)
        else:
            self.config_file = '%s/config' % (mesk.MESK_DIR)

        try:
            mesk.config.load(self.config_file, self.opts.profile)
        except IOError:
            # No config, start with a new one
            mesk.config.save(self.config_file)

        # Initialize logging
        mesk.log.init(mesk.config)
        if self.opts.log_level:
            try:
                lvl = mesk.log.string_to_level(self.opts.log_level)
            except KeyError:
                mesk.log.warning('Invalid log level \'%s\' using INFO' %
                                 self.opts.log_level)
                lvl = "INFO"
            mesk.log.set_logging_level(lvl)

        if self.opts.profile:
            mesk.log.verbose('Using profile: %s' % self.opts.profile)

        # Update config version
        config_version = mesk.config.get(mesk.CONFIG_MAIN, 'version')
        if config_version != mesk.info.APP_VERSION:
            self._migrate_config(config_version, mesk.info.APP_VERSION)
        mesk.config.set(mesk.CONFIG_MAIN, 'version', mesk.info.APP_VERSION)

        # Initialize glade i18n
        import gtk.glade
        gtk.glade.bindtextdomain('mesk', mesk.i18n.DIR)
        gtk.glade.textdomain('mesk')

        if self.opts.debug:
            # Break in pdb on unhandled exceptions
            try:
                from IPython.ultraTB import FormattedTB
                sys.excepthook = FormattedTB(mode='Verbose',
                                             color_scheme='Linux', call_pdb=1)
            except ImportError:
                mesk.log.warn('Unable to use --run-pdb, IPython module not '
                              'installed')

    def _output(self, s):
        sys.stdout.write(s.encode(locale.getpreferredencoding()))
        sys.stdout.flush()

    def _remote_control(self, interface, cmd, arg):
        cmd_method = cmd[2:].replace('-', '_')
        cmd_method = getattr(interface, cmd_method)
        mesk.log.debug("executing remote command: %s, val: %s" % (cmd,
                                                                  str(arg)))

        if cmd in ['--stop', '--play', '--pause', '--play-pause', '--next',
                   '--prev', '--toggle-mute', '--toggle-visible',
                   '--raise-window']:
            # These commands do not take arguments or require special
            # processing, they can be invoked directly
            cmd_method()
        elif cmd in ['--get-state', '--get-current-uri', '--get-current-title',
                     '--get-current-artist', '--get-current-album',
                     '--get-current-year', '--get-current-length',
                     '--list-playlists', '--get-active-playlist']:
            # These commands output something and require a trailing '\n'
            data = cmd_method()
            if isinstance(data, list):
                for item in data:
                    self._output(item + '\n')
            elif data:
                self._output(data + '\n')

        elif cmd in ['--vol-up', '--vol-down']:
            # These commands take an argument and output nothing
            cmd_method(arg)
        elif cmd in ['--set-active-playlist']:
            # Non-generic command
            if interface.set_active_playlist(arg):
                self._output(_('Playlist \'%s\' is now active\n') % arg)
            else:
                raise RemoteControlException('Playlist %s does not exist.' %
                                             arg)
        elif cmd == '--enqueue':
            if not interface.enqueue(arg):
                raise RemoteControlException('No playlist found to enqueue URI')
        else:
            raise RemoteControlException("Unknown command \'%s\'" % cmd)

        return 0

    def _migrate_config(self, old_version, my_version):
        import mesk.log, mesk.playlist
        mesk.log.info('Migrating config version %s to %s' % (old_version,
                                                             my_version))
        (major, minor, maint) = map(int, old_version.split('.'))

        if major == 0:
            if minor <= 1: # 0.1.x --> 0.2.x
                # Sink name changes for Gstreamer 0.10.x
                sink = mesk.config.get(mesk.CONFIG_AUDIO, 'gst_sink')
                if sink == 'gconf':
                    sink = 'gconfaudiosink'
                elif sink in ['alsa', 'oss', 'esd']:
                    sink += 'sink'
                else:
                    sink = 'autoaudiosink'
                mesk.config.set(mesk.CONFIG_AUDIO, 'gst_sink', sink)

                # Remove unused 'auto_open' in all playlist configs
                for sect in mesk.config.sections():
                    if sect.startswith(mesk.CONFIG_PLAYLIST):
                        mesk.config.remove_option(sect, 'auto_open')

                minor = 2

            if minor <= 2: # 0.2.x --> 0.3.x
                # Clear user playlists.  The original m3u files are left
                # untouched and can be reimported if desired.
                import mesk, config
                for name in config.get_all_playlist_names():
                    sect = mesk.CONFIG_PLAYLIST + '.' + name
                    mesk.config.remove_section(sect)
                mesk.config.set(mesk.CONFIG_MAIN, 'playlists', 'Playlist')

import optparse
class OptionParser(optparse.OptionParser):
    def __init__(self):
        version_str = \
'''%s %s (%s)
(C) Copyright 2006-2007 Travis Shirk <travis@pobox.com>
This program comes with ABSOLUTELY NO WARRANTY! See COPYING for details.
* See --help/-h and/or the manual page for more info.''' % \
(mesk.info.APP_NAME, mesk.info.APP_VERSION, mesk.info.APP_CODENAME)

        optparse.OptionParser.__init__(self,
                                       usage='%s [OPTIONS] [URI ...]' % \
                                             mesk.info.APP_NAME.lower(),
                                       version=version_str)
        self.add_option('-p', '--profile', dest='profile',
                        help=_('Start with profile NAME.'), metavar='NAME')

        # Remote control options
        rc_opts = optparse.OptionGroup(self, _('Remote Control Options'))
        rc_opts.set_description(
            _('The remote control options operate on a running instance of '
              'Mesk, starting the app if necessary. If multiples instances of '
              'Mesk are running the profile option can be used to determine '
              'which instance to pass the command.'))
        rc_opts.add_option('--stop', action='callback',
                           callback=self._remote_option_cb,
                           help=_('Stop playback'))
        rc_opts.add_option('--play', action='callback',
                           callback=self._remote_option_cb,
                           help=_('Start playback'))
        rc_opts.add_option('--pause', action='callback',
                           callback=self._remote_option_cb,
                           help=_('Pause playback'))
        rc_opts.add_option('--play-pause', action='callback',
                           callback=self._remote_option_cb,
                           help=_('If playing, playback is paused. Otherwise '
                                  'the player is started.'))
        rc_opts.add_option('--prev', action='callback',
                           callback=self._remote_option_cb,
                           help=_('Previous track'))
        rc_opts.add_option('--next', action='callback',
                           callback=self._remote_option_cb,
                           help=_('Next track'))
        rc_opts.add_option('--toggle-mute', action='callback',
                           callback=self._remote_option_cb,
                           dest='toggle_mute', help=_('Mute/Unmute'))
        rc_opts.add_option('--vol-up', action='callback',
                           callback=self._remote_option_cb,
                           type=float, metavar='N',
                           help=_('Increase the volume by N% '
                                  '(0.0 <= n <= 1.0)'))
        rc_opts.add_option('--vol-down', action='callback',
                           callback=self._remote_option_cb,
                           type=float, metavar='N',
                           help=_('Decrease the volume by N%'
                                  '(0.0 <= n <= 1.0)'))
        rc_opts.add_option('--get-state', action='callback',
                           callback=self._remote_option_cb,
                           help=_('Returns the current state of the audio '
                                  'player (stopped, playing, paused).'))
        rc_opts.add_option('--get-current-uri', action='callback',
                           callback=self._remote_option_cb,
                           help=_('Returns the URI of the current audio '
                                  'source.'))
        rc_opts.add_option('--get-current-title', action='callback',
                           callback=self._remote_option_cb,
                           help=_('Returns the title of the current audio '
                                  'source.'))
        rc_opts.add_option('--get-current-artist', action='callback',
                           callback=self._remote_option_cb,
                           help=_('Returns the artist of the current audio '
                                  'source.'))
        rc_opts.add_option('--get-current-album', action='callback',
                           callback=self._remote_option_cb,
                           help=_('Returns the album name of the current audio '
                                  'source.'))
        rc_opts.add_option('--get-current-year', action='callback',
                           callback=self._remote_option_cb,
                           help=_('Returns the year of the current audio '
                                  'source.'))
        rc_opts.add_option('--get-current-length', action='callback',
                           callback=self._remote_option_cb,
                           help=_('Returns the length (in seconds) of the '
                                  'current audio source.'))
        rc_opts.add_option('--list-playlists', action='callback',
                           callback=self._remote_option_cb,
                           help=_('List all playlists.'))
        rc_opts.add_option('--get-active-playlist', action='callback',
                           callback=self._remote_option_cb,
                           help=_('List the name of the active '
                                  'PlaylistControl.  This value may be empty '
                                  'if no playlists are active (e.g. a CDROM '
                                  'is active).'))
        rc_opts.add_option('--set-active-playlist', action='callback',
                           callback=self._remote_option_cb,
                           metavar='NAME', type=str,
                           help=_('Set the active playlist.'))
        rc_opts.add_option('--enqueue', action='callback',
                           callback=self._remote_option_cb,
                           metavar='URI', type=str,
                           help=_('Enqueue URI to the active playlist.'))
        rc_opts.add_option('--toggle-visible', action='callback',
                           callback=self._remote_option_cb,
                           help=_('Show/hide the main window (minimize to '
                                  'system tray)'))
        rc_opts.add_option('--raise-window', action='callback',
                           callback=self._remote_option_cb,
                           help=_('Raise the main window (bring to front).'))
        self.add_option_group(rc_opts)

        # Advanced (developer) options
        debug_opts = optparse.OptionGroup(self, _('Advanced Options'))
        debug_opts.add_option('-l', '--log-level', dest='log_level',
                              help=_('Select the amount of terminal logging. '
                                     'May be CRITICAL, ERROR, WARNING, INFO, '
                                     'VERBOSE, or DEBUG'),
                              metavar='LEVEL')
        debug_opts.add_option('--debug', action='store_true',
                              dest='debug',
                              help=_('Break in python debugger on unhandled '
                                     'exceptions.'))
        debug_opts.add_option('--run-profiler', action='store_true',
                              dest='run_profiler',
                              help=_('Run using python profiler.'))
        debug_opts.add_option('--gst-help', action='store_true',
                              dest='gst_help',
                              help=_('Display Gstreamer command line options.'))
        self.add_option_group(debug_opts)

        # Set defaults
        self.set_defaults(profile='', debug=False, run_profiler=False)
        self._remote_options = []

    def parse_args(self, args=None, values=None):
        '''Returns an extra third tuple value which is a list of 2-value tuples.
        These are the remote commands and argument values as they are not stored
        in opts.'''
        opts, args = optparse.OptionParser.parse_args(self, args, values)
        return (opts, args, self._remote_options)

    def _remote_option_cb(self, option, opt_str, value, parser):
        self._remote_options.append((option.get_opt_string(), value))

### Main ###
import sys, os
import gtk, gobject

# Init threads
os.environ['PYGTK_USE_GIL_STATE_API'] = ''
gobject.threads_init()

import mesk
from mesk.i18n import _

import traceback
try:
    app = MeskApp()
    if app.opts.run_profiler:
        import profile, pstats
        profile_out = 'mesk-profile.txt'
        profile.run('app.run()', profile_out)

        p = pstats.Stats(profile_out)
        p.sort_stats('cumulative').print_stats(100)
    else:
        app.run()
    retval = 0
except RemoteControlException, ex:
    mesk.log.error('%s' % str(ex))
    retval = 1
except SystemExit, ex:
    retval = int(str(ex))
    mesk.log.debug('Caught SystemExit: %s' % retval)
except Exception, ex:
    import dialogs
    from mesk.gtk_utils import escape_pango_markup
    dialog = dialogs.ErrorDialog(parent=None)
    if isinstance(ex, mesk.MeskException):
        dialog.set_markup('<b>%s</b>' % escape_pango_markup(ex.primary_msg))
        dialog.format_secondary_text(ex.secondary_msg)
    else:
        dialog.set_markup('<b>%s</b>' % escape_pango_markup(str(ex)))
        dialog.format_secondary_text(traceback.format_exc())
    dialog.run()
    retval = 2

sys.exit(retval)
