import os
import json
from urllib.parse import urljoin

import requests

from logger import log

CONFIG_PATH = '/data/options.json'


class HassClient:
    def __init__(self) -> None:
        self.has_api = False
        self.url = None
        self.token = None
        self.options = dict()
        self.http = requests.Session()
        self._get_token()
        self._load_options()

    def _get_token(self) -> None:
        self.token = os.getenv("SUPERVISOR_TOKEN")
        log.debug(f"Got HA supervisor token: {self.token}")
        if self.token:
            self.has_api = True
            self.url = "http://supervisor"
            self.http.headers.update({
                f"Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/json"
                })

    def _load_options(self) -> None:
        try:
            with open(CONFIG_PATH, 'r') as f:
                self.options = json.load(f)
            log.info(f"Configuration passed from Home Assistant: {self.options}")
        except IOError:
            log.info(f"Could not read Home Assistant config from {CONFIG_PATH}")

    def _request(self, method: str, uri: str, data = None, raise_for_status: bool = True):
        method = method.upper()
        log.info(f"Calling Home Assistant API: {method} {uri}")
        log.debug(f"Full URL: {urljoin(self.url, uri)}")
        log.debug(f"Headers:  {self.http.headers}")
        log.debug(f"Data:     {data}")
        response = self.http.request(method, urljoin(self.url, uri), data=data)
        if raise_for_status:
            response.raise_for_status()
        log.debug(f"Response from Home Assistant: {response.content}")
        return response.json()

    def get_config(self):
        log.info("Checking Home Assistant configuration")
        return self._request('GET', '/core/api/config')

    def has_abode_integration(self):
        config = self.get_config()
        log.debug(f"Installed components: {config['components']}")
        return 'abode' in config['components']

    def get_states(self):
        log.info("Getting current state of entities")
        return self._request('GET', '/core/api/states')
    
    def get_abode_cams(self):
        def __is_abode_cam(state) -> bool:
            if not state['entity_id'].startswith('camera.'):
                return False
            elif not 'device_id' in state['attributes']:
                return False
            elif not state['attributes']['device_id'].startswith('XF:'):
                return False
            elif not 'device_type' in state['attributes']:
                return False
            elif not state['attributes']['device_type'].startswith('Abode Cam'):
                return False
            return True
        states = self.get_states()
        return [s for s in states if __is_abode_cam(s)]
