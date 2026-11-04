"""Telefona kâğıt işlem bildirimi (ücretsiz): Telegram botu ve/veya WhatsApp (CallMeBot). GERÇEK EMİR YOK.

Anahtarlar proje kökünde `.env.bildirim` dosyasında (git'e girmez: `.gitignore` → `.env.*`):
    TELEGRAM_BOT_TOKEN=     # Telegram'da @BotFather → /newbot → verdiği token
    TELEGRAM_CHAT_ID=       # boş bırakılabilir: bota bir mesaj yaz, `--test` bulup dosyaya ekler
    WHATSAPP_PHONE=         # CallMeBot: ülke koduyla numaran (+90...)
    CALLMEBOT_APIKEY=       # CallMeBot botuna "I allow callmebot to send me messages" yazınca gelen anahtar
Hangi ikili doluysa o kanal açılır; ikisi de doluysa mesaj ikisine de gider. Dosya yoksa ya da boşsa bildirim
kapalıdır. Çalışan süreç dosyayı dakikada bir yeniden okur: anahtarları ekleyince yeniden başlatmak gerekmez.

    python -m uv run python -m trend.live.notify --test     # deneme mesajı (gerekirse Telegram sohbet kimliğini bulur)

Gönderim arka plan iş parçacığında yapılır, `send` beklemez. Aynı anda gelen mesajlar `batch_s` içinde tek mesajda
birleştirilir. Ağ hatası, 429 ve 5xx yanıtları yeniden denenir; başka yanıtlar denenmez (çift mesaj olmasın).
Başarısızlıklar `errors` kuyruğuna düşer; çalıştırıcı bunları SQLite'a ana iş parçacığında yazar. Yalnızca
api.telegram.org ve api.callmebot.com adreslerine bağlanılır; hata metinlerinde anahtarlar maskelenir.
"""

from __future__ import annotations

import argparse
import json
import queue
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from pathlib import Path

from trend.config import ROOT

ENV_PATH = ROOT / ".env.bildirim"
HOSTS = ("api.telegram.org", "api.callmebot.com")
TELEGRAM, WHATSAPP = "telegram", "whatsapp"
LIMIT = {TELEGRAM: 3500, WHATSAPP: 1000}       # tek mesaj karakter sınırı (Telegram 4096; CallMeBot metni URL'de)
KEYS = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "WHATSAPP_PHONE", "CALLMEBOT_APIKEY")
TEMPLATE = """\
# Telefon bildirimi (trend.live.notify). Bu dosya git'e girmez. Bir kanal yeter; ikisi de doluysa ikisine gider.
# Telegram: @BotFather'a /newbot yaz, verdiği token'ı aşağıya yapıştır, sonra bota Telegram'dan /start yaz.
#           TELEGRAM_CHAT_ID boş kalabilir: `python -m uv run python -m trend.live.notify --test` bulup ekler.
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
# WhatsApp (CallMeBot): botun numarasına "I allow callmebot to send me messages" yaz, gelen anahtarı yapıştır.
WHATSAPP_PHONE=
CALLMEBOT_APIKEY=
"""
_STOP = object()


def load_creds(path) -> dict:
    """KEY=DEĞER satırları (# yorum, boş satır, tırnak); yalnızca KEYS ve dolu değerler."""
    p = Path(path)
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.split(" #")[0].strip().strip('"').strip("'")
        if k in KEYS and v:
            out[k] = v
    return out


def channels(creds: dict) -> list[str]:
    out = []
    if creds.get("TELEGRAM_BOT_TOKEN") and creds.get("TELEGRAM_CHAT_ID"):
        out.append(TELEGRAM)
    if creds.get("WHATSAPP_PHONE") and creds.get("CALLMEBOT_APIKEY"):
        out.append(WHATSAPP)
    return out


def scrub(text: str, creds: dict) -> str:
    for k in ("TELEGRAM_BOT_TOKEN", "CALLMEBOT_APIKEY", "WHATSAPP_PHONE"):
        v = creds.get(k)
        if v and len(v) >= 4:
            text = text.replace(v, "***").replace(urllib.parse.quote_plus(v), "***")
    return text


