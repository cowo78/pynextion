#!/usr/bin/env python
# -*- coding: utf-8 -*-

from enum import Enum

from PyQt5.QtCore import pyqtSignal, QObject

from .events import AbstractMsgEvent, CommandSucceeded, CurrentPageIDHeadEvent, StringHeadEvent, NumberHeadEvent


class CommandBase(QObject):
    successful = pyqtSignal()
    failed = pyqtSignal()

    DATA_EVENT_CLASSES = None
    " To be reimplemented in subclasses, define which event(s) are to be considered a data event "

    class Status(Enum):
        CREATED = 0x00
        SENT = 0x01
        SUCCESSFUL = 0x02
        ERROR = 0x03

    def __init__(self, command, *params):
        super().__init__()
        self.status = self.Status.CREATED
        self.command = self.format_command(command, *params)
        self.data_event = None

    def __eq__(self, other) -> bool:
        return self.status == other.status and self.command == other.command and self.data_event == other.data_event

    def __str__(self):
        return "Command {0.command} - {0.status}".format(self)

    def __repr__(self):
        return str(self)

    @property
    def completed(self) -> bool:
        return self.status == self.Status.SUCCESSFUL or self.status == self.Status.ERROR

    @staticmethod
    def format_command(cmd: str, *params) -> bytes:
        """ Encode any str to bytes and append the command terminator """
        if params:
            params_str = ",".join((str(param) for param in params))
            # Docs say ASCII but 0xFF is not ASCII strictly speaking
            data = bytes("{} {}\xFF\xFF\xFF".format(cmd, params_str), 'latin1', 'strict')
        else:
            data = bytes("{}\xFF\xFF\xFF".format(cmd), 'latin1', 'strict')
        return data

    def _connect_signals(self, on_successful, on_failed):
        if on_successful:
            self.successful.connect(on_successful)
        if on_failed:
            self.failed.connect(on_failed)

    def send(self, transport):
        transport.write(self.command)
        self.status = self.status.SENT

    def reset(self):
        self.status = self.Status.CREATED
        self.data_event = None

    def finalize(self):
        """ Called by event() after internal status is updated but before notification signals are called.
            To be reimplemented in subclasses to unpack payload and update 'result' if applicable.
        """
        pass

    def event(self, event: AbstractMsgEvent) -> bool:
        """ Handle an event
        :param event: The event to be handled
        :returns: True if the command is completed
        """
        if self.DATA_EVENT_CLASSES and isinstance(event, self.DATA_EVENT_CLASSES):
            self.data_event = event
            return False

        if isinstance(event, CommandSucceeded):
            # TODO: what if we have a data event class and we receive this before data event?
            self.status = self.Status.SUCCESSFUL
            signal = self.successful
        else:
            self.status = self.Status.ERROR
            signal = self.failed

        self.finalize()
        signal.emit()
        return True


class Command(CommandBase):
    pass


class SetPropertyCommand(CommandBase):
    def __init__(self, oid, name, value, on_successful=None, on_failed=None):
        if isinstance(value, bool):
            value = 1 if value else 0

        super().__init__("%s.%s=%s" % (oid, name, value))
        self.property_name = name
        self.new_value = value
        self._connect_signals(on_successful, on_failed)


class GetPropertyCommand(CommandBase):
    DATA_EVENT_CLASSES = (StringHeadEvent, NumberHeadEvent)

    def __init__(self, oid, name, on_successful=None, on_failed=None):
        super().__init__("get %s.%s" % (oid, name))
        self.property_name = name
        self._connect_signals(on_successful, on_failed)


class SendmeCommand(CommandBase):
    DATA_EVENT_CLASSES = (CurrentPageIDHeadEvent,)

    def __init__(self, on_successful=None, on_failed=None):
        super().__init__("sendme")
        self._connect_signals(on_successful, on_failed)


class PageCommand(CommandBase):
    def __init__(self, page_number: int, on_successful=None, on_failed=None):
        super().__init__("page", page_number)
        self._connect_signals(on_successful, on_failed)
