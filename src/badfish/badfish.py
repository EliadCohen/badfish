#! /usr/bin/env python

import json
import re
import requests
import sys
import time
import warnings
import yaml

warnings.filterwarnings("ignore")


class Badfish:
    def __init__(self, _host, _username, _password):
        self.host = _host
        self.username = _username
        self.password = _password

    def get_bios_boot_mode(self):
        _response = requests.get(
            "https://%s/redfish/v1/Systems/System.Embedded.1/Bios" % self.host,
            verify=False,
            auth=(self.username, self.password)
        )
        data = _response.json()
        return data[u"Attributes"]["BootMode"]

    @staticmethod
    def get_boot_seq(bios_boot_mode):
        if bios_boot_mode == "Uefi":
            return "UefiBootSeq"
        else:
            return "BootSeq"

    def get_boot_devices(self, _boot_seq):
        _response = requests.get(
            "https://%s/redfish/v1/Systems/System.Embedded.1/BootSources" % self.host,
            verify=False,
            auth=(self.username, self.password),
        )
        data = _response.json()
        return data[u"Attributes"][_boot_seq]

    def change_boot_order(self, interfaces_path, host_type):
        with open(interfaces_path, "r") as f:
            try:
                definitions = yaml.safe_load(f)
            except yaml.YAMLError as ex:
                print(ex)
                sys.exit(1)

        host_model = self.host.split(".")[0].split("-")[-1]
        interfaces = definitions["%s_%s_interfaces" % (host_type, host_model)].split(",")

        bios_boot_mode = self.get_bios_boot_mode()
        boot_seq = self.get_boot_seq(bios_boot_mode)
        boot_devices = self.get_boot_devices(boot_seq)
        change = False
        for i in range(len(interfaces)):
            for device in boot_devices:
                if interfaces[i] == device[u"Name"]:
                    if device[u"Index"] != i:
                        device[u"Index"] = i
                        change = True
                    break

        if change:
            url = "https://%s/redfish/v1/Systems/System.Embedded.1/BootSources/Settings" % self.host
            payload = {"Attributes": {boot_seq: boot_devices}}
            headers = {"content-type": "application/json"}
            response = requests.patch(
                url, data=json.dumps(payload), headers=headers, verify=False, auth=(self.username, self.password)
            )
            if response.status_code == 200:
                print("- PASS: PATCH command passed to update boot order")
            else:
                print("- FAIL: There was something wrong with your request")
        else:
            print("- WARNING: No changes were made since the boot order already matches the requested.")
            sys.exit()
        return

    def set_next_boot_pxe(self):
        _url = "https://%s/redfish/v1/Systems/System.Embedded.1" % self.host
        _payload = {"Boot": {"BootSourceOverrideTarget": "Pxe"}}
        _headers = {"content-type": "application/json"}
        _response = requests.patch(
            _url, data=json.dumps(_payload), headers=_headers, verify=False, auth=(self.username, self.password)
        )
        time.sleep(5)
        if _response.status_code == 200:
            print('- PASS: PATCH command passed to set next boot onetime boot device to: "%s"' % "Pxe")
        else:
            print("- FAIL: Command failed, error code is %s" % _response.status_code)
            detail_message = str(_response.__dict__)
            print(detail_message)
            sys.exit()
        return

    def clear_job_queue(self, _job_queue):
        _url = "https://%s/redfish/v1/Managers/iDRAC.Embedded.1/Jobs" % self.host
        _headers = {'content-type': 'application/json'}
        if not _job_queue:
            print("\n- WARNING, job queue already cleared for iDRAC %s, DELETE command will not execute" % self.host)
            return
        print("\n- WARNING, clearing job queue for job IDs: %s\n" % _job_queue)
        for _job in _job_queue:
            job = _job.strip("'")
            url = '%s/%s' % (_url, job)
            requests.delete(url, headers=_headers, verify=False, auth=(self.username, self.password))
        job_queue = self.get_job_queue()
        if not job_queue:
            print("- PASS, job queue for iDRAC %s successfully cleared" % self.host)
        else:
            print("- FAIL, job queue not cleared, current job queue contains jobs: %s" % job_queue)
            sys.exit()
        return

    def get_job_queue(self):
        _url = "https://%s/redfish/v1/Managers/iDRAC.Embedded.1/Jobs" % self.host
        _response = requests.get(_url, auth=(self.username, self.password), verify=False)
        data = _response.json()
        data = str(data)
        job_queue = re.findall("JID_.+?'", data)
        return job_queue

    def create_bios_config_job(self):
        _url = "https://%s/redfish/v1/Managers/iDRAC.Embedded.1/Jobs" % self.host
        _payload = {"TargetSettingsURI": "/redfish/v1/Systems/System.Embedded.1/Bios/Settings"}
        _headers = {"content-type": "application/json"}
        _response = requests.post(
            _url, data=json.dumps(_payload), headers=_headers, verify=False, auth=(self.username, self.password)
        )
        status_code = _response.status_code

        if status_code == 200:
            print("- PASS: POST command passed to create target config job, status code 200 returned.")
        else:
            print("- FAIL: POST command failed to create BIOS config job, status code is %s" % status_code)
            detail_message = str(_response.__dict__)
            print(detail_message)
            sys.exit()
        convert_to_string = str(_response.__dict__)
        job_id_search = re.search("JID_.+?,", convert_to_string).group()
        _job_id = re.sub("[,']", "", job_id_search)
        print("- INFO: %s job ID successfully created" % _job_id)
        return _job_id

    def get_job_status(self, _job_id):
        while True:
            req = requests.get(
                "https://%s/redfish/v1/Managers/iDRAC.Embedded.1/Jobs/%s" % (self.host, _job_id),
                verify=False,
                auth=(self.username, self.password),
            )
            status_code = req.status_code
            if status_code == 200:
                print("- PASS: Command passed to check job status, code 200 returned")
                time.sleep(10)
            else:
                print("- FAIL: Command failed to check job status, return code is %s" % status_code)
                print("    Extended Info Message: {0}".format(req.json()))
                sys.exit()
            data = req.json()
            if data[u"Message"] == "Task successfully scheduled.":
                print("- PASS: job id %s successfully scheduled" % _job_id)
                break
            else:
                print("- WARNING: JobStatus not scheduled, current status is: %s" % data[u"Message"])

    def reboot_server(self):
        _response = requests.get(
            "https://%s/redfish/v1/Systems/System.Embedded.1/" % self.host,
            verify=False,
            auth=(self.username, self.password)
        )
        data = _response.json()
        print("- WARNING: Current server power state is: %s" % data[u"PowerState"])
        if data[u"PowerState"] == "On":
            _url = "https://%s/redfish/v1/Systems/System.Embedded.1/Actions/ComputerSystem.Reset" % self.host
            _payload = {"ResetType": "GracefulRestart"}
            _headers = {"content-type": "application/json"}
            _response = requests.post(
                _url, data=json.dumps(_payload), headers=_headers, verify=False, auth=(self.username, self.password)
            )
            status_code = _response.status_code
            if status_code == 204:
                print("- PASS: Command passed to gracefully restart server, code return is %s" % status_code)
                time.sleep(3)
            else:
                print("- FAIL: Command failed to gracefully restart server, status code is: %s" % status_code)
                print("    Extended Info Message: {0}".format(_response.json()))
                sys.exit()
            count = 0
            while True:
                _response = requests.get(
                    "https://%s/redfish/v1/Systems/System.Embedded.1/" % self.host, verify=False,
                    auth=(self.username, self.password)
                )
                data = _response.json()
                if data[u"PowerState"] == "Off":
                    print("- PASS: GET command passed to verify server is in OFF state")
                    break
                elif count == 20:
                    print("- WARNING: unable to graceful shutdown the server, will perform forced shutdown now")
                    _url = "https://%s/redfish/v1/Systems/System.Embedded.1/Actions/ComputerSystem.Reset" % self.host
                    _payload = {"ResetType": "ForceOff"}
                    _headers = {"content-type": "application/json"}
                    _response = requests.post(
                        _url, data=json.dumps(_payload),
                        headers=_headers,
                        verify=False,
                        auth=(self.username, self.password)
                    )
                    status_code = _response.status_code
                    if status_code == 204:
                        print("- PASS: Command passed to forcefully power OFF server, code return is %s" % status_code)
                        time.sleep(10)
                    else:
                        print("- FAIL, Command failed to gracefully power OFF server, status code is: %s" % status_code)
                        print("    Extended Info Message: {0}".format(_response.json()))
                        sys.exit()

                else:
                    time.sleep(1)
                    count += 1
                    continue

            _payload = {"ResetType": "On"}
            _headers = {"content-type": "application/json"}
            _response = requests.post(
                _url, data=json.dumps(_payload), headers=_headers, verify=False, auth=(self.username, self.password)
            )
            status_code = _response.status_code
            if status_code == 204:
                print("- PASS: Command passed to power ON server, code return is %s" % status_code)
            else:
                print("- FAIL: Command failed to power ON server, status code is: %s" % status_code)
                print("    Extended Info Message: {0}".format(_response.json()))
                sys.exit()
        elif data[u"PowerState"] == "Off":
            _url = "https://%s/redfish/v1/Systems/System.Embedded.1/Actions/ComputerSystem.Reset" % self.host
            _payload = {"ResetType": "On"}
            _headers = {"content-type": "application/json"}
            _response = requests.post(
                _url, data=json.dumps(_payload), headers=_headers, verify=False, auth=(self.username, self.password)
            )
            status_code = _response.status_code
            if status_code == 204:
                print("- PASS: Command passed to power ON server, code return is %s" % status_code)
            else:
                print("- FAIL: Command failed to power ON server, status code is: %s" % status_code)
                print("    Extended Info Message: {0}".format(_response.json()))
                sys.exit()
        else:
            print("- FAIL: unable to get current server power state to perform either reboot or power on")
            sys.exit()