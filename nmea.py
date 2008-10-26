#   NMEA functions
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
import re


ENCODE_RE = re.compile('\\A[\x20-\x7f]{1,79}\\Z')
DECODE_RE = re.compile('\\A\\$(.{1,79})\\*([0-9A-F]{2})\r\n\\Z')


class NMEAError(UnicodeError):
    pass


class NMEACodec(Codec):

    def decode(self, input, errors='strict'):
        if errors != 'strict':
            raise NotImplementedError
        if not input:
            return ('', 0)
        m = DECODE_RE.match(input)
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
        if not ENCODE_RE.match(input):
            raise NMEAError(input)
        checksum = 0
        for c in input:
            checksum ^= ord(c)
        return ('$%s*%02X\r\n' % (input, checksum), len(input))


def _search(encoding):
    if encoding == 'nmea':
        codec = NMEACodec()
        return CodecInfo(codec.encode, codec.decode, name='nmea')
    else:
        return None

codecs.register(_search)
