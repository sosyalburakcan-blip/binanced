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
