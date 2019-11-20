#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#############################################################################
#
# OnAirScreen
# Copyright (c) 2012-2019 Sascha Ludwig, astrastudio.de
# All rights reserved.
#
# start.py
# This file is part of OnAirScreen
#
# You may use this file under the terms of the BSD license as follows:
#
# "Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#   * Redistributions of source code must retain the above copyright
#     notice, this list of conditions and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright
#     notice, this list of conditions and the following disclaimer in
#     the documentation and/or other materials provided with the
#     distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE."
#
#############################################################################

import os
import sys
import re
from datetime import datetime

from PyQt5.QtGui import QCursor, QPalette, QColor, QKeySequence, QIcon, QPixmap
from PyQt5.QtWidgets import QApplication, QWidget, QColorDialog, QShortcut, QDialog, QLineEdit, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt, pyqtSignal, QSettings, QCoreApplication, QTimer, QObject, QVariant, QDate, QThread, QUrl
from PyQt5.QtNetwork import QUdpSocket, QHostAddress, QHostInfo, QNetworkInterface
from mainscreen import Ui_MainScreen
import ntplib
import signal
import socket
from settings_functions import Settings, versionString
from urllib.parse import unquote
from http.server import BaseHTTPRequestHandler, HTTPServer

#HOST = '127.0.0.1'
HOST = '0.0.0.0'


