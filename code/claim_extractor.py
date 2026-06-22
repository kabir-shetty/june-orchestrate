import json
from pathlib import Path
import re
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = ROOT_DIR / 'dataset'
CLAIMS_CSV = DATASET_DIR / 'claims.csv'
CLAIM_DATA_JSON = DATASET_DIR / 'claimData.json'

def main():
    # Important claim data grouped by object type.
    # issueType captures the damage/action words.
    # objectParts captures the parts mentioned in the claim.
    claimData = {
        'car': {
            'issueType': {
                'dent': ['dent', 'dented', 'dents', 'hail dents', 'bump'],
                'scratch': ['scratch', 'scratched', 'scrapes', 'scrape', 'mark', 'scrape lag gaya'],
                'crack': ['crack', 'cracked', 'cracks'],
                'glass_shatter': ['shattered', 'shatter', 'glass shatter', 'broken glass'],
                'broken_part': ['broken', 'broke', 'broken off', 'damaged', 'damage', 'break'],
                'missing_part': ['missing', 'fell off', 'came off'],
                'water_damage': ['water damage', 'wet', 'liquid damage', 'water damaged'],
                'stain': ['stain', 'stained'],
                'none': ['none', 'no damage'],
                'unknown': ['unknown']
            },
            'objectParts': [
                'front bumper',
                'rear bumper',
                'headlight',
                'taillight',
                'windshield',
                'side mirror',
                'door',
                'hood',
                'fender',
                'quarter panel',
                'body',
                'unknown',
            ],
        },
        'laptop': {
            'issueType': {
                'dent': ['dent', 'dented', 'dents'],
                'scratch': ['scratch', 'scratched', 'scrapes', 'scrape', 'mark'],
                'crack': ['crack', 'cracked', 'cracks'],
                'glass_shatter': ['shattered', 'shatter', 'glass shatter', 'broken glass'],
                'broken_part': ['broken', 'broke', 'broken off', 'damaged', 'damage', 'break'],
                'missing_part': ['missing', 'fell off', 'came off', 'keys missing', 'key missing'],
                'water_damage': ['water damage', 'wet', 'liquid damage', 'water damaged'],
                'stain': ['stain', 'stained', 'sticky'],
                'none': ['none', 'no damage'],
                'unknown': ['unknown']
            },
            'objectParts': [
                'screen',
                'keyboard',
                'hinge',
                'trackpad',
                'body',
                'lid',
                'base',
                'corner',
                'port',
                'unknown',
            ],
        },
        'package': {
            'issueType': {
                'torn_packaging': ['torn', 'torn open', 'open', 'phati', 'phata', 'opened'],
                'crushed_packaging': ['crushed', 'crush', 'dented', 'dent', 'crease', 'creased'],
                'water_damage': ['water damage', 'wet', 'water damaged', 'liquid damage'],
                'stain': ['stain', 'stained', 'oily mark', 'oily', 'unreadable'],
                'none': ['none', 'no damage'],
                'unknown': ['unknown', 'missing', 'broken']
            },
            'objectParts': [
                'box',
                'side',
                'seal',
                'label',
                'corner',
                'contents',
                'item',
                'unknown',
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
    
    # Sort claims for easier handling
    claims = dict(sorted(claims.items()))
    
    # Make a json file with the following format:
    # user_id: {claim_object: {issueType: [...], objectParts: [...]}}
    claimDataByUser = {}
    for user_id, claim in claims.items():
        claim_object = claim['claim_object']
        user_claim = claim['user_claim']
        object_data = claimData.get(claim_object, {'issueType': {}, 'objectParts': []})

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
    if not text or not keywords:
        return present

    text_lower = text.lower()
    if isinstance(keywords, dict):
        for issue_type, kw_list in keywords.items():
            for kw in kw_list:
                pattern = r'\b' + re.escape(kw.lower()) + r'\b'
                if re.search(pattern, text_lower):
                    if issue_type not in present:
                        present.append(issue_type)
                    break
        return present

    for keyword in keywords:
        pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
        if re.search(pattern, text_lower) and keyword not in present:
            present.append(keyword)

    return present

if __name__ == "__main__":
    main()
