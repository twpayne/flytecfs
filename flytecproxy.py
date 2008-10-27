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
from tempfile import mkstemp

from serialproxy import SerialProxy


class FlytecProxy(object):

    def __init__(self, flytec, cachedir=None):
        self.flytec = SerialProxy(flytec)
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
        self._tracklogs[track.index] = tracklog
        return self._tracklogs[track.index]

    def tracks(self):
        if self._tracks is None:
            self._tracks = self.flytec.pbrtl()
        return self._tracks

    def waypoint(self, long_name):
        if self._waypoints is None:
            self._waypoints()
        return self._waypoints_by_long_name[long_name]

    def waypoints(self):
        if self._waypoints is None:
            self._waypoints = self.flytec.pbrwps()
            self._waypoints_by_long_name = {}
            for waypoint in self._waypoints:
                self._waypoints_by_long_name[waypoint.long_name] = waypoint
        return self._waypoints