class MainScreen(QWidget, Ui_MainScreen):
    getTimeWindow: QDialog
    ntpHadWarning: bool
    ntpWarnMessage: str

    def __init__(self):
        QWidget.__init__(self)
        Ui_MainScreen.__init__(self)
        self.setupUi(self)

        # load weather widget

        self.settings = Settings()
        self.restoreSettingsFromConfig()
        # quit app from settings window
        self.settings.sigExitOAS.connect(self.exitOAS)
        self.settings.sigRebootHost.connect(self.reboot_host)
        self.settings.sigShutdownHost.connect(self.shutdown_host)
        self.settings.sigConfigFinished.connect(self.configFinished)
        self.settings.sigConfigClosed.connect(self.configClosed)

        settings = QSettings(QSettings.UserScope, "astrastudio", "OnAirScreen")
        settings.beginGroup("General")
        if settings.value('fullscreen', True, type=bool):
            self.showFullScreen()
            app.setOverrideCursor(QCursor(Qt.BlankCursor))
        settings.endGroup()
        print("Loading Settings from: ", settings.fileName())

        #self.labelWarning.hide()

        # init warning prio array (0-2
        self.warnings = ["", "", ""]

        # add hotkey bindings
        QShortcut(QKeySequence("Ctrl+F"), self, self.toggleFullScreen)
        QShortcut(QKeySequence("F"), self, self.toggleFullScreen)
        QShortcut(QKeySequence(16777429), self, self.toggleFullScreen)  # 'Display' Key on OAS USB Keyboard
        QShortcut(QKeySequence(16777379), self, self.shutdown_host)  # 'Calculator' Key on OAS USB Keyboard
        QShortcut(QKeySequence("Ctrl+Q"), self, QCoreApplication.instance().quit)
        QShortcut(QKeySequence("Q"), self, QCoreApplication.instance().quit)
        QShortcut(QKeySequence("Ctrl+C"), self, QCoreApplication.instance().quit)
        QShortcut(QKeySequence("ESC"), self, QCoreApplication.instance().quit)
        QShortcut(QKeySequence("Ctrl+S"), self, self.showsettings)
        QShortcut(QKeySequence("Ctrl+,"), self, self.showsettings)
        QShortcut(QKeySequence("1"), self, self.manualToggleLED1)
        QShortcut(QKeySequence("2"), self, self.manualToggleLED2)
        QShortcut(QKeySequence("3"), self, self.manualToggleLED3)
        QShortcut(QKeySequence("M"), self, self.toggleAIR1)
        QShortcut(QKeySequence("/"), self, self.toggleAIR1)

        self.statusLED1 = False
        self.statusLED2 = False
        self.statusLED3 = False

        self.LED1on = False
        self.LED2on = False
        self.LED3on = False

        # Setup and start timers
        self.ctimer = QTimer()
        self.ctimer.timeout.connect(self.constantUpdate)
        self.ctimer.start(100)
        # LED timers
        self.timerLED1 = QTimer()
        self.timerLED1.timeout.connect(self.toggleLED1)
        self.timerLED2 = QTimer()
        self.timerLED2.timeout.connect(self.toggleLED2)
        self.timerLED3 = QTimer()
        self.timerLED3.timeout.connect(self.toggleLED3)
        #self.timerLED4 = QTimer()
        #self.timerLED4.timeout.connect(self.toggleLED4)

        # Setup OnAir Timers
        self.timerAIR1 = QTimer()
        self.timerAIR1.timeout.connect(self.updateAIR1Seconds)
        self.Air1Seconds = 0
        self.statusAIR1 = False

        #self.timerAIR2 = QTimer()
        #self.timerAIR2.timeout.connect(self.updateAIR2Seconds)
        #self.Air2Seconds = 0
        #self.statusAIR2 = False

        #self.timerAIR3 = QTimer()
        #self.timerAIR3.timeout.connect(self.updateAIR3Seconds)
        #self.Air3Seconds = 0
        #self.statusAIR3 = False
        #self.radioTimerMode = 0  # count up mode

        #self.timerAIR4 = QTimer()
        #self.timerAIR4.timeout.connect(self.updateAIR4Seconds)
        #self.Air4Seconds = 0
        #self.statusAIR4 = False
        #self.streamTimerMode = 0  # count up mode

        # Setup NTP Check Thread
        #self.checkNTPOffset = checkNTPOffsetThread(self)

        # Setup check NTP Timer
        #self.ntpHadWarning = True
        #self.ntpWarnMessage = ""
        #self.timerNTP = QTimer()
        #self.timerNTP.timeout.connect(self.triggerNTPcheck)
        # initial check
        #self.timerNTP.start(1000)

        # Setup UDP Socket
        self.udpsock = QUdpSocket()
        settings = QSettings(QSettings.UserScope, "astrastudio", "OnAirScreen")
        settings.beginGroup("Network")
        port = int(settings.value('udpport', 3310))
        settings.endGroup()
        self.udpsock.bind(port, QUdpSocket.ShareAddress)
        self.udpsock.readyRead.connect(self.cmdHandler)

        # Setup HTTP Server
        self.httpd = HttpDaemon(self)
        self.httpd.start()

        # display all host addresses
        self.displayAllHostaddresses()

        # set NTP warning
        #settings = QSettings(QSettings.UserScope, "astrastudio", "OnAirScreen")
        #settings.beginGroup("NTP")
        #if settings.value('ntpcheck', True, type=bool):
        #    self.ntpHadWarning = True
        #    self.ntpWarnMessage = "waiting for NTP status check"
        #settings.endGroup()

    def radioTimerStartStop(self):
        pass
        #self.startStopAIR3()

    def radioTimerReset(self):
        pass
        #self.resetAIR3()
        #self.radioTimerMode = 0  # count up mode

    def radioTimerSet(self, seconds):
        pass
        #self.Air3Seconds = seconds
        #if seconds > 0:
        #    self.radioTimerMode = 1  # count down mode
        #else:
        #    self.radioTimerMode = 0  # count up mode
        #self.AirLabel_3.setText("Timer\n%d:%02d" % (self.Air3Seconds / 60, self.Air3Seconds % 60))

    def getTimerDialog(self):
        return
        # generate and display timer input window
        self.getTimeWindow = QDialog()
        self.getTimeWindow.resize(200, 100)
        self.getTimeWindow.setWindowTitle("Please enter timer")
        self.getTimeWindow.timeEdit = QLineEdit("Enter timer here")
        self.getTimeWindow.timeEdit.selectAll()
        self.getTimeWindow.infoLabel = QLabel("Examples:\nenter 2,10 for 2:10 minutes\nenter 30 for 30 seconds")
        layout = QVBoxLayout()
        layout.addWidget(self.getTimeWindow.infoLabel)
        layout.addWidget(self.getTimeWindow.timeEdit)
        self.getTimeWindow.setLayout(layout)
        self.getTimeWindow.timeEdit.setFocus()
        self.getTimeWindow.timeEdit.returnPressed.connect(self.parseTimerInput)
        self.getTimeWindow.show()

    def parseTimerInput(self):
        minutes = 0
        seconds = 0
        # hide input window
        self.sender().parent().hide()
        # get time string
        text = str(self.sender().text())
        if re.match('^[0-9]*,[0-9]*$', text):
            (minutes, seconds) = text.split(",")
            minutes = int(minutes)
            seconds = int(seconds)
        elif re.match('^[0-9]*\.[0-9]*$', text):
            (minutes, seconds) = text.split(".")
            minutes = int(minutes)
            seconds = int(seconds)
        elif re.match('^[0-9]*$', text):
            seconds = int(text)
        seconds = (minutes * 60) + seconds
        self.radioTimerSet(seconds)

    def streamTimerStartStop(self):
        self.startStopAIR4()

    def streamTimerReset(self):
        self.resetAIR4()
        self.streamTimerMode = 0  # count up mode

    def showsettings(self):
        global app
        # un-hide mouse cursor
        app.setOverrideCursor(QCursor(Qt.ArrowCursor));
        self.settings.showsettings()

    def displayAllHostaddresses(self):
        v4addrs = list()
        v6addrs = list()
        for address in QNetworkInterface().allAddresses():
            if address.protocol() == 0:
                v4addrs.append(address.toString())
            # if address.protocol() == 1:
            #    v6addrs.append(address.toString())

        self.setCurrentSongText(", ".join(["%s" % addr for addr in v4addrs]))
        self.setNewsText(", ".join(["%s" % (addr) for addr in v6addrs]))

    def cmdHandler(self):
        while self.udpsock.hasPendingDatagrams():
            data, host, port = self.udpsock.readDatagram(self.udpsock.pendingDatagramSize())
            # print("DATA: ", data)
            lines = data.splitlines()
            for line in lines:
                # print("Line:", line)
                try:
                    (command, value) = line.decode('utf_8').split(':', 1)
                except ValueError:
                    return
                command = str(command)
                value = str(value)
                # print("command: >" + command + "<")
                # print("value: >" + value + "<")
                if command == "NOW":
                    self.setCurrentSongText(value)
                if command == "NEXT":
                    self.setNewsText(value)
                if command == "LED1":
                    if value == "OFF":
                        self.ledLogic(1, False)
                    else:
                        self.ledLogic(1, True)
                if command == "LED2":
                    if value == "OFF":
                        self.ledLogic(2, False)
                    else:
                        self.ledLogic(2, True)
                if command == "LED3":
                    if value == "OFF":
                        self.ledLogic(3, False)
                    else:
                        self.ledLogic(3, True)
                if command == "LED4":
                    if value == "OFF":
                        self.ledLogic(4, False)
                    else:
                        self.ledLogic(4, True)
                if command == "WARN":
                    if value:
                        self.addWarning(value, 1)
                    else:
                        self.removeWarning(1)

                if command == "AIR1":
                    if value == "OFF":
                        self.setAIR1(False)
                    else:
                        self.setAIR1(True)

                if command == "AIR2":
                    if value == "OFF":
                        self.setAIR2(False)
                    else:
                        self.setAIR2(True)

                if command == "AIR3":
                    if value == "OFF":
                        self.stopAIR3()
                    if value == "ON":
                        self.startAIR3()
                    if value == "RESET":
                        self.radioTimerReset()
                    if value == "TOGGLE":
                        self.radioTimerStartStop()

                if command == "AIR3TIME":
                    self.radioTimerSet(int(value))

                if command == "AIR4":
                    if value == "OFF":
                        self.setAIR4(False)
                    if value == "ON":
                        self.setAIR4(True)
                    if value == "RESET":
                        self.streamTimerReset()

                if command == "CMD":
                    if value == "REBOOT":
                        self.reboot_host()
                    if value == "SHUTDOWN":
                        self.shutdown_host()
                    if value == "QUIT":
                        QApplication.quit()

                if command == "CONF":
                    # split group, config and values and apply them
                    try:
                        (group, paramvalue) = value.split(':', 1)
                        (param, content) = paramvalue.split('=', 1)
                        # print "CONF:", param, content
                    except ValueError:
                        return

                    if group == "General":
                        if param == "stationname":
                            self.settings.StationName.setText(content)
                        if param == "slogan":
                            self.settings.Slogan.setText(content)
                        if param == "stationcolor":
                            self.settings.setStationNameColor(self.settings.getColorFromName(content))
                        if param == "slogancolor":
                            self.settings.setSloganColor(self.settings.getColorFromName(content))

                    if group == "LED1":
                        if param == "used":
                            self.settings.LED1.setChecked(QVariant(content).toBool())
                        if param == "text":
                            self.settings.LED1Text.setText(content)
                        if param == "activebgcolor":
                            self.settings.setLED1BGColor(self.settings.getColorFromName(content))
                        if param == "activetextcolor":
                            self.settings.setLED1FGColor(self.settings.getColorFromName(content))
                        if param == "autoflash":
                            self.settings.LED1Autoflash.setChecked(QVariant(content).toBool())
                        if param == "timedflash":
                            self.settings.LED1Timedflash.setChecked(QVariant(content).toBool())

                    if group == "LED2":
                        if param == "used":
                            self.settings.LED2.setChecked(QVariant(content).toBool())
                        if param == "text":
                            self.settings.LED2Text.setText(content)
                        if param == "activebgcolor":
                            self.settings.setLED2BGColor(self.settings.getColorFromName(content))
                        if param == "activetextcolor":
                            self.settings.setLED2FGColor(self.settings.getColorFromName(content))
                        if param == "autoflash":
                            self.settings.LED2Autoflash.setChecked(QVariant(content).toBool())
                        if param == "timedflash":
                            self.settings.LED2Timedflash.setChecked(QVariant(content).toBool())

                    if group == "LED3":
                        if param == "used":
                            self.settings.LED3.setChecked(QVariant(content).toBool())
                        if param == "text":
                            self.settings.LED3Text.setText(content)
                        if param == "activebgcolor":
                            self.settings.setLED3BGColor(self.settings.getColorFromName(content))
                        if param == "activetextcolor":
                            self.settings.setLED3FGColor(self.settings.getColorFromName(content))
                        if param == "autoflash":
                            self.settings.LED3Autoflash.setChecked(QVariant(content).toBool())
                        if param == "timedflash":
                            self.settings.LED3Timedflash.setChecked(QVariant(content).toBool())

                    if group == "LED4":
                        if param == "used":
                            self.settings.LED4.setChecked(QVariant(content).toBool())
                        if param == "text":
                            self.settings.LED4Text.setText(content)
                        if param == "activebgcolor":
                            self.settings.setLED4BGColor(self.settings.getColorFromName(content))
                        if param == "activetextcolor":
                            self.settings.setLED4FGColor(self.settings.getColorFromName(content))
                        if param == "autoflash":
                            self.settings.LED4Autoflash.setChecked(QVariant(content).toBool())
                        if param == "timedflash":
                            self.settings.LED4Timedflash.setChecked(QVariant(content).toBool())

                    if group == "Clock":
                        if param == "digital":
                            if content == "True":
                                self.settings.clockDigital.setChecked(True)
                                self.settings.clockAnalog.setChecked(False)
                            if content == "False":
                                self.settings.clockAnalog.setChecked(False)
                                self.settings.clockDigital.setChecked(True)
                        if param == "showseconds":
                            if content == "True":
                                self.settings.showSeconds.setChecked(True)
                            if content == "False":
                                self.settings.showSeconds.setChecked(False)
                        if param == "digitalhourcolor":
                            self.settings.setDigitalHourColor(self.settings.getColorFromName(content))
                        if param == "digitalsecondcolor":
                            self.settings.setDigitalSecondColor(self.settings.getColorFromName(content))
                        if param == "digitaldigitcolor":
                            self.settings.setDigitalDigitColor(self.settings.getColorFromName(content))
                        if param == "logopath":
                            self.settings.setLogoPath(content)

                    if group == "Network":
                        if param == "udpport":
                            self.settings.udpport.setText(content)

                    if group == "CONF":
                        if param == "APPLY":
                            if content == "TRUE":
                                # apply and save settings
                                self.settings.applySettings()

    def manualToggleLED1(self):
        if self.LED1on:
            self.ledLogic(1, False)
        else:
            self.ledLogic(1, True)

    def manualToggleLED2(self):
        if self.LED2on:
            self.ledLogic(2, False)
        else:
            self.ledLogic(2, True)

    def manualToggleLED3(self):
        if self.LED3on:
            self.ledLogic(3, False)
        else:
            self.ledLogic(3, True)

    def manualToggleLED4(self):
        if self.LED4on:
            self.ledLogic(4, False)
        else:
            self.ledLogic(4, True)

    def toggleLED1(self):
        if self.statusLED1:
            self.setLED1(False)
        else:
            self.setLED1(True)

    def toggleLED2(self):
        if self.statusLED2:
            self.setLED2(False)
        else:
            self.setLED2(True)

    def toggleLED3(self):
        if self.statusLED3:
            self.setLED3(False)
        else:
            self.setLED3(True)

    def toggleLED4(self):
        if self.statusLED4:
            self.setLED4(False)
        else:
            self.setLED4(True)

    def toggleAIR1(self):
        if self.statusAIR1:
            self.setAIR1(False)
        else:
            self.setAIR1(True)

    def toggleAIR2(self):
        if self.statusAIR2:
            self.setAIR2(False)
        else:
            self.setAIR2(True)

    def toggleAIR4(self):
        if self.statusAIR4:
            self.setAIR4(False)
        else:
            self.setAIR4(True)

    def unsetLED1(self):
        self.ledLogic(1, False)

    def unsetLED2(self):
        self.ledLogic(2, False)

    def unsetLED3(self):
        self.ledLogic(3, False)

    def unsetLED4(self):
        self.ledLogic(4, False)

    def ledLogic(self, led, state):
        if state:
            if led == 1:
                if self.settings.LED1Autoflash.isChecked():
                    self.timerLED1.start(500)
                if self.settings.LED1Timedflash.isChecked():
                    self.timerLED1.start(500)
                    QTimer.singleShot(20000, self.unsetLED1)
                self.setLED1(state)
                self.LED1on = state
            if led == 2:
                if self.settings.LED2Autoflash.isChecked():
                    self.timerLED2.start(500)
                if self.settings.LED2Timedflash.isChecked():
                    self.timerLED2.start(500)
                    QTimer.singleShot(20000, self.unsetLED2)
                self.setLED2(state)
                self.LED2on = state
            if led == 3:
                if self.settings.LED3Autoflash.isChecked():
                    self.timerLED3.start(500)
                if self.settings.LED3Timedflash.isChecked():
                    self.timerLED3.start(500)
                    QTimer.singleShot(20000, self.unsetLED3)
                self.setLED3(state)
                self.LED3on = state

        if state == False:
            if led == 1:
                self.setLED1(state)
                self.timerLED1.stop()
                self.LED1on = state
            if led == 2:
                self.setLED2(state)
                self.timerLED2.stop()
                self.LED2on = state
            if led == 3:
                self.setLED3(state)
                self.timerLED3.stop()
                self.LED3on = state

    def setStationColor(self, newcolor):
        palette = self.labelStation.palette()
        palette.setColor(QPalette.WindowText, newcolor)
        self.labelStation.setPalette(palette)

    def setSloganColor(self, newcolor):
        palette = self.labelSlogan.palette()
        palette.setColor(QPalette.WindowText, newcolor)
        self.labelSlogan.setPalette(palette)

    def restoreSettingsFromConfig(self):
        settings = QSettings(QSettings.UserScope, "astrastudio", "OnAirScreen")
        settings.beginGroup("General")
        #self.labelStation.setText(settings.value('stationname', 'Radio Eriwan'))
        #self.labelSlogan.setText(settings.value('slogan', 'Your question is our motivation'))
        #self.setStationColor(self.settings.getColorFromName(settings.value('stationcolor', '#FFAA00')))
        #self.setSloganColor(self.settings.getColorFromName(settings.value('slogancolor', '#FFAA00')))
        settings.endGroup()

        settings.beginGroup("LED1")
        self.setLED1Text(settings.value('text', 'ON AIR'))
        settings.endGroup()

        settings.beginGroup("LED2")
        self.setLED2Text(settings.value('text', 'PHONE'))
        settings.endGroup()

        settings.beginGroup("LED3")
        self.setLED3Text(settings.value('text', 'DOORBELL'))
        settings.endGroup()

        #settings.beginGroup("LED4")
        #self.setLED4Text(settings.value('text', 'ARI'))
        #settings.endGroup()

        #settings.beginGroup("Clock")
        #self.clockWidget.setClockMode(settings.value('digital', True, type=bool))
        #self.clockWidget.setDigiHourColor(
        #    self.settings.getColorFromName(settings.value('digitalhourcolor', '#3232FF')))
        #self.clockWidget.setDigiSecondColor(
        #    self.settings.getColorFromName(settings.value('digitalsecondcolor', '#FF9900')))
        #self.clockWidget.setDigiDigitColor(
        #    self.settings.getColorFromName(settings.value('digitaldigitcolor', '#3232FF')))
        #self.clockWidget.setLogo(
        #    settings.value('logopath', ':/astrastudio_logo/images/astrastudio_transparent.png'))
        #self.clockWidget.setShowSeconds(settings.value('showSeconds', False, type=bool))
        #settings.endGroup()

        #settings.beginGroup("Formatting")
        #self.clockWidget.setAmPm(settings.value('isAmPm', False, type=bool))
        #settings.endGroup()

        settings.beginGroup("WeatherWidget")
        if settings.value('owmWidgetEnabled', False, type=bool):
            pass
            #self.weatherWidget =

            #page = self.weatherWidget.page()
            #page.setBackgroundColor(Qt.transparent)
            #page.setHtml(widgetHtml)
            #self.weatherWidget.setUrl(QUrl("qrc:/html/weatherwidget.html"))
        self.weatherWidget.setVisible(settings.value('owmWidgetEnabled', False, type=bool))
        settings.endGroup()


    def constantUpdate(self):
        # slot for constant timer timeout
        self.updateDate()
        self.updateBacktimingText()
        self.updateBacktimingSeconds()
        self.updateNTPstatus()
        self.processWarnings()

    def updateDate(self):
        return
        settings = QSettings(QSettings.UserScope, "astrastudio", "OnAirScreen")
        settings.beginGroup("Formatting")
        now = datetime.now()
        #self.setLeftText(QDate.currentDate().toString(settings.value('dateFormat', 'dddd, dd. MMMM yyyy')))
        settings.endGroup()

    def updateBacktimingText(self):
        return
        settings = QSettings(QSettings.UserScope, "astrastudio", "OnAirScreen")
        settings.beginGroup("Formatting")
        textClockLang = settings.value('textClockLanguage', 'English')
        isampm = settings.value('isAmPm', False, type=bool)
        settings.endGroup()

        string = ""
        now = datetime.now()
        hour = now.hour
        minute = now.minute
        remain_min = 60 - minute

        if textClockLang == "German":
            # german textclock
            if hour > 12:
                hour -= 12
            if 0 < minute < 25:
                string = "%d Minute%s nach %d" % (minute, 'n' if minute > 1 else '', hour)
            if 25 <= minute < 30:
                string = "%d Minute%s vor halb %d" % (remain_min - 30, 'n' if remain_min - 30 > 1 else '', hour + 1)
            if 30 <= minute <= 39:
                string = "%d Minute%s nach halb %d" % (30 - remain_min, 'n' if 30 - remain_min > 1 else '', hour + 1)
            if 40 <= minute <= 59:
                string = "%d Minute%s vor %d" % (remain_min, 'n' if remain_min > 1 else '', hour + 1)
            if minute == 30:
                string = "halb %d" % (hour + 1)
            if minute == 0:
                string = "%d" % hour

        else:
            # english textclock
            if isampm:
                if hour > 12:
                    hour -= 12
            if minute == 0:
                string = "it's %d o'clock" % hour
            if (0 < minute < 15) or (16 <= minute <= 29):
                string = "it's %d minute%s past %d:00" % (minute, 's' if minute > 1 else '', hour)
            if minute == 15:
                string = "it's a quarter past %d:00" % hour
            if minute == 30:
                string = "it's half past %d:00" % hour
            if minute == 45:
                string = "it's a quarter to %d:00" % hour
            if (31 <= minute <= 44) or (46 <= minute <= 59):
                string = "it's %d minute%s to %d:00" % (
                    remain_min, 's' if remain_min > 1 else '', 1 if hour == 12 else hour + 1)

        self.setRightText(string)

    def updateBacktimingSeconds(self):
        now = datetime.now()
        second = now.second
        remain_seconds = 60 - second
        self.setBacktimingSecs(remain_seconds)

    def updateNTPstatus(self):
        return
        if self.ntpHadWarning and len(self.ntpWarnMessage):
            self.addWarning(self.ntpWarnMessage, 0)
        else:
            self.ntpWarnMessage = ""
            self.removeWarning(0)

    def toggleFullScreen(self):
        global app
        settings = QSettings(QSettings.UserScope, "astrastudio", "OnAirScreen")
        settings.beginGroup("General")
        if not settings.value('fullscreen', True, type=bool):
            self.showFullScreen()
            app.setOverrideCursor(QCursor(Qt.BlankCursor))
            settings.setValue('fullscreen', True)
        else:
            self.showNormal()
            app.setOverrideCursor(QCursor(Qt.ArrowCursor))
            settings.setValue('fullscreen', False)
        settings.endGroup()

    def setAIR1(self, action):
        settings = QSettings(QSettings.UserScope, "astrastudio", "OnAirScreen")
        if action:
            self.Air1Seconds = 0
            self.AirLabel_1.setStyleSheet("color: #000000; background-color: #FF0000")
            self.AirIcon_1.setStyleSheet("color: #000000; background-color: #FF0000")
            self.AirLabel_1.setText("Mic\n%d:%02d" % (self.Air1Seconds / 60, self.Air1Seconds % 60))
            self.statusAIR1 = True
            # AIR1 timer
            self.timerAIR1.start(1000)
        else:
            settings.beginGroup("LEDS")
            self.AirIcon_1.setStyleSheet("color:" + settings.value('inactivetextcolor',
                                                                   '#555555') + ";background-color:" + settings.value(
                'inactivebgcolor', '#222222'))
            self.AirLabel_1.setStyleSheet("color:" + settings.value('inactivetextcolor',
                                                                    '#555555') + ";background-color:" + settings.value(
                'inactivebgcolor', '#222222'))
            settings.endGroup()
            self.statusAIR1 = False
            self.timerAIR1.stop()

    def updateAIR1Seconds(self):
        self.Air1Seconds += 1
        self.AirLabel_1.setText("Mic\n%d:%02d" % (self.Air1Seconds / 60, self.Air1Seconds % 60))

    def setAIR2(self, action):
        return
        settings = QSettings(QSettings.UserScope, "astrastudio", "OnAirScreen")
        if action:
            self.Air2Seconds = 0
            self.AirLabel_2.setStyleSheet("color: #000000; background-color: #FF0000")
            self.AirIcon_2.setStyleSheet("color: #000000; background-color: #FF0000")
            self.AirLabel_2.setText("Phone\n%d:%02d" % (self.Air2Seconds / 60, self.Air2Seconds % 60))
            self.statusAIR2 = True
            # AIR2 timer
            self.timerAIR2.start(1000)
        else:
            settings.beginGroup("LEDS")
            self.AirIcon_2.setStyleSheet("color:" + settings.value('inactivetextcolor',
                                                                   '#555555') + ";background-color:" + settings.value(
                'inactivebgcolor', '#222222'))
            self.AirLabel_2.setStyleSheet("color:" + settings.value('inactivetextcolor',
                                                                    '#555555') + ";background-color:" + settings.value(
                'inactivebgcolor', '#222222'))
            settings.endGroup()
            self.statusAIR2 = False
            self.timerAIR2.stop()

    def updateAIR2Seconds(self):
        return
        self.Air2Seconds += 1
        self.AirLabel_2.setText("Phone\n%d:%02d" % (self.Air2Seconds / 60, self.Air2Seconds % 60))

    def resetAIR3(self):
        return
        self.timerAIR3.stop()
        self.Air3Seconds = 0
        self.AirLabel_3.setText("Timer\n%d:%02d" % (self.Air3Seconds / 60, self.Air3Seconds % 60))
        if self.statusAIR3 == True:
            self.timerAIR3.start(1000)

    def setAIR3(self, action):
        return
        settings = QSettings(QSettings.UserScope, "astrastudio", "OnAirScreen")
        if action:
            self.AirLabel_3.setStyleSheet("color: #000000; background-color: #FF0000")
            self.AirIcon_3.setStyleSheet("color: #000000; background-color: #FF0000")
            self.AirLabel_3.setText("Timer\n%d:%02d" % (self.Air3Seconds / 60, self.Air3Seconds % 60))
            self.statusAIR3 = True
            # substract initial second on countdown with display update
            if self.radioTimerMode == 1 and self.Air3Seconds > 1:
                self.updateAIR3Seconds()
            # AIR3 timer
            self.timerAIR3.start(1000)
        else:
            settings.beginGroup("LEDS")
            self.AirIcon_3.setStyleSheet("color:" + settings.value('inactivetextcolor',
                                                                   '#555555') + ";background-color:" + settings.value(
                'inactivebgcolor', '#222222'))
            self.AirLabel_3.setStyleSheet("color:" + settings.value('inactivetextcolor',
                                                                    '#555555') + ";background-color:" + settings.value(
                'inactivebgcolor', '#222222'))
            settings.endGroup()
            self.statusAIR3 = False
            self.timerAIR3.stop()

    def startStopAIR3(self):
        return
        if self.statusAIR3 == False:
            self.startAIR3()
        else:
            self.stopAIR3()

    def startAIR3(self):
        return
        self.setAIR3(True)

    def stopAIR3(self):
        return
        self.setAIR3(False)

    def updateAIR3Seconds(self):
        return
        if self.radioTimerMode == 0:  # count up mode
            self.Air3Seconds += 1
        else:
            self.Air3Seconds -= 1
            if self.Air3Seconds < 1:
                self.stopAIR3()
                self.radioTimerMode = 0
        self.AirLabel_3.setText("Timer\n%d:%02d" % (self.Air3Seconds / 60, self.Air3Seconds % 60))

    def resetAIR4(self):
        return
        self.timerAIR4.stop()
        self.Air4Seconds = 0
        self.AirLabel_4.setText("Stream\n%d:%02d" % (self.Air4Seconds / 60, self.Air4Seconds % 60))
        if self.statusAIR4 == True:
            self.timerAIR4.start(1000)

    def setAIR4(self, action):
        return
        settings = QSettings(QSettings.UserScope, "astrastudio", "OnAirScreen")
        if action:
            self.AirLabel_4.setStyleSheet("color: #000000; background-color: #FF0000")
            self.AirIcon_4.setStyleSheet("color: #000000; background-color: #FF0000")
            self.AirLabel_4.setText("Stream\n%d:%02d" % (self.Air4Seconds / 60, self.Air4Seconds % 60))
            self.statusAIR4 = True
            # substract initial second on countdown with display update
            if self.streamTimerMode == 1 and self.Air4Seconds > 1:
                self.updateAIR4Seconds()
            # AIR4 timer
            self.timerAIR4.start(1000)
        else:
            settings.beginGroup("LEDS")
            self.AirIcon_4.setStyleSheet("color:" + settings.value('inactivetextcolor',
                                                                   '#555555') + ";background-color:" + settings.value(
                'inactivebgcolor', '#222222'))
            self.AirLabel_4.setStyleSheet("color:" + settings.value('inactivetextcolor',
                                                                    '#555555') + ";background-color:" + settings.value(
                'inactivebgcolor', '#222222'))
            settings.endGroup()
            self.statusAIR4 = False
            self.timerAIR4.stop()

    def startStopAIR4(self):
        return
        if self.statusAIR4 == False:
            self.startAIR4()
        else:
            self.stopAIR4()

    def startAIR4(self):
        return
        self.setAIR4(True)

    def stopAIR4(self):
        return
        self.setAIR4(False)

    def updateAIR4Seconds(self):
        return
        if self.streamTimerMode == 0:  # count up mode
            self.Air4Seconds += 1
        else:
            self.Air4Seconds -= 1
            if self.Air4Seconds < 1:
                self.stopAIR4()
                self.radioTimerMode = 0
        self.AirLabel_4.setText("Stream\n%d:%02d" % (self.Air4Seconds / 60, self.Air4Seconds % 60))

    def triggerNTPcheck(self):
        print("NTP Check triggered")
        settings = QSettings(QSettings.UserScope, "astrastudio", "OnAirScreen")
        settings.beginGroup("NTP")
        ntpcheck = settings.value('ntpcheck', True, type=bool)
        settings.endGroup()
        if not ntpcheck:
            self.timerNTP.stop()
            return
        else:
            self.timerNTP.stop()
            self.checkNTPOffset.start()
            self.timerNTP.start(60000)


    def setLED1(self, action):
        settings = QSettings(QSettings.UserScope, "astrastudio", "OnAirScreen")
        if action:
            settings.beginGroup("LED1")
            self.buttonLED1.setStyleSheet("color:" + settings.value('activetextcolor',
                                                                    '#FFFFFF') + ";background-color:" + settings.value(
                'activebgcolor', '#FF0000'))
            settings.endGroup()
            self.statusLED1 = True
        else:
            settings.beginGroup("LEDS")
            self.buttonLED1.setStyleSheet("color:" + settings.value('inactivetextcolor',
                                                                    '#555555') + ";background-color:" + settings.value(
                'inactivebgcolor', '#222222'))
            settings.endGroup()
            self.statusLED1 = False

    def setLED2(self, action):
        settings = QSettings(QSettings.UserScope, "astrastudio", "OnAirScreen")
        if action:
            settings.beginGroup("LED2")
            self.buttonLED2.setStyleSheet("color:" + settings.value('activetextcolor',
                                                                    '#FFFFFF') + ";background-color:" + settings.value(
                'activebgcolor', '#DCDC00'))
            settings.endGroup()
            self.statusLED2 = True
        else:
            settings.beginGroup("LEDS")
            self.buttonLED2.setStyleSheet("color:" + settings.value('inactivetextcolor',
                                                                    '#555555') + ";background-color:" + settings.value(
                'inactivebgcolor', '#222222'))
            settings.endGroup()
            self.statusLED2 = False

    def setLED3(self, action):
        settings = QSettings(QSettings.UserScope, "astrastudio", "OnAirScreen")
        if action:
            settings.beginGroup("LED3")
            self.buttonLED3.setStyleSheet("color:" + settings.value('activetextcolor',
                                                                    '#FFFFFF') + ";background-color:" + settings.value(
                'activebgcolor', '#00C8C8'))
            settings.endGroup()
            self.statusLED3 = True
        else:
            settings.beginGroup("LEDS")
            self.buttonLED3.setStyleSheet("color:" + settings.value('inactivetextcolor',
                                                                    '#555555') + ";background-color:" + settings.value(
                'inactivebgcolor', '#222222'))
            settings.endGroup()
            self.statusLED3 = False

    def setLED4(self, action):
        return
        settings = QSettings(QSettings.UserScope, "astrastudio", "OnAirScreen")
        if action:
            settings.beginGroup("LED4")
            self.buttonLED4.setStyleSheet("color:" + settings.value('activetextcolor',
                                                                    '#FFFFFF') + ";background-color:" + settings.value(
                'activebgcolor', '#FF00FF'))
            settings.endGroup()
            self.statusLED4 = True
        else:
            settings.beginGroup("LEDS")
            self.buttonLED4.setStyleSheet("color:" + settings.value('inactivetextcolor',
                                                                    '#555555') + ";background-color:" + settings.value(
                'inactivebgcolor', '#222222'))
            settings.endGroup()
            self.statusLED4 = False

    def setStation(self, text):
        self.labelStation.setText(text)

    def setSlogan(self, text):
        self.labelSlogan.setText(text)

    def setLeftText(self, text):
        self.labelTextLeft.setText(text)

    def setRightText(self, text):
        self.labelTextRight.setText(text)

    def setLED1Text(self, text):
        self.buttonLED1.setText(text)

    def setLED2Text(self, text):
        self.buttonLED2.setText(text)

    def setLED3Text(self, text):
        self.buttonLED3.setText(text)

    def setLED4Text(self, text):
        self.buttonLED4.setText(text)

    def setCurrentSongText(self, text):
        pass
        #self.labelCurrentSong.setText(text)

    def setNewsText(self, text):
        pass
        #self.labelNews.setText(text)

    def setBacktimingSecs(self, value):
        pass
        # self.labelSeconds.setText( str(value) )

    def addWarning(self, text, priority=0):
        pass
        #self.warnings[priority] = text

    def removeWarning(self, priority=0):
        pass
        #self.warnings[priority] = ""

    def processWarnings(self):
        warningAvailable = False

        for warning in self.warnings:
            if len(warning) > 0:
                lastwarning = warning
                warningAvailable = True
        if warningAvailable:
            self.showWarning(lastwarning)
        else:
            self.hideWarning()

    def showWarning(self, text):
        self.labelCurrentSong.hide()
        self.labelNews.hide()
        self.labelWarning.setText(text)
        font = self.labelWarning.font()
        font.setPointSize(45)
        self.labelWarning.setFont(font)
        self.labelWarning.show()

    def hideWarning(self, priority=0):
        return
        self.labelWarning.hide()
        self.labelCurrentSong.show()
        self.labelNews.show()
        self.labelWarning.setText("")
        self.labelWarning.hide()

    def exitOAS(self):
        global app
        app.exit()

    def configClosed(self):
        global app
        # hide mouse cursor if in fullscreen mode
        settings = QSettings(QSettings.UserScope, "astrastudio", "OnAirScreen")
        settings.beginGroup("General")
        if settings.value('fullscreen', True, type=bool):
            app.setOverrideCursor(QCursor(Qt.BlankCursor));
        settings.endGroup()

    def configFinished(self):
        self.restoreSettingsFromConfig()

    def reboot_host(self):
        self.addWarning("SYSTEM REBOOT IN PROGRESS", 2)
        if os.name == "posix":
            cmd = "sudo reboot"
            os.system(cmd)
        if os.name == "nt":
            cmd = "shutdown -f -r -t 0"
            pass

    def shutdown_host(self):
        self.addWarning("SYSTEM SHUTDOWN IN PROGRESS", 2)
        if os.name == "posix":
            cmd = "sudo halt"
            os.system(cmd)
        if os.name == "nt":
            cmd = "shutdown -f -t 0"
            pass

    def closeEvent(self, event):
        self.httpd.stop()


