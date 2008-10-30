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


import errno
import os
import stat
import sys
import time

import fuse

fuse.fuse_python_api = (0, 2)


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
        self.st_blksize = 0
        self.st_blocks = 0
        _time = time.time()
        self.st_atime = _time
        self.st_mtime = _time
        self.st_ctime = _time
        fuse.Direntry.__init__(self, name, **kwargs)

    def getattr(self):
        return self


class File(Direntry):

    def __init__(self, name, mode=0444, **kwargs):
        if not 'type' in kwargs:
            kwargs['type'] = stat.S_IFREG
        Direntry.__init__(self, name, **kwargs)
        self.st_mode = self.type | mode
        self.st_nlink = 1

    def content(self):
        return ''

    def getattr(self):
        self.st_size = len(self.content())
        return self

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
        self.st_nlink = 2
        self.direntries = {}

    def add(self, *args):
        for direntry in args:
            self.direntries[direntry.name] = direntry
            if isinstance(direntry, Directory):
                self.st_nlink += 1
        return self

    def readdir(self, offset):
        yield Direntry('.')
        yield Direntry('..')
        for direntry in self.direntries.values():
            yield direntry


class Filesystem(fuse.Fuse):

    def __init__(self, root, *args, **kwargs):
        fuse.Fuse.__init__(self, *args, **kwargs)
        self.root = root

    def get(self, path):
        if path == '/':
            return self.root
        else:
            direntry = self.root
            for name in path.split(os.sep)[1:]:
                try:
                    direntry = direntry.direntries[name]
                except KeyError:
                    raise IOError, (errno.ENOENT, None)
            return direntry

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

    def main(self):
        if callable(self.root):
            self.root = self.root(self)
        fuse.Fuse.main(self)

    def open(self, path, flags):
        return self.get(path).open(flags, context=self.GetContext())


class FileX(File):

    def __init__(self):
        File.__init__(self, 'y')
        self.content = '5678\n'
        self.st_size = 1


def main(argv):
    root = Directory('')
    root.add(File('x', content='1234\n'))
    root.add(FileX())
    server = Filesystem(root, dash_s_do='setsingle', usage=fuse.Fuse.fusage)
    server.parser.add_option(mountopt='device', metavar='PATH', help='set device')
    server.parse(args=argv, values=server, errex=1)
    if server.fuse_args.mount_expected():
        server.main()

if __name__ == '__main__':
    main(sys.argv)