def http_request(url: str, data: dict | None = None, timeout: float = 20.0) -> tuple[int, str]:
    """(durum kodu, gövde); yalnızca HOSTS üzerinde https. `data` verilirse form POST."""
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or u.hostname not in HOSTS:
        raise ValueError(f"izin verilmeyen adres: {u.scheme}://{u.hostname}")
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers={"User-Agent": "trend-live-notify"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def send_one(channel: str, creds: dict, text: str, http=http_request) -> tuple[bool, bool, str]:
    """(başarılı, yeniden denensin mi, bilgi)."""
    if channel == TELEGRAM:
        st, body = http(f"https://api.telegram.org/bot{creds['TELEGRAM_BOT_TOKEN']}/sendMessage",
                        {"chat_id": creds["TELEGRAM_CHAT_ID"], "text": text, "disable_web_page_preview": "true"})
        try:
            ok = st == 200 and bool(json.loads(body).get("ok"))
        except ValueError:
            ok = False
    elif channel == WHATSAPP:
        q = urllib.parse.urlencode({"phone": creds["WHATSAPP_PHONE"], "text": text,
                                    "apikey": creds["CALLMEBOT_APIKEY"]})
        st, body = http(f"https://api.callmebot.com/whatsapp.php?{q}")
        low = body.lower()
        ok = st == 200 and "invalid" not in low and "paused" not in low     # bilinen hata yanıtları
    else:
        raise ValueError(f"bilinmeyen kanal: {channel}")
    return ok, (st == 429 or st >= 500), f"{st} {body[:200]}"


def pack(texts: list[str], limit: int) -> list[str]:
    """Mesajları boş satırla birleştirir; her parça ≤ limit (tek başına uzun mesaj kırpılır)."""
    out, cur = [], ""
    for t in texts:
        t = t if len(t) <= limit else t[: limit - 1] + "…"
        if cur and len(cur) + 2 + len(t) > limit:
            out.append(cur)
            cur = ""
        cur = f"{cur}\n\n{t}" if cur else t
    if cur:
        out.append(cur)
    return out


class Notifier:
    """Arka plan gönderici; `send` beklemez. Açık kanal yoksa mesajlar sayılıp atılır."""

    def __init__(self, path=ENV_PATH, *, header: str = "", http=http_request, batch_s: float = 3.0,
                 reload_s: float = 60.0, retry_s: tuple = (5.0, 30.0), max_queue: int = 200, sleep=time.sleep,
                 clock=time.monotonic, start: bool = True):
        self.path = Path(path)
        self.header = header
        self.http, self.sleep, self.clock = http, sleep, clock
        self.batch_s, self.reload_s, self.retry_s, self.max_queue = float(batch_s), float(reload_s), retry_s, max_queue
        self.errors: deque = deque(maxlen=100)
        self.stats: dict[str, int] = defaultdict(int)
        self._q: queue.Queue = queue.Queue()
        self._keys: dict[str, float] = {}
        self._creds: dict = {}
        self._stamp = None
        self._next_load = -float("inf")
        self._thread: threading.Thread | None = None
        if start:
            self.start()

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="notify", daemon=True)
            self._thread.start()

    def creds(self) -> dict:
        """Dosya değiştiyse (`reload_s`'de bir bakılır) yeniden okunan anahtarlar."""
        now = self.clock()
        if now >= self._next_load:
            self._next_load = now + self.reload_s
            try:
                st = self.path.stat()
                stamp = (st.st_mtime_ns, st.st_size)
            except OSError:
                stamp = None
            if stamp != self._stamp:
                self._stamp = stamp
                self._creds = load_creds(self.path) if stamp else {}
        return self._creds

    def send(self, text: str, key: str | None = None, every_s: float = 0.0) -> bool:
        """Kuyruğa ekler; aynı `key` için `every_s` saniyede en fazla bir mesaj."""
        if key is not None:
            now = self.clock()
            last = self._keys.get(key)
            if last is not None and now - last < every_s:
                self.stats["throttled"] += 1
                return False
            self._keys[key] = now
        if self._q.qsize() >= self.max_queue:
            self.stats["dropped"] += 1
            return False
        self._q.put(text)
        return True

    def deliver(self, texts: list[str]) -> int:
        """Birleştirip açık kanallara gönderir (eşzamanlı); başarılı gönderim sayısı."""
        creds = self.creds()
        chans = channels(creds)
        if not chans:
            self.stats["no_channel"] += len(texts)
            return 0
        n = 0
        for ch in chans:
            room = LIMIT[ch] - (len(self.header) + 1 if self.header else 0)
            for chunk in pack(texts, room):
                n += self._send_retry(ch, creds, f"{self.header}\n{chunk}" if self.header else chunk)
        return n

    def _send_retry(self, ch: str, creds: dict, text: str) -> int:
        attempt, info = 0, ""
        for attempt in range(len(self.retry_s) + 1):
            try:
                ok, retry, info = send_one(ch, creds, text, self.http)
            except Exception as e:  # noqa: BLE001 — ağ hatası: yeniden dene
                ok, retry, info = False, True, repr(e)
            if ok:
                self.stats[f"sent_{ch}"] += 1
                return 1
            if not retry or attempt == len(self.retry_s):
                break
            self.sleep(self.retry_s[attempt])
        self.stats[f"failed_{ch}"] += 1
        self.errors.append({"channel": ch, "attempts": attempt + 1, "info": scrub(info, creds)[:300]})
        return 0

    def drain_errors(self) -> list[dict]:
        out = []
        while self.errors:
            out.append(self.errors.popleft())
        return out

    def _run(self) -> None:
        while True:
            item = self._q.get()
            if item is _STOP:
                return
            batch, stop = [item], False
            end = time.monotonic() + self.batch_s
            while (left := end - time.monotonic()) > 0:
                try:
                    x = self._q.get(timeout=left)
                except queue.Empty:
                    break
                if x is _STOP:
                    stop = True
                    break
                batch.append(x)
            try:
                self.deliver(batch)
            except Exception as e:  # noqa: BLE001 — gönderici durmaz
                self.errors.append({"channel": None, "info": scrub(repr(e), self._creds)[:300]})
            if stop:
                return

    def close(self, timeout: float = 15.0) -> None:
        """Kuyruktakileri gönderip durur (en fazla `timeout` sn bekler)."""
        if self._thread is not None and self._thread.is_alive():
            self._q.put(_STOP)
            self._thread.join(timeout)


