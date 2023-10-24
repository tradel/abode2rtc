#! /usr/bin/env python3

import json
import subprocess
import tempfile
from urllib.parse import parse_qs, urljoin, urlparse
from dataclasses import dataclass

# import arrow
import requests

from logger import log, go2rtc_log
from utils import generate_uuid
import go2rtc
from hass import HassClient

BASE_URL = 'https://my.goabode.com'
CAMERA_TYPE = 'device_type.mini_cam'
ERR_CAMERA_OFFLINE = 2604


go2rtc_path = go2rtc.find_or_download()

hass = HassClient()
has_abode = hass.has_abode_integration()
log.info(f"Home Assistant {'does' if has_abode else 'does not'} have the Abode integration installed")
abode_cameras = hass.get_abode_cams()
log.info(f"Found {len(abode_cameras)} Abode cameras in Home Assistant")

if not hass.options['abode_username']:
    raise Exception("Abode API username not set. Check configuration of the addon.")
if not hass.options['abode_password']:
    raise Exception("Abode API password not set. Check configuration of the addon.")


with requests.Session() as https:
    def _request(method, uri, data = None, raise_for_status = False):
        response = https.request(method, urljoin(BASE_URL, uri), data=data)
        if raise_for_status:
            response.raise_for_status()
        return response.json()

    def get_api_key():
        login = _request('POST', '/api/auth2/login', data={
            'id': hass.options['abode_username'],
            'password': hass.options['abode_password'],
            'locale_code': hass.options['locale'],
            'uuid': generate_uuid()
        })
        https.headers.update({'Abode-Api-Token': login['token']})
        return login['token']

    def get_access_token():
        claims = _request('GET', '/api/auth2/claims')
        https.headers.update({'Authorization': f"Bearer {claims['access_token']}"})
        return claims['access_token']

    def get_features():
        features = _request('GET', '/integrations/v1/features')
        if 'cameras' not in features:
            raise Exception("No cameras found in Abode feature API response")
        return features

    def get_cameras():
        devices = _request('GET', '/api/v1/devices')
        cameras = [d for d in devices if d['type_tag'] == CAMERA_TYPE and d['origin'] == 'abode_cam']
        if len(cameras) == 0:
            raise Exception(f"No cameras found in your Abode setup")
        return cameras

    def check_247_recording(cam_uuid, cam_name, features):
        for cam_feature in features['cameras']:
            if cam_feature['id'] == cam_uuid and not cam_feature['canStream247']:
                log.warning(f"Camera {cam_name} is not enabled for 24x7 recording")

    @dataclass
    class KVSEndpointData:
        endpoint_url: str
        channel_arn: str
        channel_id: str
        client_id: str
        ice_servers: str

    def parse_kvs_response(data, cam_slug) -> KVSEndpointData:
        endpoint = data['channelEndpoint']
        endpoint_url = urlparse(endpoint)
        endpoint_qs = parse_qs(endpoint_url.query)

        channel_arn = endpoint_qs['X-Amz-ChannelARN'][0]
        log.debug(f"Channel ARN for {cam_slug} is {channel_arn}")
        channel_arn = channel_arn.split(':')
        assert channel_arn[0] == 'arn'
        assert channel_arn[1] == 'aws'
        assert channel_arn[2] == 'kinesisvideo'

        channel_parts = channel_arn[-1].split('/')
        assert channel_parts[0] == 'channel'

        channel_id = channel_parts[1]
        client_id = channel_parts[2]
        ice_servers = json.dumps(data['iceServers'])

        return KVSEndpointData(endpoint, channel_arn, channel_id, client_id, ice_servers)

    def get_kvs_stream(cam_uuid, cam_slug):
        log.debug(f"Getting KVS endpoint url for camera {cam_slug}")
        data = _request('POST', f"/integrations/v1/camera/{cam_uuid}/kvs/stream", raise_for_status=False)
        if 'errorCode' in data:
            if data['errorCode'] == ERR_CAMERA_OFFLINE:
                log.warning(f"Camera '{cam_slug}' is offline, skipping")
                return None
            else:
                raise Exception(f"Error {data['errorCode']} ({data['message']}) getting stream for {cam_slug}")
        return parse_kvs_response(data, cam_slug)

    def write_go2rtc_config(cameras, features):
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml') as f:
            log.info(f"Writing go2rtc configuration to {f.name}")

            f.write("webrtc:\n  candidates:\n    - stun:8555\n\n")
            f.write("hass:\n  config: '/config'\n\n")
            f.write("log:\n  level: 'debug'\n\n")
            f.write('streams:\n')
            for cam in cameras:
                cam_slug = cam['name'].lower().replace(' ', '_')
                log.info(f"{cam['name']} will be configured in go2rtc as '{cam_slug}'")

                check_247_recording(cam['uuid'], cam['name'], features)
                kvs = get_kvs_stream(cam['uuid'], cam_slug)
                if kvs:
                    f.write(f"  {cam_slug}: 'webrtc:{kvs.endpoint_url}"
                            "#format=kinesis"
                            f"#client_id={kvs.client_id}"
                            f"#ice_servers={kvs.ice_servers}'\n")
            return f.name

    def run_go2rtc(bin_path, config_path):
        log.info("Starting go2rtc...")
        p = subprocess.Popen([bin_path, '-config', config_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        while not p.poll():
            for line in p.stdout:
                _, severity, message = line.decode('utf-8').strip().split(' ', maxsplit=2)
                if severity == 'ERR':
                    go2rtc_log.error(message)
                else:
                    go2rtc_log.info(message)

        if p.returncode:
            log.warning(f"Exit code from go2rtc is {p.returncode}")
        else:
            log.info("go2rtc exited normally")

    get_api_key()
    get_access_token()

    features = get_features()
    cameras = get_cameras()

    go2rtc_conf = write_go2rtc_config(cameras, features)
    run_go2rtc(go2rtc_path, go2rtc_conf)

