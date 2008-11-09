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

TRACKLOG_ID_RE = re.compile(r'\A(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)Z\Z')


class Flytec(object):

    def __init__(self, file_or_path, cachebasedir=None):
        self.device = FlytecDevice(file_or_path)
        self._memory = [None] * 352
        self._routes = None
        self._routes_rev = None
        self._snp = self.device.pbrsnp()
        self._tracklogs = None
        self._waypoints = None
        self._waypoints_rev = None
        self.revs = defaultdict(int)
        if cachebasedir is None:
            cachebasedir = os.path.expanduser('~/.flytecfs/cache')
        self.cachedir = os.path.join(cachebasedir,
                                     self._snp.instrument,
                                     self._snp.serial_number)

    def get_cache_path(self, *args):
        return os.path.join(self.cachedir, *args)

    def memory(self, sl=slice(None, None)):
        if sl.start is None:
            sl = slice(0, sl.stop)
        elif sl.start >= len(self._memory):
            sl = slice(len(self._memory), sl.stop)
        if sl.stop is None or sl.stop > len(self._memory):
            sl = slice(sl.start, len(self._memory))
        address = sl.start
        while address < sl.stop:
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
            self._routes_rev = self.revs['routes']
        self.revs['route_%s' % route.long_name] += 1
        return True

    def routes(self):
        if self._routes is None or self._routes_rev != self.revs['routes']:
            self._routes = self.device.pbrrts()
            self._routes_rev = self.revs['routes']
        return self._routes

    def snp(self):
        if self._snp is None:
            self._snp = self.device.pbrsnp()
        return self._snp

    def tracklog_content(self, tracklog):
        if hasattr(tracklog, '_content'):
            return tracklog._content
        cache_path = self.get_cache_path('tracklogs', 'contents', tracklog.id)
        try:
            with open(cache_path) as file:
                gzfile = GzipFile(None, 'r', None, file)
                tracklog._content = gzfile.read()
                gzfile.close()
        except IOError:
            tracklog._content = self.device.pbrtr(tracklog)
            try:
                dirname = os.path.dirname(cache_path)
                if not os.path.exists(dirname):
                    os.makedirs(dirname)
                fd, tmppath = mkstemp('', '', dirname) 
                try:
                    with os.fdopen(fd, 'w') as file:
                        gzfile = GzipFile(tracklog.igc_filename, 'w', 9, file)
                        gzfile.write(tracklog._content)
                        gzfile.close()
                    os.rename(tmppath, cache_path)
                except:
                    os.remove(tmppath)
                    raise
            except IOError:
                pass
        return tracklog._content

    def tracklog_rename(self, tracklog, filename):
        tracklog.filename = filename
        try:
            rename_path = self.get_cache_path('tracklogs', 'rename', tracklog.id)
            dirname = os.path.dirname(rename_path)
            if not os.path.exists(dirname):
                os.makedirs(dirname)
            if os.path.lexists(rename_path):
                os.unlink(rename_path)
            os.symlink(filename, rename_path)
        except IOError:
            pass
        self.revs['tracklogs'] += 1

    def tracklog_unlink(self, tracklog):
        cache_path = self.get_cache_path('tracklogs', 'contents', tracklog.id)
        if os.path.exists(cache_path):
            os.unlink(cache_path)
        rename_path = self.get_cache_path('tracklogs', 'rename', tracklog.id)
        if os.path.lexists(rename_path):
            os.unlink(rename_path)
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
        cache_path = self.get_cache_path('tracklogs', 'contents')
        if os.path.exists(cache_path):
            for path in listdir(cache_path):
                m = TRACKLOG_ID_RE.match(path)
                if m:
                    date = datetime.date(*map(int, m.groups()[0:3]))
                    time = datetime.time(*map(int, m.groups()[3:6]))
                    dates.setdefault(date, set()).add(time)
        for date, _set in dates.items():
            dates[date] = sorted(_set)
        for tracklog in self._tracklogs:
            tracklog.id = tracklog.dt.strftime('%Y-%m-%dT%H:%M:%SZ')
            index = dates[tracklog.dt.date()].index(tracklog.dt.time()) + 1
            tracklog.igc_filename = '%s-%s-%s-%02d.IGC' \
                                    % (tracklog.dt.strftime('%Y-%m-%d'),
                                       manufacturer,
                                       serial_number,
                                       index)
            rename_path = self.get_cache_path('tracklogs',
                                              'rename',
                                              tracklog.id)
            if os.path.islink(rename_path):
                tracklog.filename = os.readlink(rename_path)
            else:
                tracklog.filename = tracklog.igc_filename
            date = tracklog.dt.date()
        return self._tracklogs

    def waypoint_create(self, waypoint):
        self.device.pbrwpr(waypoint)
        self.revs['waypoints'] += 1
        self.revs['waypoint_%s' % waypoint.long_name] += 1

    def waypoint_get(self, long_name):
        for waypoint in self.waypoints():
            if waypoint.long_name == long_name:
                return waypoint
        return None

    def waypoint_unlink(self, waypoint):
        for route in self.routes():
            if any(waypoint.long_name == rp.long_name
                   for rp in route.routepoints):
                return False
        self.device.pbrwpx(waypoint)
        self.revs['waypoints'] += 1
        self._waypoints = [w for w in self._waypoints if w != waypoint]
        self._waypoints_rev = self.revs['waypoints']
        self.revs['waypoint_%s' % waypoint.long_name] += 1
        return True

    def waypoints(self):
        if self._waypoints is None \
           or self._waypoints_rev != self.revs['waypoints']:
            self._waypoints = self.device.pbrwps()
            self._waypoints_rev = self.revs['waypoints']
        return self._waypoints
