# C3 (volatil dönemde piyasanın sert 60 dk hareketine karşı, en yüksek betalı 4 altcoin, 60 dk tut) bağımsız yeniden yazım.
# Ajanın kodu kullanılmaz. Dakika ızgarası, her dakikanın ilk defter görüntüsü. Kullanım: python -I bu_dosya.py <klasör>
import pandas as pd, numpy as np
import sys
S = sys.argv[1] if len(sys.argv) > 1 else '.'   # içinde work/mid.pkl olan klasör (defter arşivinden çıkarılan dakikalık fiyatlar)
m=pd.read_pickle(S+'/work/mid.pkl').sort_values('ts'); m['mn']=m.ts//60000
m=m.drop_duplicates(['mn','sym'])
idx=range(m.mn.min(),m.mn.max()+1)
B=m.pivot(index='mn',columns='sym',values='bid').reindex(idx); A=m.pivot(index='mn',columns='sym',values='ask').reindex(idx)
M=(A+B)/2; L=np.log(M)
r1=L.diff()                                   # 1 dk log getiri (eksik dakikada NaN)
mk1=r1.mean(axis=1).fillna(0)                 # eşit ağırlıklı piyasa
mlev=mk1.cumsum()
mk60=mlev-mlev.shift(60)
sd=mk60.rolling(1440,min_periods=240).std().shift(1)
vol60=mk1.rolling(60,min_periods=40).std(); volmed=vol60.rolling(1440,min_periods=240).median()
# beta: son 240 dk, coin 1 dk getirisi ~ piyasa 1 dk getirisi
cov=r1.mul(mk1,axis=0).rolling(240,min_periods=120).mean()-r1.rolling(240,min_periods=120).mean().mul(mk1.rolling(240,min_periods=120).mean(),axis=0)
var=mk1.rolling(240,min_periods=120).var(ddof=0)
beta=cov.div(var,axis=0).clip(-1,4)
alts=[c for c in M.columns if c not in ('BTCUSDT','ETHUSDT')]
HOLD=pd.Timestamp('2026-11-08').value//60_000_000_000
TAKER,SLIP,N=0.0005,0.0001,1500.0
def run(phase, z=1.0, hold=60, n=4, mode='rev'):
    tr=[]
    t=idx[0]+300
    t+= (phase - t) % 60
    while t+1+hold<=idx[-1]:
        if np.isfinite(sd[t]) and np.isfinite(volmed[t]) and vol60[t]>volmed[t] and abs(mk60[t])>z*sd[t]:
            s=-np.sign(mk60[t]) if mode=='rev' else np.sign(mk60[t])
            b=beta.loc[t,alts]; ok=b.notna()&M.loc[t,alts].notna()&M.loc[t+1,alts].notna()
            pick=b[ok].sort_values(ascending=False).index[:n]
            for c in pick:
                ep=A.at[t+1,c]*(1+SLIP) if s>0 else B.at[t+1,c]*(1-SLIP)
                xs=M.loc[t+1:t+hold,c].dropna()
                if len(xs)==0: continue
                xm=xs.index[-1]
                xp=B.at[xm,c]*(1-SLIP) if s>0 else A.at[xm,c]*(1+SLIP)
                g=N*s*(xp/ep-1); fee=N*TAKER*(1+xp/ep)
                tr.append(dict(t=t,sym=c,side=s,gross=g,net=g-fee,gap=(t+hold)-xm))
        t+=hold
    return pd.DataFrame(tr)
if __name__=='__main__':
    rows=[]
    for ph in range(60):
        d=run(ph)
        if len(d)==0: continue
        a=d[d.t<HOLD]; h=d[d.t>=HOLD]
        rows.append(dict(phase=ph,t_ev=a.t.nunique(),t_net=a.net.sum(),h_ev=h.t.nunique(),h_net=h.net.sum(),h_long=(h.side>0).sum(),h_short=(h.side<0).sum()))
    r=pd.DataFrame(rows)
    print(r.describe().round(1).to_string())
    print('tasarım net>0: %d/60, bekletme net>0: %d/60'%((r.t_net>0).sum(),(r.h_net>0).sum()))
    print('bekletme net çeyrekler:',r.h_net.quantile([.1,.25,.5,.75,.9]).round(1).to_dict())
    r.to_csv('phases.csv',index=False)
