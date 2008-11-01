#   GPX functions
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

from contextlib import contextmanager
try:
    from xml.etree.cElementTree import ElementTree, TreeBuilder
except ImportError:
    from xml.etree.ElementTree import ElementTree, TreeBuilder


@contextmanager
def tag(tb, name, attrs={}):
    tb.start(name, attrs)
    yield tb
    tb.end(name)


GPX_NAMESPACE = 'http://www.topografix.com/GPX/1/1'
GPX_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'


@contextmanager
def gpx_tag():
    attrs = {
        'creator': 'http://code.google.com/p/flytecfs',
        'version': '1.1',
        'xmlns': GPX_NAMESPACE,
        'xmlns:xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsi:schemaLocation': 'http://www.topografix.com/GPX/1/1 '
                              'http://www.topografix.com/GPX/1/1/gpx.xsd',
        }
    with tag(TreeBuilder(), 'gpx', attrs) as tb:
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


def write(tb, file, indent='\t'):
    def helper(et, prefix=''):
        attrs = ''.join(' %s="%s"' % pair for pair in et.attrib.items())
        if et.getchildren():
            file.write('%s<%s%s>\n' % (prefix, et.tag, attrs))
            for child in et.getchildren():
                helper(child, prefix + indent)
            file.write('%s</%s>\n' % (prefix, et.tag))
        elif et.text:
            file.write('%s<%s%s>%s</%s>\n' %
                       (prefix, et.tag, attrs, et.text, et.tag))
        else:
            file.write('%s<%s%s/>\n' % (prefix, et.tag, attrs))
    helper(ElementTree(tb.close()).getroot())