class checkNTPOffsetThread(QThread):

    def __init__(self, oas):
        self.oas = oas
        QThread.__init__(self)

    def __del__(self):
        self.wait()

    def run(self):
        print("entered checkNTPOffsetThread.run")
        settings = QSettings(QSettings.UserScope, "astrastudio", "OnAirScreen")
        settings.beginGroup("NTP")
        ntpserver = str(settings.value('ntpcheckserver', 'pool.ntp.org'))
        settings.endGroup()
        max_deviation = 0.3
        c = ntplib.NTPClient()
        try:
            response = c.request(ntpserver)
            if response.offset > max_deviation or response.offset < -max_deviation:
                print("offset too big: %f while checking %s" % (response.offset, ntpserver))
                self.oas.ntpWarnMessage = "Clock not NTP synchronized: offset too big"
                self.oas.ntpHadWarning = True
            else:
                if self.oas.ntpHadWarning:
                    self.oas.ntpHadWarning = False
        except socket.timeout:
            print("NTP error: timeout while checking NTP %s" % ntpserver)
            self.oas.ntpWarnMessage = "Clock not NTP synchronized"
            self.oas.ntpHadWarning = True
        except socket.gaierror:
            print("NTP error: socket error while checking NTP %s" % ntpserver)
            self.oas.ntpWarnMessage = "Clock not NTP synchronized"
            self.oas.ntpHadWarning = True
        except ntplib.NTPException as e:
            print("NTP error:", e)
            self.oas.ntpWarnMessage = str(e)
            self.oas.ntpHadWarning = True


