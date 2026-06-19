import pandas as pd

claims = pd.read_csv('../dataset/claims.csv')
user_history = pd.read_csv('../dataset/user_history.csv')
evidence_requirements = pd.read_csv('../dataset/evidence_requirements.csv')

print(claims.head())
print(user_history.head())
print(evidence_requirements.head())