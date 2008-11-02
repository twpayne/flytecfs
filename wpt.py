import re

from flytecdevice import Waypoint


def waypoints(file):
    for line in file:
        line = line.rstrip()
        # OziExplorer Waypoint File
        m = re.match(r'\s*\d+\s*,'
                     r'\s*(\S{3})(\d{3})\s*,'
                     r'\s*(-?\d+\.\d+)\s*,'
                     r'\s*(-?\d+\.\d+)\s*,'
                     r'(?:\s*[^,]*\s*,){6}'
                     r'([^,]*)',
                     line)
        if m:
            lat = int(round(60000 * float(m.group(3))))
            lon = int(round(60000 * float(m.group(4))))
            long_name = '%s %s' % (m.group(1), m.group(5))
            short_name = '%s%s' % (m.group(1), m.group(2))
            ele = 10 * int(m.group(2))
            yield Waypoint(lat, lon, short_name, long_name, ele)
            continue
        #
        m = re.match(r'\AW\s+'
                     r'(\S{3})(.{3})\s+'
                     r'([NS])(\d+\.\d+)\s+'
                     r'([EW])(\d+\.\d+)\s+'
                     r'\S+\s+'
                     r'\S+\s+'
                     r'(-?\d+)\s+'
                     r'(.*)',
                     line)
        if m:
            lat = int(round(60000 * float(m.group(4))))
            if m.group(3) == 'S':
                lat = -lat
            lon = int(round(60000 * float(m.group(6))))
            if m.group(5) == 'W':
                lon = -lon
            long_name = '%s %s' % (m.group(1), m.group(8))
            ele = int(m.group(7))
            if ele == -9999:
                if re.match('\d+\Z', m.group(2)):
                    ele = 10 * int(m.group(2))
                else:
                    ele = 0
            short_name = '%s%03d' % (long_name, (ele + 5) / 10)
            yield Waypoint(lat, lon, short_name, long_name, ele)
            continue
        #
        m = re.match(r'\AW\s+'
                     r'(\S{3})(\d+)\s+'
                     r'A\s+'
                     '(\\d+\\.\\d+)\xba([NS])\\s+'
                     '(\\d+\\.\\d+)\xba([EW])\\s+'
                     r'\S+\s+'
                     r'\S+\s+'
                     r'(-?\d+\.\d+)\s+'
                     r'(.*)',
                     line)
        if m:
            lat = int(round(60000 * float(m.group(3))))
            if m.group(4) == 'S':
                lat = -lat
            lon = int(round(60000 * float(m.group(5))))
            if m.group(6) == 'W':
                lon = -lon
            long_name = m.group(8)
            ele = int(float(m.group(7)))
            if ele == -9999:
                ele = 10 * int(m.group(2))
            short_name = '%-3s%03d' % (m.group(1), (ele + 5) / 10)
            yield Waypoint(lat, lon, short_name, long_name, ele)
            continue
        # FormatGEO
        m = re.match(r'(\S{3})(\d{3})\s+'
                     r'([NS])\s+(\d\d)\s+(\d\d)\s+(\d\d),(\d\d)\s+'
                     r'([EW])\s+(\d{3})\s+(\d\d)\s+(\d\d),(\d\d)\s+'
                     r'(\d+)\s+'
                     r'(.*)',
                     line)
        if m:
            lat = int(round(60000 * sum(map(lambda n, d: int(n) / d,
                                            m.groups()[3:7],
                                            (1.0, 60.0, 3600.0, 360000.0)))))
            if m.group(3) == 'S':
                lat = -lat
            lon = int(round(60000 * sum(map(lambda n, d: int(n) / d,
                                            m.groups()[8:12],
                                            (1.0, 60.0, 3600.0, 360000.0)))))
            if m.group(8) == 'W':
                lon = -lon
            long_name = '%s %s' % (m.group(1), m.group(14))
            ele = int(m.group(13))
            short_name = '%s%03d' % (m.group(1), (ele + 5) / 10)
            yield Waypoint(lat, lon, short_name, long_name, ele)
            continue
