"""Classify RentCast post-fire sale owners: individuals/trusts vs companies.

Deduced method (see summary): RentCast's own owner_type is NOT usable directly
because it flags personal/family TRUSTS and multi-person families as
"Organization". We instead classify on the owner NAME with token precedence:

  1) Company  -- name carries a legal suffix (LLC/INC/LP/CORP/LTD...) or a
                 business-activity keyword (HOLDINGS/INVESTMENTS/DEVELOPMENT/
                 CAPITAL/PROPERTIES/CONSTRUCTION/HOMES/GROUP...). Checked FIRST.
  2) Individual (trust) -- else, a trust/estate-planning token
                 (TRUST/REVOCABLE/LIVING/FAMILY/SURVIVOR..., truncation-tolerant).
  3) Individual -- else, a plain personal name.

Company precedence means a business that also contains "FAMILY"/"TRUST" (e.g.
IRON FAMILY INVESTMENTS LLC) is still a company. Validated on the local cache:
0 RentCast-"Individual" records fall to Company, and every RentCast-"Organization"
lacking a company token is in fact an individual or family trust.
"""
import json, csv, re
from collections import Counter

COMPANY_TOKENS = [
    r'LLC', r'L\.L\.C', r'INC', r'INCORPORATED', r'CORP', r'CORPORATION',
    r'LP', r'L\.P', r'LLP', r'LTD', r'LIMITED', r'COMPANY', r'FOUNDATION',
    r'HOLDINGS?', r'INVESTMENTS?', r'CAPITAL', r'DEVELOPMENT', r'PROPERTIES',
    r'PROPERTY', r'REALTY', r'VENTURES?', r'PARTNERS', r'GROUP', r'BUILDERS?',
    r'CONSTRUCTION', r'HOMES', r'EQUITY', r'ENTERPRISES?', r'MANAGEMENT',
    r'REDEVELOPMENT', r'REAL ESTATE', r'DYNAMICS', r'SOLUTIONS', r'TRADING',
    r'PROCESSING', r'LEASING', r'GLOBAL', r'SYNERGY',
]
COMPANY_RE = re.compile(r'(?<![A-Z])(' + '|'.join(COMPANY_TOKENS) + r')(?![A-Z])')
TRUST_RE = re.compile(
    r'(?<![A-Z])(TRUST|TRUS|REVOCABLE|IRREVOCABLE|LIVING|FAMILY|SURVIVOR'
    r'|BYPASS|DECEDENT|FMTR|FMLY|RLT|\bTR\b)(?![A-Z])'
)
ADDR_LLC_RE = re.compile(r'^\s*\d+\s+\S+.*\b(LLC|LP|INC)\b')  # single-purpose vehicle

def classify(name):
    if not name or not name.strip():
        return ('Unknown', 'Unknown', 'no owner name on record')
    up = name.upper()
    c = COMPANY_RE.search(up)
    if c:
        return ('Company', 'Company', f'company token "{c.group(0)}"')
    t = TRUST_RE.search(up)
    if t:
        return ('Individual', 'Trust', f'trust vehicle ("{t.group(0)}")')
    return ('Individual', 'Individual', 'personal name(s)')

data = json.load(open('data/rentcast-cache.json'))
sold = data['sold']
freq = Counter(r.get('owner_name') for r in sold if r.get('owner_name'))

cols = ['ain','sale_date','sale_price','owner_name','rentcast_owner_type',
        'owner_occupied','owner_class','owner_subtype','classifier_reason',
        'single_purpose_llc','buyer_parcel_count','portfolio_buyer']
out = 'data/sales-owners.csv'
with open(out,'w',newline='') as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
    for r in sold:
        name = r.get('owner_name')
        cls, sub, why = classify(name)
        n = freq.get(name, 0)
        sp_llc = bool(cls=='Company' and name and ADDR_LLC_RE.search(name.upper()))
        w.writerow({
            'ain': r.get('ain'),
            'sale_date': (r.get('sale_date') or '')[:10],
            'sale_price': r.get('sale_price'),
            'owner_name': name,
            'rentcast_owner_type': r.get('owner_type'),
            'owner_occupied': r.get('owner_occupied'),
            'owner_class': cls,
            'owner_subtype': sub,
            'classifier_reason': why,
            'single_purpose_llc': sp_llc,
            'buyer_parcel_count': n,
            'portfolio_buyer': n > 1,
        })

# summary
sub_ct = Counter(classify(r.get('owner_name'))[1] for r in sold)
cls_ct = Counter(classify(r.get('owner_name'))[0] for r in sold)
print('wrote', out, 'rows:', len(sold))
print('owner_class :', dict(cls_ct))
print('owner_subtype:', dict(sub_ct))
n_sp = sum(1 for r in sold if (nm:=r.get('owner_name')) and classify(nm)[0]=='Company' and ADDR_LLC_RE.search(nm.upper()))
print('single-purpose address LLCs:', n_sp)
print('company records held by portfolio (repeat) buyers:',
      sum(1 for r in sold if freq.get(r.get('owner_name'),0)>1 and classify(r.get('owner_name'))[0]=='Company'))