def find_chat_id(token: str, http=http_request) -> str | None:
    """Bota yazılan son mesajın sohbet kimliği (getUpdates); yoksa None."""
    st, body = http(f"https://api.telegram.org/bot{token}/getUpdates", {"limit": "50"})
    try:
        d = json.loads(body)
    except ValueError:
        return None
    ids = [u[k]["chat"]["id"] for u in d.get("result") or [] for k in ("message", "edited_message", "channel_post")
           if isinstance(u.get(k), dict) and "chat" in u[k]]
    return str(ids[-1]) if ids else None


def save_chat_id(path, chat_id: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8-sig") if p.exists() else ""
    line = f"TELEGRAM_CHAT_ID={chat_id}"
    new, n = re.subn(r"(?m)^TELEGRAM_CHAT_ID=[ \t]*$", line, text)
    if not n:
        new = text + ("" if not text or text.endswith("\n") else "\n") + line + "\n"
    p.write_text(new, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    from trend.data._http import utf8_stdout
    ap = argparse.ArgumentParser(prog="python -m trend.live.notify", description="Telefon bildirimi (kâğıt takip)")
    ap.add_argument("--test", action="store_true", help="deneme mesajı gönder")
    ap.add_argument("--file", default=str(ENV_PATH), help="anahtar dosyası (varsayılan .env.bildirim)")
    a = ap.parse_args(argv)
    utf8_stdout()
    path = Path(a.file)
    if not path.exists():
        path.write_text(TEMPLATE, encoding="utf-8")
        print(f"şablon yazıldı: {path} — anahtarları doldurup tekrar çalıştır")
        return 1
    creds = load_creds(path)
    if creds.get("TELEGRAM_BOT_TOKEN") and not creds.get("TELEGRAM_CHAT_ID"):
        try:
            cid = find_chat_id(creds["TELEGRAM_BOT_TOKEN"])
        except Exception as e:  # noqa: BLE001
            cid = None
            print("Telegram getUpdates hatası:", scrub(repr(e), creds)[:200])
        if cid:
            save_chat_id(path, cid)
            creds["TELEGRAM_CHAT_ID"] = cid
            print("Telegram sohbet kimliği bulundu ve dosyaya yazıldı")
        else:
            print("Telegram: önce Telegram'dan bota bir mesaj yaz (ör. /start), sonra bunu tekrar çalıştır")
    chans = channels(creds)
    if not chans:
        print("açık kanal yok: .env.bildirim içinde Telegram ya da WhatsApp ikilisini doldur")
        return 1
    if not a.test:
        print("açık kanallar:", ", ".join(chans), "(deneme için --test)")
        return 0
    n = Notifier(path, start=False, retry_s=(3.0,))
    n._creds, n._next_load = creds, float("inf")
    n.deliver(["✅ Deneme: kâğıt takip bildirimleri çalışıyor (gerçek emir yok)."])
    for ch in chans:
        print(f"{ch}: {'gönderildi' if n.stats.get(f'sent_{ch}') else 'HATA'}")
    for e in n.drain_errors():
        print("  ", e)
    return 0 if all(n.stats.get(f"sent_{ch}") for ch in chans) else 1


if __name__ == "__main__":
    raise SystemExit(main())
