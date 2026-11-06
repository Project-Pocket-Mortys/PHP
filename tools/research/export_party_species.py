"""Export only species identifiers from the pinned multiplayer MortyInfo asset."""
import json
from pathlib import Path
from export_item_effects import load_text

rows, source = load_text('mpdata.assetbundle', 'MortyInfo')
assert source['asset_sha256'] == '96072cc81591577cc31245c6f0ef7518d6ef1b5b5b47e261fd93163caba5ea99'
assert source['bundle_sha256'] == 'f9101d6012defb85545913db6a0f3fa0d1eb06014d604a6f341937a61887b413'
ids = sorted(row['morty_id'] for row in rows)
assert len(ids) == len(set(ids)) and 'MortyDefault' in ids
target = Path(__file__).resolve().parents[2] / 'config/multiplayer_morty_ids.json'
target.write_text(json.dumps({'schema_version':1,'source':source,'morty_ids':ids},indent=2)+'\n',newline='\n')
print(f'Exported {len(ids)} multiplayer species IDs; no stats or formulas.')
