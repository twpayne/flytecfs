#   Flytec/Brauniger low-level device functions
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


from codecs import Codec, CodecInfo
import codecs
from datetime import datetime, timedelta, tzinfo
import logging
import os
import re


class UTC(tzinfo):
    """UTC"""

    def utcoffset(self, dt):
        return timedelta(0)

    def tzname(self):
        return "UTC"

    def dst(self, dt):
        return timedelta(0)


NMEA_ENCODE_RE = re.compile('\\A[\x20-\x7f]{1,79}\\Z')
NMEA_DECODE_RE = re.compile('\\A\\$(.{1,79})\\*([0-9A-F]{2})\r\n\\Z')


class NMEAError(UnicodeError):
    pass


class NMEACodec(Codec):

    def decode(self, input, errors='strict'):
        if errors != 'strict':
            raise NotImplementedError
        if not input:
            return ('', 0)
        m = NMEA_DECODE_RE.match(input)
        if not m:
            raise NMEAError(input)
        checksum = 0
        for c in m.group(1):
            checksum ^= ord(c)
        if checksum != ord(m.group(2).decode('hex')):
            raise NMEAError(input)
        return (m.group(1), len(input))

    def encode(self, input, errors='strict'):
        if errors != 'strict':
            raise NotImplementedError
        if not input:
            return ('', 0)
        if not NMEA_ENCODE_RE.match(input):
            raise NMEAError(input)
        checksum = 0
        for c in input:
            checksum ^= ord(c)
        return ('$%s*%02X\r\n' % (input, checksum), len(input))


def nmea_search(encoding):
    if encoding == 'nmea':
        codec = NMEACodec()
        return CodecInfo(codec.encode, codec.decode, name='nmea')
    else:
        return None


codecs.register(nmea_search)


XON = '\021'
XOFF = '\023'

PBRMEMR_RE = re.compile(r'\APBRMEMR,([0-9A-F]+),([0-9A-F]+(?:,[0-9A-F]+)*)\Z')
PBRRTS_RE1 = re.compile(r'\APBRRTS,(\d+),(\d+),0+,(.*)\Z')
PBRRTS_RE2 = re.compile(r'\APBRRTS,(\d+),(\d+),(\d+),([^,]*),(.*?)\Z')
PBRSNP_RE = re.compile(r'\APBRSNP,([^,]*),([^,]*),([^,]*),([^,]*)\Z')
PBRTL_RE = re.compile(r'\APBRTL,(\d+),(\d+),(\d+).(\d+).(\d+),'
                      r'(\d+):(\d+):(\d+),(\d+):(\d+):(\d+)\Z')
PBRWPS_RE = re.compile(r'\APBRWPS,(\d{2})(\d{2})\.(\d{3}),([NS]),'
                       r'(\d{3})(\d{2})\.(\d{3}),([EW]),([^,]*),([^,]*),(\d+)'
                       r'\Z')


class Error(RuntimeError): pass
class TimeoutError(Error): pass
class ReadError(Error): pass
class WriteError(Error): pass
class ProtocolError(Error): pass


class SerialIO(object):

    def __init__(self, filename):
        self.logger = logging.getLogger('%s.%s' % (__name__, filename))
        self.buffer = ''

    def readblock(self):
        if self.buffer == '':
            self.buffer = self.read(1024)
        if self.buffer[0] == XON or self.buffer[0] == XOFF:
            result = self.buffer[0]
            self.buffer = self.buffer[1:]
            self.logger.info('%s', result.encode('string_escape'),
                             extra=dict(direction='read'))
            return result
        else:
            index = self.buffer.find(XON)
            if index == -1:
                result = self.buffer
                self.buffer = ''
            else:
                result = self.buffer[:index]
                self.buffer = self.buffer[index:]
            self.logger.info('%s', result.encode('string_escape'),
                             extra=dict(direction='read'))
            return result

    def readline(self):
        if self.buffer == '':
            self.buffer = self.read(1024)
        if self.buffer[0] == XON or self.buffer[0] == XOFF:
            result = self.buffer[0]
            self.buffer = self.buffer[1:]
            self.logger.info('%s', result.encode('string_escape'),
                             extra=dict(direction='read'))
            return result
        else:
            result = ''
            while True:
                index = self.buffer.find('\n')
                if index == -1:
                  result += self.buffer
                  self.buffer = self.read(1024)
                else:
                  result += self.buffer[0:index + 1]
                  self.buffer = self.buffer[index + 1:]
                  self.logger.info('%s', result.encode('string_escape'),
                                   extra=dict(direction='read'))
                  return result

    def writeline(self, line):
        self.logger.info('%s', line.encode('string_escape'),
                         extra=dict(direction='write'))
        self.write(line)

    def close(self):
        pass

    def flush(self):
        pass

    def read(self, n):
        raise NotImplementedError

    def write(self, data):
        raise NotImplementedError


