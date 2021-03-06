#
# auto-pts - The Bluetooth PTS Automation Framework
#
# Copyright (c) 2017, Intel Corporation.
#
# This program is free software; you can redistribute it and/or modify it
# under the terms and conditions of the GNU General Public License,
# version 2, as published by the Free Software Foundation.
#
# This program is distributed in the hope it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for
# more details.
#

import logging
from threading import Lock, Timer, Event

STACK = None


class Property(object):
    def __init__(self, data):
        self._lock = Lock()
        self.data = data

    def __get__(self, instance, owner):
        with self._lock:
            return getattr(instance, self.data)

    def __set__(self, instance, value):
        with self._lock:
            setattr(instance, self.data, value)


def timeout_cb(flag):
    flag.clear()


class Gap:
    def __init__(self, name, manufacturer_data):
        self.name = name
        self.manufacturer_data = manufacturer_data

        # If disconnected - None
        # If connected - remote address tuple (addr, addr_type)
        self.connected = Property(None)
        self.current_settings = Property({
            "Powered": False,
            "Connectable": False,
            "Fast Connectable": False,
            "Discoverable": False,
            "Bondable": False,
            "Link Level Security": False,  # Link Level Security (Sec. mode 3)
            "SSP": False,  # Secure Simple Pairing
            "BREDR": False,  # Basic Rate/Enhanced Data Rate
            "HS": False,  # High Speed
            "LE": False,  # Low Energy
            "Advertising": False,
            "SC": False,  # Secure Connections
            "Debug Keys": False,
            "Privacy": False,
            "Controller Configuration": False,
            "Static Address": False,
        })
        self.iut_bd_addr = Property({
            "address": None,
            "type": None,
        })
        self.discoverying = Property(False)
        self.found_devices = Property([])  # List of found devices

        self.passkey = Property(None)

    def wait_for_connection(self, timeout):
        if self.is_connected():
            return True

        flag = Event()
        flag.set()

        t = Timer(timeout, timeout_cb, [flag])
        t.start()

        while flag.is_set():
            if self.is_connected():
                t.cancel()
                return True

        return False

    def wait_for_disconnection(self, timeout):
        if not self.is_connected():
            return True

        flag = Event()
        flag.set()

        t = Timer(timeout, timeout_cb, [flag])
        t.start()

        while flag.is_set():
            if not self.is_connected():
                t.cancel()
                return True

        return False

    def is_connected(self):
        return False if (self.connected.data is None) else True

    def current_settings_set(self, key):
        if key in self.current_settings.data:
            self.current_settings.data[key] = True
        else:
            logging.error("%s %s not in current_settings",
                          self.current_settings_set.__name__, key)

    def current_settings_clear(self, key):
        if key in self.current_settings.data:
            self.current_settings.data[key] = False
        else:
            logging.error("%s %s not in current_settings",
                          self.current_settings_clear.__name__, key)

    def current_settings_get(self, key):
        if key in self.current_settings.data:
            return self.current_settings.data[key]
        else:
            logging.error("%s %s not in current_settings",
                          self.current_settings_get.__name__, key)
            return False

    def iut_addr_get_str(self):
        return str(self.iut_bd_addr.data["address"])

    def iut_addr_set(self, addr, addr_type):
        self.iut_bd_addr.data["address"] = addr
        self.iut_bd_addr.data["type"] = addr_type

    def iut_addr_is_random(self):
        # FIXME: Do not use hard-coded 0x01 <-> le_random
        return True if self.iut_bd_addr.data["type"] == 0x01 else False

    def iut_has_privacy(self):
        return self.current_settings_get("Privacy")

    def reset_discovery(self):
        self.discoverying.data = True
        self.found_devices.data = []

    def get_passkey(self, timeout=5):
        if self.passkey.data is None:
            flag = Event()
            flag.set()

            t = Timer(timeout, timeout_cb, [flag])
            t.start()

            while flag.is_set():
                if self.passkey.data:
                    t.cancel()
                    break

        return self.passkey.data


