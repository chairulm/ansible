#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# (c) 2017, Ansible by Red Hat, inc
#
# This file is part of Ansible by Red Hat
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
#

from __future__ import absolute_import, division, print_function

from copy import deepcopy
from time import sleep

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.network_common import conditional, \
    remove_default_spec

from ansible.module_utils.mlnxos import get_interfaces_config
from ansible.module_utils.mlnxos import mlnxos_argument_spec
from ansible.modules.network.mlnxos import BaseMlnxosApp


ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'network'}


DOCUMENTATION = """
---
module: mlnxos_interface
version_added: "2.5"
author: "Samer Deeb (@samerd)"
short_description: Manage Interface on MLNX-OS network devices
description:
  - This module provides declarative management of Interfaces
    on MLNX-OS network devices.
notes:
  -
options:
  name:
    description:
      - Name of the Interface.
    required: true
  description:
    description:
      - Description of Interface.
  enabled:
    description:
      - Interface link status.
  speed:
    description:
      - Interface link speed.
  mtu:
    description:
      - Maximum size of transmit packet.
  aggregate:
    description: List of Interfaces definitions.
  delay:
    description:
      - Time in seconds to wait before checking for the operational state on remote
        device. This wait is applicable for operational state argument which are
        I(state) with values C(up)/C(down), I(tx_rate) and I(rx_rate).
    default: 10
  state:
    description:
      - State of the Interface configuration, C(up) means present and
        operationally up and C(down) means present and operationally C(down)
    default: present
    choices: ['present', 'absent', 'up', 'down']
"""

EXAMPLES = """
- name: configure interface
  mlnxos_interface:
      name: ethernet 1/2
      description: test-interface
      speed: 100 GB
      mtu: 512

- name: make interface up
  mlnxos_interface:
    name: ethernet 1/2
    enabled: True

- name: make interface down
  mlnxos_interface:
    name: ethernet 1/2
    enabled: False

- name: Check intent arguments
  mlnxos_interface:
    name: ethernet 1/2
    state: up

- name: Config + intent
  mlnxos_interface:
    name: ethernet 1/2
    enabled: False
    state: down
"""

RETURN = """
commands:
  description: The list of configuration mode commands to send to the device.
  returned: always, except for the platforms that use Netconf transport to manage the device.
  type: list
  sample:
  - interface ethernet 1/2
  - description test-interface
  - mtu 512
"""


class MlnxosInterfaceApp(BaseMlnxosApp):

    @classmethod
    def _get_element_spec(cls):
        return dict(
            name=dict(),
            description=dict(),
            speed=dict(),
            mtu=dict(),
            enabled=dict(default=True, type='bool'),
            delay=dict(default=10, type='int'),
            state=dict(default='present',
                       choices=['present', 'absent', 'up', 'down'])
        )

    @classmethod
    def _get_aggregate_spec(cls, element_spec):
        aggregate_spec = deepcopy(element_spec)
        aggregate_spec['name'] = dict(required=True)

        # remove default in aggregate spec, to handle common arguments
        remove_default_spec(aggregate_spec)
        return aggregate_spec

    def init_module(self):
        """ main entry point for module execution
        """
        element_spec = self._get_element_spec()
        aggregate_spec = self._get_aggregate_spec(element_spec)
        if aggregate_spec:
            argument_spec = dict(
                aggregate=dict(type='list', elements='dict',
                               options=aggregate_spec),
            )
        else:
            argument_spec = dict()
        argument_spec.update(element_spec)
        argument_spec.update(mlnxos_argument_spec)
        required_one_of = [['name', 'aggregate']]
        mutually_exclusive = [['name', 'aggregate']]
        self._module = AnsibleModule(
            argument_spec=argument_spec,
            required_one_of=required_one_of,
            mutually_exclusive=mutually_exclusive,
            supports_check_mode=True)

    def get_required_config(self):
        self._required_config = list()
        module_params = self._module.params
        aggregate = module_params.get('aggregate')
        if aggregate:
            for item in aggregate:
                for key in item:
                    if item.get(key) is None:
                        item[key] = module_params[key]

                self.validate_param_values(item, item)
                d = item.copy()

                if d['enabled']:
                    d['disable'] = False
                else:
                    d['disable'] = True

                self._required_config.append(d)

        else:
            params = {
                'name': module_params['name'],
                'description': module_params['description'],
                'speed': module_params['speed'],
                'mtu': module_params['mtu'],
                'state': module_params['state'],
                'delay': module_params['delay'],
            }

            self.validate_param_values(params)
            if module_params['enabled']:
                params.update({'disable': False})
            else:
                params.update({'disable': True})

            self._required_config.append(params)

    @classmethod
    def get_if_name(cls, item):
        header = cls.get_config_attr(item, "header")
        return header.replace("Eth", "ethernet ")

    @classmethod
    def get_admin_state(cls, item):
        admin_state = cls.get_config_attr(item, "Admin state")
        return str(admin_state).lower() == "enabled"

    @classmethod
    def get_oper_state(cls, item):
        oper_state = cls.get_config_attr(item, "Operational state")
        return str(oper_state).lower()

    @classmethod
    def search_obj_in_list(cls, name, lst):
        for o in lst:
            if o['name'] == name:
                return o

    def add_command_to_interface(self, interface, cmd):
        if interface not in self._commands:
            self._commands.append(interface)
        self._commands.append(cmd)

    def _create_if_data(self, item):
        return {
            'name': self.get_if_name(item),
            'description': self.get_config_attr(item, 'Description'),
            'speed': self.get_config_attr(item, 'Actual speed'),
            'mtu': self.get_mtu(item),
            'disable': not self.get_admin_state(item),
            'state': self.get_oper_state(item)
        }

    def load_current_config(self):
        self._current_config = list()
        config = get_interfaces_config(self._module, "ethernet")

        for item in config:
            self._current_config.append(self._create_if_data(item))

    def generate_commands(self):
        for req_if in self._required_config:
            name = req_if['name']
            curr_if = self.search_obj_in_list(
                name, self._current_config)
            if not curr_if:
                self._module.fail_json(
                    msg='could not find interface %s' % name)
                continue
            self._generate_if_commands(name, req_if, curr_if)

    def _generate_if_commands(self, name, req_if, curr_if):
        args = ('speed', 'description', 'mtu')
        disable = req_if['disable']
        state = req_if['state']

        interface = 'interface ' + name

        if state == 'absent':
            curr_state = curr_if['state']
            if curr_state == "up":
                self._commands.append('no ' + interface)

        else:
            for item in args:
                candidate = req_if.get(item)
                running = curr_if.get(item)
                if candidate != running:
                    if candidate:
                        cmd = item + ' ' + str(candidate)
                        if item == "mtu":
                            cmd = cmd + ' ' + 'force'
                        self.add_command_to_interface(interface, cmd)

            if disable and not curr_if.get('disable', False):
                self.add_command_to_interface(interface, 'shutdown')
            elif not disable and curr_if.get('disable', False):
                self.add_command_to_interface(interface, 'no shutdown')

    def check_declarative_intent_params(self, result):
        failed_conditions = []
        for req_if in self._required_config:
            want_state = req_if.get('state')
            name = req_if['name']
            if want_state not in ('up', 'down'):
                continue

            if result['changed']:
                sleep(req_if['delay'])
            curr_if = self.search_obj_in_list(
                name, self._current_config)
            curr_state = curr_if['state']
            if curr_state is None or not \
                    conditional(want_state, curr_state.strip()):
                failed_conditions.append('state ' + 'eq(%s)' % want_state)
        return failed_conditions


if __name__ == '__main__':
    MlnxosInterfaceApp.main()
