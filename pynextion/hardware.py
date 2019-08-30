#!/usr/bin/env python
# -*- coding: utf-8 -*-

import collections
import queue
import threading
import typing

from .constants import S_END_OF_CMD

try:
    import serial
    _HAS_PYSERIAL = True
except ImportError:
    _HAS_PYSERIAL = False


class AbstractSerialNex(object):
    INCOMING_BUFFER_SIZE = 1024  # Seems the Nextion buffer size, mentioned in official docs
    MIN_SIZE_READ = len(S_END_OF_CMD) + 1  # Minimum return data size
    TERMINATOR_SIZE = len(S_END_OF_CMD)

    def __init__(self):
        super().__init__()
        self._port_mutex = threading.Lock()
        # Queue of event objects
        self._events = queue.Queue()
        # Incoming serial buffer
        self._buffer = bytearray(self.INCOMING_BUFFER_SIZE)
        self._events_queue = collections.deque()  # type: typing.Sequence[bytearray]

    def write(self, data: bytes) -> int:
        """ Raw write access to underlying transport. Threadsafe.
        :returns: Number of bytes written
        """
        with self._port_mutex:
            nbytes = self.sp.write(data)

        return nbytes
    send = write

    def read_all(self) -> bytes:
        """ Read all buffered data. Threadsafe. """
        with self._port_mutex:
            data = self.sp.read_all()

        return data

    def read_next(self) -> bytes:
        """ Read next message. Threadsafe. May return an empty array is no event is available. """
        # At some point (along with editor 0.58) the Nextion firmware changed and now it returns
        # an "instruction successful" everytime, even after a string or numeric data event
        if self._events_queue:
            return self._events_queue.pop()

        buffer_size = 0
        with self._port_mutex:
            # Reading one byte at a time is of course inefficient, so serial.read_until is not the best option
            # We know the minimal read should be 4 chars (i.e. Invalid Instruction) and must be prepared to
            # partial command reads since we have no guarantee that we will always have complete commands in the buffer
            if self.sp.in_waiting < self.MIN_SIZE_READ:
                # Partial event, unlikely at this point
                return b''

            # Read bulk of data
            chunk = self.sp.read(self.sp.in_waiting)
            self._buffer[buffer_size:buffer_size+len(chunk)] = chunk
            buffer_size = len(chunk)
            while self._buffer[buffer_size - self.TERMINATOR_SIZE:buffer_size] != S_END_OF_CMD:
                # Trickle until end of event
                chunk = self.sp.read(1)
                self._buffer[buffer_size:buffer_size+1] = chunk
                buffer_size += 1

        # Finished reading and we are sure we have complete event(s), now split into single events
        start = 0
        while True:
            pos = self._buffer.find(S_END_OF_CMD, start, buffer_size)
            if pos == -1:
                break

            self._events_queue.appendleft(self._buffer[start:pos+self.TERMINATOR_SIZE])
            start = pos + self.TERMINATOR_SIZE

        return self._events_queue.pop()

    def close(self):
        return self.sp.close()


if _HAS_PYSERIAL:
    class PySerialNex(AbstractSerialNex):
        def __init__(self, port_or_url: str, *args, **kwargs):
            super().__init__()
            self.sp = serial.serial_for_url(port_or_url, *args, **kwargs)
            self.sp.reset_input_buffer()
            self.sp.reset_output_buffer()


# TODO: rotten
class NexSerialMock(AbstractSerialNex):
    def __init__(self, *args, **kwargs):
        super().__init__()

    def write(self, cmd):
        pass

    def read(self):
        return None

    def close(self):
        print("close")


"""
# PyBoard 1.1
# https://docs.micropython.org/en/latest/pyboard/pyboard/quickref.html
# RED: VIN
# BLACK: GND
# YELLOW: X9 (Board TX)
# BLUE: X10 (Board RX)

import machine
import time


class uPyNexSerial(AbstractSerialNex):
    def __init__(self, *args, **kwargs):
        self.sp = machine.UART(*args, **kwargs)

"""