class Mesh:
    def __init__(self, uuid, oob, output_size, output_actions, input_size,
                 input_actions, crpl_size):

        # init data
        self.dev_uuid = uuid
        self.static_auth = oob
        self.output_size = output_size
        self.output_actions = output_actions
        self.input_size = input_size
        self.input_actions = input_actions
        self.crpl_size = crpl_size

        self.oob_action = Property(None)
        self.oob_data = Property(None)
        self.is_provisioned = Property(False)
        self.is_initialized = False
        self.last_seen_prov_link_state = Property(None)
        self.prov_invalid_bearer_rcv = Property(False)

        # provision node data
        self.net_key = '0123456789abcdef0123456789abcdef'
        self.net_key_idx = 0x0000
        self.flags = 0x00
        self.iv_idx = 0x00000000
        self.seq_num = 0x00000000
        self.addr = 0x0b0c
        self.dev_key = '0123456789abcdef0123456789abcdef'

        # health model data
        self.health_test_id = Property(0x00)
        self.health_current_faults = Property(None)
        self.health_registered_faults = Property(None)

        # vendor model data
        self.vendor_model_id = '0002'

        # IV update
        self.iv_update_timeout = Property(120)
        self.is_iv_test_mode_enabled = Property(False)
        self.iv_test_mode_autoinit = False

        # Network
        # net_recv_ev_store - store data for further verification
        self.net_recv_ev_store = Property(False)
        # net_recv_ev_data (ttl, ctl, src, dst, payload)
        self.net_recv_ev_data = Property(None)
        self.incomp_timer_exp = Property(False)

        #LPN
        self.lpn_subscriptions = []

        # Node Identity
        self.proxy_identity = False

    def proxy_identity_enable(self):
        self.proxy_identity = True

    def wait_for_incomp_timer_exp(self, timeout):
        if self.incomp_timer_exp.data:
            return True

        flag = Event()
        flag.set()

        t = Timer(timeout, timeout_cb, [flag])
        t.start()

        while flag.is_set():
            if self.incomp_timer_exp.data:
                t.cancel()
                return True

        return False


class Synch:
    def __init__(self, set_pending_response_func, clear_pending_responses_func):
        self._synch_table = []
        self._pending_responses = {}
        self._set_pending_response_func = set_pending_response_func
        self._clear_pending_responses_func = clear_pending_responses_func

    def add_synch_element(self, elem):
        wid_dict = {}

        """Initialize element with empty description array, tester don't know
        which wid happens earlier"""
        for e in elem:
            tc_name = e[0]
            wid = e[1]

            wid_dict[tc_name] = [wid, None]

        self._synch_table.append(wid_dict)

    def perform_synch(self, wid, tc_name, description):
        action_wids = []

        for elem in self._synch_table:
            # i[value][description]
            descs = [i[1][1] for i in elem.iteritems()]

            e_wid = elem[tc_name][0]
            if tc_name in elem and e_wid == wid:
                # Not all pending wids are already waiting = schedule also me
                if descs.count(None) > (len(descs) - 1):
                    elem[tc_name][1] = description
                    continue

                # Pack all pending actions to be performed right out of synch
                for inst in elem:
                    if inst == tc_name:
                        continue

                    i_wid = elem[inst][0]
                    i_desc = elem[inst][1]
                    action_wids.append((i_wid, i_desc, inst,
                                       self._set_pending_response_func))

                self._synch_table.remove(elem)

                return action_wids

        return None

    def is_required_synch(self, tc_name, wid):
        for elem in self._synch_table:
            if tc_name in elem:
                e_wid = elem[tc_name][0]

                if e_wid == wid:
                    return True

        return False

    def prepare_pending_response(self, test_case_name, response):
        self._pending_responses[test_case_name] = response

    def set_pending_responses_if_any(self):
        for rsp in self._pending_responses.iteritems():
            self._set_pending_response_func(rsp)

        self._pending_responses = {}

    def cancel_synch(self):
        self._synch_table = []
        self._pending_responses = {}
        self._clear_pending_responses_func()


class Stack:
    def __init__(self):
        self.gap = None
        self.mesh = None
        self.synch = None

    def gap_init(self, name=None, manufacturer_data=None):
        self.gap = Gap(name, manufacturer_data)

    def mesh_init(self, uuid, oob, output_size, output_actions, input_size,
                  input_actions, crpl_size):
        self.mesh = Mesh(uuid, oob, output_size, output_actions, input_size,
                         input_actions, crpl_size)

    def synch_init(self, set_pending_response_func,
                   clear_pending_responses_func):
        self.synch = Synch(set_pending_response_func,
                           clear_pending_responses_func)

    def cleanup(self):
        if self.gap:
            self.gap_init(self.gap.name, self.gap.manufacturer_data)

        if self.mesh:
            self.mesh_init(self.mesh.dev_uuid, self.mesh.static_auth,
                           self.mesh.output_size, self.mesh.output_actions,
                           self.mesh.input_size, self.mesh.input_actions,
                           self.mesh.crpl_size)

        if self.synch:
            self.synch.cancel_synch()


def init_stack():
    global STACK

    STACK = Stack()


def cleanup_stack():
    global STACK

    STACK = None


def get_stack():
    return STACK
