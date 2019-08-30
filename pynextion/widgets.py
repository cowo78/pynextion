#!/usr/bin/env python
# -*- coding: utf-8 -*-

import collections
import logging
import typing

from collections import ChainMap, OrderedDict

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from .commands import CommandBase, PageCommand
from .exceptions import NexComponentNameException, NexComponentIdException

from .interfaces import NxInterface, IViewable, IBooleanValued, INumericalUnsignedValued, INumericalSignedValued, \
    IStringValued, IFontStyleable, IColourable, IPicturable, ITouchable, IWidthable, IHeightable


class NexWidget(QObject):
    """ Base class for all widgets"""

    enqueue_command = pyqtSignal(CommandBase)
    """ Emitted whenever a command needs to be enqueued """

    command_failed = pyqtSignal(CommandBase)
    """ Emitted whenever a command has failed """

    REFRESH_VARIABLES = None  # type: typing.Union[None, typing.Iterable[str]]
    ONETIME_REFRESH_VARIABLES = None  # type: typing.Union[None, typing.Iterable[str]]

    def __init__(self, name: str, pid: int, cid: int = None, parent=None):
        super().__init__(parent)
        self._logger = logging.getLogger("pynextion.NexWidget")
        self.name = name
        self.pid = pid  # Page ID
        self.cid = cid  # Component (widget) ID
        self._properties_cache = {}  # type: typing.Dict[str, typing.Any]
        self.commands = collections.deque()  # type: typing.Sequence[CommandBase]

    def __str__(self) -> str:
        return "{0.__class__.__name__} - Page ID {0.pid} - Component ID {0.cid} - Name {0.name}".format(self)

    @pyqtSlot()
    def _on_command_successful(self):
        """ Dequeue command and disconnect handlers """
        command = self.sender()
        command.successful.disconnect()
        command.failed.disconnect()
        existing = self.commands.pop()
        assert existing == command

    @pyqtSlot()
    def _on_command_failed(self):
        """ Dequeue command and disconnect handlers. Relay command to command_failed signal. """
        command = self.sender()
        self.command_failed.emit(command)
        command.successful.disconnect()
        command.failed.disconnect()
        existing = self.commands.pop()
        assert existing == command
        self._logger.error("Command %s failed on object %s with data event %s: {}", command, self, command.data_event)

    def send_command(self, command: CommandBase):
        """ Enqueue a command to be executed """
        self.commands.appendleft(command)
        command.failed.connect(self._on_command_failed)
        command.successful.connect(self._on_command_successful)
        self.enqueue_command.emit(command)

    def to_dict(self):
        return {
            "pid": self.pid,
            "cid": self.cid,
            "name": self.name,
            "type": self.__class__.__name__.strip("Nex")
        }


class NexButton(NexWidget, IViewable, IStringValued, IFontStyleable, IColourable, ITouchable):
    ONETIME_REFRESH_VARIABLES = ("txt",)


class NexCheckbox(NexWidget, IViewable, IBooleanValued, IColourable, ITouchable):
    pass


class NexCrop(NexWidget, IViewable, IPicturable, ITouchable):
    pass


class NexDualStateButton(NexWidget, IViewable, IBooleanValued, IColourable, ITouchable):
    pass


class NexGauge(NexWidget, IViewable, INumericalUnsignedValued, IColourable, ITouchable):
    pass


class NexHotspot(NexWidget, ITouchable):
    pass


class NexNumber(NexWidget, IViewable, INumericalSignedValued, IFontStyleable, IColourable, ITouchable):
    pass


class NexPage(NexWidget):
    def __init__(self, name, pid=None, **kwargs_ignored):
        """ Create a new Page. kwargs are ignored to be compatible with factory function """
        super().__init__(name, pid)
        self.D_WIDGETS_BY_NAME = OrderedDict()
        self.D_WIDGETS_BY_CID = OrderedDict()
        self._widgets_by_name_or_id = ChainMap(self.D_WIDGETS_BY_NAME, self.D_WIDGETS_BY_CID)
        self._page_switch_in_progress = False

    @property
    def widgets(self):
        return self.D_WIDGETS_BY_NAME.values()

    def widget(self, name_or_id: typing.Union[str, int]):
        """ Access a widget by either name or ID"""
        return self._widgets_by_name_or_id[name_or_id]

    __getitem__ = widget

    @pyqtSlot()
    def refresh(self):
        """ Refresh all (hooked) widgets in current page """
        if not self._page_switch_in_progress:
            [widget.refresh() for widget in self.widgets]

    @pyqtSlot()
    def onetime_refresh(self):
        if not self._page_switch_in_progress:
            [widget.onetime_refresh() for widget in self.widgets]

    def show(self):
        """ Bring the current page to foreground.
            **DO NOT** call this method directly, use select_page() on parent NexDevice instead
            so it can keep track of current page
        """
        self._page_switch_in_progress = True
        target = self.name if self.pid is None else self.pid
        self.send_command(PageCommand(target))

    def hook_widget(self, widget_type: str, name: str, cid=None) -> NexWidget:
        """ Hook and return a new widget of the specified type/name/ID to the current page """
        pid = self.pid

        if name in self.D_WIDGETS_BY_NAME:
            raise NexComponentNameException("Widget name (%s) must be unique" % name)

        if cid in self.D_WIDGETS_BY_CID:
            raise NexComponentIdException("Widget ID (%s) must be unique" % cid)

        widget = WidgetFactory.create(widget_type, name, pid, cid)
        self.D_WIDGETS_BY_NAME[name] = widget
        if cid is not None:
            self.D_WIDGETS_BY_CID[cid] = widget
        widget.enqueue_command.connect(self.enqueue_command)
        self._logger.debug("Hooked new widget %s", name)
        return widget

    def hook_widgets(self, widget_data: typing.Iterable[typing.Tuple[str, str, int]]) -> typing.List[NexWidget]:
        """ Hook and return some widgets
            :param widget_data: iterable of (widget type, widget name, widget id)
        """
        return [self.hook_widget(widget_type, name, cid) for widget_type, name, cid in widget_data]

    @pyqtSlot()
    def _on_command_successful(self):
        command = self.sender()
        command.successful.disconnect()
        command.failed.disconnect()
        existing = self.commands.pop()
        assert existing == command
        if isinstance(command, PageCommand):
            self._page_switch_in_progress = False

    def to_dict(self):
        return {
            "pid": self.pid,
            "name": self.name,
            "components": [widget.to_dict() for widget in self.widgets]
        }


