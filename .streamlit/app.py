import html
import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Pavel TV", page_icon="▶️", layout="wide",
                   initial_sidebar_state="collapsed")

BASE = "https://iptv-org.github.io/iptv"
PAGE_SIZE, PER_BLOCK, CANDIDATES = 48, 6, 18

# Vos listes M3U intégrées (liens) : elles apparaissent dans « Ma liste ».
EXTRA_M3U = []  # ex. ["https://mon-site.com/ma-liste.m3u"]

# Flux OFFICIELS des chaînes camerounaises, à compléter avec les liens fournis par
# les chaînes elles-mêmes (.m3u8) : {"name": "Canal 2 International", "url": "https://…m3u8", "logo": ""}
CM_OFFICIEL = []

LEAGUES = {  # identifiants TheSportsDB (calendrier des matchs)
    "🏆 Ligue des champions": 4480, "🏴 Premier League": 4328, "🇫🇷 Ligue 1": 4334,
    "🇪🇸 Liga": 4335, "🇮🇹 Serie A": 4332, "🇩🇪 Bundesliga": 4331,
}
TIMEZONES = {"Cameroun": "Africa/Douala", "France": "Europe/Paris", "Maroc": "Africa/Casablanca",
             "Côte d'Ivoire": "Africa/Abidjan", "Sénégal": "Africa/Dakar", "Canada (Montréal)": "America/Toronto"}

# ---------------------------------------------------------------- Données
POPULAR = [
    "TF1", "France 2", "France 3", "M6", "France 5", "Arte", "C8", "W9", "TMC",
    "TFX", "NRJ 12", "France 4", "BFM TV", "CNews", "LCI", "franceinfo",
    "France 24", "Euronews", "RMC Story", "RMC Decouverte", "Gulli", "6ter",
    "L'Equipe", "Canal+", "Eurosport 1", "Eurosport 2", "beIN Sports 1",
    "RMC Sport 1", "TV5Monde", "LCP", "Paris Premiere", "CStar", "Cherie 25",
    "CRTV", "Canal 2 International", "Equinoxe TV", "Vision 4", "Africa 24",
    "Al Jazeera", "BBC News", "DW", "Red Bull TV",
]
LANGS = {
    "Français": "fra", "English": "eng", "Español": "spa", "العربية": "ara",
    "Português": "por", "Deutsch": "deu", "Italiano": "ita", "Türkçe": "tur",
    "Русский": "rus", "Nederlands": "nld", "Polski": "pol",
}
COUNTRIES = {
    "fr": "France", "cm": "Cameroun", "ci": "Côte d'Ivoire", "sn": "Sénégal",
    "ma": "Maroc", "dz": "Algérie", "tn": "Tunisie", "be": "Belgique",
    "ch": "Suisse", "ca": "Canada", "gb": "Royaume-Uni", "us": "États-Unis",
    "es": "Espagne", "de": "Allemagne", "it": "Italie", "pt": "Portugal",
    "tr": "Turquie", "br": "Brésil", "mx": "Mexique", "ar": "Argentine",
    "ru": "Russie", "in": "Inde", "ae": "Émirats arabes unis", "qa": "Qatar",
    "eg": "Égypte", "nl": "Pays-Bas", "pl": "Pologne",
}
COUNTRY_PRIORITY = {c: i for i, c in enumerate(["fr", "cm", "ci", "sn", "ma", "be", "ch", "ca"])}
FR_COUNTRIES = {"fr", "cm", "ci", "sn", "ma", "be", "ch", "ca", "dz", "tn"}

# Paliers : (id, emoji, titre, palier du menu)
BLOCKS = [
    ("pop", "🔥", "Les plus regardées", "À la une"),
    ("frall", "🗣️", "Toutes les chaînes en français", "Francophone"),
    ("fr", "🇫🇷", "Chaînes françaises", "Francophone"),
    ("film", "🎬", "Films et séries en français", "Francophone"),
    ("cm", "🇨🇲", "Chaînes camerounaises", "Afrique"),
    ("ci", "🇨🇮", "Chaînes ivoiriennes", "Afrique"),
    ("sn", "🇸🇳", "Chaînes sénégalaises", "Afrique"),
    ("ma", "🇲🇦", "Chaînes marocaines", "Afrique"),
    ("sport", "⚽", "Toutes les chaînes sportives", "Sport"),
    ("bein", "🟣", "beIN Sports", "Sport"),
    ("canal", "🔷", "Bouquet Canal+", "Bouquets"),
    ("news", "📰", "Actualités", "Thématiques"),
    ("ent", "🎭", "Divertissement", "Thématiques"),
    ("doc", "📚", "Documentaires", "Thématiques"),
]
LABEL = {b[0]: f"{b[1]} {b[2]}" for b in BLOCKS}
BLOCK_BY_LABEL = {LABEL[b[0]]: b[0] for b in BLOCKS}
HOME_BLOCKS = ["pop", "fr", "cm", "sport", "bein", "canal", "film", "ci", "news"]
COUNTRY_BLOCKS = ["fr", "cm", "ci", "sn", "ma"]
CATEGORY_FILES = {
    "sport": "categories/sports.m3u", "news": "categories/news.m3u",
    "ent": "categories/entertainment.m3u", "doc": "categories/documentary.m3u",
    "movies": "categories/movies.m3u", "series": "categories/series.m3u",
}
PROBE_EXEMPT = {"canal"}

HOME, FAVS, LANG, COUNTRY, CUSTOM, MATCHES = (
    "🏠 Accueil", "⭐ Favoris", "🗣️ Par langue", "🌍 Par pays", "📎 Ma liste", "📅 Matchs et championnats",
)
ATTR = re.compile(r'([\w-]+)="([^"]*)"')
COUNTRY_IN_ID = re.compile(r"\.([a-z]{2})(?:@|$)")
CANAL = re.compile(r"canal\s*(\+|plus)|\b(cstar|c8|cnews)\b|(cin[eé]|planete)\s*\+", re.I)
BEIN = re.compile(r"bein\s*sport", re.I)
CM = re.compile(r"crtv|canal\s*2|equinoxe|vision\s*4|cameroun|cameroon|mboa|afrique\s*media", re.I)
FILMS = re.compile(r"cin[eé]ma|cin[eé]\s*\+|\baction\b|\bocs\b|paramount|\btcm\b|polar|film|s[eé]rie", re.I)


def norm(s):
    s = re.sub(r"[\(\[].*?[\)\]]", "", s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]", "", s)
    return re.sub(r"(fhd|uhd|hd)$", "", s)


RANK = {norm(n): i for i, n in enumerate(POPULAR)}


def flag(code):
    code = {"uk": "gb"}.get(code, code)
    if len(code) == 2 and code.isalpha():
        return "".join(chr(0x1F1E6 + ord(c) - 97) for c in code.lower())
    return "🌐"


def parse_m3u(text, default_country=""):
    out, seen = [], set()
    attrs = name = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            attrs = {k.lower(): v for k, v in ATTR.findall(line)}
            q = line.rfind('"')
            c = line.find(",", max(q, 0))
            name = line[c + 1:].strip() if c >= 0 else ""
            name = name or attrs.get("tvg-name") or "Chaîne"
        elif line.startswith("#"):
            continue
        elif attrs is not None and line.startswith("http"):
            if line not in seen:
                seen.add(line)
                m = COUNTRY_IN_ID.search(attrs.get("tvg-id", "").lower())
                out.append({
                    "name": name, "url": line, "logo": attrs.get("tvg-logo") or "",
                    "country": m.group(1) if m else default_country,
                    "group": attrs.get("group-title") or "", "key": norm(name),
                })
            attrs = name = None
    return out


