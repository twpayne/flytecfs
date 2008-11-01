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


from __future__ import with_statement

from collections import defaultdict
import datetime
from dircache import listdir
from gzip import GzipFile
import os
import os.path
import re
import sys
from tempfile import mkstemp

from flytecdevice import FlytecDevice


MANUFACTURER = {}
for instrument in 'COMPEO COMPEO+ COMPETINO COMPETINO+ GALILEO'.split(' '):
    MANUFACTURER[instrument] = ('B', 'XBR', 'Brauniger')
for instrument in '5020 5030 6020 6030'.split(' '):
    MANUFACTURER[instrument] = ('F', 'XFL', 'Flytec')

TRACKLOG_CACHE_PATH_RE = re.compile(r'\A(\d{4})-(\d\d)-(\d\d)T'
                                    r'(\d\d):(\d\d):(\d\d)Z\.gz\Z')


class Flytec(object):

    def __init__(self, file_or_path, cachedir=None):
        self.device = FlytecDevice(file_or_path)
        self._memory = [None] * 352
        self._routes = None
        self._snp = self.device.pbrsnp()
        self._tracklogs = None
        self._waypoints = None
        self.revs = defaultdict(int)
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
        self.revs['routes'] += 1
        self.revs['route_%s' % route.long_name] += 1
        return True

    def routes(self):
        if self._routes is None:
            self._routes = self.device.pbrrts()
        return self._routes

    def snp(self):
        if self._snp is None:
            self._snp = self.device.pbrsnp()
        return self._snp

    def tracklog_content(self, tracklog):
        if hasattr(tracklog, '_content'):
            return tracklog._content
        try:
            with open(tracklog.cache_path) as file:
                gzfile = GzipFile(tracklog.igc_filename, 'r', None, file)
                tracklog._content = gzfile.read()
                gzfile.close()
        except IOError:
            tracklog._content = ''.join(self.device.pbrtr(tracklog.index))
            try:
                if not os.path.exists(self.tracklogcachedir):
                    os.makedirs(self.tracklogcachedir)
                fd, tmppath = mkstemp('.IGC.gz', '', self.tracklogcachedir) 
                try:
                    with os.fdopen(fd, 'w') as file:
                        gzfile = GzipFile(None, 'w', 9, file)
                        gzfile.write(tracklog._content)
                        gzfile.close()
                    os.rename(tmppath, tracklog.cache_path)
                except:
                    os.remove(tmppath)
                    raise
            except IOError:
                pass
        return tracklog._content

    def tracklog_unlink(self, tracklog):
        try:
            os.unlink(tracklog.cache_path)
        except IOError:
            pass
        self._tracklogs = [t for t in self._tracklogs if t != tracklog]
        self.revs['tracklogs'] += 1

    def tracklogs(self):
        if not self._tracklogs is None:
            return self._tracklogs
        self._tracklogs = self.device.pbrtl()
        snp = self.snp()
        manufacturer = MANUFACTURER[snp.instrument][1]
        serial_number = re.sub(r'\A0+', '', snp.serial_number)
        dates = {}
        for tracklog in self._tracklogs:
            dates.setdefault(tracklog.dt.date(), set()).add(tracklog.dt.time())
        if os.path.exists(self.tracklogcachedir):
            for path in listdir(self.tracklogcachedir):
                m = TRACKLOG_CACHE_PATH_RE.match(path)
                if not m:
                    continue
                date = datetime.date(*map(int, m.groups()[0:3]))
                time = datetime.time(*map(int, m.groups()[3:6]))
                dates.setdefault(date, set()).add(time)
        for date, _set in dates.items():
            dates[date] = sorted(_set)
        for tracklog in self._tracklogs:
            index = dates[tracklog.dt.date()].index(tracklog.dt.time()) + 1
            tracklog.igc_filename = '%s-%s-%s-%02d.IGC' \
                                    % (tracklog.dt.strftime('%Y-%m-%d'),
                                       manufacturer,
                                       serial_number,
                                       index)
            filename = tracklog.dt.strftime('%Y-%m-%dT%H:%M:%SZ.gz')
            tracklog.cache_path = os.path.join(self.tracklogcachedir, filename)
            date = tracklog.dt.date()
        return self._tracklogs

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
        self.revs['waypoints'] += 1
        self.revs['waypoint_%s' % waypoint.long_name] += 1
        return True

    def waypoints(self):
        if self._waypoints is None:
            self._waypoints = self.device.pbrwps()
        return self._waypoints
