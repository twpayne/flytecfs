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
# TODO waypoint deletion
# TODO waypoint upload
# TODO route deletion
# TODO route upload


from __future__ import with_statement

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO
from contextlib import contextmanager
import logging
import sys
import time
try:
    from xml.etree.cElementTree import ElementTree, TreeBuilder
except ImportError:
    from xml.etree.ElementTree import ElementTree, TreeBuilder
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

import fuse

from filesystem import Directory, File, Filesystem

from flytec import Flytec, POSIXSerialIO
from flytecproxy import FlytecCache, SerialProxy


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
def rte_tag(tb, route, lookup):
    with tag(tb, 'rte'):
        with tag(tb, 'name'):
            tb.data(route.name.rstrip())
        for routepoint in route.routepoints:
            waypoint = lookup(routepoint.long_name)
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


class RoutesDirectory(Directory):

    def __init__(self, flytec):
        Directory.__init__(self, 'routes')
        self.add(RoutesFile(flytec))
        for route in flytec.routes():
            self.add(RouteFile(flytec, route))


class RouteFile(GPXFile):

    def __init__(self, flytec, route):
        File.__init__(self, '%s.gpx' % route.name.rstrip())
        self.flytec = flytec
        self.route = route

    def gpx_content(self, tb):
        rte_tag(tb, self.route, self.flytec.waypoint)


class RoutesFile(GPXFile):

    def __init__(self, flytec):
        File.__init__(self, 'routes.gpx')
        self.flytec = flytec

    def gpx_content(self, tb):
        for route in self.flytec.routes():
            rte_tag(tb, route, self.flytec.waypoint)


class TracklogFile(File):

    def __init__(self, flytec, track):
        File.__init__(self, track.igc_filename)
        self.flytec = flytec
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

    def __init__(self, flytec):
        Directory.__init__(self, 'tracklogs')
        self.add(*[TracklogFile(flytec, track) for track in flytec.tracks()])
        self.add(TracklogsZipFile(flytec))


class TracklogsZipFile(File):

    def __init__(self, flytec):
        File.__init__(self, 'tracklogs.zip')
        self.flytec = flytec
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

    def __init__(self, flytec):
        Directory.__init__(self, 'waypoints')
        self.add(WaypointsFile(flytec))
        for waypoint in flytec.waypoints():
            self.add(WaypointFile(flytec, waypoint))


class WaypointFile(GPXFile):

    def __init__(self, flytec, waypoint):
        File.__init__(self, '%s.gpx' % waypoint.long_name.rstrip())
        self.flytec = flytec
        self.waypoint = waypoint

    def gpx_content(self, tb):
        wptType_tag(tb, self.waypoint, 'wpt')


class WaypointsFile(GPXFile):

    def __init__(self, flytec):
        File.__init__(self, 'waypoints.gpx')
        self.flytec = flytec

    def gpx_content(self, tb):
        for waypoint in self.flytec.waypoints():
            wptType_tag(tb, waypoint, 'wpt')


class FlytecDirectory(Directory):

    def __init__(self, filesystem):
        Directory.__init__(self, '')
        flytec = FlytecCache(Flytec(POSIXSerialIO(filesystem.device)))
        self.add(RoutesDirectory(flytec))
        self.add(TracklogsDirectory(flytec))
        self.add(WaypointsDirectory(flytec))


def main(argv):
    logging.basicConfig(level=logging.INFO)
    server = Filesystem(FlytecDirectory, dash_s_do='setsingle', usage=fuse.Fuse.fusage)
    server.device = '/dev/ttyUSB0'
    server.parser.add_option(mountopt='device', metavar='DEVICE', help='set device')
    server.parse(args=argv, values=server, errex=1)
    if server.fuse_args.mount_expected():
        server.main()


if __name__ == '__main__':
    main(sys.argv)
