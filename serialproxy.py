#   Serial proxy functions
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

from Queue import Queue
import sys
from threading import Lock, Thread


class SerialProxy(Thread):

    def __init__(self, obj):
        Thread.__init__(self)
        self.setDaemon(True)
        self.obj = obj
        self.lock = Lock()
        self.queue = Queue()
        self.start()

    def run(self):
        while True:
            queue, attr, args, kwargs = self.queue.get()
            with self.lock:
                try:
                    result = getattr(self.obj, attr)(*args, **kwargs)
                except:
                    queue.put((sys.exc_info(), None))
                else:
                    queue.put((None, result))

    def __getattr__(self, attr):
        with self.lock:
            value = getattr(self.obj, attr)
            if value is None:
                raise AttributeError
            elif callable(value):
                def proxy(*args, **kwargs):
                    queue = Queue()
                    self.queue.put((queue, attr, args, kwargs))
                    exc_info, result = queue.get()
                    if exc_info:
                        raise exc_info.type, exc_info.value, exc_info.traceback
                    else:
                        return result
                setattr(self, attr, proxy)
                return proxy
            else:
                return value
