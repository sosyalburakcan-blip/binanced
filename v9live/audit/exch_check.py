# Bağımsız borsa denetimi: bot.py'yi içe aktarmaz; yalnızca GET (okuma) çağrıları, demo-fapi.
import base64, json, time, urllib.parse, requests
from cryptography.hazmat.primitives.serialization import load_pem_private_key
env = {}
for l in open("/root/binanced/.env.testnet"):
    l = l.strip()
    if l and not l.startswith("#") and "=" in l:
        k, v = l.split("=", 1); env[k] = v.strip()
key = load_pem_private_key(open(env["BINANCE_TESTNET_PRIVATE_KEY_PATH"], "rb").read(), None)
B = "https://demo-fapi.binance.com"
S = requests.Session(); S.headers["X-MBX-APIKEY"] = env["BINANCE_TESTNET_API_KEY"]
def g(path, **p):
    p["timestamp"] = int(time.time() * 1000); p["recvWindow"] = 10000
    q = urllib.parse.urlencode(p)
    sig = base64.b64encode(key.sign(q.encode())).decode()
    r = S.get(f"{B}{path}?{q}&signature={urllib.parse.quote(sig)}", timeout=15)
    r.raise_for_status(); return r.json()
st = json.load(open("/root/binanced/v9live/state.json"))
pos = [p for p in g("/fapi/v3/positionRisk") if float(p["positionAmt"]) != 0]
print("== Borsadaki pozisyonlar")
for p in pos:
    print(f"  {p['symbol']:9} adet {p['positionAmt']:>8} giriş {p['entryPrice']:>10} mark {float(p['markPrice']):.5g} "
          f"gerçekleşmemiş {float(p['unRealizedProfit']):+.3f} $ kaldıraç-notional {p.get('notional')}")
print("== Açık normal emirler")
for o in g("/fapi/v1/openOrders"):
    print(f"  {o['symbol']:9} {o['side']} {o['type']} {o['origQty']} @ {o['price']} reduceOnly={o['reduceOnly']} cid={o['clientOrderId']}")
print("== Açık algo emirler")
for o in g("/fapi/v1/openAlgoOrders"):
    print(f"  {o['symbol']:9} {o['side']} {o.get('orderType')} tetik {o.get('triggerPrice')} closePos={o.get('closePosition')} "
          f"workingType={o.get('workingType')} cid={o.get('clientAlgoId')}")
print("== Dolumlar (userTrades, 08:00 sonrası)")
for s in st:
    for t in g("/fapi/v1/userTrades", symbol=s["sym"], startTime=s["decision_ms"]):
        print(f"  {t['symbol']:9} {t['side']} {t['qty']} @ {t['price']} maker={t['maker']} komisyon {t['commission']} {t['commissionAsset']} "
              f"oid={t['orderId']} {time.strftime('%H:%M:%S', time.gmtime(t['time']/1000))}")
print("== state.json karşılaştırma")
pm = {p["symbol"]: p for p in pos}
for s in st:
    p = pm.get(s["sym"])
    print(f"  {s['sym']:9} bot: {s['filled_qty']} @ {s['entry']} es_px {s['es_px']} | borsa: "
          f"{p['positionAmt'] if p else 'YOK'} @ {p['entryPrice'] if p else '-'}")
b = [x for x in g("/fapi/v3/balance") if x["asset"] == "USDT"][0]
print(f"== USDT cüzdan {float(b['balance']):.2f}, kullanılabilir {float(b['availableBalance']):.2f}, gerçekleşmemiş {float(b['crossUnPnl']):+.3f}")