@st.cache_resource
def raw_cache():
    return {}


RAW = raw_cache()


def fetch(url, default_country=""):
    hit = RAW.get(url)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    r = requests.get(url, timeout=40, headers={"User-Agent": "PavelTV/2.0"})
    r.raise_for_status()
    data = parse_m3u(r.text, default_country)
    RAW[url] = (time.time(), data)
    return data


def fetch_all(sources):
    def one(src):
        try:
            return src[0], fetch(*src)
        except Exception:
            return src[0], None

    with ThreadPoolExecutor(max_workers=12) as ex:
        return dict(ex.map(one, sources))


def dedupe(lists):
    seen, out = set(), []
    for lst in lists:
        for c in lst or []:
            if c["url"] not in seen:
                seen.add(c["url"])
                out.append(c)
    return out


def sort_channels(chs):
    return sorted(chs, key=lambda c: (
        RANK.get(c["key"], 999), COUNTRY_PRIORITY.get(c["country"], 99),
        0 if c["logo"] else 1, c["name"].lower(),
    ))


# ------------------------------------------------------- Test des flux
@st.cache_resource
def probe_cache():
    return {}


PROBES = probe_cache()


def probe(url):
    if url in PROBES:
        return PROBES[url]
    try:
        r = requests.get(url, timeout=(4, 5), stream=True,
                         headers={"User-Agent": "Mozilla/5.0", "Origin": "https://share.streamlit.io"})
        status = r.status_code
        acao = r.headers.get("access-control-allow-origin", "")
        head = next(r.iter_content(chunk_size=64), b"")
        r.close()
        if status != 200:
            res = (False, f"réponse HTTP {status} (hors ligne ou géo-bloqué)")
        elif head.lstrip().startswith(b"<"):
            res = (False, "le lien renvoie une page web, pas un flux vidéo")
        elif not acao:
            res = (False, "le serveur de la chaîne interdit la lecture dans un navigateur (CORS)")
        else:
            res = (True, "ok")
    except Exception:
        res = (False, "serveur injoignable ou trop lent")
    PROBES[url] = res
    return res


def probe_many(urls):
    todo = [u for u in dict.fromkeys(urls) if u not in PROBES]
    if todo:
        with ThreadPoolExecutor(max_workers=48) as ex:
            list(ex.map(probe, todo))
    return {u: PROBES[u][0] for u in urls if u in PROBES}


def playable_channels(chs, needed):
    ok, i = [], 0
    while len(ok) <= needed and i < len(chs):
        batch = chs[i:i + PAGE_SIZE]
        i += PAGE_SIZE
        good = probe_many([c["url"] for c in batch])
        ok += [c for c in batch if good.get(c["url"])]
    return ok[:needed], (len(ok) > needed or i < len(chs))


# ------------------------------------------------------------ Style
LOGO_SVG = """
<svg width="52" height="52" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
<defs><linearGradient id="pg" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#7C3AED"/><stop offset=".55" stop-color="#EC4899"/>
<stop offset="1" stop-color="#F59E0B"/></linearGradient></defs>
<rect x="2" y="2" width="60" height="60" rx="17" fill="url(#pg)"/>
<path d="M25 17 L25 47 L48 32 Z" fill="#fff"/></svg>
"""

CSS = """
<style>
.stApp{background:
  radial-gradient(1100px 520px at 8% -8%, rgba(124,58,237,.38), transparent 60%),
  radial-gradient(900px 480px at 100% 0%, rgba(236,72,153,.28), transparent 55%), #0A0A1A;}
#MainMenu, footer{visibility:hidden;}
section[data-testid="stSidebar"]{background:#0E0E22;border-right:1px solid rgba(255,255,255,.07);}
.block-container{padding-top:1.4rem;max-width:1300px;}
.hero{display:flex;align-items:center;gap:16px;padding:18px 24px;border-radius:24px;margin-bottom:14px;
  background:linear-gradient(135deg,rgba(124,58,237,.38),rgba(236,72,153,.26),rgba(245,158,11,.20));
  border:1px solid rgba(255,255,255,.14);box-shadow:0 10px 40px rgba(124,58,237,.25);}
.brand-name{font-size:34px;font-weight:900;letter-spacing:1px;line-height:1;color:#fff;}
.brand-name span{background:linear-gradient(135deg,#EC4899,#F59E0B);-webkit-background-clip:text;
  background-clip:text;color:transparent;margin-left:6px;}
.tagline{color:rgba(255,255,255,.72);font-size:14px;margin-top:6px;}
.bt{display:flex;align-items:center;gap:12px;margin:26px 0 12px;font-size:22px;font-weight:800;color:#fff;}
.bt::before{content:"";width:6px;height:28px;border-radius:6px;
  background:linear-gradient(180deg,#8B5CF6,#EC4899,#F59E0B);}
.bt small{font-size:12px;font-weight:700;color:#fff;padding:3px 10px;border-radius:999px;background:rgba(255,255,255,.12);}
.grp{font-size:12px;font-weight:800;letter-spacing:.5px;color:#EC4899;margin:12px 0 2px;}

/* Bouton menu moderne (pilule dégradée) */
[data-testid="stPopover"] button,[data-testid="stPopoverButton"]{
  border-radius:999px!important;padding:.65rem 1.5rem!important;font-weight:800!important;font-size:15px!important;
  background:linear-gradient(135deg,#7C3AED,#EC4899)!important;color:#fff!important;border:0!important;
  box-shadow:0 8px 26px rgba(124,58,237,.5);transition:transform .15s ease,box-shadow .15s ease;}
[data-testid="stPopover"] button:hover{transform:translateY(-2px);box-shadow:0 12px 32px rgba(236,72,153,.55);}

[class*="st-key-card_"]{background:linear-gradient(160deg,rgba(255,255,255,.08),rgba(255,255,255,.02));
  border:1px solid rgba(255,255,255,.10);border-radius:20px;padding:12px;transition:all .2s ease;}
[class*="st-key-card_"]:hover{transform:translateY(-4px);border-color:rgba(236,72,153,.7);
  box-shadow:0 12px 30px rgba(236,72,153,.22);}
.tile{height:84px;border-radius:14px;background:rgba(255,255,255,.96);display:flex;
  align-items:center;justify-content:center;margin-bottom:10px;overflow:hidden;}
.tile img{max-height:64px;max-width:86%;object-fit:contain;}
.tile .ph{font-size:38px;}
.cname{font-size:13px;font-weight:700;color:#fff;text-align:center;min-height:36px;line-height:1.3;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;margin-bottom:8px;}
.stButton>button{width:100%;border-radius:12px;font-weight:700;border:1px solid rgba(255,255,255,.14);}
button[data-testid="stBaseButton-primary"], button[kind="primary"]{
  background:linear-gradient(135deg,#7C3AED,#EC4899);border:0;color:#fff;}
.stTextInput input{border-radius:999px;background:rgba(255,255,255,.07);
  border:1px solid rgba(255,255,255,.14);padding:12px 18px;}
.mrow{display:flex;align-items:center;gap:14px;padding:11px 16px;margin-bottom:8px;border-radius:14px;
  background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.09);color:#fff;font-size:14px;}
.mrow span{min-width:92px;font-weight:800;color:#F59E0B;}
@media (max-width:1000px){
  [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;gap:.6rem!important;}
  [data-testid="stHorizontalBlock"]>div{flex:1 1 calc(33.33% - .8rem)!important;min-width:calc(33.33% - .8rem)!important;}
}
@media (max-width:640px){
  [data-testid="stHorizontalBlock"]>div{flex:1 1 calc(50% - .8rem)!important;min-width:calc(50% - .8rem)!important;}
  .brand-name{font-size:26px;} .hero{padding:14px 16px;}
}
</style>
"""

