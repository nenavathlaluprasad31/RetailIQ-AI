import argparse,json
from pathlib import Path
import pandas as pd
import numpy as np

COLS=['invoice','stock_code','description','quantity','invoice_date','unit_price','customer_id','country']
ALIASES={'invoice':'invoice','invoiceno':'invoice','stockcode':'stock_code','description':'description','quantity':'quantity','invoicedate':'invoice_date','price':'unit_price','unitprice':'unit_price','customerid':'customer_id','country':'country'}
def read_source(path):
    sheets=pd.read_excel(path,sheet_name=None) if str(path).lower().endswith('.xlsx') else {'csv':pd.read_csv(path,encoding='utf-8-sig')}
    frames=[]
    for name,df in sheets.items():
        df=df.rename(columns=lambda x:ALIASES.get(''.join(str(x).lower().split()),x))
        if not set(COLS)<=set(df.columns): raise ValueError(f'Missing required columns in {name}: {set(COLS)-set(df.columns)}')
        frames.append(df[COLS])
    return pd.concat(frames,ignore_index=True)

def clean(df):
    d=df.copy(); audit={'raw_rows':len(d)}
    for c in ['invoice','stock_code','description','country','customer_id']:
        d[c]=d[c].astype('string').str.strip().replace('',pd.NA)
    d.customer_id=d.customer_id.str.replace(r'\.0$','',regex=True)
    d.invoice_date=pd.to_datetime(d.invoice_date,errors='coerce')
    for c in ['quantity','unit_price']: d[c]=pd.to_numeric(d[c],errors='coerce')
    audit['missing_customer_rows']=int(d.customer_id.isna().sum())
    before=len(d); d=d.drop_duplicates(); audit['exact_duplicates_removed']=before-len(d)
    valid=d[['invoice','stock_code','invoice_date','quantity','unit_price']].notna().all(axis=1)&np.isfinite(d.quantity)&np.isfinite(d.unit_price)&(d.unit_price>=0)&(d.quantity!=0)&(d.quantity%1==0)
    rejected=d.loc[~valid].copy(); d=d.loc[valid].copy()
    d['is_return']=d.invoice.str.upper().str.startswith('C') | (d.quantity<0)
    d['line_amount']= (d.quantity.abs()*d.unit_price*np.where(d.is_return,-1,1)).round(4)
    d['is_outlier']=False
    for c in ['quantity','unit_price']:
        x=d[c].abs(); q1,q3=x.quantile([.25,.75]); d['is_outlier'] |= x>q3+3*(q3-q1)
    d['country']=d.country.fillna('Unknown'); d['description']=d.description.fillna('Unknown')
    audit.update(clean_rows=len(d),rejected_rows=len(rejected),return_rows=int(d.is_return.sum()),outlier_rows=int(d.is_outlier.sum()),net_sales_gbp=float(d.line_amount.sum()))
    return d,rejected,audit

def main():
    p=argparse.ArgumentParser(); p.add_argument('source'); p.add_argument('--out',default='data/processed'); a=p.parse_args(); out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    d,r,audit=clean(read_source(a.source)); d.to_parquet(out/'transactions.parquet',index=False); r.to_csv(out/'rejected.csv',index=False); (out/'quality.json').write_text(json.dumps(audit,indent=2)); print(json.dumps(audit,indent=2))
if __name__=='__main__': main()
