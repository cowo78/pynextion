#!/usr/bin/env python
# -*- coding: utf-8 -*-

from PyQt5.QtCore import pyqtProperty, pyqtSignal, pyqtSlot

from .commands import GetPropertyCommand, SetPropertyCommand
from .constants import Alignment
from .resources import Font, Picture


class NxInterface(object):
    """ Base interface (or, better, mixin) TO BE SUBCLASSED by a NexWidget or subclass """

    @pyqtSlot()
    def refresh(self):
        """ Called by device poller. Responsible of enqueuing commands needed to read interesting variables.
            It is generally NOT feasible to keep all variables updated on every cycle for performance reasons,
            so only those that are modified directly by the user should be placed here
        """
        if self.REFRESH_VARIABLES:
            [self._refresh_internal(var) for var in self.REFRESH_VARIABLES]

    @pyqtSlot()
    def onetime_refresh(self):
        """ Initial variables refresh to update widget status """
        if self.ONETIME_REFRESH_VARIABLES:
            [self._refresh_internal(var) for var in self.ONETIME_REFRESH_VARIABLES]

    @pyqtSlot()
    def _refresh_internal(self, property_name: str):
        # No need to keep a reference to the command
        command = GetPropertyCommand(self.name, property_name, self._on_get_property_command_successful)
        self.send_command(command)

    @pyqtSlot()
    def _on_get_property_command_successful(self):
        command = self.sender()
        # Usually the data_event uses the "value" attribute, but subclasses may use different stuff, see
        # INumericalUnsignedValued
        previous = self._properties_cache.get(command.property_name, None)
        self._properties_cache[command.property_name] = command.data_event.value
        if previous != command.data_event.value:
            self.value_changed.emit(command.data_event.value)


class INumericalUnsignedValued(NxInterface):
    value_changed = pyqtSignal(int)

    @pyqtProperty(int)
    def value(self):
        return self._properties_cache["val"]

    @value.setter
    def value(self, value: int):
        self.send_command(SetPropertyCommand(self.name, "val", value, on_successful=self._on_set_property_command_successful))

    @pyqtSlot(int)
    def set_value(self, value):
        self.value = value

    @pyqtSlot()
    def _on_set_property_command_successful(self):
        command = self.sender()
        # Update cache and send value_changed signal
        previous = self._properties_cache.get(command.property_name, None)
        self._properties_cache[command.property_name] = command.new_value
        if previous != command.new_value:
            self.value_changed.emit(command.new_value)


class INumericalSignedValued(INumericalUnsignedValued):
    @pyqtSlot()
    def _on_get_property_command_successful(self):
        command = self.sender()
        # NumberHeadEvent
        self._properties_cache[command.property_name] = command.data_event.signed_value


class IBooleanValued(INumericalUnsignedValued):
    @pyqtSlot()
    def _on_get_property_command_successful(self):
        command = self.sender()
        # NumberHeadEvent
        self._properties_cache[command.property_name] = bool(command.data_event.value)


class IStringValued(NxInterface):
    value_changed = pyqtSignal(str)

    @pyqtProperty(str)
    def text(self):
        return self._properties_cache["txt"]

    @text.setter
    def text(self, value):
        self.send_command(SetPropertyCommand(self.name, "txt", value))

    @pyqtSlot(str)
    def set_text(self, txt):
        self.text = txt


class IColourable(NxInterface):
    @pyqtProperty(int)
    def backcolor(self):
        return self._get_nex_number_property("bco", False, 32)

    @backcolor.setter
    def backcolor(self, color):
        self._set_nex_number_property("bco", color.value)

    @pyqtProperty(int)
    def forecolor(self):
        return self._get_nex_number_property("pco", False, 32)

    @forecolor.setter
    def forecolor(self, color):
        self._set_nex_number_property("pco", color.value)


class AlignmentDirection(NxInterface):
    def __init__(self, nid):
        self = nid

    @pyqtProperty(int)
    def vertical(self):
        return Alignment.Vertical(self._get_nex_number_property("ycen", False, 32))

    @vertical.setter
    def vertical(self, value):
        assert isinstance(value, Alignment.Vertical), "Argument must be %r" % Alignment.Vertical
        self._set_nex_number_property("ycen", value.value)

    @pyqtProperty(int)
    def horizontal(self):
        return Alignment.Horizontal(self._get_nex_number_property("xcen", False, 32))

    @horizontal.setter
    def horizontal(self, value):
        assert isinstance(value, Alignment.Horizontal), "Argument must be %r" % Alignment.Horizontal
        self._set_nex_number_property("xcen", value.value)


class IFontStyleable(NxInterface):
    @pyqtProperty(int)
    def font(self):
        return self._get_nex_number_property("font", False, 32)

    @font.setter
    def font(self, value):
        assert isinstance(value, Font), "Argument must be %r" % Font
        self._set_nex_number_property("font", value.id)

    @pyqtProperty(AlignmentDirection)
    def alignment(self):
        return AlignmentDirection(self)


class IPicturable(NxInterface):
    @pyqtProperty(int)
    def picture(self):
        return self._get_nex_number_property("pic", False, 32)

    @picture.setter
    def picture(self, value):
        assert isinstance(value, Picture), "Argument must be %r" % Picture
        self._set_nex_number_property("pic", value.id)


class IViewable(NxInterface):
    @pyqtProperty(bool)
    def visible(self):
        raise AttributeError("It is not possible to know if a Nextion widget is currently visible")

    @visible.setter
    def visible(self, value):
        oid = self.name
        if value:
            cmd = "vis %s,1" % oid
        else:
            cmd = "vis %s,0" % oid
        self._send(cmd)


class IHeightable(NxInterface):
    @pyqtProperty(int)
    def height(self):
        return self._get_nex_number_property("hig", False, 32)

    @height.setter
    def height(self, value):
        self._set_nex_number_property("hig", value)


class IWidthable(NxInterface):
    @pyqtProperty(int)
    def width(self):
        return self._get_nex_number_property("wid", False, 32)

    @width.setter
    def width(self, value):
        self._set_nex_number_property("wid", value)


class ITouchable(NxInterface):
    pressed = pyqtSignal()
    " Emitted whenever the button is pressed "
    released = pyqtSignal()
    " Emitted whenever the button is released. WARNING: UNRELIABLE!!! "

    # TODO: these do not seem to work, I always get an "invalid variable" response
    def enable_touch_event(self):
        self._send("tsw {}, 1".format(self.cid or self.name))

    def disable_touch_event(self):
        self._send("tsw {}, 0".format(self.cid or self.name))
