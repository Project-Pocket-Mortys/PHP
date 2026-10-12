#!/usr/bin/env python3
"""Reconcile native request/handler candidates with the inventory and DTO index."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/protocol'

def main():
    native = json.loads((OUT / 'native-transport.json').read_text())
    inventory = json.loads((OUT / 'inventory.json').read_text())
    types = {t['type']: t for t in json.loads((OUT / 'client-types.json').read_text())}
    parsers = []
    for method in native:
        for reference in method['generic_method_candidates']:
            match = re.search(r'(?:ParseHTTPResponse|Deserialize)<(.+)>\(', reference['name'])
            if match:
                parsers.append({'method': method['method'], 'address': method['address'],
                    'type': match[1], 'reference': reference, 'schema_available': match[1] in types,
                    'operation_mapping': 'unresolved; correlate caller/event registration before assigning endpoint'})
    requests = []
    for endpoint in inventory['endpoints']:
        for candidate in endpoint.get('native_request_candidates', []):
            requests.append({'path': endpoint['path'], **candidate})
    events = []
    for event in inventory['events']:
        candidates = []
        for method in native:
            if any(ref['literal'] == event['name'] for ref in method['literal_candidates']):
                candidates.append({'method': method['method'], 'address': method['address'],
                    'handler_candidates': [r for r in method['generic_method_candidates'] if r['name'].startswith('Method$Network')]})
        events.append({'event': event['name'], 'registration_candidates': candidates,
                       'status': 'unresolved association' if candidates else 'no registration found by linear scan'})
    (OUT / 'parser-mapping.json').write_text(json.dumps({'request_constructors': requests,
        'response_parsers': parsers, 'event_registrations': events}, indent=2)+'\n')

    reviewed = {
        'schema_version': 1, 'evidence': 'ARM64 binary in artifacts.json; native-transport.json instruction references; server integration tests',
        'http': {
            '/session/battle/ready': {'method': 'POST', 'native_constructor': 'NetworkBattleAPI$$SelectingMove', 'address': '0x1788078',
                'request': {'type':'object', 'properties': {'session_id': {'type':'string'}, 'battle_id': {'type':'string'}}, 'required':['session_id','battle_id']},
                'success': {'success': True}, 'success_origin': 'replacement server; original acknowledgement body not established',
                'event': 'battle:move-timer-started', 'error_enum':'eBattleReadyError',
                'errors': {'400':'missing/malformed identifier', '401':'invalid session','403':'other initiator','404':'missing battle','409':'inactive battle or missing room'},
                'errors_origin': 'replacement server regression contract; original error envelopes unresolved'},
            '/session/battle/move': {'method':'POST', 'native_constructor':'NetworkBattleAPI$$SelectMove', 'address':'0x17882bc',
                'request': {'type':'object', 'properties': {k:{'type':'string'} for k in ['session_id','battle_id','type','owned_morty_id','move_id']},
                    'required':['session_id','battle_id','type'], 'description':'Client constructs all five properties. Required list describes current server validation only.'},
                'success':{'success':True}, 'event':'battle:turn-result',
                'limitations':['combat remains placeholder','capture is not persisted','duplicate active turns are not idempotent','item consumption unresolved']}
        },
        'sse': {},
        'transport': {'content_type':'application/json', 'client_header':'X-PMCLIENT',
            'evidence':'NetworkHTTP$$Request 0x17b5a44; ARM64 0x17b5ba0..0x17b5bb4 selects Post=2 for a default Get=0 request with non-null serialized postData',
            'session_auth':'Request bodies carry session_id; replacement SSE decodes it from token query JWT payload without verifying signature',
            'reconnect':'Server accepts Last-Event-ID/since but does not emit event IDs; client retry/cursor behavior needs runtime verification'},
        'udp': {'status':'native transport discovered; wire schema incomplete',
            'send_position': {'method':'UdpNodeSender$$SendPosition','address':'0x17c04c4', 'packet_size':24,
                'layout_candidates':[{'offset':0,'length':16,'meaning':'session GUID conversion'},
                    {'offset':16,'length':1,'meaning':'sequence low byte'}, {'offset':17,'length':2,'meaning':'coordinate component'},
                    {'offset':19,'length':2,'meaning':'coordinate component'}, {'offset':21,'length':2,'meaning':'position history'},
                    {'offset':23,'length':1,'meaning':'direction'}],
                'unresolved':['GUID byte order','coordinate encoding','history packing','receive packet format','server endpoint lifecycle']}}
    }
    for event, typename, address in [('battle:start','BattleStartResponse','0x1788674'),
            ('battle:move-timer-started','BattleMoveTimeResponse','0x1788d00'),
            ('battle:turn-result','BattleTurnResultResponse','0x1788dc4')]:
        reviewed['sse'][event] = {'client_type':typename,'handler_address':address,
            'managed_fields':types[typename]['fields'], 'requiredness':'unknown; managed fields alone do not establish missing-field handling',
            'audience':'requesting player in current PvWM server implementation'}
    (OUT / 'contracts.json').write_text(json.dumps(reviewed,indent=2)+'\n')
    api = json.loads((OUT / 'openapi.json').read_text())
    for path, contract in reviewed['http'].items():
        api['paths'][path].pop('x-method-unresolved', None)
        api['paths'][path]['post'] = {'summary':contract['native_constructor'], 'requestBody':{'required':True,
            'content':{'application/json':{'schema':contract['request']}}},
            'responses':{'200':{'description':'Current replacement-server acknowledgement',
                'content':{'application/json':{'schema':{'type':'object','properties':{'success':{'const':True}},'required':['success']}}}},
                'default':{'description':'Error envelope compatibility remains unresolved'}},
            'x-native-address':contract['address']}
    (OUT / 'openapi.json').write_text(json.dumps(api,indent=2)+'\n')
    print(len(requests), 'request candidates;', len(parsers), 'parser references;', len(events), 'event entries')

if __name__ == '__main__':
    main()
