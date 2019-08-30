#!/usr/bin/env python
# -*- coding: utf-8 -*-

import ctypes

from enum import Enum

from .constants import (Return, S_END_OF_CMD)
from .exceptions import (
    NexMessageException,
    NexMessageEndException,
    NexMessageLengthException,
    NexMessageFirstByteException
)


class Event:
    class Touch(Enum):
        Press = 0x01
        Release = 0x00


def hex_disp(msg):
    return ''.join(('0x%x ' % b for b in msg))


def has_end(msg: bytes):
    return (len(msg) > 3) and (msg[-3:] == S_END_OF_CMD)


def ensure_has_end(msg):
    if not has_end(msg):
        raise NexMessageEndException("Message %r must end with 0xFFFFFF" % msg)


class AbstractMsgEvent:
    EXPECTED_LENGTH = None
    FIRST_BYTE = None

    @classmethod
    def ensure_has_expected_length(cls, msg):
        expected_length = cls.EXPECTED_LENGTH
        n = len(msg)
        if expected_length is not None and n != expected_length:
            raise NexMessageLengthException("Event message %r must have %d bytes not %d" % (msg, expected_length, n))

    @classmethod
    def ensure_has_expected_first_byte(cls, msg, first_byte):
        expected_first_byte = cls.FIRST_BYTE
        if first_byte != expected_first_byte:
            raise NexMessageFirstByteException(
                "Event message %r must have %d as first byte not %d" % (msg, expected_first_byte, first_byte))

    def isempty(self):
        return False

    def issuccess(self):
        return True


class TouchEvent(AbstractMsgEvent):
    EXPECTED_LENGTH = 7
    FIRST_BYTE = Return.Code.EVENT_TOUCH_HEAD

    def __init__(self, code, pid, cid, press_event):
        self.code = code
        self.pid = pid
        self.cid = cid
        self.press_event = press_event

    def __str__(self):
        return "Touch {0} event - Page {1.pid} - Component {1.cid}".format(
            "PRESS" if self.press_event is Event.Touch.Press else "RELEASE",
            self
        )

    @classmethod
    def parse(cls, msg):
        ensure_has_end(msg)
        cls.ensure_has_expected_length(msg)
        code = Return.Code(msg[0])
        cls.ensure_has_expected_first_byte(msg, code)
        pid = int(msg[1])
        cid = int(msg[2])
        tevts = Event.Touch(msg[3])
        return TouchEvent(code, pid, cid, tevts)


class CurrentPageIDHeadEvent(AbstractMsgEvent):
    EXPECTED_LENGTH = 5
    FIRST_BYTE = Return.Code.CURRENT_PAGE_ID_HEAD

    def __init__(self, code, pid):
        self.code = code
        self.pid = pid

    @classmethod
    def parse(cls, msg):
        ensure_has_end(msg)
        cls.ensure_has_expected_length(msg)
        code = Return.Code(msg[0])
        cls.ensure_has_expected_first_byte(msg, code)
        pid = int(msg[1])
        return CurrentPageIDHeadEvent(code, pid)


class PositionHeadEvent(AbstractMsgEvent):
    EXPECTED_LENGTH = 9
    FIRST_BYTE = Return.Code.EVENT_POSITION_HEAD

    def __init__(self, code, x, y, tevts):
        self.code = code
        self.x = x
        self.y = y
        self.tevts = tevts

    @classmethod
    def parse(cls, msg):
        ensure_has_end(msg)
        cls.ensure_has_expected_length(msg)
        code = Return.Code(msg[0])
        cls.ensure_has_expected_first_byte(msg, code)
        x = (msg[1] << 8) + msg[2]
        y = (msg[3] << 8) + msg[4]
        tevts = Event.Touch(msg[5])
        return PositionHeadEvent(code, x, y, tevts)


class SleepPositionHeadEvent(AbstractMsgEvent):
    EXPECTED_LENGTH = 9
    FIRST_BYTE = Return.Code.EVENT_SLEEP_POSITION_HEAD

    def __init__(self, code, x, y, tevts):
        self.code = code
        self.x = x
        self.y = y
        self.tevts = tevts

    @classmethod
    def parse(cls, msg):
        ensure_has_end(msg)
        cls.ensure_has_expected_length(msg)
        code = Return.Code(msg[0])
        cls.ensure_has_expected_first_byte(msg, code)
        x = (msg[1] << 8) + msg[2]
        y = (msg[3] << 8) + msg[4]
        tevts = Event.Touch(msg[5])
        return SleepPositionHeadEvent(code, x, y, tevts)


