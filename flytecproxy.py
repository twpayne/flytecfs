#   Flytec thread and caching functions
#   Copyright (C) 2008  Tom Payne
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.


# TODO move cache into Flytec object to correctly calculate track indexes
# except cache access would then be serialized.  cleverness required.


from __future__ import with_statement

from gzip import GzipFile
import os
import os.path
from pprint import pprint
from Queue import Queue
import sys
from tempfile import mkstemp
from threading import Event, Lock, Thread


class SerialProxy(object):

    def __init__(self, obj):
        self.events = {}
        self.events_lock = Lock()
        self.queue = Queue()
        self.results = {}
        self.results_lock = Lock()
        thread = Thread(target=self.__thread, args=(obj,))
        thread.setDaemon(True)
        thread.start()

    def __thread(self, obj):
        while True:
            key = self.queue.get()
            with self.events_lock:
                event = self.events[key]
            with self.results_lock:
                if key in self.results:
                    event.set()
                    continue
            attr, args = key
            try:
                result = getattr(obj, attr)(*args)
            except:
                with self.results_lock:
                    self.results[key] = (sys.exc_info(), None)
            else:
                with self.results_lock:
                    self.results[key] = (None, result)
            event.set()

    def __getattr__(self, attr):
        def f(*args):
            key = (attr, args)
            with self.events_lock:
                if not key in self.events:
                    self.events[key] = Event()
                event = self.events[key]
            if not event.isSet():
                self.queue.put(key)
                event.wait()
            with self.results_lock:
                exc_info, result = self.results[key]
            if exc_info:
                type, value, traceback = exc_info
                raise type, value, traceback
            return result
        setattr(self, attr, f)
        return f


class FlytecCache(object):

    def __init__(self, flytec, cachedir=None):
        self.flytec = flytec
        self._memory = [None] * 352
        self._routes = None
        self._snp = self.flytec.pbrsnp()
        self._tracklogs = {}
        self._tracks = None
        self._waypoints = None
        self.cachedir = cachedir or os.path.expanduser('~/.flytecfs/cache')
        self.tracklogcachedir = os.path.join(self.cachedir,
                                             self._snp.instrument,
                                             self._snp.serial_number,
                                             'tracklogs')

    def memory(self, sl):
        if sl.start >= len(self._memory):
            return ''
        address = sl.start
        stop = sl.stop if sl.stop <= len(self._memory) else len(self._memory)
        while address < stop:
            if self._memory[address] is None:
                page = self.flytec.pbrmemr(slice(address, address + 8))
                self._memory[address:address + len(page)] = page
                address += len(page)
            else:
                address += 1
        return ''.join(map(chr, self._memory[sl]))

    def routes(self):
        if self._routes is None:
            self._routes = self.flytec.pbrrts()
        return self._routes

    def snp(self):
        if self._snp is None:
            self._snp = self.flytec.pbrsnp()
        return self._snp

    def tracklog(self, track):
        if track.index in self._tracklogs:
            return self._tracklogs[track.index]
        filename = track.dt.strftime('%Y-%m-%dT%H:%M:%SZ.IGC')
        path = os.path.join(self.tracklogcachedir, filename + '.gz')
        try:
            with open(path) as file:
                gzfile = GzipFile(None, 'r', None, file)
                tracklog = gzfile.read()
                gzfile.close()
        except IOError:
            tracklog = ''.join(self.flytec.pbrtr(track.index))
            try:
                if not os.path.exists(self.tracklogcachedir):
                    os.makedirs(self.tracklogcachedir)
                fd, tmppath = mkstemp('.IGC.gz', '', self.tracklogcachedir) 
                try:
                    with os.fdopen(fd, 'w') as file:
                        gzfile = GzipFile(filename, 'w', 9, file)
                        gzfile.write(tracklog)
                        gzfile.close()
                    os.rename(tmppath, path)
                except:
                    os.remove(tmppath)
                    raise
            except IOError:
                pass
        self._tracklogs[track.index] = tracklog
        return self._tracklogs[track.index]

    def tracks(self):
        if self._tracks is None:
            self._tracks = self.flytec.pbrtl()
        return self._tracks

    def waypoint(self, long_name):
        if self._waypoints is None:
            self.waypoints()
        return self._waypoints_by_long_name[long_name]

    def waypoints(self):
        if self._waypoints is None:
            self._waypoints = self.flytec.pbrwps()
            self._waypoints_by_long_name = {}
            for waypoint in self._waypoints:
                self._waypoints_by_long_name[waypoint.long_name] = waypoint
        return self._waypoints
