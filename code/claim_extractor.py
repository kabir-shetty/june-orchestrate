import json
from pathlib import Path
import re
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = ROOT_DIR / 'dataset'
CLAIMS_CSV = DATASET_DIR / 'claims.csv'
CLAIM_DATA_JSON = ROOT_DIR / 'claimData.json'

def main():
    # Important claim data grouped by object type.
    # issueType captures the damage/action words.
    # objectParts captures the parts mentioned in the claim.
    claimData = {
        'car': {
            'issueType': [
                'damaged',
                'damage',
                'broken',
                'broke',
                'cracked',
                'crack',
                'crushed',
                'dented',
                'dent',
                'scratched',
                'scratch',
                'shattered',
                'missing',
                'broken off',
                'hail dents',
                'water damage',
            ],
            'objectParts': [
                'bumper',
                'front bumper',
                'rear bumper',
                'headlight',
                'taillight',
                'windshield',
                'side mirror',
                'door',
                'hood',
                'car body',
                'body panel',
                'mirror',
                'glass',
            ],
        },
        'laptop': {
            'issueType': [
                'cracked',
                'crack',
                'broken',
                'broke',
                'missing',
                'damaged',
                'damage',
                'liquid damage',
                'stained',
                'stain',
                'came off',
                'keys missing',
            ],
            'objectParts': [
                'screen',
                'keyboard',
                'key',
                'keycap',
                'hinge',
                'trackpad',
                'body',
                'lid',
                'outer body',
                'corner',
                'palm-rest',
                'palm rest',
            ],
        },
        'package': {
            'issueType': [
                'crushed',
                'crush',
                'torn',
                'torn open',
                'open',
                'wet',
                'water damaged',
                'water damage',
                'damaged',
                'damage',
                'stain',
                'oily mark',
                'unreadable',
                'missing',
                'broken',
            ],
            'objectParts': [
                'package',
                'box',
                'delivery box',
                'cardboard box',
                'seal',
                'label',
                'corner',
                'contents',
                'item inside',
                'item',
                'wrapping',
            ],
        },
    }

    # Extract claims from the claims.csv file
    claims_df = pd.read_csv(CLAIMS_CSV)
    claims = {}

    for _, row in claims_df.iterrows():
        user_id = row['user_id']
        claims[user_id] = {
            'image_paths': row['image_paths'],
            'user_claim': row['user_claim'],
            'claim_object': row['claim_object'],
        }
        
    # Make a json file with the following format:
    # user_id: {claim_object: {issueType: [...], objectParts: [...]}}
    claimDataByUser = {}
    for user_id, claim in claims.items():
        claim_object = claim['claim_object']
        user_claim = claim['user_claim']
        object_data = claimData.get(claim_object, {'issueType': [], 'objectParts': []})

        claimDataByUser[user_id] = {
            claim_object: {
            'issueType': find_present_keywords(user_claim, object_data['issueType']),
            'objectParts': find_present_keywords(user_claim, object_data['objectParts']),
            }
        }

    with open(CLAIM_DATA_JSON, 'w', encoding='utf-8') as f:
        json.dump(claimDataByUser, f, indent=2)



def find_present_keywords(text, keywords):
    present = []

    for keyword in keywords:
        pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
        if re.search(pattern, text.lower()) and keyword not in present:
            present.append(keyword)

    return present


main()