if os.name == 'posix':
    import select
    import tty


class POSIXSerialIO(SerialIO):

    def __init__(self, filename):
        SerialIO.__init__(self, filename)
        self.fd = os.open(filename, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        tty.setraw(self.fd)
        attr = tty.tcgetattr(self.fd)
        attr[tty.ISPEED] = attr[tty.OSPEED] = tty.B57600
        tty.tcsetattr(self.fd, tty.TCSAFLUSH, attr)

    def close(self):
        os.close(self.fd)

    def flush(self):
        tty.tcflush(self.fd, tty.TCIOFLUSH)

    def read(self, n):
        if select.select([self.fd], [], [], 1) == ([], [], []):
            raise TimeoutError()
        data = os.read(self.fd, n)
        if not data:
            raise ReadError()
        return data

    def write(self, data):
        if os.write(self.fd, data) != len(data):
            raise WriteError()


class _Struct:

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, repr(self.__dict__))


class Route(_Struct):

    def __init__(self, index, name, routepoints):
        self.index = index
        self.name = name
        self.routepoints = routepoints


class Routepoint(_Struct):

    def __init__(self, short_name, long_name):
        self.short_name = short_name
        self.long_name = long_name


class SNP(_Struct):

    def __init__(self, instrument, pilot_name, serial_number, software_version):
        self.instrument = instrument
        self.pilot_name = pilot_name
        self.serial_number = serial_number
        self.software_version = software_version


class Track(_Struct):

    def __init__(self, count, index, dt, duration, igc_filename=None):
        self.count = count
        self.index = index
        self.dt = dt
        self.duration = duration
        self.igc_filename = igc_filename


class Waypoint(_Struct):

    def __init__(self, lat, lon, short_name, long_name, alt):
        self.lat = lat
        self.lon = lon
        self.short_name = short_name
        self.long_name = long_name
        self.alt = alt

    def nmea(self):
        lat_hemi = 'S' if self.lat < 0 else 'N'
        lat_deg, lat_mmin = divmod(abs(self.lat), 60000)
        lat_min, lat_mmin = divmod(lat_mmin, 1000)
        lon_hemi = 'S' if self.lon < 0 else 'N'
        lon_deg, lon_mmin = divmod(abs(self.lon), 60000)
        lon_min, lon_mmin = divmod(lon_mmin, 1000)
        lat = '%02d%02d.%03d,%s' % (lat_deg, lat_min, lat_mmin, lat_hemi)
        lon = '%02d%02d.%03d,%s' % (lon_deg, lon_min, lon_mmin, lon_hemi)
        return '%s,%s' % (lat, lon)


