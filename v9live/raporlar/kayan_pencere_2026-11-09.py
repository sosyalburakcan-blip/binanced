import itertools
"""Kayan pencere: her 5 dk bak; piyasanın (listedeki coinlerin eşit ağırlıklı ortalaması) son W dk hareketi son 24 saatine göre
sertse (|z| > eşik) ve piyasa çalkantılıysa, BTC/ETH hariç betası en yüksek 4 altcoinde TERS (fade) ya da AYNI (takip) yönde
1.500 $'lık piyasa emriyle gir, H dk sonra kapat. Aynı anda tek olay. Taker %0,05 + 1 bps kayma her iki uçta.
Kullanım: python -I kayan_pencere_2026-11-09.py <klasör>   (klasör/work/mid.pkl: defter arşivinden dakikalık alış/satış)
Not: 08.11 bekletme günü C3 sınavında kullanıldı; buradaki 'sınav' sütunu artık yalnız kontroldür."""
import sys
import pandas as pd, numpy as np
S=sys.argv[1]
m=pd.read_pickle(S+'/work/mid.pkl').sort_values('ts'); m['mn']=m.ts//60000
m=m.drop_duplicates(['mn','sym']); idx=range(m.mn.min(),m.mn.max()+1)
B=m.pivot(index='mn',columns='sym',values='bid').reindex(idx); A=m.pivot(index='mn',columns='sym',values='ask').reindex(idx)
M=(A+B)/2; r1=np.log(M).diff()
mk1=r1.mean(axis=1).fillna(0); mlev=mk1.cumsum()
vol60=mk1.rolling(60,min_periods=40).std(); volmed=vol60.rolling(1440,min_periods=240).median()
cov=r1.mul(mk1,axis=0).rolling(240,min_periods=120).mean()-r1.rolling(240,min_periods=120).mean().mul(mk1.rolling(240,min_periods=120).mean(),axis=0)
beta=cov.div(mk1.rolling(240,min_periods=120).var(ddof=0),axis=0).clip(-1,4)
alts=[c for c in M.columns if c not in ('BTCUSDT','ETHUSDT')]
HOLD=pd.Timestamp('2026-11-08').value//60_000_000_000
TAKER,SLIP,N=0.0005,0.0001,1500.0
Z={}
for W in (15,20,30,45,60):
    mw=mlev-mlev.shift(W); Z[W]=mw/mw.rolling(1440,min_periods=240).std().shift(1)
Zens=pd.concat([Z[w] for w in (15,20,30,60)],axis=1).mean(axis=1)   # çok pencereli ortalama z
def legs(t,s,H):
    b=beta.loc[t,alts]; ok=b.notna()&M.loc[t,alts].notna()&M.loc[t+1,alts].notna()
    out=[]
    for c in b[ok].sort_values(ascending=False).index[:4]:
        ep=A.at[t+1,c]*(1+SLIP) if s>0 else B.at[t+1,c]*(1-SLIP)
        xs=M.loc[t+1:t+H,c].dropna()
        if len(xs)==0: continue
        xm=xs.index[-1]; xp=B.at[xm,c]*(1-SLIP) if s>0 else A.at[xm,c]*(1+SLIP)
        g=N*s*(xp/ep-1); out.append(g-N*TAKER*(1+xp/ep))
    return out
def run(zser,thr,H,phase=0,step=5,mode='rev',volf=True):
    ev=[]; t=idx[0]+300; t+=(phase-t)%step; busy=-1
    while t+1+H<=idx[-1]:
        z=zser.get(t,np.nan)
        if t>=busy and np.isfinite(z) and abs(z)>thr and (not volf or (np.isfinite(volmed[t]) and vol60[t]>volmed[t])):
            s=-np.sign(z) if mode=='rev' else np.sign(z)
            L=legs(t,s,H)
            if L: ev.append((t,s,sum(L),len(L))); busy=t+H+1
        t+=step
    return pd.DataFrame(ev,columns=['t','side','net','n'])

if __name__ == "__main__":
    rows = []
    for W, thr, H in itertools.product((15, 20, 30, 45, 60), (1.0, 1.5, 2.0), (15, 30, 60)):
        for mode in ("rev", "mom"):
            v = []
            for ph in range(5):
                d = run(Z[W], thr, H, phase=ph, mode=mode)
                v.append((d[d.t < HOLD].net.sum(), d[d.t >= HOLD].net.sum(), (d.t < HOLD).sum(), (d.t >= HOLD).sum()))
            v = np.array(v)
            rows.append(dict(W=W, esik=thr, tut=H, yon=mode, tasarim=np.median(v[:, 0]), sinav=np.median(v[:, 1]),
                             t_olay=np.median(v[:, 2]), s_olay=np.median(v[:, 3])))
    R = pd.DataFrame(rows)
    pd.set_option("display.width", 200); pd.set_option("display.max_rows", 200)
    print(R.round(1).to_string(index=False))
    print()
    for W in (15, 20, 30, 45, 60):
        for mode, lab in (("rev", "TERSINE"), ("mom", "YONUNDE")):
            y = R[(R.W == W) & (R.yon == mode)]
            print(f"W{W:<3} {lab:8s} tasarımda artı {int((y.tasarim > 0).sum())}/9 (ortanca {y.tasarim.median():+7.1f} $) | "
                  f"sınavda artı {int((y.sinav > 0).sum())}/9 (ortanca {y.sinav.median():+7.1f} $)")
    for H in (15, 30, 60):
        for mode in ("rev", "mom"):
            y = R[(R.tut == H) & (R.yon == mode)]
            print(f"tutma {H:>2} dk {mode}: tasarımda artı {int((y.tasarim > 0).sum())}/15, sınavda artı {int((y.sinav > 0).sum())}/15")