class HttpDaemon(QThread):
    def run(self):
        settings = QSettings(QSettings.UserScope, "astrastudio", "OnAirScreen")
        settings.beginGroup("Network")
        port = int(settings.value('httpport', 8010))
        settings.endGroup()

        handler = OASHTTPRequestHandler
        self._server = HTTPServer((HOST, port), handler)
        self._server.serve_forever()

    def stop(self):
        self._server.shutdown()
        self._server.socket.close()
        self.wait()


class OASHTTPRequestHandler(BaseHTTPRequestHandler):
    server_version = "OnAirScreen/%s" % versionString

    # handle HEAD request
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

    # handle GET command
    def do_GET(self):
        print(self.path)
        if self.path.startswith('/?cmd'):
            try:
                cmd, message = unquote(str(self.path)[5:]).split("=", 1)
            except ValueError:
                self.send_error(400, 'no command was given')
                return

            if len(message) > 0:
                self.send_response(200)

                # send header first
                self.send_header('Content-type', 'text-html')
                self.end_headers()

                settings = QSettings(QSettings.UserScope, "astrastudio", "OnAirScreen")
                settings.beginGroup("Network")
                port = int(settings.value('udpport', 3310))
                settings.endGroup()

                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.sendto(message.encode(), ("127.0.0.1", port))

                # send file content to client
                self.wfile.write(message.encode())
                self.wfile.write("\n".encode())
                return
            else:
                self.send_error(400, 'no command was given')
                return

        self.send_error(404, 'file not found')


###################################
# App SIGINT handler
###################################
def sigint_handler(*args):
    # Handler for SIGINT signal
    sys.stderr.write("\n")
    QApplication.quit()


###################################
# App Init
###################################
if __name__ == "__main__":
    signal.signal(signal.SIGINT, sigint_handler)
    app = QApplication(sys.argv)
    icon = QIcon()
    icon.addPixmap(QPixmap(":/oas_icon/oas_icon.png"), QIcon.Normal, QIcon.Off)
    app.setWindowIcon(icon)

    timer = QTimer()
    timer.start(100)
    timer.timeout.connect(lambda: None)

    mainscreen = MainScreen()
    mainscreen.setWindowIcon(icon)

    for i in range(1, 5):
        mainscreen.ledLogic(i, False)

    mainscreen.setAIR1(False)
    mainscreen.setAIR2(False)
    mainscreen.setAIR3(False)
    mainscreen.setAIR4(False)

    mainscreen.show()

    sys.exit(app.exec_())