class FlytecDevice(object):

    def __init__(self, file_or_path):
        if isinstance(file_or_path, str):
            if os.name == 'posix':
                self.io = POSIXSerialIO(file_or_path)
            else:
                raise RuntimeError
        else:
            self.io = file_or_path
        self.snp = None

    def ieachblock(self, command):
        try:
            self.io.writeline(command.encode('nmea'))
            if self.io.readline() != XOFF:
                raise Error
            while True:
                block = self.io.readblock()
                if block == XON:
                    break
                yield block
        except:
            self.io.flush()

    def ieachline(self, command, re=None):
        try:
            self.io.writeline(command.encode('nmea'))
            if self.io.readline() != XOFF:
                raise Error
            while True:
                line = self.io.readline()
                if line == XON:
                    break
                elif re is None:
                    yield line
                else:
                    m = re.match(line.decode('nmea'))
                    if m is None:
                        raise Error(line)
                    yield m
        except:
            self.io.flush()
            raise

    def none(self, command):
        for m in self.ieachline(command):
            raise Error(m)

    def one(self, command, re=None):
        result = None
        for m in self.ieachline(command, re):
            if not result is None:
                raise Error(m)
            result = m
        return result

    def pbrconf(self):
        self.none('PBRCONF,')

    def ipbrigc(self):
        return self.ieachblock('PBRIGC,')

    def pbrigc(self):
        return ''.join(self.ipbrigc())

    def pbrmemr(self, sl):
        result = []
        address = sl.start
        while address < sl.stop:
            m = self.one('PBRMEMR,%04X' % address, PBRMEMR_RE)
            if int(m.group(1), 16) != address:
                raise ProtocolError()
            data = [int(byte, 16) for byte in m.group(2).split(',')]
            result.extend(data)
            address += len(data)
        return result[:sl.stop - sl.start]

    def ipbrrts(self):
        for line in self.ieachline('PBRRTS,'):
            line = line.decode('nmea')
            m = PBRRTS_RE1.match(line)
            if m:
                index = int(m.group(1))
                count = int(m.group(2))
                name = m.group(3)
                if count == 1:
                    yield Route(index, name, [])
                else:
                    routepoints = []
            else:
                m = PBRRTS_RE2.match(line)
                if m:
                    index = int(m.group(1))
                    count = int(m.group(2))
                    routepoint_index = int(m.group(3))
                    routepoint_short_name = m.group(4)
                    routepoint_long_name = m.group(5)
                    routepoint = Routepoint(routepoint_short_name,
                                            routepoint_long_name)
                    routepoints.append(routepoint)
                    if routepoint_index == count - 1:
                        yield Route(index, name, routepoints)
                else:
                    raise Error(m)

    def pbrrts(self):
        return list(self.ipbrrts())

    def pbrsnp(self):
        if self.snp is None:
            self.snp = SNP(*self.one('PBRSNP,', PBRSNP_RE).groups())
        return self.snp

    def ipbrtl(self):
        for m in self.ieachline('PBRTL,', PBRTL_RE):
            count, index = map(int, m.groups()[0:2])
            day, month, year, hour, minute, second = map(int, m.groups()[2:8])
            dt = datetime(year + 2000, month, day, hour, minute, second,
                          tzinfo=UTC())
            hours, minutes, seconds = map(int, m.groups()[8:11])
            duration = timedelta(hours=hours, minutes=minutes, seconds=seconds)
            yield Track(count, index, dt, duration)

    def pbrtl(self):
        return list(self.ipbrtl())

    def ipbrtr(self, tracklog):
        return self.ieachblock('PBRTR,%02d' % tracklog.index)

    def pbrtr(self, tracklog):
        return ''.join(self.ipbrtr(tracklog))

    def pbrrtx(self, route=None):
        if route:
            self.none('PBRRTX,%-17s' % route.name)
        else:
            self.none('PBRRTX,')

    def pbrwpr(self, waypoint):
        self.none('PBRWPR,%s,,%-17s,%04d'
                  % (waypoint.nmea(), waypoint.long_name[:17], waypoint.alt))

    def ipbrwps(self):
        for m in self.ieachline('PBRWPS,', PBRWPS_RE):
            lat_deg = int(m.group(1))
            lat_min = int(m.group(2))
            lat_mmin = int(m.group(3))
            lat = 60000 * lat_deg + 1000 * lat_min + lat_mmin
            if m.group(4) == 'S':
                lat = -lat
            lon_deg = int(m.group(5))
            lon_min = int(m.group(6))
            lon_mmin = int(m.group(7))
            lon = 60000 * lon_deg + 1000 * lon_min + lon_mmin
            if m.group(8) == 'W':
                lon = -lon
            short_name = m.group(9)
            long_name = m.group(10)
            alt = int(m.group(11))
            yield Waypoint(lat, lon, short_name, long_name, alt)

    def pbrwps(self):
        return list(self.ipbrwps())

    def pbrwpx(self, waypoint=None):
        if waypoint:
            self.none('PBRWPX,%-17s' % waypoint.long_name)
        else:
            self.none('PBRWPX,')