class StringHeadEvent(AbstractMsgEvent):
    EXPECTED_LENGTH = None
    FIRST_BYTE = Return.Code.STRING_HEAD

    def __init__(self, code, value):
        self.code = code
        self.value = value

    @classmethod
    def parse(cls, msg):
        ensure_has_end(msg)
        cls.ensure_has_expected_length(msg)
        code = Return.Code(msg[0])
        cls.ensure_has_expected_first_byte(msg, code)
        value = bytearray(msg[1:-3]).decode("utf-8")
        return StringHeadEvent(code, value)


class NumberHeadEvent(AbstractMsgEvent):
    EXPECTED_LENGTH = 8
    FIRST_BYTE = Return.Code.NUMBER_HEAD

    def __init__(self, code, value, signed_value):
        self.code = code
        self.value = value
        self.signed_value = signed_value

    @classmethod
    def parse(cls, msg):
        ensure_has_end(msg)
        cls.ensure_has_expected_length(msg)
        code = Return.Code(msg[0])
        cls.ensure_has_expected_first_byte(msg, code)
        value = msg[1] + (msg[2] << 8) + (msg[3] << 16) + (msg[4] << 24)
        signed_value = ctypes.c_int32(value).value
        return NumberHeadEvent(code, value, signed_value)


class CommandSucceeded(AbstractMsgEvent):
    EXPECTED_LENGTH = 4
    FIRST_BYTE = Return.Code.CMD_FINISHED

    @classmethod
    def parse(cls, msg):
        ensure_has_end(msg)
        cls.ensure_has_expected_length(msg)
        code = Return.Code(msg[0])
        cls.ensure_has_expected_first_byte(msg, code)
        return CommandSucceeded()


class EventLaunched(AbstractMsgEvent):
    EXPECTED_LENGTH = 4
    FIRST_BYTE = Return.Code.EVENT_LAUNCHED

    @classmethod
    def parse(cls, msg):
        ensure_has_end(msg)
        cls.ensure_has_expected_length(msg)
        code = Return.Code(msg[0])
        cls.ensure_has_expected_first_byte(msg, code)
        return EventLaunched()


class EventStartup(AbstractMsgEvent):
    # We don't "parse" this but identify it directly in the loop
    pass


class EmptyMessage(AbstractMsgEvent):
    EXPECTED_LENGTH = 0
    FIRST_BYTE = None

    def __init__(self):
        pass

    def issuccess(self):
        return False

    def isempty(self):
        return True


D_BYTE0_EVENT = {
    Return.Code.EVENT_LAUNCHED.value: EventLaunched,
    Return.Code.CMD_FINISHED.value: CommandSucceeded,
    Return.Code.EVENT_TOUCH_HEAD.value: TouchEvent,
    Return.Code.CURRENT_PAGE_ID_HEAD.value: CurrentPageIDHeadEvent,
    Return.Code.EVENT_POSITION_HEAD.value: PositionHeadEvent,
    Return.Code.EVENT_SLEEP_POSITION_HEAD.value: SleepPositionHeadEvent,
    Return.Code.STRING_HEAD.value: StringHeadEvent,
    Return.Code.NUMBER_HEAD.value: NumberHeadEvent
}

NEX_EXCEPTIONS = {
    Return.Code.INVALID_CMD,
    Return.Code.CMD_FINISHED,
    Return.Code.INVALID_COMPONENT_ID,
    Return.Code.INVALID_PAGE_ID,
    Return.Code.INVALID_PICTURE_ID,
    Return.Code.INVALID_FONT_ID,
    Return.Code.INVALID_BAUD,
    Return.Code.INVALID_VARIABLE,
    Return.Code.INVALID_OPERATION,
    Return.Code.INVALID_ASSIGN,
    Return.Code.INVALID_EEPROM,
    Return.Code.INVALID_PARAMETER_QUANTITY,
    Return.Code.INVALID_IO,
    Return.Code.INVALID_ESC_CHAR,
    Return.Code.INVALID_VAR_NAME_TOO_LONG
}


class MsgEvent:
    @classmethod
    def parse(cls, msg):
        if not msg:
            return EmptyMessage()

        first_byte = msg[0]
        if first_byte in D_BYTE0_EVENT:
            evt_typ = D_BYTE0_EVENT[first_byte]
            return evt_typ.parse(msg)

        code = Return.Code(first_byte)
        # Unfortunately the "startup" event starts as an INVALID_CMD and must be checked explicitly
        if code is Return.Code.INVALID_CMD and msg == b'\x00\x00\x00\xFF\xFF\xFF':
            return EventStartup()

        if code in NEX_EXCEPTIONS:
            raise NexMessageException(code)

        raise NotImplementedError("Code 0x{:02X} unknown".format(first_byte))
