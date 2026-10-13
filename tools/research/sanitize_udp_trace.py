"""Export 24-byte sendto buffers with session GUIDs replaced by a synthetic ID."""
import argparse
import json
from pathlib import Path
import re


def sanitize(trace):
    packets = []
    pattern = r'sendto\(\d+, "((?:\\x[0-9a-f]{2}){24})", 24,'
    for match in re.finditer(pattern, trace):
        raw = bytes.fromhex(match[1].replace('\\x', ''))
        packets.append({'hex': (bytes.fromhex('00112233445566778899aabbccddeeff') + raw[16:]).hex()})
    return {'provenance': 'Client sendto buffers; GUIDs replaced with synthetic 00112233-4455-6677-8899-aabbccddeeff. Attempted sends do not prove UDP delivery. Verify socket identity separately.',
            'packets': packets}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = sanitize(args.trace.read_text())
    args.output.write_text(json.dumps(result, indent=2) + '\n', newline='\n')
    print(f"Exported {len(result['packets'])} sanitized attempted sends")