HERO = f"""
<div class="hero">{LOGO_SVG}
  <div><div class="brand-name">PAVEL<span>TV</span></div>
  <div class="tagline">La télévision du monde, partout avec vous</div></div>
</div>
"""

PLAYER_HTML = """
<video id="v" controls autoplay playsinline
  style="width:100%;max-height:60vh;background:#000;border-radius:14px"></video>
<p id="err" style="color:#ff8a8a;font-family:sans-serif;font-size:14px"></p>
<script src="https://cdn.jsdelivr.net/npm/hls.js@1.5.15"></script>
<script>
  const url = __URL__, raw = __RAW__;
  const v = document.getElementById('v'), err = document.getElementById('err');
  function fail(m) {
    err.innerHTML = '⚠️ Flux indisponible : ' + m +
      '<br><a style="color:#8ab4ff" target="_blank" href="' + raw + '">Ouvrir le flux dans un nouvel onglet</a>' +
      ' · ou collez le lien dans VLC.';
  }
  if (location.protocol === 'https:' && raw.startsWith('http:')) {
    fail('lien non sécurisé (HTTP) bloqué par le navigateur.');
  } else if (window.Hls && Hls.isSupported()) {
    const h = new Hls({manifestLoadingMaxRetry: 2, levelLoadingMaxRetry: 2, fragLoadingMaxRetry: 3});
    let retried = false, fixed = false;
    h.loadSource(url); h.attachMedia(v);
    h.on(Hls.Events.ERROR, (e, d) => {
      if (!d.fatal) return;
      if (d.type === Hls.ErrorTypes.MEDIA_ERROR && !fixed) { fixed = true; h.recoverMediaError(); return; }
      if (d.type === Hls.ErrorTypes.NETWORK_ERROR && !retried) { retried = true; h.startLoad(); return; }
      const code = d.response ? d.response.code : 0;
      fail(code === 0 ? 'bloqué par le serveur de la chaîne (CORS) ou hors ligne.'
        : code === 403 || code === 451 ? 'accès refusé (géo-blocage probable).'
        : 'chaîne hors ligne (HTTP ' + code + ').');
    });
  } else if (v.canPlayType('application/vnd.apple.mpegurl')) {
    v.src = url; v.onerror = () => fail('lecture impossible.');
  } else { v.src = url; v.onerror = () => fail('format non pris en charge.'); }
</script>
"""


def player(url):
    proxy = st.session_state.get("proxy", "").strip()
    final = proxy + quote(url, safe="") if proxy else url
    components.html(PLAYER_HTML.replace("__URL__", json.dumps(final)).replace("__RAW__", json.dumps(url)),
                    height=470)


# -------------------------------------------------------------- État
st.session_state.setdefault("favs", {})
st.session_state.setdefault("custom", [])
st.session_state.setdefault("shown", PAGE_SIZE)
st.session_state.setdefault("nav", HOME)


def go(label):
    st.session_state.nav = label


def toggle_fav(ch):
    favs = st.session_state.favs
    if ch["url"] in favs:
        del favs[ch["url"]]
    else:
        favs[ch["url"]] = ch


def more_channels():
    st.session_state.shown += PAGE_SIZE


def add_custom(chs):
    st.session_state.custom = dedupe([st.session_state.custom, chs])


@st.dialog("▶ Pavel TV", width="large")
def watch(ch):
    st.markdown(f"#### 🔴 {ch['name']}")
    known = PROBES.get(ch["url"])
    if known and not known[0]:
        st.warning(f"Ce flux risque de ne pas se lire ici : {known[1]}.")
    player(ch["url"])
    is_fav = ch["url"] in st.session_state.favs
    st.button("💔 Retirer des favoris" if is_fav else "❤️ Ajouter aux favoris",
              key="dlg_fav", on_click=toggle_fav, args=(ch,))
    st.caption("📡 Sur TV : Chrome ⋮ → « Enregistrer, partager et caster » → « Caster… », "
               "ou copiez ce lien dans VLC / une appli Cast.")
    st.code(ch["url"], language=None)


def card(ch, prefix, i):
    with st.container(key=f"card_{prefix}_{i}"):
        if ch["logo"]:
            img = (f'<img src="{html.escape(ch["logo"], quote=True)}" alt="" '
                   f'loading="lazy" referrerpolicy="no-referrer">')
        else:
            img = '<span class="ph">📺</span>'
        heart = "❤️ " if ch["url"] in st.session_state.favs else ""
        fl = f"{flag(ch['country'])} " if ch["country"] else ""
        st.markdown(f'<div class="tile">{img}</div>'
                    f'<div class="cname">{heart}{fl}{html.escape(ch["name"])}</div>',
                    unsafe_allow_html=True)
        if st.button("▶ Regarder", key=f"play_{prefix}_{i}", type="primary"):
            watch(ch)


def grid(items, prefix, per_row=6):
    for start in range(0, len(items), per_row):
        cols = st.columns(per_row)
        for j, col in enumerate(cols):
            if start + j < len(items):
                with col:
                    card(items[start + j], prefix, start + j)


def block_title(text, count=None):
    badge = f"<small>{count}</small>" if count is not None else ""
    st.markdown(f'<div class="bt">{html.escape(text)}{badge}</div>', unsafe_allow_html=True)


# ------------------------------------------------------ Réglages
st.markdown(CSS, unsafe_allow_html=True)
with st.sidebar:
    st.markdown(f'<div style="display:flex;align-items:center;gap:10px">{LOGO_SVG}'
                f'<div class="brand-name" style="font-size:26px">PAVEL<span>TV</span></div></div>',
                unsafe_allow_html=True)
    st.markdown("### ⚙️ Réglages")
    only_playable = st.checkbox("Masquer les flux qui ne marchent pas ici", value=True,
                                help="Teste chaque flux et ne garde que ceux que le navigateur peut lire.")
    https_only = st.checkbox("Flux HTTPS uniquement", value=True)
    logo_only = st.checkbox("Seulement les chaînes avec logo", value=False)
    st.selectbox("Fuseau horaire des matchs", list(TIMEZONES), key="tzname")
    st.text_input("Proxy CORS (optionnel)", key="proxy", placeholder="https://mon-proxy.workers.dev/?url=",
                  help="Si une chaîne affiche « CORS », un proxy à vous (ex. Cloudflare Worker) peut la débloquer.")
    with st.expander("💾 Sauvegarder / restaurer"):
        st.download_button("Télécharger favoris + ma liste",
                           json.dumps({"favs": list(st.session_state.favs.values()),
                                       "custom": st.session_state.custom}, ensure_ascii=False),
                           file_name="pavel_tv.json", mime="application/json")
        up = st.file_uploader("Restaurer", type="json")
        if up is not None:
            try:
                data = json.load(up)
                favs, cus = (data, []) if isinstance(data, list) else (data.get("favs", []), data.get("custom", []))
                for c in favs:
                    st.session_state.favs[c["url"]] = c
                add_custom(cus)
                st.success("Restauré.")
            except Exception:
                st.error("Fichier invalide.")

