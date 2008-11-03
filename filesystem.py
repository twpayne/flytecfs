#   FUSE Wrapper
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


# TODO correct permissions checking in open


import errno
import os
import stat
import sys
import time

import fuse

fuse.fuse_python_api = (0, 2)
fuse.feature_assert(26)


class Direntry(fuse.Direntry):

    def __init__(self, name, **kwargs):
        self.st_dev = 0
        self.st_ino = 0
        self.st_mode = kwargs.get('type', 0)
        self.st_nlink = 0
        self.st_uid = os.getuid()
        self.st_gid = os.getgid()
        self.st_size = 0
        self.st_rdev = 0
        self.st_blksize = 4096
        self.st_blocks = 0
        _time = time.time()
        self.st_atime = _time
        self.st_mtime = _time
        self.st_ctime = _time
        fuse.Direntry.__init__(self, name, **kwargs)

    def getattr(self):
        self.st_blocks = (self.st_size + self.st_blksize - 1) / self.st_blksize
        return self

    def rename(self, old, new):
        raise IOError, (errno.EPERM, None)

    def unlink(self):
        raise IOError, (errno.EPERM, None)


class File(Direntry):

    def __init__(self, name, mode=0444, **kwargs):
        if not 'type' in kwargs:
            kwargs['type'] = stat.S_IFREG
        Direntry.__init__(self, name, **kwargs)
        self.st_mode = self.type | mode
        self.st_nlink = 1
        self.direct_io = False
        self.keep_cache = False

    def content(self):
        return ''

    def getattr(self):
        self.st_size = len(self.content())
        return Direntry.getattr(self)

    def fgetattr(self):
        return self.getattr()

    def flush(self):
        pass

    def open(self, flags, context):
        if flags & (os.O_RDONLY | os.O_RDWR | os.O_WRONLY) != os.O_RDONLY:
            raise IOError, (errno.EACCES, None)
        return self

    def read(self, size, offset):
        return self.content()[offset:offset + size]


class Directory(Direntry):

    def __init__(self, name, mode=0555, **kwargs):
        if not 'type' in kwargs:
            kwargs['type'] = stat.S_IFDIR
        Direntry.__init__(self, name, **kwargs)
        self.st_mode = self.type | mode

    def content(self):
        pass

    def getattr(self):
        self.st_nlink = 2
        for direntry in self.content():
            if isinstance(direntry, Directory):
                self.st_nlink += 1
        return Direntry.getattr(self)

    def create(self, path, mode):
        raise IOError, (errno.EPERM, None)

    def readdir(self, offset):
        yield Directory('.')
        yield Directory('..')
        for direntry in self.content():
            yield direntry


class Filesystem(fuse.Fuse):

    def __init__(self, *args, **kwargs):
        fuse.Fuse.__init__(self, *args, **kwargs)
        self.f_bsize = 0
        self.f_frsize = 0
        self.f_blocks = 0
        self.f_bfree = 0
        self.f_bavail = 0
        self.f_files = 0
        self.f_ffree = 0
        self.f_favail = 0
        self.f_flag = 0
        self.f_namemax = 0

    def get(self, path):
        if path == '/':
            return self.root
        else:
            direntry = self.root
            for name in path.split(os.sep)[1:]:
                for de in direntry.content():
                    if de.name == name:
                        direntry = de
                        break
                else:
                    raise IOError, (errno.ENOENT, None)
            return direntry

    def create(self, path, unknown, mode):
        dirname, basename = os.path.split(path)
        return self.get(dirname).create(basename, mode)

    def fgetattr(self, path, fh=None):
        return fh.fgetattr()

    def flush(self, path, fh=None):
        return fh.flush()

    def fsinit(self):
        if hasattr(self.root, 'fsinit'):
            self.root.fsinit()

    def getattr(self, path):
        return self.get(path).getattr()

    def read(self, path, size, offset, fh=None):
        return fh.read(size, offset)

    def readdir(self, path, offset):
        for direntry in self.get(path).readdir(offset):
            yield direntry

    def rename(self, old, new):
        return self.get(old).rename(old, new)

    def statfs(self):
        return self

    def open(self, path, flags):
        return self.get(path).open(flags, context=self.GetContext())

    def unlink(self, path):
        self.get(path).unlink()

    def write(self, path, buffer, offset, fh):
        return fh.write(buffer, offset)
