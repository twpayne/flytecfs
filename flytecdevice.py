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


NMEA_ENCODE_RE = re.compile('\\A[\x20-\x7e]{1,79}\\Z')
NMEA_DECODE_RE = re.compile('\\A\\$(.{1,79})\\*([0-9A-F]{2})\r\n\\Z')
NMEA_INVALID_CHAR_RE = re.compile('[^\x20-\x7e]')


class NMEAError(UnicodeError):
    pass


class NMEASentenceCodec(Codec):

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


class NMEACharacterCodec(object):

    def encode(self, input, errors='strict'):
        if errors != 'replace':
            raise NotImplementedError
        return (NMEA_INVALID_CHAR_RE.sub('?', input), len(input))


def nmea_search(encoding):
    if encoding == 'nmea_sentence':
        codec = NMEASentenceCodec()
        return CodecInfo(codec.encode, codec.decode, name=encoding)
    if encoding == 'nmea_characters':
        codec = NMEACharacterCodec()
        return CodecInfo(codec.encode, None, name=encoding)
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

    def readline(self, timeout):
        if self.buffer == '':
            self.buffer = self.read(1024, timeout)
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
                    self.buffer = self.read(1024, timeout)
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

    def read(self, n, timeout):
        if select.select([self.fd], [], [], timeout) == ([], [], []):
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
        return '<%s %r>' % (self.__class__.__name__, self.__dict__)


class Route(_Struct):

    def __init__(self, index, name, routepoints):
        self.index = index
        self.name = '%-17s' % name.encode('nmea_characters', 'replace')[:17]
        self.routepoints = routepoints


class Routepoint(_Struct):

    def __init__(self, short_name, long_name):
        self.short_name = short_name.encode('nmea_characters', 'replace')
        self.long_name = long_name.encode('nmea_characters', 'replace')


class SNP(_Struct):

    def __init__(self, instrument, pilot_name, serial_number, software_version):
        self.instrument = instrument
        self.pilot_name = pilot_name
        self.serial_number = serial_number
        self.software_version = software_version
        if self.instrument in 'COMPEO COMPEO+ COMPETINO COMPETINO+ GALILEO'.split():
            self.manufacturer = ('X', 'XBR', 'Brauniger')
        elif self.instrument in '5020 5030 6020 6030'.split():
            self.manufacturer = ('X', 'XFL', 'Flytec')
        else:
            self.manufacturer = ('X', 'XXX', 'Unknown')


class Tracklog(_Struct):

    def __init__(self, count, index, dt, duration):
        self.count = count
        self.index = index
        self.dt = dt
        self.duration = duration


class Waypoint(_Struct):

    def __init__(self, lat, lon, short_name, long_name, ele):
        self.lat = min(max(-(60000 * 180 - 1), lat), 60000 * 180 - 1)
        self.lon = min(max(-(60000 * 90 - 1), lon), 60000 * 90 - 1)
        self.short_name = '%-6s' % short_name.encode('nmea_characters',
                                                     'replace')[:6]
        self.long_name = '%-17s' % long_name.encode('nmea_characters',
                                                    'replace')[:17]
        self.ele = min(max(-999, ele), 9999)

    def nmea(self):
        lat_hemi = 'S' if self.lat < 0 else 'N'
        lat_deg, lat_mmin = divmod(abs(self.lat), 60000)
        lat_min, lat_mmin = divmod(lat_mmin, 1000)
        lon_hemi = 'W' if self.lon < 0 else 'E'
        lon_deg, lon_mmin = divmod(abs(self.lon), 60000)
        lon_min, lon_mmin = divmod(lon_mmin, 1000)
        lat = '%02d%02d.%03d,%s' % (lat_deg, lat_min, lat_mmin, lat_hemi)
        lon = '%03d%02d.%03d,%s' % (lon_deg, lon_min, lon_mmin, lon_hemi)
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

    def ieach(self, command, re=None, timeout=1):
        try:
            self.io.writeline(command.encode('nmea_sentence'))
            if self.io.readline(timeout) != XOFF:
                raise Error
            while True:
                line = self.io.readline(timeout)
                if line == XON:
                    break
                elif re is None:
                    yield line
                else:
                    m = re.match(line.decode('nmea_sentence'))
                    if m is None:
                        raise Error(line)
                    yield m
        except:
            self.io.flush()
            raise

    def none(self, command, timeout=1):
        for m in self.ieach(command, timeout=timeout):
            raise Error(m)

    def one(self, command, re=None, timeout=1):
        result = None
        for m in self.ieach(command, re, timeout=timeout):
            if not result is None:
                raise Error(m)
            result = m
        return result

    def pbrconf(self):
        self.none('PBRCONF,', timeout=4)

    def ipbrigc(self):
        return self.ieach('PBRIGC,')

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
        for line in self.ieach('PBRRTS,'):
            line = line.decode('nmea_sentence')
            m = PBRRTS_RE1.match(line)
            if m:
                index, count = map(int, m.groups()[0:2])
                name = m.group(3)
                if count == 1:
                    yield Route(index, name, [])
                else:
                    routepoints = []
                continue
            m = PBRRTS_RE2.match(line)
            if m:
                index, count, routepoint_index = map(int, m.groups()[0:3])
                short_name, long_name = m.groups()[3:5]
                routepoint = Routepoint(short_name, long_name)
                routepoints.append(routepoint)
                if routepoint_index == count - 1:
                    yield Route(index, name, routepoints)
                continue
            raise Error(line)

    def pbrrts(self):
        return list(self.ipbrrts())

    def pbrsnp(self):
        if self.snp is None:
            self.snp = SNP(*self.one('PBRSNP,', PBRSNP_RE).groups())
        return self.snp

    def ipbrtl(self):
        for m in self.ieach('PBRTL,', PBRTL_RE):
            count, index = map(int, m.groups()[0:2])
            day, month, year, hour, minute, second = map(int, m.groups()[2:8])
            dt = datetime(year + 2000, month, day, hour, minute, second,
                          tzinfo=UTC())
            hours, minutes, seconds = map(int, m.groups()[8:11])
            duration = timedelta(hours=hours, minutes=minutes, seconds=seconds)
            yield Tracklog(count, index, dt, duration)

    def pbrtl(self):
        return list(self.ipbrtl())

    def ipbrtr(self, tracklog):
        return self.ieach('PBRTR,%02d' % tracklog.index)

    def pbrtr(self, tracklog):
        return ''.join(self.ipbrtr(tracklog))

    def pbrrtx(self, route):
        self.none('PBRRTX,%s' % route.name, timeout=4)

    def pbrwpr(self, waypoint):
        self.none('PBRWPR,%s,,%s,%04d'
                  % (waypoint.nmea(), waypoint.long_name, waypoint.ele))

    def ipbrwps(self):
        for m in self.ieach('PBRWPS,', PBRWPS_RE):
            lat = sum(map(lambda x, y: int(x) * y,
                          m.groups()[0:3],
                          (60000, 1000, 1)))
            if m.group(4) == 'S':
                lat = -lat
            lon = sum(map(lambda x, y: int(x) * y,
                          m.groups()[4:7],
                          (60000, 1000, 1)))
            if m.group(8) == 'W':
                lon = -lon
            short_name, long_name = m.groups()[8:10]
            ele = int(m.group(11))
            yield Waypoint(lat, lon, short_name, long_name, ele)

    def pbrwps(self):
        return list(self.ipbrwps())

    def pbrwpx(self, waypoint):
        self.none('PBRWPX,%s' % waypoint.long_name, timeout=8)
