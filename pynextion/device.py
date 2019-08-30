#!/usr/bin/env python
# -*- coding: utf-8 -*-

import collections
import logging
import threading
import typing

from .constants import Return
from .commands import CommandBase, Command, SendmeCommand
from .events import MsgEvent, TouchEvent, Event
from .exceptions import NexComponentNameException, NexComponentIdException
from .widgets import WidgetFactory, NexPage
from . import draw

from PyQt5.QtCore import QObject, QReadWriteLock, pyqtSignal, pyqtSlot, QRunnable, QThread

__all__ = ['NexDevice']


class NexDevice(QObject):
    page_changed = pyqtSignal(int)
    """ Emitted whenever a page change event occurs. Parameter is page ID. """

    def __init__(self, transport, parent=None):
        super().__init__(parent)
        self.transport = transport
        self._logger = logging.getLogger("pynextion.NexDevice")
        self._initialized = False
        # Reference to the current NexPage
        self._current_page = None
        # "page_name" -> NexPage
        self._pages_by_name = {}  # type: typing.Dict[str, NexPage]
        # id: int -> NexPage
        self._pages_by_id = {}  # type: typing.Dict[int, NexPage]
        self._pages_by_name_or_id = collections.ChainMap(self._pages_by_name, self._pages_by_id)
        self._sendme_command = SendmeCommand()
        self._sendme_command.successful.connect(self._on_sendme_successful)
        self._sendme_command.failed.connect(self._on_sendme_failed)
        # FIFO of outstanding commands (to be sent, sent, waiting response)
        self._commands = collections.deque()
        # Incoming async events
        self._events = collections.deque()

    # Accessors ---------------------------------------------------------------
    def get_page(self, name_or_id) -> NexPage:
        """ Return the NexPage with specified name or ID """
        return self._pages_by_name_or_id[name_or_id]

    @property
    def pages(self) -> typing.Dict[typing.Union[str, int], NexPage]:
        """ Return a dict-like object indexed by page name or ID """
        return self._pages_by_name_or_id

    @property
    def pages_by_id(self) -> typing.Dict[int, NexPage]:
        return self._pages_by_id

    @property
    def current_page(self) -> NexPage:
        """ Return visible page (cached). Must call select_page(). """
        return self._current_page

    def get_current_page(self):
        """ Get the visible page from device. Asynchronous. When completed the current_page property will be updated
            and page_changed signal emitted if necessary.
        """
        if self._sendme_command in self._commands:
            # It is being handled, do nothing.
            pass
        else:
            # Do NOT reset() it, it is a job for the command completion handlers
            if not self._sendme_command.completed:
                self._commands.appendleft(self._sendme_command)

    __getitem__ = get_page

    @property
    def initialized(self) -> bool:
        return self._initialized

    # ~Accessors --------------------------------------------------------------

    # Drawing primitives ------------------------------------------------------
    def cls(self, colour=None):
        draw.cls(self.transport, colour)

    # ~Drawing primitives -----------------------------------------------------

    # Methods -----------------------------------------------------------------
    def init(self):
        """ Set the device to always send responses and select page 0. To be called in single-threaded environment
            WITHOUT any poller running
        """
        self._logger.info("Initializing Nextion device")
        # Flush incoming data
        while True:
            if not self.transport.read_all():
                break
        # mode = Return.Mode.NO_RETURN
        # mode = Return.Mode.SUCCESS_ONLY  # production setting
        # mode = Return.Mode.FAIL_ONLY  # default screen setting
        mode = Return.Mode.ALWAYS  # for debug

        self._commands.extendleft((
            Command("bkcmd=%d" % mode.value),  # This must come first as is the first to be executed
        ))
        while self._commands:
            self.poll()

        for page_id, page in self._pages_by_id.items():
            self.select_page(page_id)
            while self._commands:
                self.poll()

            page.onetime_refresh()
            while self._commands:
                self.poll()

        self.select_page(0)
        while self._commands:
            self.poll()

        self._initialized = True
        self._logger.info("Nextion device initialized")

    @pyqtSlot()
    def reset(self):
        self._logger.debug("Sending RESET command to device")
        self.transport.write("rest")
        # When rebooting it will send an
        # b'\x00\x00\x00\xff\xff\xff' (Nextion Startup)
        # and an b'\x88\xff\xff\xff' (Nextion Ready)
        # The event poller will eat these

    def hook_page(self, name, pid=None) -> NexPage:
        """ Create a NexPage tied to an existing page on device """
        if name in self._pages_by_name:
            raise NexComponentNameException("Page name ({}) must be unique".format(name))
        if pid in self._pages_by_id:
            raise NexComponentIdException("Page ID ({}) must be unique".format(pid))

        page = WidgetFactory.create("page", name, pid)
        if pid is not None:
            self._pages_by_id[pid] = page
        self._pages_by_name[name] = page
        self._logger.debug("Hooked new page %s", page)
        page.enqueue_command.connect(self._on_enqueue_command)
        return page

    def select_page(self, name_id_or_instance: typing.Union[str, int, NexPage]) -> NexPage:
        """ Show the page and return it """
        if isinstance(name_id_or_instance, NexPage):
            self._current_page = name_id_or_instance
        else:
            self._current_page = self._pages_by_name_or_id[name_id_or_instance]
        self._current_page.show()
        self.page_changed.emit(self._current_page.pid)
        self._logger.debug("Selected page %s", self._current_page)
        return self._current_page

    @pyqtSlot()
    def refresh(self):
        # We don't call "sendme" to refresh current page because:
        # - the caller should be using select_page anyway so we always know what page we're on
        # - if we change page we enqueue commands related to the old page until the next sendme
        #   response updates the current page
        pass

    @pyqtSlot(CommandBase)
    def _on_enqueue_command(self, command):
        self._commands.appendleft(command)

    @pyqtSlot()
    def _on_sendme_successful(self):
        # data_event is a CurrentPageIDHeadEvent
        pid = self._sendme_command.data_event.pid
        current_page = self.pages_by_id[pid]

        if self._current_page is None:
            self.page_changed.emit(current_page.pid)
        elif self._current_page.pid != current_page.pid:
            self.page_changed.emit(current_page.pid)
        self._current_page = current_page
        # Will need this because it will be reenqueued only if status is CREATED
        self._sendme_command.reset()

    @pyqtSlot()
    def _on_sendme_failed(self):
        self._current_page = None
        self._logger.error("SENDME command failed: %s", self._sendme_command.data_event)
        # Will need this because it will be reenqueued only if status is CREATED
        self._sendme_command.reset()

    @pyqtSlot()
    def poll(self) -> bool:
        """ Poll the incoming events and dispatch them. Manage the commands queue. Return True if commands queue
            is empty.
        """
        events = []
        # First we read any events that may have come in since the last scan.
        # They may be either responses to commands or touch events
        while True:
            data = self.transport.read_next()
            if data:
                event = MsgEvent.parse(data)
                events.append(event)
                # self._logger.debug("Incoming event %s", event)
            else:
                break

        for event in events:
            # TODO: support more async events!
            if isinstance(event, TouchEvent):
                self._logger.debug("Received touch event %s", event)
                try:
                    page = self.get_page(event.pid)
                    widget = page.widget(event.cid)
                except KeyError:
                    self._logger.info("Received Touch event for unknown page:widget %d:%d", event.pid, event.cid)
                else:
                    if event.press_event is Event.Touch.Press:
                        widget.pressed.emit()
                    else:
                        widget.released.emit()
            else:
                # This is a response to a previous command.
                # Look for the first command in SENT status and feed it the event
                # Since new commands are appended to the left we expect the right one to be the one missing a response
                while self._commands:
                    command = self._commands[-1]
                    if command.status == CommandBase.Status.CREATED:
                        # The rightmost (oldest) one has not been sent. There's something wrong.
                        # Just rotate (and possibly starve this command) and hope for good.
                        self._logger.warning("Event %s received but oldest command is %s", event, command)
                        # Will be sent later
                        self._commands.rotate()
                    elif command.status == CommandBase.Status.SENT:
                        # Feed the event to the command and remove it from the queue if completed.
                        # If it has some handlers attached the signals emitted will have a copy so it SHOULD
                        # not be garbage collected
                        if command.event(event):
                            self._logger.info("Event %s -> command removed %s", event, command)
                            self._commands.pop()
                        break
                    else:
                        self._logger.error("Event %s received but oldest command is %s", event, command)
                        # Should NEVER get here, see above
                        self._commands.rotate()

        if self._commands:
            # self._logger.debug("Commands queue %s", self._commands)
            # We send only one command at a time since the Nextion is single-core
            # and will process one command at a time anyway
            command = self._commands[-1]
            if command.status == CommandBase.Status.CREATED:
                self._logger.debug("Sending command %s", command)
                command.send(self.transport)

        if self._initialized and not self._commands:
            # Device must be initialized before refreshing widgets
            # Refresh components status
            # self._logger.info("Refreshing components")
            self.refresh()
            # Starting from some firmware version (Nextion editor 0.58) we can ask for properties
            # only for currently visible page
            if self.current_page:
                self.current_page.refresh()

        return not self._commands

    # ~Methods ----------------------------------------------------------------


class NexEventPoller(QRunnable):
    def __init__(self, device: NexDevice, poll_interval_ms: int):
        super().__init__()
        self._device = device
        self._logger = logging.getLogger("pynextion.NexEventPoller")
        self._run_poll_loop = True
        self._run_poll_loop_lock = QReadWriteLock()
        self._thread_local = threading.local()
        self._poll_interval_ms = poll_interval_ms

    def stop(self):
        self._logger.info("Stopping Nextion event poller loop")
        try:
            self._run_poll_loop_lock.lockForWrite()
            self._run_poll_loop = False
        finally:
            self._run_poll_loop_lock.unlock()

    def run(self):
        self._logger.info("Starting Nextion event poller with a %d [ms] interval", self._poll_interval_ms)
        while True:
            try:
                self._run_poll_loop_lock.lockForRead()
                self._thread_local.run = self._run_poll_loop
            finally:
                self._run_poll_loop_lock.unlock()

            if not self._thread_local.run:
                self._logger.info("Exiting Nextion event poller loop")
                break

            self._device.poll()
            QThread.msleep(self._poll_interval_ms)