# ------------------------------------------------------ Chargement
sources = (
    [(f"{BASE}/countries/{c}.m3u", c) for c in COUNTRY_BLOCKS]
    + [(f"{BASE}/{p}", "") for p in CATEGORY_FILES.values()]
    + [(f"{BASE}/languages/fra.m3u", ""), (f"{BASE}/index.m3u", "")]
    + [(u, "") for u in EXTRA_M3U]
)
with st.spinner("Chargement des chaînes…"):
    pools = fetch_all(sources)

P = lambda path: pools.get(f"{BASE}/{path}") or []
fra = P("languages/fra.m3u")
fra_urls = {c["url"] for c in fra}
extra = dedupe([pools.get(u) for u in EXTRA_M3U])
official = [{"name": o["name"], "url": o["url"], "logo": o.get("logo", ""), "country": "cm",
             "group": "Cameroun (officiel)", "key": norm(o["name"])} for o in CM_OFFICIEL]
ALL = dedupe([*[P(f"countries/{c}.m3u") for c in COUNTRY_BLOCKS],
              *[P(p) for p in CATEGORY_FILES.values()], fra, P("index.m3u"),
              official, extra, st.session_state.custom])

RAW_BLOCKS = {c: sort_channels(P(f"countries/{c}.m3u")) for c in COUNTRY_BLOCKS}
for k in ("sport", "news", ,
    "🇪🇸 Liga": 4335, "🇮🇹 Serie A": 4332, "🇩🇪 Bundesliga": 4331,}
TIMEZONES = {"Cameroun": "Africa/Douala", "France": "Europe/Paris", "Maroc": "Africa/Casablanca",
             "Côte d'Ivoire": "Africa/Abidjan", "Sénégal": "Africa/Dakar", "Canada (Montréal)": "America/Toronto"}

# ---------------------------------------------------------------- Données
POPULAR = [
    "TF1", "France 2", "France 3", "M6", "France 5", "Arte", "C8", "W9", "TMC",
    "TFX", "NRJ 12", "France 4", "BFM TV", "CNews", "LCI", "franceinfo",
    "France 24", "Euronews", "RMC Story", "RMC Decouverte", "Gulli", "6ter",
    "L'Equipe", "Canal+", "Eurosport 1", "Eurosport 2", "beIN Sports 1",
    "RMC Sport 1", "TV5Monde", "LCP", "Paris Premiere", "CStar", "Cherie 25",
    "CRTV", "Canal 2 International", "Equinoxe TV", "Vision 4", "Africa 24",
    "Al Jazeera", "BBC News", "DW", "Red Bull TV",
]
LANGS = {
    "Français": "fra", "English": "eng", "Español": "spa", "العربية": "ara",
    "Português": "por", "Deutsch": "deu", "Italiano": "ita", "Türkçe": "tur",
    "Русский": "rus", "Nederlands": "nld", "Polski": "pol",
}
COUNTRIES = {
    "fr": "France", "cm": "Cameroun", "ci": "Côte d'Ivoire", "sn": "Sénégal",
    "ma": "Maroc", "dz": "Algérie", "tn": "Tunisie", "be": "Belgique",
    "ch": "Suisse", "ca": "Canada", "gb": "Royaume-Uni", "us": "États-Unis",
    "es": "Espagne", "de": "Allemagne", "it": "Italie", "pt": "Portugal",
    "tr": "Turquie", "br": "Brésil", "mx": "Mexique", "ar": "Argentine",
    "ru": "Russie", "in": "Inde", "ae": "Émirats arabes unis", "qa": "Qatar",
    "eg": "Égypte", "nl": "Pays-Bas", "pl": "Pologne",
}
COUNTRY_PRIORITY = {c: i for i, c in enumerate(["fr", "cm", "ci", "sn", "ma", "be", "ch", "ca"])}
FR_COUNTRIES = {"fr", "cm", "ci", "sn", "ma", "be", "ch", "ca", "dz", "tn"}

# Paliers : (id, emoji, titre, palier du menu)
BLOCKS = [
    ("pop", "🔥", "Les plus regardées", "À la une"),
    ("frall", "🗣️", "Toutes les chaînes en français", "Francophone"),
    ("fr", "🇫🇷", "Chaînes françaises", "Francophone"),
    ("film", "🎬", "Films et séries en français", "Francophone"),
    ("cm", "🇨🇲", "Chaînes camerounaises", "Afrique"),
    ("ci", "🇨🇮", "Chaînes ivoiriennes", "Afrique"),
    ("sn", "🇸🇳", "Chaînes sénégalaises", "Afrique"),
    ("ma", "🇲🇦", "Chaînes marocaines", "Afrique"),
    ("sport", "⚽", "Toutes les chaînes sportives", "Sport"),
    ("bein", "🟣", "beIN Sports", "Sport"),
    ("canal", "🔷", "Bouquet Canal+", "Bouquets"),
    ("news", "📰", "Actualités", "Thématiques"),
    ("ent", "🎭", "Divertissement", "Thématiques"),
    ("doc", "📚", "Documentaires", "Thématiques"),
]
LABEL = {b[0]: f"{b[1]} {b[2]}" for b in BLOCKS}
BLOCK_BY_LABEL = {LABEL[b[0]]: b[0] for b in BLOCKS}
HOME_BLOCKS = ["pop", "fr", "cm", "sport", "bein", "canal", "film", "ci", "news"]
COUNTRY_BLOCKS = ["fr", "cm", "ci", "sn", "ma"]
CATEGORY_FILES = {
    "sport": "categories/sports.m3u", "news": "categories/news.m3u",
    "ent": "categories/entertainment.m3u", "doc": "categories/documentary.m3u",
    "movies": "categories/movies.m3u", "series": "categories/series.m3u",}
PROBE_EXEMPT = {"canal"}

HOME, FAVS, LANG, COUNTRY, CUSTOM, MATCHES = (
    "🏠 Accueil", "⭐ Favoris", "🗣️ Par langue", "🌍 Par pays", "📎 Ma liste", "📅 Matchs et championnats",
)
ATTR = re.compile(r'([\w-]+)="([^"]*)"')
COUNTRY_IN_ID = re.compile(r"\.([a-z]{2})(?:@|$)")
CANAL = re.compile(r"canal\s*(\+|plus)|\b(cstar|c8|cnews)\b|(cin[eé]|planete)\s*\+", re.I)
BEIN = re.compile(r"bein\s*sport", re.I)
CM = re.compile(r"crtv|canal\s*2|equinoxe|vision\s*4|cameroun|cameroon|mboa|afrique\s*media", re.I)
FILMS = re.compile(r"cin[eé]ma|cin[eé]\s*\+|\baction\b|\bocs\b|paramount|\btcm\b|polar|film|s[eé]rie", re.I)


