import pandas as pd
from retailiq.etl import clean,COLS

def test_clean():
    row=['1','A','Gift',2,'2011-01-01',3,None,'UK']
    ret=['C2','A','Gift',-1,'2011-01-02',3,'12','UK']
    bad=['3','A','Gift',1,'invalid',3,'12','UK']
    d,r,a=clean(pd.DataFrame([row,row,ret,bad],columns=COLS))
    assert len(d)==2 and len(r)==1 and a['exact_duplicates_removed']==1
    assert d.line_amount.sum()==3 and d.customer_id.isna().sum()==1
