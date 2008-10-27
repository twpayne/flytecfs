#   Flytec/Brauniger FUSE functions
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


# TODO cache tracklogs
# TODO tracklogs.zip
# TODO tracklogs/*.IGC
# TODO routes/*.gpx
# TODO waypoints/*.gpx
# nlink on waypoints?

from __future__ import with_statement

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO
import errno
import logging
import os
from pprint import pprint
import stat
import sys
import time
try:
    from xml.etree.cElementTree import ElementTree, TreeBuilder
except ImportError:
    from xml.etree.ElementTree import ElementTree, TreeBuilder

import fuse

from flytec import Flytec, POSIXSerialIO


fuse.fuse_python_api = (0, 2)


class tag(object):

    def __init__(self, tb, name, attrs={}):
        self.tb = tb
        self.name = name
        self.attrs = attrs

    def __enter__(self):
        self.tb.start(self.name, self.attrs)
        return self.tb

    def __exit__(self, type, value, traceback):
        self.tb.end(self.name)


GPX_NAMESPACE = 'http://www.topografix.com/GPX/1/1'
GPX_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'


class gpx_tag(object):

    def __init__(self, tb):
        self.tb = tb

    def __enter__(self):
        attrs = {
            'creator': 'http://github.com/twpayne/tini/wikis',
            'version': '1.1',
            'xmlns': GPX_NAMESPACE,
            'xmlns:xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'xsi:schemaLocation': 'http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd',
            }
        self.tb.start('gpx', attrs)
        return self.tb

    def __exit__(self, type, value, traceback):
        self.tb.end('gpx')


class Stat(fuse.Stat):

    def __init__(self, **kwargs):
        self.st_dev = 0
        self.st_ino = 0
        self.st_mode = 0
        self.st_nlink = 0
        self.st_uid = 0
        self.st_gid = 0
        self.st_size = 0
        self.st_rdev = 0
        self.st_blksize = 4096
        self.st_blocks = 0
        self.st_atime = 0
        self.st_mtime = 0
        self.st_ctime = 0
        fuse.Stat.__init__(self, **kwargs)


class Direntry(fuse.Direntry):

    def __init__(self, name, **kwargs):
        fuse.Direntry.__init__(self, name, **kwargs)
        self.st = Stat()
        self.st.st_mode = self.type

    def stat(self):
        return self.st


class TracklogFile(Direntry):

    def __init__(self, flytec, track):
        Direntry.__init__(self, track.igc_filename, type=stat.S_IFREG)
        self.flytec = flytec
        self.track = track
        self.content = None
        self.st.st_mode |= 0444
        self.st.st_nlink = 1
        self.st.st_ctime = time.mktime(track.dt.timetuple())
        self.st.st_mtime = self.st.st_ctime + track.duration.seconds
        self.st.st_atime = self.st.st_mtime

    def open(self, flags):
        if flags & (os.O_RDONLY | os.O_RDWR | os.O_WRONLY) != os.O_RDONLY:
            return -errno.EACCESS

    def read(self, size, offset):
        if self.content is None:
            self.content = ''.join(self.flytec.pbrtr(self.track.index))
        self.st.st_size = len(self.content)
        return self.content[offset:offset + size]


class WaypointsFile(Direntry):

    def __init__(self, flytec):
        Direntry.__init__(self, 'waypoints.gpx', type=stat.S_IFREG)
        self.flytec = flytec
        self.content = None
        self.st.st_mode |= 0444
        self.st.st_nlink = 1

    def open(self, flags):
        if flags & (os.O_RDONLY | os.O_RDWR | os.O_WRONLY) != os.O_RDONLY:
            return -errno.EACCESS

    def read(self, size, offset):
        if self.content is None:
            string_io = StringIO()
            string_io.write('<?xml version="1.0" encoding="utf-8"?>')
            with gpx_tag(TreeBuilder()) as tb:
                for waypoint in self.flytec.ipbrwps():
                    lat = '%.8f' % (waypoint.lat / 60000.0)
                    lon = '%.8f' % (waypoint.lon / 60000.0)
                    with tag(tb, 'wpt', {'lat': lat, 'lon': lon}):
                        with tag(tb, 'name'):
                            tb.data(waypoint.long_name.rstrip())
                        with tag(tb, 'ele'):
                            tb.data(str(waypoint.alt))
            ElementTree(tb.close()).write(string_io)
            self.content = string_io.getvalue()
            string_io.close()
        return self.content[offset:offset + size]


