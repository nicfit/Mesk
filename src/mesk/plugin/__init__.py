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
import os, sys
import gobject

import mesk
from mesk.i18n import _
from interfaces import MetaDataSearch

def emit(listener_type, event, *data):
    '''Emit an event to all active plugins of type listener_type'''
    mgr = get_manager()
    if mgr:
        for plugin in mgr.get_active_plugins(listener_type):
            method = getattr(plugin, event)
            # XXX: There has got to be a better way
            if len(data) == 0:
                method()
            elif len(data) == 1:
                method(data[0])
            elif len(data) == 2:
                method(data[0], data[1])
            elif len(data) == 3:
                method(data[0], data[1], data[2])
            elif len(data) == 4:
                method(data[0], data[1], data[2], data[3])
            elif len(data) == 5:
                method(data[0], data[1], data[2], data[3], data[4])
            else:
                mesk.log.error('Plugin callback argument limit reached')
                assert(False)

def get_menuitems(menu_type):
    items = []
    if get_manager():
        for plugin in get_manager().get_active_plugins(menu_type):
            items += plugin.plugin_view_menu_items()
    return items

def search(caps, artist, album, track, cb, cb_arg=None):
    global __search_thread
    mgr = get_manager()
    if mgr:
        for plugin in get_manager().get_active_plugins(MetaDataSearch):
            if plugin.get_caps() & caps:
                # Start search thread if necessary.
                if __search_thread is None:
                    __search_thread = SearchThread()
                    __search_thread.start()

                __search_thread.search(plugin, artist, album, track, cb, cb_arg)

def shutdown():
    global __manager
    if __manager is not None:
        for plugin in get_manager().get_active_plugins():
            # Shudown each plugin
            plugin.shutdown()
        __manager = None

    global __search_thread
    if __search_thread:
        __search_thread.stop()
        __search_thread.join()
        __search_thread = None

class PluginMgr:
    SYS_PLUGINS_DIR = './plugins'

    def __init__(self):
        # All available plugins {name: plugin_dict}
        self.__all_plugins = {}
        # Active plugins: {name: plugin_instance}
        self.__active_plugins = {}

        sys.path.append(mesk.DEFAULT_PLUGINS_DIR)
        sys.path.append(self.SYS_PLUGINS_DIR)
        def load_plugins(root):
            mesk.log.debug('Loading plugins in %s...' % root)
            plugins = []
            for file in os.listdir(root):
                file = root + os.sep + file
                plugin = self._load_plugin(file)
                if plugin:
                    plugins.append(plugin)
            return plugins
        # The order of these calls dictates that user plugins override
        # system plugins
        load_plugins(self.SYS_PLUGINS_DIR)
        load_plugins(mesk.config.get(mesk.CONFIG_MAIN, 'plugins_dir'))

        # Activate plugins specified in config
        active_plugins_config = mesk.config.getlist(mesk.CONFIG_MAIN, 'plugins')
        for plugin_info in self.__all_plugins.values():
            plugin_name = plugin_info['NAME']
            if plugin_name in active_plugins_config:
                self.activate_plugin(plugin_name)
                i = active_plugins_config.index(plugin_name)
                del active_plugins_config[i]
        # Warn about plugins in the config that were not activated
        for name in active_plugins_config:
            mesk.log.warning(_('Plugin not found: %s') % name)

    def get_all_plugins(self):
        return [plugin for plugin in self.__all_plugins.values()]

    def get_active_plugins(self, type=None):
        if not type:
            return [plugin for plugin in self.__active_plugins.values()]

        plugins = []
        for p in self.__active_plugins.values():
            if isinstance(p, type):
                plugins.append(p)
        return plugins

    def get_plugin(self, name):
        try:
            return self.__active_plugins[name]
        except:
            return None

    def update_active_config(self):
            active_names = \
                [plugin.name for plugin in self.__active_plugins.values()]
            mesk.config.set(mesk.CONFIG_MAIN, 'plugins', active_names)

    def activate_plugin(self, plugin_name):
        if plugin_name not in self.__active_plugins:
            try:
                plugin_info = self.__all_plugins[plugin_name]
                mesk.log.verbose(_('Activating %s plugin') % plugin_name)
                plugin = plugin_info['CLASS']()
                self.__active_plugins[plugin_name] = plugin
            except KeyError:
                mesk.log.warning(_('Invalid plugin name: %s') % plugin_name)
                return False
            except Exception, ex:
                mesk.log.warning(_('Error activating %s plugin: %s') % \
                                 (plugin_name, str(ex)))
                raise
            self.update_active_config()
            return True
        return False

    def deactivate_plugin(self, plugin_name):
        if plugin_name in self.__active_plugins:
            mesk.log.info(_('Deactivating %s plugin') % plugin_name)
            plugin = self.__active_plugins[plugin_name]
            del self.__active_plugins[plugin_name]
            try:
                plugin.shutdown()
            except Exception, ex:
                mesk.log.warning(_('Error deactivating %s plugin: %s') % \
                                 (plugin_name, str(ex)))
                raise
            self.update_active_config()
            return True
        return False

    def _load_plugin(self, plugin_file):
        plugin = None

        (module, ext) = os.path.splitext(plugin_file)
        if not os.path.isfile(plugin_file) or ext != '.py':
            # Non plugin file
            return None

        module = os.path.basename(module)
        try:
            mesk.log.debug(_('Loading plugin %s') % module)
            __import__(module)
            module = sys.modules[module]
            plugin_info = self._get_plugin_info(module)
            if plugin_info:
                self.__all_plugins[plugin_info['NAME']] = plugin_info
        except Exception, ex:
            mesk.log.error(_('Plugin \'%s\' failed to load: %s') % (module,
                                                                    str(ex)))
            return None

        if plugin and not isinstance(plugin, mesk.plugin.Plugin):
            mesk.log.error(_('Invalid type for plugin \'%s\': %s') % \
                           (module, type(plugin)))
            return None

        return plugin

    def _get_plugin_info(self, module):
        try:
            info = getattr(module, 'PLUGIN_INFO')
        except AttributeError, ex:
            mesk.log.verbose('Skipping plugin module %s: %s' % (module,
                                                                str(ex)))
            return None
        else:
            return info

class SearchThread(mesk.utils.Thread):
    def __init__(self):
        import Queue
        mesk.utils.Thread.__init__(self)
        self._queue = Queue.Queue()

    def search(self, plugin, artist, album, track, cb, cb_arg):
        functor = (plugin, artist, album, track, cb, cb_arg)
        self._queue.put(functor)

    def stop(self):
        mesk.utils.Thread.stop(self)
        # Poke the queue
        self._queue.put(None)

    def run(self):
        mesk.log.debug('SearchThread started')

        while True:
            # Check shutdown
            self._lock.acquire()
            if self._stopped:
                self._lock.release()
                break
            self._lock.release()

            functor = self._queue.get()
            if functor:
                try:
                    (plugin, artist, album, track, cb, cb_arg) = functor
                    results = plugin.plugin_metadata_search(artist, album,
                                                            track)
                    gobject.idle_add(lambda: cb(results, cb_arg))
                except Exception, ex:
                    import traceback
                    # Broken plugins do not halt this thread
                    mesk.log.error('SearchThread caught Exception: %s\n%s' %
                                   (str(ex), traceback.format_exc()))

        mesk.log.debug('SearchThread exiting')

# PluginMgr access
__manager = None
def get_manager():
    return __manager
def set_manager(mgr):
    global __manager
    __manager = mgr

# A dedicated thread for plugin searching
__search_thread = None
