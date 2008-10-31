#   Brauniger/Flytec high-level functions
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
import sys
from tempfile import mkstemp

from flytecdevice import FlytecDevice


class Flytec(object):

    def __init__(self, file_or_path, cachedir=None):
        self.device = FlytecDevice(file_or_path)
        self._memory = [None] * 352
        self._routes = None
        self._snp = self.device.pbrsnp()
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
                page = self.device.pbrmemr(slice(address, address + 8))
                self._memory[address:address + len(page)] = page
                address += len(page)
            else:
                address += 1
        return ''.join(map(chr, self._memory[sl]))

    def route_unlink(self, route):
        if not route.index:
            return False
        self.device.pbrrtx(route)
        if not self._routes is None:
            self._routes = [r for r in self._routes if r != route]
        return True

    def routes(self):
        if self._routes is None:
            self._routes = self.device.pbrrts()
        return self._routes

    def snp(self):
        if self._snp is None:
            self._snp = self.device.pbrsnp()
        return self._snp

    def tracklog(self, track):
        if track.index in self._tracklogs:
            return self._tracklogs[track.index]
        filename = track.dt.strftime('%d.%m.%y,%H:%M:%S')
        path = os.path.join(self.tracklogcachedir, filename + '.gz')
        try:
            with open(path) as file:
                gzfile = GzipFile(None, 'r', None, file)
                tracklog = gzfile.read()
                gzfile.close()
        except IOError:
            tracklog = ''.join(self.device.pbrtr(track.index))
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
            self._tracks = self.device.pbrtl()
        return self._tracks

    def waypoint_get(self, long_name):
        if self._waypoints is None:
            self.waypoints()
        for waypoint in self._waypoints:
            if waypoint.long_name == long_name:
                return waypoint
        return None

    def waypoint_unlink(self, waypoint):
        if self._routes is None:
            self.routes()
        for route in self._routes:
            if any(rp.long_name == waypoint.long_name
                   for rp in route.routepoints):
                return False
        self.device.pbrwpx(waypoint)
        self._waypoints = [wp for wp in self._waypoints if wp != waypoint]
        return True

    def waypoints(self):
        if self._waypoints is None:
            self._waypoints = self.device.pbrwps()
        return self._waypoints