class RoutesFile(Direntry):

    def __init__(self, flytec):
        Direntry.__init__(self, 'routes.gpx', type=stat.S_IFREG)
        self.flytec = flytec
        self.content = None
        self.st.st_mode |= 0444
        self.st.st_nlink = 1

    def open(self, flags):
        if flags & (os.O_RDONLY | os.O_RDWR | os.O_WRONLY) != os.O_RDONLY:
            return -errno.EACCESS

    def read(self, size, offset):
        if self.content is None:
            string_io = StringIO()
            string_io.write('<?xml version="1.0" encoding="utf-8"?>')
            waypoints = {}
            for waypoint in self.flytec.ipbrwps():
                waypoints[waypoint.long_name] = waypoint
            with gpx_tag(TreeBuilder()) as tb:
                for route in self.flytec.ipbrrts():
                    with tag(tb, 'rte'):
                        with tag(tb, 'name'):
                            tb.data(route.name.rstrip())
                        for routepoint in route.routepoints:
                            waypoint = waypoints[routepoint.long_name]
                            lat = '%.8f' % (waypoint.lat / 60000.0)
                            lon = '%.8f' % (waypoint.lon / 60000.0)
                            with tag(tb, 'rtept', {'lat': lat, 'lon': lon}):
                                with tag(tb, 'name'):
                                    tb.data(waypoint.long_name.rstrip())
                                with tag(tb, 'ele'):
                                    tb.data(str(waypoint.alt))
            ElementTree(tb.close()).write(string_io)
            self.content = string_io.getvalue()
            string_io.close()
        return self.content[offset:offset + size]


class FlytecFuse(fuse.Fuse):

    def __init__(self, *args, **kwargs):
        fuse.Fuse.__init__(self, *args, **kwargs)
        self.device = '/dev/ttyUSB0'

    def main(self):
        self.time = time.time()
        self.flytec = Flytec(POSIXSerialIO(self.device))
        self.direntries = {}
        for track in self.flytec.pbrtl():
            self.direntries['/' + track.igc_filename] = TracklogFile(self.flytec, track)
        self.direntries['/waypoints.gpx'] = WaypointsFile(self.flytec)
        self.direntries['/routes.gpx'] = RoutesFile(self.flytec)
        fuse.Fuse.main(self)

    def getattr(self, path):
        if path == '/':
            return Stat(st_mode=stat.S_IFDIR | 0755, st_nlink=2)
        if path in self.direntries:
            return self.direntries[path].stat()
        return -errno.ENOENT

    def readdir(self, path, offset):
        for name in ['.', '..']:
            yield Direntry(name, type=stat.S_IFDIR)
        for direntry in self.direntries.values():
            yield direntry

    def open(self, path, flags):
        if path in self.direntries:
            return self.direntries[path].open(flags)
        return -errno.ENOENT

    def read(self, path, size, offset):
        if path in self.direntries:
            return self.direntries[path].read(size, offset)
        return -errno.ENOENT


def main(argv):
    logging.basicConfig(level=logging.INFO)
    server = FlytecFuse(dash_s_do='setsingle', usage=fuse.Fuse.fusage)
    server.parser.add_option(mountopt='device', metavar='DEVICE', help='set device')
    server.parse(args=argv, values=server, errex=1)
    if server.fuse_args.mount_expected():
        server.main()


if __name__ == '__main__':
    main(sys.argv)
