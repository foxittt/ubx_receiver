#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Author: 
Marcus Voß (m.voss@laposte.net)

Description:
Library for communication with the ublox F9T receiver

License:
MIT
"""
import serial
import logging

ubx_msg_dict = {
    # lookup table for ubx messages
    b"\x01": {
        "classname": "NAV",

    },
    b"\x02": {
        "classname": "RXM",
        b"\x14": "MEASX",
        b"\x41": "PMREQ",
        b"\x15": "RAWX",
        b"\x59": "RLM",
        b"\x13": "SFRBX"
    },
    b"\x04": {
        "classname": "INF",

    },
    b"\x05":  {
        "classname": "ACK",
        b"\x00": "NAK",
        b"\x01": "ACK"
    },
    b"\x06":  {
        "classname": "CFG",

    },
    b"\x09":  {
        "classname": "UPD",

    },
    b"\x0A":  {
        "classname": "MON",

    },
    b"\x0D":  {
        "classname": "TIM",

    },
    b"\x13":  {
        "classname": "MGA",

    },
    b"\x21":  {
        "classname": "LOG",

    },
    b"\x27":  {
        "classname": "SEC",

    },
}


def fletcher_checksum(msg):
    '''8-Bit Fletcher Algorithm modelled after ublox documentation. Returns checksum'''
    # print(f"computing checksum of {msg}")
    CK_A = CK_B = 0
    # start at class (byte 2)
    for i in range(2, len(msg)):
        CK_A += msg[i]
        CK_B += CK_A
    # mask to 8bit uint
    CK_A &= 0xFF
    CK_B &= 0xFF
    # convert to bytes
    CK_A = bytes([CK_A])
    CK_B = bytes([CK_B])
    # print("CK_A", CK_A)
    # print("CK_B", CK_B)
    return CK_A+CK_B


def safeget(dict, *keys):
    '''safe getmethod for nested dicts'''
    # print(f"keys:{keys}")
    for key in keys:
        try:
            dict = dict[key]
        except KeyError:
            return None
    return dict


ubx_config_dict = {
    "GLL_UART1": b'\xCA\x00\x91\x20',
    "GSV_UART1": b'\xC5\x00\x91\x20',
    "GGA_UART1": b'\xbb\x00\x91\x20',
    "GSA_UART1": b'\xC0\x00\x91\x20',
    "GST_UART1": b'\xD4\x00\x91\x20',
    "RMC_UART1": b'\xAC\x00\x91\x20',
    "ZDA_UART1": b'\xD9\x00\x91\x20',
    "VTG_UART1": b'\xB1\x00\x91\x20',
    "RAWX_UART1": b'\xA5\x02\x91\x20',
    "SFRBX_UART1": b'\x32\x02\x91\x20',
    "NAVSPG-DYNMODEL": b'\x21\x00\x11\x20'

}


class UBX_receiver:
    serialport = None
    baudrate = None
    port = None
    current_parse = None
    parse_data = []
    last_byte = None

    def __init__(self, port, baudrate):
        self.serialport = port
        self.baudrate = baudrate
        self.connect()

    def __del__(self):
        if self.port != None:
            self.port.close()

    def connect(self):
        if self.port != None:
            try:
                self.port.close()
            except Exception as err:
                print(f"lol this should not happen: {err}")
        logging.info(f"connectiong to {self.serialport}:{self.baudrate}")
        self.port = serial.Serial(
            self.serialport, self.baudrate)  # open serial port

    def reset_data(self):
        self.parse_data = []
        self.current_parse = None

    def parse(self):

        while (self.port.in_waiting > 0):  # non blocking read
            logging.debug(f"mode: {self.current_parse} data {self.parse_data}")
            byte = self.port.read()
            logging.debug(f"byte: {byte} lastbyte: {self.last_byte}")
            if (self.current_parse == None):
                if (byte == b'\x62' and self.last_byte == b'\xB5'):
                    self.current_parse = "UBX"
                    self.parse_data = []
                    logging.debug("received UBX start frame")
                elif (byte == b'G' and self.last_byte == b'$'):
                    self.current_parse = "NMEA"
                    self.parse_data = [b'G']
                    logging.debug("received NMEA start frame")
                self.last_byte = byte
                return

            if (self.current_parse == "UBX"):
                self.parse_data.append(byte)
                if (len(self.parse_data) >= 4):
                    length = int.from_bytes(
                        self.parse_data[2] + self.parse_data[3], 'little')
                    ubx_length = length
                    if (len(self.parse_data) == (ubx_length + 6)):
                        data_string = b''.join(self.parse_data)
                        try:
                            message = UBX_message(data_string)
                        except ValueError as err:
                            message = f"invalid ubx-message! ({err})"
                        self.reset_data()
                        return message

            if (self.current_parse == "NMEA"):
                self.parse_data.append(byte)
                if (byte == b'\n'):
                    data_string = b''.join(self.parse_data)
                    try:
                        message = NMEA_message(data_string)
                    except ValueError:
                        message = "invalid nmea-message!"
                    self.reset_data()
                    return message

    def ubx_msg(self, c, id, payload):
        '''generate a valid ubx message with checksum'''
        sync = b'\xB5\x62'
        print("payload", list(payload))
        length = bytes([len(payload)])
        if (len(length) < 2):
            length += b'\x00'
        msg = sync+c+id+length+payload
        checksum = fletcher_checksum(msg)
        msg += checksum
        return msg

    def reset(self):
        '''force-reset the receiver. This will reset all configuration to default'''
        msg = self.ubx_msg(b'\x06', b'\x04', b'\x00\x00\x00\x00')
        print(f"msg:{msg}")
        self.port.write(msg)

    def set_val(self, *args):
        '''set ubx config values'''
        logging.debug(f"set val:{args}")
        if (len(args) % 2 != 0):
            raise ValueError("Number of arguments must be even!")
        c = b'\x06'
        id = b'\x8A'
        payload = b'\x00\x01\x00\x00'
        for arg in args:
            if (type(arg) == int):
                arg = bytes([arg])
            elif (type(arg) == str):
                arg = ubx_config_dict[arg]
            payload += arg
        msg = self.ubx_msg(c, id, payload)
        # send the constructed ubx message to the receiver
        print(f"msg:{msg}")
        self.port.write(msg)
        logging.info("payload written")

    def ubx_config_disable(self, *args):
        '''disable ubx messages (multiple strings as argument)'''
        vals = []
        for arg in args:
            vals.append(ubx_config_dict[arg])
            vals.append(b'\x00')
        self.set_val(*vals)

    def ubx_config_disable_all(self):
        '''disable all messages defined in config'''
        self.ubx_config_disable(*list(ubx_config_dict.keys()))

    def ubx_config_enable(self, *args):
        '''enable ubx messages (multiple strings as argument)'''
        vals = []
        for arg in args:
            vals.append(ubx_config_dict[arg])
            vals.append(b"\x01")
        self.set_val(*vals)

    def ubx_config_enable_all(self):
        '''disable all messages defined in config'''
        self.ubx_config_enable(*list(ubx_config_dict.keys()))


class UBX_message:
    correct = False
    sync = b'\xB5\x62'
    raw_data = None
    ubx_class = None
    ubx_class_name = None
    ubx_id = None
    ubx_id_name = None
    length = None
    payload = None
    checksum = None

    def __init__(self, data):
        if type(data) == list:
            data = bytes(data)
        if data[:2] == self.sync:
            data = data[2:]
        self.raw_data = self.sync+data

        checksum = fletcher_checksum(self.raw_data[:-2])
        if list(checksum) != list(data[-2:]):
            raise ValueError(
                f"wrong checksum {list(checksum)} is not {list(data[-2:])}")
        else:
            self.correct = True
            self.ubx_class = data[0]
            self.ubx_class_name = safeget(ubx_msg_dict, bytes(
                [self.ubx_class]), "classname") or "unknown"
            self.ubx_id = data[1]
            self.ubx_id_name = safeget(ubx_msg_dict, bytes(
                [self.ubx_class]), bytes([self.ubx_id])) or "unknown"
            self.length = int.from_bytes(data[2:4], 'little')
            self.payload = data[4:-2]
            if (len(self.payload) != self.length):
                raise ValueError(
                    f"payload length is incorrect ({len(self.payload)} != {self.length})")

    def __str__(self):
        return f"ubx message (class:{self.ubx_class_name} id:{self.ubx_id_name} payload_length: {self.length})"


class NMEA_message:
    correct = False
    data = None
    raw_data = None
    talker_id = None
    msg_type = None
    checksum = None

    def __init__(self, data):
        if type(data) != str:
            data = data.decode()
        self.raw_data = data
        self.talker_id = data[:2]
        self.msg_type = data[2:5]
        self.data = data[6:-5]
        nmea_data, chk = data.split('*')
        checksum = 0
        for s in nmea_data:  # NMEA checksum is XOR sum of all characters between $ and *
            checksum ^= ord(s)
        checksum = hex(checksum)
        self.checksum = chk[:-2]
        parsed_checksum = hex(int(self.checksum, 16))
        if checksum != parsed_checksum:
            raise ValueError(f"checksum {checksum} is not {parsed_checksum}")

    def __str__(self):
        return f"NMEA message (talkerID:{self.talker_id} type:{self.msg_type} data: {self.data} checksum {self.checksum})"
