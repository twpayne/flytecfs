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
from threading import Event, Lock, Thread



class SerialProxy(object):

    def __init__(self, obj):
        self.events = {}
        self.events_lock = Lock()
        self.queue = Queue()
        self.results = {}
        self.results_lock = Lock()
        thread = Thread(target=self.__thread, args=(obj,))
        thread.setDaemon(True)
        thread.start()

    def __thread(self, obj):
        while True:
            key = self.queue.get()
            with self.events_lock:
                event = self.events[key]
            with self.results_lock:
                if key in self.results:
                    event.set()
                    continue
            attr, args = key
            try:
                result = getattr(obj, attr)(*args)
            except:
                with self.results_lock:
                    self.results[key] = (sys.exc_info(), None)
            else:
                with self.results_lock:
                    self.results[key] = (None, result)
            event.set()

    def __getattr__(self, attr):
        def f(*args):
            key = (attr, args)
            with self.events_lock:
                if not key in self.events:
                    self.events[key] = Event()
                event = self.events[key]
            if not event.isSet():
                self.queue.put(key)
                event.wait()
            with self.results_lock:
                exc_info, result = self.results[key]
            if exc_info:
                type, value, traceback = exc_info
                raise type, value, traceback
            return result
        setattr(self, attr, f)
        return f