def norm(s):
    s = re.sub(r"[\(\[].*?[\)\]]", "", s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]", "", s)
    return re.sub(r"(fhd|uhd|hd)$", "", s)


RANK = {norm(n): i for i, n in enumerate(POPULAR)}


def flag(code):
    code = {"uk": "gb"}.get(code, code)
    if len(code) == 2 and code.isalpha():
        return "".join(chr(0x1F1E6 + ord(c) - 97) for c in code.lower())
    return "🌐"


def parse_m3u(text, default_country=""):
    out, seen = [], set()
    attrs = name = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            attrs = {k.lower(): v for k, v in ATTR.findall(line)}
            q = line.rfind('"')
            c = line.find(",", max(q, 0))
            name = line[c + 1:].strip() if c >= 0 else ""
            name = name or attrs.get("tvg-name") or "Chaîne"
        elif line.startswith("#"):
            continue
        elif attrs is not None and line.startswith("http"):
            if line not in seen:
                seen.add(line)
                m = COUNTRY_IN_ID.search(attrs.get("tvg-id", "").lower())
                out.append({
                    "name": name, "url": line, "logo": attrs.get("tvg-logo") or "",
                    "country": m.group(1) if m else default_country,
                    "group": attrs.get("group-title") or "", "key": norm(name),
                })
            attrs = name = None
    return out
    @st.cache_resource
def raw_cache():
    return {}


RAW = raw_cache()


def fetch(url, default_country=""):
    hit = RAW.get(url)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    r = requests.get(url, timeout=40, headers={"User-Agent": "PavelTV/2.0"})
    r.raise_for_status()
    data = parse_m3u(r.text, default_country)
    RAW[url] = (time.time(), data)
    return data


def fetch_all(sources):
    def one(src):
        try:
            return src[0], fetch(*src)
        except Exception:
            return src[0], None

    with ThreadPoolExecutor(max_workers=12) as ex:
        return dict(ex.map(one, sources))


def dedupe(lists):
    seen, out = set(), []
    for lst in lists:
        for c in lst or []:
            if c["url"] not in seen:
                seen.add(c["url"])
                out.append(c)
    return out


def sort_channels(chs):
    return sorted(chs, key=lambda c: (
        RANK.get(c["key"], 999), COUNTRY_PRIORITY.get(c["country"], 99),
        0 if c["logo"] else 1, c["name"].lower(),
    ))


# ------------------------------------------------------- Test des flux
@st.cache_resource
def probe_cache():
    return {}


PROBES = probe_cache()


def probe(url):
    if url in PROBES:
        return PROBES[url]
    try:
        r = requests.get(url, timeout=(4, 5), stream=True,
                         headers={"User-Agent": "Mozilla/5.0", "Origin": "https://share.streamlit.io"})
        status = r.status_code
        acao = r.headers.get("access-control-allow-origin", "")
        head = next(r.iter_content(chunk_size=64), b"")
        r.close()
        if status != 200:
            res = (False, f"réponse HTTP {status} (hors ligne ou géo-bloqué)")
        elif head.lstrip().startswith(b"<"):
            res = (False, "le lien renvoie une page web, pas un flux vidéo")
        elif not acao:
            res = (False, "le serveur de la chaîne interdit la lecture dans un navigateur (CORS)")
        else:
            res = (True, "ok")
    except Exception:
        res = (False, "serveur injoignable ou trop lent")
    PROBES[url] = res
    return res


def probe_many(urls):
    todo = [u for u in dict.fromkeys(urls) if u not in PROBES]
    if todo:
        with ThreadPoolExecutor(max_workers=48) as ex:
            list(ex.map(probe, todo))
    return {u: PROBES[u][0] for u in urls if u in PROBES}


def playable_channels(chs, needed):
    ok, i = [], 0
    while len(ok) <= needed and i < len(chs):
        batch = chs[i:i + PAGE_SIZE]
        i += PAGE_SIZE
        good = probe_many([c["url"] for c in batch])
        ok += [c for c in batch if good.get(c["url"])]
    return ok[:needed], (len(ok) > needed or i < len(chs))


