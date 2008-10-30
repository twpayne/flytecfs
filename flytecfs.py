#   Flytec/Brauniger Filesystem
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


# TODO enable multi-threading
# TODO move tracklog cache into this module?
# TODO waypoint upload
# TODO fix route deletion
# TODO route upload
# TODO preferences application


from __future__ import with_statement

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO
from contextlib import contextmanager
import errno
import logging
import sys
import time
try:
    from xml.etree.cElementTree import ElementTree, TreeBuilder
except ImportError:
    from xml.etree.ElementTree import ElementTree, TreeBuilder
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

import fuse

import filesystem
from flytec import Flytec, POSIXSerialIO
from flytecproxy import FlytecCache, SerialProxy


class File(filesystem.File):

    def __init__(self, flytec, *args, **kwargs):
        filesystem.File.__init__(self, *args, **kwargs)
        self.flytec = flytec


class Directory(filesystem.Directory):

    def __init__(self, flytec, *args, **kwargs):
        filesystem.Directory.__init__(self, *args, **kwargs)
        self.flytec = flytec


@contextmanager
def tag(tb, name, attrs={}):
    tb.start(name, attrs)
    yield tb
    tb.end(name)


GPX_NAMESPACE = 'http://www.topografix.com/GPX/1/1'
GPX_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'


@contextmanager
def gpx_tag(tb):
    attrs = {
        'creator': 'http://code.google.com/p/flytecfs',
        'version': '1.1',
        'xmlns': GPX_NAMESPACE,
        'xmlns:xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsi:schemaLocation': 'http://www.topografix.com/GPX/1/1 '
                              'http://www.topografix.com/GPX/1/1/gpx.xsd',
        }
    with tag(tb, 'gpx', attrs) as tb:
        yield tb


@contextmanager
def wptType_tag(tb, waypoint, name):
    lat = '%.8f' % (waypoint.lat / 60000.0)
    lon = '%.8f' % (waypoint.lon / 60000.0)
    with tag(tb, name, {'lat': lat, 'lon': lon}):
        with tag(tb, 'name'):
            tb.data(waypoint.long_name.rstrip())
        with tag(tb, 'ele'):
            tb.data(str(waypoint.alt))


@contextmanager
def rte_tag(tb, route, waypoint_get):
    with tag(tb, 'rte'):
        with tag(tb, 'name'):
            tb.data(route.name.rstrip())
        for routepoint in route.routepoints:
            waypoint = waypoint_get(routepoint.long_name)
            wptType_tag(tb, waypoint, 'rtept')


def write_xml(et, file, indent='\t', prefix=''):
    attrs = ''.join(' %s="%s"' % pair for pair in et.attrib.items())
    if et.getchildren():
        file.write('%s<%s%s>\n' % (prefix, et.tag, attrs))
        for child in et.getchildren():
            write_xml(child, file, indent, prefix + indent)
        file.write('%s</%s>\n' % (prefix, et.tag))
    elif et.text:
        file.write('%s<%s%s>%s</%s>\n' % (prefix, et.tag, attrs, et.text, et.tag))
    else:
        file.write('%s<%s%s/>\n' % (prefix, et.tag, attrs))


class GPXFile(File):

    def content(self):
        if hasattr(self, '_content'):
            return self._content
        string_io = StringIO()
        string_io.write('<?xml version="1.0" encoding="utf-8"?>\n')
        with gpx_tag(TreeBuilder()) as tb:
            self.gpx_content(tb)
        write_xml(ElementTree(tb.close()).getroot(), string_io)
        self._content = string_io.getvalue()
        return self._content

    def gpx_content(self):
        pass


class MemoryFile(File):

    def __init__(self, flytec, *args, **kwargs):
        File.__init__(self, flytec, *args, **kwargs)
        self.st_size = 352
        self.st_blksize = 8
        self.st_blocks = (self.st_size + self.st_blksize - 1) / self.st_blksize

    def getattr(self):
        return self

    def read(self, size, offset):
        if offset >= self.st_size:
            return ''
        if offset + size > self.st_size:
            size = self.st_size - offset
        return self.flytec.memory(slice(offset, offset + size))


class RoutesDirectory(Directory):

    def content(self):
        for route in self.flytec.routes():
            yield RouteFile(self.flytec, route)
        yield RoutesFile(self.flytec, 'routes.gpx')


