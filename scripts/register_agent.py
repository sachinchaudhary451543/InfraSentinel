#!/usr/bin/env python3
"""Simple agent registration script for testing admin_portal

Usage:
  python scripts/register_agent.py --url http://127.0.0.1:5001 --key <AGENT_KEY> --hostname my-test-host

This will POST to /api/register_agent and print the JSON response.
"""
import argparse
import requests

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:5001', help='Base URL of admin portal')
parser.add_argument('--key', required=True, help='Agent key to register with')
parser.add_argument('--hostname', default=None, help='Hostname to register (defaults to local hostname)')
parser.add_argument('--ip', default=None, help='IP address to report (optional)')
args = parser.parse_args()

import socket
hostname = args.hostname or socket.gethostname()

payload = {'agent_key': args.key, 'hostname': hostname}
if args.ip:
    payload['ip'] = args.ip

resp = requests.post(args.url.rstrip('/') + '/api/register_agent', json=payload, timeout=10)
try:
    print('Status:', resp.status_code)
    print(resp.json())
except Exception:
    print('Response:', resp.text)