# ------------------------------------------------------------ Style
LOGO_SVG = """
<svg width="52" height="52" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
<defs><linearGradient id="pg" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#7C3AED"/><stop offset=".55" stop-color="#EC4899"/>
<stop offset="1" stop-color="#F59E0B"/></linearGradient></defs>
<rect x="2" y="2" width="60" height="60" rx="17" fill="url(#pg)"/>
<path d="M25 17 L25 47 L48 32 Z" fill="#fff"/></svg>
CSS = """
<style>
.stApp{background:
  radial-gradient(1100px 520px at 8% -8%, rgba(124,58,237,.38), transparent 60%),
  radial-gradient(900px 480px at 100% 0%, rgba(236,72,153,.28), transparent 55%), #0A0A1A;}
#MainMenu, footer{visibility:hidden;}
section[data-testid="stSidebar"]{background:#0E0E22;border-right:1px solid rgba(255,255,255,.07);}
.block-container{padding-top:1.4rem;max-width:1300px;}
.hero{display:flex;align-items:center;gap:16px;padding:18px 24px;border-radius:24px;margin-bottom:14px;
  background:linear-gradient(135deg,rgba(124,58,237,.38),rgba(236,72,153,.26),rgba(245,158,11,.20));
  border:1px solid rgba(255,255,255,.14);box-shadow:0 10px 40px rgba(124,58,237,.25);}
.brand-name{font-size:34px;font-weight:900;letter-spacing:1px;line-height:1;color:#fff;}
.brand-name span{background:linear-gradient(135deg,#EC4899,#F59E0B);-webkit-background-clip:text;
  background-clip:text;color:transparent;margin-left:6px;}
.tagline{color:rgba(255,255,255,.72);font-size:14px;margin-top:6px;}
.bt{display:flex;align-items:center;gap:12px;margin:26px 0 12px;font-size:22px;font-weight:800;color:#fff;}
.bt::before{content:"";width:6px;height:28px;border-radius:6px;
  background:linear-gradient(180deg,#8B5CF6,#EC4899,#F59E0B);}
.bt small{font-size:12px;font-weight:700;color:#fff;padding:3px 10px;border-radius:999px;background:rgba(255,255,255,.12);}
.grp{font-size:12px;font-weight:800;letter-spacing:.5px;color:#EC4899;margin:12px 0 2px;}

/* Bouton menu moderne (pilule dégradée) */
[data-testid="stPopover"] button,[data-testid="stPopoverButton"]{
  border-radius:999px!important;padding:.65rem 1.5rem!important;font-weight:800!important;font-size:15px!important;
  background:linear-gradient(135deg,#7C3AED,#EC4899)!important;color:#fff!important;border:0!important;
  box-shadow:0 8px 26px rgba(124,58,237,.5);transition:transform .15s ease,box-shadow .15s ease;}
[data-testid="stPopover"] button:hover{transform:translateY(-2px);box-shadow:0 12px 32px rgba(236,72,153,.55);}

[class*="st-key-card_"]{background:linear-gradient(160deg,rgba(255,255,255,.08),rgba(255,255,255,.02));
  border:1px solid rgba(255,255,255,.10);border-radius:20px;padding:12px;transition:all .2s ease;}
[class*="st-key-card_"]:hover{transform:translateY(-4px);border-color:rgba(236,72,153,.7);
  box-shadow:0 12px 30px rgba(236,72,153,.22);}
.tile{height:84px;border-radius:14px;background:rgba(255,255,255,.96);display:flex;
  align-items:center;justify-content:center;margin-bottom:10px;overflow:hidden;}
.tile img{max-height:64px;max-width:86%;object-fit:contain;}
.tile .ph{font-size:38px;}
.cname{font-size:13px;font-weight:700;color:#fff;text-align:center;min-height:36px;line-height:1.3;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;margin-bottom:8px;}
.stButton>button{width:100%;border-radius:12px;font-weight:700;border:1px solid rgba(255,255,255,.14);}
button[data-testid="stBaseButton-primary"], button[kind="primary"]{
  background:linear-gradient(135deg,#7C3AED,#EC4899);border:0;color:#fff;}
.stTextInput input{border-radius:999px;background:rgba(255,255,255,.07);
  border:1px solid rgba(255,255,255,.14);padding:12px 18px;}
.mrow{display:flex;align-items:center;gap:14px;padding:11px 16px;margin-bottom:8px;border-radius:14px;
  background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.09);color:#fff;font-size:14px;}
.mrow span{min-width:92px;font-weight:800;color:#F59E0B;}
@media (max-width:1000px){
  [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;gap:.6rem!important;}
  [data-testid="stHorizontalBlock"]>div{flex:1 1 calc(33.33% - .8rem)!important;min-width:calc(33.33% - .8rem)!important;}
}
@media (max-width:640px){
  [data-testid="stHorizontalBlock"]>div{flex:1 1 calc(50% - .8rem)!important;min-width:calc(50% - .8rem)!important;}
  .brand-name{font-size:26px;} .hero{padding:14px 16px;}
}
</style>
"""

HERO = f"""
<div class="hero">{LOGO_SVG}
  <div><div class="brand-name">PAVEL<span>TV</span></div>
  <div class="tagline">La télévision du monde, partout avec vous</div></div>
</div>
"""

PLAYER_HTML = """
<video id="v" controls autoplay playsinline
  style="width:100%;max-height:60vh;background:#000;border-radius:14px"></video>
<p id="err" style="color:#ff8a8a;font-family:sans-serif;font-size:14px"></p>
<script src="https://cdn.jsdelivr.net/npm/hls.js@1.5.15"></script>
<script>
  const url = __URL__, raw = __RAW__;
  const v = document.getElementById('v'), err = document.getElementById('err');
  function fail(m) {
    err.innerHTML = '⚠️ Flux indisponible : ' + m +
      '<br><a style="color:#8ab4ff" target="_blank" href="' + raw + '">Ouvrir le flux dans un nouvel onglet</a>' +
      ' · ou collez le lien dans VLC.';
  }
  if (location.protocol === 'https:' && raw.startsWith('http:')) {
    fail('lien non sécurisé (HTTP) bloqué par le navigateur.');
  } else if (window.Hls && Hls.isSupported()) {
    const h = new Hls({manifestLoadingMaxRetry: 2, levelLoadingMaxRetry: 2, fragLoadingMaxRetry: 3});
    let retried = false, fixed = false;
    h.loadSource(url); h.attachMedia(v);
    h.on(Hls.Events.ERROR, (e, d) => {
      if (!d.fatal) return;
      if (d.type === Hls.ErrorTypes.MEDIA_ERROR && !fixed) { fixed = true; h.recoverMediaError(); return; }
      if (d.type === Hls.ErrorTypes.NETWORK_ERROR && !retried) { retried = true; h.startLoad(); return; }
      const code = d.response ? d.response.code : 0;
      fail(code === 0 ? 'bloqué par le serveur de la chaîne (CORS) ou hors ligne.'
        : code === 403 || code === 451 ? 'accès refusé (géo-blocage probable).'
        : 'chaîne hors ligne (HTTP ' + code + ').');
    });
  } else if (v.canPlayType('application/vnd.apple.mpegurl')) {
    v.src = url; v.onerror = () => fail('lecture impossible.');
  } else { v.src = url; v.onerror = () => fail('format non pris en charge.'); }
</script>
"""
def player(url):
    proxy = st.session_state.get("proxy", "").strip()
    final = proxy + quote(url, safe="") if proxy else url
    components.html(PLAYER_HTML.replace("__URL__", json.dumps(final)).replace("__RAW__", json.dumps(url)),
                    height=470)


# -------------------------------------------------------------- État
st.session_state.setdefault("favs", {})
st.session_state.setdefault("custom", [])
st.session_state.setdefault("shown", PAGE_SIZE)
st.session_state.setdefault("nav", HOME)


def go(label):
    st.session_state.nav = label


def toggle_fav(ch):
    favs = st.session_state.favs
    if ch["url"] in favs:
        del favs[ch["url"]]
    else:
        favs[ch["url"]] = ch


def more_channels():
    st.session_state.shown += PAGE_SIZE


def add_custom(chs):
    st.session_state.custom = dedupe([st.session_state.custom, chs])


@st.dialog("▶ Pavel TV", width="large")
def watch(ch):
    st.markdown(f"#### 🔴 {ch['name']}")
    known = PROBES.get(ch["url"])
    if known and not known[0]:
        st.warning(f"Ce flux risque de ne pas se lire ici : {known[1]}.")
    player(ch["url"])
    is_fav = ch["url"] in st.session_state.favs
    st.button("💔 Retirer des favoris" if is_fav else "❤️ Ajouter aux favoris",
              key="dlg_fav", on_click=toggle_fav, args=(ch,))
    st.caption("📡 Sur TV : Chrome ⋮ → « Enregistrer, partager et caster » → « Caster… », "
               "ou copiez ce lien dans VLC / une appli Cast.")
    st.code(ch["url"], language=None)


def card(ch, prefix, i):
    with st.container(key=f"card_{prefix}_{i}"):
        if ch["logo"]:
            img = (f'<img src="{html.escape(ch["logo"], quote=True)}" alt="" '
                   f'loading="lazy" referrerpolicy="no-referrer">')
        else:
            img = '<span class="ph">📺</span>'
        heart = "❤️ " if ch["url"] in st.session_state.favs else ""
        fl = f"{flag(ch['country'])} " if ch["country"] else ""
        st.markdown(f'<div class="tile">{img}</div>'
                    f'<div class="cname">{heart}{fl}{html.escape(ch["name"])}</div>',
                    unsafe_allow_html=True)
        if st.button("▶ Regarder", key=f"play_{prefix}_{i}", type="primary"):
            watch(ch)


def grid(items, prefix, per_row=6):
    for start in range(0, len(items), per_row):
        cols = st.columns(per_row)
        for j, col in enumerate(cols):
            if start + j < len(items):
                with col:
                    card(items[start + j], prefix, start + j)


def block_title(text, count=None):
    badge = f"<small>{count}</small>" if count is not None else ""
    st.markdown(f'<div class="bt">{html.escape(text)}{badge}</div>', unsafe_allow_html=True)


# ------------------------------------------------------ Réglages
st.markdown(CSS, unsafe_allow_html=True)
with st.sidebar:
    st.markdown(f'<div style="display:flex;align-items:center;gap:10px">{LOGO_SVG}'
                f'<div class="brand-name" style="font-size:26px">PAVEL<span>TV</span></div></div>',
                unsafe_allow_html=True)
    st.markdown("### ⚙️ Réglages")
    only_playable = st.checkbox("Masquer les flux qui ne marchent pas ici", value=True,
                                help="Teste chaque flux et ne garde que ceux que le navigateur peut lire.")
    https_only = st.checkbox("Flux HTTPS uniquement", value=True)
    logo_only = st.checkbox("Seulement les chaînes avec logo", value=False)
    st.selectbox("Fuseau horaire des matchs", list(TIMEZONES), key="tzname")
    st.text_input("Proxy CORS (optionnel)", key="proxy", placeholder="https://mon-proxy.workers.dev/?url=",
                  help="Si une chaîne affiche « CORS », un proxy à vous (ex. Cloudflare Worker) peut la débloquer.")
    with st.expander("💾 Sauvegarder / restaurer"):
        st.download_button("Télécharger favoris + ma liste",
                           json.dumps({"favs": list(st.session_state.favs.values()),
                                       "custom": st.session_state.custom}, ensure_ascii=False),
                           file_name="pavel_tv.json", mime="application/json")
        up = st.file_uploader("Restaurer", type="json")
        if up is not None:
            try:
                data = json.load(up)
                favs, cus = (data, []) if isinstance(data, list) else (data.get("favs", []), data.get("custom", []))
                for c in favs:
                    st.session_state.favs[c["url"]] = c
                add_custom(cus)
                st.success("Restauré.")
            except Exception:
                st.error("Fichier invalide.")

# ------------------------------------------------------ Chargement
sources = (
    [(f"{BASE}/countries/{c}.m3u", c) for c in COUNTRY_BLOCKS]
    + [(f"{BASE}/{p}", "") for p in CATEGORY_FILES.values()]
    + [(f"{BASE}/languages/fra.m3u", ""), (f"{BASE}/index.m3u", "")]
    + [(u, "") for u in EXTRA_M3U]
)
with st.spinner("Chargement des chaînes…"):
    pools = fetch_all(sources)
    P = lambda path: pools.get(f"{BASE}/{path}") or []
fra = P("languages/fra.m3u")
fra_urls = {c["url"] for c in fra}
extra = dedupe([pools.get(u) for u in EXTRA_M3U])
official = [{"name": o["name"], "url": o["url"], "logo": o.get("logo", ""), "country": "cm",
             "group": "Cameroun (officiel)", "key": norm(o["name"])} for o in CM_OFFICIEL]
ALL = dedupe([*[P(f"countries/{c}.m3u") for c in COUNTRY_BLOCKS],
              *[P(p) for p in CATEGORY_FILES.values()], fra, P("index.m3u"),
              official, extra, st.session_state.custom])

RAW_BLOCKS = {c: sort_channels(P(f"countries/{c}.m3u")) for c in COUNTRY_BLOCKS}
for k in ("sport", "news", "ent", "doc"):
    RAW_BLOCKS[k] = sort_channels(P(CATEGORY_FILES[k]))
RAW_BLOCKS["cm"] = sort_channels(dedupe([official, RAW_BLOCKS["cm"], [c for c in ALL if CM.search(c["name"])]]))
RAW_BLOCKS["frall"] = sort_channels(dedupe([fra, RAW_BLOCKS["fr"]]))
RAW_BLOCKS["bein"] = sort_channels([c for c in ALL if BEIN.search(c["name"])])
RAW_BLOCKS["canal"] = sort_channels([c for c in ALL if CANAL.search(c["name"])])
RAW_BLOCKS["film"] = sort_channels(dedupe([
    [c for c in dedupe([P("categories/movies.m3u"), P("categories/series.m3u")]) if c["url"] in fra_urls],
    [c for c in ALL if FILMS.search(c["name"]) and (c["url"] in fra_urls or c["country"] in FR_COUNTRIES)],
]))
best = {}
for c in sort_channels([c for c in ALL if c["key"] in RANK]):
    best.setdefault(c["key"], c)
RAW_BLOCKS["pop"] = sorted(best.values(), key=lambda c: RANK[c["key"]])


def apply_filters(chs):
    if https_only:
        chs = [c for c in chs if c["url"].startswith("https")]
    if logo_only:
        chs = [c for c in chs if c["logo"]]
    return chs


def paged_grid(chs, sig, exempt=False):
    if st.session_state.get("sig") != sig:
        st.session_state.sig = sig
        st.session_state.shown = PAGE_SIZE
    shown = st.session_state.shown
    if only_playable and not exempt:
        with st.spinner("Test des flux en cours…"):
            view, more = playable_channels(chs, shown)
        st.caption(f"{len(view)} lisible(s)")
    else:
        view, more = chs[:shown], len(chs) > shown
        st.caption(f"{len(chs)} chaîne(s)")
    if not view:
        st.info("Aucune chaîne ici. Décochez « Masquer les flux qui ne marchent pas ici » "
                "dans ⚙️ Réglages (menu ›), ou choisissez une autre rubrique.")
    grid(view, "g")
    if more:
        st.button("Afficher plus ⬇", key="more", on_click=more_channels)


@st.cache_data(ttl=1800, show_spinner=False)
def get_matches(league_id):
    try:
        r = requests.get(f"https://www.thesportsdb.com/api/v1/json/3/eventsnextleague.php?id={league_id}",
                         timeout=10)
        ev = r.json().get("events") or []
    except Exception:
        return None
    return [(e.get("dateEvent", ""), (e.get("strTime") or "")[:5], e.get("strHomeTeam", ""),
             e.get("strAwayTeam", "")) for e in ev[:10]]


def show_matches(league_name, key):
    rows = get_matches(LEAGUES[league_name])
    tz = TIMEZONES.get(st.session_state.get("tzname", "Cameroun"), "Africa/Douala")
    if rows is None:
        st.info("Calendrier indisponible pour le moment.")
        return
    if not rows:
        st.info("Aucun match programmé prochainement.")
    for d, t, h, a in rows:
        try:
            dt = datetime.strptime(f"{d} {t or '00:00'}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            when = dt.astimezone(ZoneInfo(tz)).strftime("%d/%m · %H:%M")
        except Exception:
            when = d
        st.markdown(f'<div class="mrow"><span>{when}</span><b>{html.escape(h)} – {html.escape(a)}</b></div>',
                    unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.button("📺 Chaînes sportives", key=f"ms_{key}", on_click=go, args=(LABEL["sport"],))
    c2.button("🟣 beIN Sports", key=f"mb_{key}", on_click=go, args=(LABEL["bein"],))
    def back_button():
    st.button("← Accueil", key="back", on_click=go, args=(HOME,))


# ------------------------------------------------------------- Page
st.markdown(HERO, unsafe_allow_html=True)
top = st.columns([1, 2.4])
with top[0]:
    with st.popover("☰  Catégories"):
        st.button(HOME, key="m_home", on_click=go, args=(HOME,))
        st.button(f"{FAVS} ({len(st.session_state.favs)})", key="m_favs", on_click=go, args=(FAVS,))
        st.button(MATCHES, key="m_matches", on_click=go, args=(MATCHES,))
        for g in dict.fromkeys(b[3] for b in BLOCKS):
            st.markdown(f'<div class="grp">{g}</div>', unsafe_allow_html=True)
            for b in BLOCKS:
                if b[3] == g:
                    st.button(LABEL[b[0]], key=f"m_{b[0]}", on_click=go, args=(LABEL[b[0]],))
        st.markdown('<div class="grp">Plus</div>', unsafe_allow_html=True)
        for lab in (LANG, COUNTRY, CUSTOM):
            st.button(lab, key=f"m_{lab}", on_click=go, args=(lab,))
with top[1]:
    query = st.text_input("Recherche", placeholder="🔍  Rechercher une chaîne (TF1, CRTV, beIN, Canal+…)",
                          label_visibility="collapsed")
nav = st.session_state.nav

if any(v is None for v in pools.values()):
    st.caption("⚠️ Certaines listes n'ont pas pu être chargées (réseau). Rechargez la page.")

if query.strip():
    q = query.strip().lower()
    block_title(f"Résultats pour « {query.strip()} »")
    hits = apply_filters(sort_channels([c for c in ALL if q in c["name"].lower()]))
    paged_grid(hits, ("search", q, https_only, logo_only, only_playable))

elif nav == HOME:
    full = {bid: apply_filters(RAW_BLOCKS[bid]) for bid in HOME_BLOCKS}
    ok = {}
    if only_playable:
        urls = [c["url"] for bid, lst in full.items() if bid not in PROBE_EXEMPT for c in lst[:CANDIDATES]]
        with st.spinner("Test des flux (première visite : quelques secondes)…"):
            ok = probe_many(urls)
    block_title("📅 Matchs à venir")
    lg = st.radio("Championnat", list(LEAGUES), horizontal=True, key="lg_home", label_visibility="collapsed")
    show_matches(lg, "home")
    block_title("📦 Bouquets")
    chips = [("canal", "🔷 Canal+"), ("bein", "🟣 beIN Sports"), ("cm", "🇨🇲 Cameroun"), ("frall", "🗣️ Français"),
             ("film", "🎬 Films"), ("sport", "⚽ Sport")]
    for col, (bid, txt) in zip(st.columns(len(chips)), chips):
        col.button(txt, key=f"chip_{bid}", on_click=go, args=(LABEL[bid],))
    if st.session_state.favs:
        block_title("⭐ Mes favoris", len(st.session_state.favs))
        grid(list(st.session_state.favs.values())[:PER_BLOCK], "hf")
    for bid in HOME_BLOCKS:
        lst = full[bid][:CANDIDATES]
        if only_playable and bid not in PROBE_EXEMPT:
            lst = [c for c in lst if ok.get(c["url"])]
        lst = lst[:PER_BLOCK]
        if not lst:
            continue
        block_title(LABEL[bid])
        grid(lst, f"h_{bid}")
        st.button(f"Voir toutes les chaînes · {LABEL[bid]}", key=f"all_{bid}", on_click=go, args=(LABEL[bid],))

elif nav == FAVS:
    block_title(FAVS, len(st.session_state.favs))
    back_button()
    if st.session_state.favs:
        grid(list(st.session_state.favs.values()), "fav")
    else:
        st.info("Pas encore de favoris : ouvrez une chaîne et touchez « Ajouter aux favoris ».")

elif nav in BLOCK_BY_LABEL:
    bid = BLOCK_BY_LABEL[nav]
    block_title(nav)
    back_button()
    paged_grid(apply_filters(RAW_BLOCKS[bid]), (nav, https_only, logo_only, only_playable),
               exempt=bid in PROBE_EXEMPT)

elif nav == MATCHES:
    block_title(MATCHES)
    back_button()
    lg = st.selectbox("Championnat", list(LEAGUES), key="lg_page")
    show_matches(lg, "page")

elif nav == LANG:
    block_title(LANG)
    back_button()
    sel = st.selectbox("Langue", list(LANGS))
    try:
        chs = apply_filters(sort_channels(fetch(f"{BASE}/languages/{LANGS[sel]}.m3u")))
    except Exception:
        chs = []
        st.error("Liste indisponible pour le moment.")
    paged_grid(chs, (LANG, sel, https_only, logo_only, only_playable))

elif nav == COUNTRY:
    block_title(COUNTRY)
    back_button()
    code = st.selectbox("Pays", list(COUNTRIES), format_func=lambda c: f"{flag(c)} {COUNTRIES[c]}")
    try:
        chs = apply_filters(sort_channels(fetch(f"{BASE}/countries/{code}.m3u", code)))
    except Exception:
        chs = []
        st.error("Liste indisponible pour le moment.")
    paged_grid(chs, (COUNTRY, code, https_only, logo_only, only_playable))

elif nav == CUSTOM:
    block_title(CUSTOM)
    back_button()
    t1, t2, t3, t4 = st.tabs(["🔗 Lien M3U", "📋 Coller", "📁 Fichier", "➕ Une chaîne"])
    with t1:
        link = st.text_input("URL de la playlist", placeholder="https://…/liste.m3u", key="m3u_link")
        if st.button("Charger la playlist", key="load_link") and link.strip():
            try:
                add_custom(fetch(link.strip()))
                st.success("Playlist ajoutée.")
            except Exception:
                st.error("Impossible de lire ce lien (hors ligne, privé ou format invalide).")
    with t2:
        txt = st.text_area("Contenu M3U", height=140, placeholder="#EXTM3U\n#EXTINF:-1,Ma chaîne\nhttps://…/flux.m3u8")
        if st.button("Importer le texte", key="load_txt") and txt.strip():
            add_custom(parse_m3u(txt))
            st.success("Chaînes ajoutées.")
    with t3:
        f = st.file_uploader("Fichier .m3u / .m3u8", type=["m3u", "m3u8", "txt"], key="m3u_file")
        if f is not None and st.button("Importer le fichier", key="load_file"):
            add_custom(parse_m3u(f.getvalue().decode("utf-8", "ignore")))
            st.success("Chaînes ajoutées.")
    with t4:
    n = st.text_input("Nom", key="c_name")
        u = st.text_input("Lien du flux (.m3u8)", key="c_url")
        g = st.text_input("Catégorie (optionnel)", key="c_grp")
        lg = st.text_input("Logo (URL, optionnel)", key="c_logo")
        if st.button("Ajouter la chaîne", key="add_one"):
            if n.strip() and u.strip().startswith("http"):
                add_custom([{"name": n.strip(), "url": u.strip(), "logo": lg.strip(), "country": "",
                             "group": g.strip(), "key": norm(n)}])
                st.success("Chaîne ajoutée.")
            else:
                st.error("Indiquez un nom et un lien commençant par http.")
    mine = dedupe([extra, st.session_state.custom])
    if mine:
        groups = sorted({c["group"] for c in mine if c["group"]})
        pick = st.selectbox("Catégorie", ["Toutes", *groups]) if groups else "Toutes"
        view = [c for c in mine if pick == "Toutes" or c["group"] == pick]
        st.caption(f"{len(view)} chaîne(s) dans ma liste")
        grid(view[:200], "mine")
        if st.session_state.custom:
            st.button("🗑️ Vider ma liste", key="clear_custom", on_click=lambda: st.session_state.update(custom=[]))
    else:
        st.info("Ajoutez une playlist M3U, collez-en une, ou saisissez une chaîne : elle apparaîtra ici.")
        