class RouteFile(GPXFile):

    def __init__(self, flytec, route):
        GPXFile.__init__(self, flytec, '%s.gpx' % route.name.rstrip())
        self.route = route

    def gpx_content(self, tb):
        rte_tag(tb, self.route, self.flytec.waypoint_get)

    def unlink(self):
        self.flytec.route_unlink(self.route)


class RoutesFile(GPXFile):

    def gpx_content(self, tb):
        for route in self.flytec.routes():
            rte_tag(tb, route, self.flytec.waypoint_get)


class SettingsDirectory(Directory):

    def __init__(self, *args, **kwargs):
        Directory.__init__(self, *args, **kwargs)
        self._content = []
        self._content.append(MemoryFile(self.flytec, '.memory'))

    def content(self):
        return iter(self._content)


class TracklogFile(File):

    def __init__(self, flytec, track):
        File.__init__(self, flytec, track.igc_filename)
        self.track = track
        self.st_ctime = time.mktime(track.dt.timetuple())
        self.st_mtime = self.st_ctime + track.duration.seconds
        self.st_atime = self.st_mtime

    def content(self):
        if hasattr(self, '_content'):
            return self._content
        self._content = ''.join(self.flytec.tracklog(self.track))
        return self._content


class TracklogsDirectory(Directory):

    def __init__(self, flytec, *args, **kwargs):
        Directory.__init__(self, flytec, *args, **kwargs)
        self._content = []
        for track in self.flytec.tracks():
            self._content.append(TracklogFile(self.flytec, track))
        self._content.append(TracklogsZipFile(self.flytec, 'tracks.zip'))

    def content(self):
        return iter(self._content)


class TracklogsZipFile(File):

    def __init__(self, flytec, *args, **kwargs):
        File.__init__(self, flytec, *args, **kwargs)
        self.st_ctime = time.mktime(min(t.dt for t in self.flytec.tracks()).timetuple())
        self.st_mtime = time.mktime(max(t.dt + t.duration for t in self.flytec.tracks()).timetuple())
        self.st_atime = self.st_mtime

    def content(self):
        if hasattr(self, '_content'):
            return self._content
        string_io = StringIO()
        zip_file = ZipFile(string_io, 'w', ZIP_DEFLATED)
        for track in self.flytec.tracks():
            zi = ZipInfo(track.igc_filename)
            zi.compress_type = ZIP_DEFLATED
            zi.date_time = (track.dt + track.duration).timetuple()[:6]
            zi.external_attr = 0444 << 16
            zip_file.writestr(zi, self.flytec.tracklog(track))
        zip_file.close()
        self._content = string_io.getvalue()
        return self._content


class WaypointsDirectory(Directory):

    def content(self):
        for waypoint in self.flytec.waypoints():
            yield WaypointFile(self.flytec, waypoint)
        yield WaypointsFile(self.flytec, 'waypoints.gpx')


class WaypointFile(GPXFile):

    def __init__(self, flytec, waypoint):
        GPXFile.__init__(self, flytec, '%s.gpx' % waypoint.long_name.rstrip())
        self.waypoint = waypoint

    def gpx_content(self, tb):
        wptType_tag(tb, self.waypoint, 'wpt')

    def unlink(self):
        if not self.flytec.waypoint_unlink(self.waypoint):
            raise IOError, (errno.EPERM, None)


class WaypointsFile(GPXFile):

    def gpx_content(self, tb):
        for waypoint in self.flytec.waypoints():
            wptType_tag(tb, waypoint, 'wpt')


class FlytecRootDirectory(Directory):

    def __init__(self, filesystem):
        flytec = FlytecCache(Flytec(POSIXSerialIO(filesystem.device)))
        Directory.__init__(self, flytec, '')
        self._content = []
        self._content.append(RoutesDirectory(self.flytec, 'routes'))
        self._content.append(SettingsDirectory(self.flytec, 'settings'))
        self._content.append(TracklogsDirectory(self.flytec, 'tracklogs'))
        self._content.append(WaypointsDirectory(self.flytec, 'waypoints'))

    def content(self):
        return iter(self._content)


def main(argv):
    logging.basicConfig(level=logging.INFO)
    server = filesystem.Filesystem(FlytecRootDirectory, dash_s_do='setsingle', usage=fuse.Fuse.fusage)
    server.device = '/dev/ttyUSB0'
    server.parser.add_option(mountopt='device', metavar='DEVICE', help='set device')
    server.parse(args=argv, values=server, errex=1)
    if server.fuse_args.mount_expected():
        server.main()


if __name__ == '__main__':
    main(sys.argv)