class NexPicture(NexWidget, IViewable, IPicturable):
    pass


class NexProgressBar(NexWidget, IViewable, INumericalUnsignedValued, IColourable, ITouchable):
    ONETIME_REFRESH_VARIABLES = ("val",)

    def increase(self, amount: int = 1):
        self
        self.value += amount

    def decrease(self, amount: int = 1):
        self.value -= amount


class NexQRcode(NexWidget, IViewable, IStringValued):
    pass


class NexRadio(NexWidget, IViewable, IBooleanValued, IColourable, ITouchable):
    pass


class NexScrollText(NexWidget, IViewable, IStringValued, IFontStyleable, IColourable, ITouchable):
    pass


class NexSliderCursor(NexWidget, IWidthable, IHeightable):
    def __init__(self, nid):
        self._nid = nid


class NexSlider(NexWidget, IViewable, INumericalUnsignedValued, IColourable, ITouchable):
    ONETIME_REFRESH_VARIABLES = ("val",)

    @property
    def cursor(self):
        return NexSliderCursor(self._nid)


class NexText(NexWidget, IViewable, IStringValued, IFontStyleable, IColourable, ITouchable):
    ONETIME_REFRESH_VARIABLES = ("txt",)


class NexWaveformChannel:
    def __init__(self, nid, chid):
        self._nid = nid
        self._chid = chid  # channel id

    def append(self, value):
        nid = self._nid
        cid = nid.cid
        chid = self._chid
        nexserial = nid._nexserial
        if isinstance(value, list):
            vals = value
            n = len(vals)
            cmd = "addt %s,%s,%s" % (cid, chid, n)
            nexserial.send(cmd)
            nexserial.sp.write(bytearray(vals))
            return nexserial.read_all()
        else:
            if value < 0 or value > 255:
                raise (Exception("value must be in 0-255 range"))
            cmd = "add %s,%s,%s" % (cid, chid, value)
            return nexserial.send(cmd)


class NexWaveformChannels:
    def __init__(self, nid):
        self._nid = nid

    def __getitem__(self, id):
        return NexWaveformChannel(self._nid, id)


class NexWaveformGrid(NexWidget, NxInterface):
    def __init__(self, nid):
        self._nid = nid

    @property
    def width(self):
        return self._get_nex_number_property("gdw")

    @width.setter
    def width(self, value):
        self._set_nex_number_property("gdw", value)

    @property
    def height(self):
        return self._get_nex_number_property("gdh")

    @height.setter
    def height(self, value):
        self._set_nex_number_property("gdh", value)

    @property
    def color(self):
        return self._get_nex_number_property("gdc")

    @color.setter
    def color(self, new_color):
        self._set_nex_number_property("gdc", new_color.value)


class NexWaveform(NexWidget, IViewable, IColourable, ITouchable):
    @property
    def grid(self):
        return NexWaveformGrid(self._nid)

    @property
    def channels(self):
        return NexWaveformChannels(self._nid)


class WidgetFactory:
    D_FACTORY = {
        "button": NexButton,
        "checkbox": NexCheckbox,
        "crop": NexCrop,
        "dualstatebutton": NexDualStateButton,
        "gauge": NexGauge,
        "hotspot": NexHotspot,
        "number": NexNumber,
        "page": NexPage,
        "picture": NexPicture,
        "progressbar": NexProgressBar,
        "qrcode": NexQRcode,
        "radio": NexRadio,
        "scrolltext": NexScrollText,
        "slider": NexSlider,
        "text": NexText,
        "waveform": NexWaveform
    }

    @classmethod
    def type(cls, typ: str):
        return cls.D_FACTORY[typ.lower()]

    @classmethod
    def create(cls, typ: typing.Union[str, typing.Type], name: str, pid=None, cid=None) -> NexWidget:
        """ Create a new instance of specified widget
            :param typ: Widget type as string (defined in D_FACTORY) or widget class
            :param name: Widget name
            :param pid: Page ID
            :param cid: Widget ID
        """
        if isinstance(typ, str):
            widget = cls.D_FACTORY[typ.lower()](name, pid=pid, cid=cid)
        else:
            # Assume it is a type
            widget = typ(name, pid, cid)

        return widget
