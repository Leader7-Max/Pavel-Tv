import html
import json
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import requests
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Pavel TV", page_icon="▶️", layout="wide")

BASE = "https://iptv-org.github.io/iptv"
PAGE_SIZE = 48
PER_BLOCK = 6
CANDIDATES = 18

# ---------------------------------------------------------------- Données
POPULAR = [
    "TF1", "France 2", "France 3", "M6", "France 5", "Arte", "C8", "W9", "TMC",
    "TFX", "NRJ 12", "France 4", "BFM TV", "CNews", "LCI", "franceinfo",
    "France 24", "Euronews", "RMC Story", "RMC Decouverte", "Gulli", "6ter",
    "L'Equipe", "Canal+", "Eurosport 1", "Eurosport 2", "beIN Sports 1",
    "RMC Sport 1", "TV5Monde", "LCP", "Paris Premiere", "CStar", "Cherie 25",
    "Al Jazeera", "BBC News", "CNN", "DW", "Sky News", "Red Bull TV",
]

LANGS = {
    "Français": "fra", "English": "eng", "Español": "spa", "العربية": "ara",
    "Português": "por", "Deutsch": "deu", "Italiano": "ita", "Türkçe": "tur",
    "Русский": "rus", "Nederlands": "nld", "Polski": "pol",
}

COUNTRIES = {
    "fr": "France", "cm": "Cameroun", "ci": "Côte d'Ivoire", "sn": "Sénégal",
    "ma": "Maroc", "dz": "Algérie", "tn": "Tunisie", "be": "Belgique",
    "ch": "Suisse", "ca": "Canada", "gb": "Royaume-Uni", "uk": "Royaume-Uni",
    "us": "États-Unis", "es": "Espagne", "de": "Allemagne", "it": "Italie",
    "pt": "Portugal", "tr": "Turquie", "br": "Brésil", "mx": "Mexique",
    "ar": "Argentine", "ru": "Russie", "in": "Inde", "ae": "Émirats arabes unis",
    "qa": "Qatar", "eg": "Égypte", "nl": "Pays-Bas", "pl": "Pologne",
}
PICKABLE_COUNTRIES = [c for c in COUNTRIES if c != "uk"]
COUNTRY_PRIORITY = {c: i for i, c in enumerate(["fr", "cm", "ci", "sn", "ma", "be", "ch", "ca"])}

BLOCKS = [
    {"id": "pop", "emoji": "🔥", "title": "Les plus regardées"},
    {"id": "cm", "emoji": "🇨🇲", "title": "Chaînes camerounaises"},
    {"id": "fr", "emoji": "🇫🇷", "title": "Chaînes françaises"},
    {"id": "sport", "emoji": "⚽", "title": "Chaînes sportives"},
    {"id": "ci", "emoji": "🇨🇮", "title": "Chaînes ivoiriennes"},
    {"id": "canal", "emoji": "🔷", "title": "Toutes les chaînes Canal+"},
    {"id": "sn", "emoji": "🇸🇳", "title": "Chaînes sénégalaises"},
    {"id": "ma", "emoji": "🇲🇦", "title": "Chaînes marocaines"},
    {"id": "news", "emoji": "📰", "title": "Actualités"},
    {"id": "ent", "emoji": "🎬", "title": "Divertissement"},
    {"id": "doc", "emoji": "📚", "title": "Documentaires"},
]
for _b in BLOCKS:
    _b["label"] = f'{_b["emoji"]} {_b["title"]}'
BLOCK_BY_LABEL = {b["label"]: b for b in BLOCKS}

COUNTRY_BLOCKS = ["cm", "fr", "ci", "sn", "ma"]
CATEGORY_FILES = {
    "sport": "categories/sports.m3u",
    "news": "categories/news.m3u",
    "ent": "categories/entertainment.m3u",
    "doc": "categories/documentary.m3u",
}
FILTERABLE = {"sport", "news", "ent", "doc", "canal", "pop"}
PROBE_EXEMPT = {"canal"}

HOME, FAVS, LANG, COUNTRY, CUSTOM = (
    "🏠 Accueil", "⭐ Favoris", "🗣️ Par langue", "🌍 Par pays", "📎 Ma liste M3U",
)
NAV = [HOME, FAVS, *[b["label"] for b in BLOCKS], LANG, COUNTRY, CUSTOM]

ATTR = re.compile(r'([\w-]+)="([^"]*)"')
COUNTRY_IN_ID = re.compile(r"\.([a-z]{2})(?:@|$)")
CANAL = re.compile(r"canal\s*(\+|plus)", re.I)


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
                    "name": name,
                    "url": line,
                    "logo": attrs.get("tvg-logo") or "",
                    "country": m.group(1) if m else default_country,
                    "key": norm(name),
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
    r = requests.get(url, timeout=40, headers={"User-Agent": "PavelTV/1.0"})
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
        RANK.get(c["key"], 999),
        COUNTRY_PRIORITY.get(c["country"], 99),
        0 if c["logo"] else 1,
        c["name"].lower(),
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
        r = requests.get(
            url, timeout=(4, 5), stream=True,
            headers={"User-Agent": "Mozilla/5.0", "Origin": "https://share.streamlit.io"},
        )
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
  radial-gradient(900px 480px at 100% 0%, rgba(236,72,153,.28), transparent 55%),
  radial-gradient(800px 400px at 50% 110%, rgba(245,158,11,.14), transparent 60%), #0A0A1A;}
#MainMenu, footer{visibility:hidden;}
section[data-testid="stSidebar"]{background:#0E0E22;border-right:1px solid rgba(255,255,255,.07);}
.block-container{padding-top:1.4rem;max-width:1300px;}

.hero{display:flex;align-items:center;gap:16px;padding:20px 24px;border-radius:24px;margin-bottom:14px;
  background:linear-gradient(135deg,rgba(124,58,237,.38),rgba(236,72,153,.26),rgba(245,158,11,.20));
  border:1px solid rgba(255,255,255,.14);box-shadow:0 10px 40px rgba(124,58,237,.25);}
.brand-name{font-size:34px;font-weight:900;letter-spacing:1px;line-height:1;color:#fff;}
.brand-name span{background:linear-gradient(135deg,#EC4899,#F59E0B);-webkit-background-clip:text;
  background-clip:text;color:transparent;margin-left:6px;}
.tagline{color:rgba(255,255,255,.72);font-size:14px;margin-top:6px;}

.bt{display:flex;align-items:center;gap:12px;margin:26px 0 12px;font-size:22px;font-weight:800;color:#fff;}
.bt::before{content:"";width:6px;height:28px;border-radius:6px;
  background:linear-gradient(180deg,#8B5CF6,#EC4899,#F59E0B);}
.bt small{font-size:12px;font-weight:700;color:#fff;padding:3px 10px;border-radius:999px;
  background:rgba(255,255,255,.12);}

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
button[data-testid="stBaseButton-primary"]:hover, button[kind="primary"]:hover{filter:brightness(1.15);}
.stTextInput input{border-radius:999px;background:rgba(255,255,255,.07);
  border:1px solid rgba(255,255,255,.14);padding:12px 18px;}

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
  style="width:100%;max-height:68vh;background:#000;border-radius:14px"></video>
<p id="err" style="color:#ff6b6b;font-family:sans-serif"></p>
<script src="https://cdn.jsdelivr.net/npm/hls.js@1.5.15"></script>
<script>
  const url = __URL__;
  const v = document.getElementById('v');
  const err = document.getElementById('err');
  if (window.Hls && Hls.isSupported()) {
    const h = new Hls();
    h.loadSource(url);
    h.attachMedia(v);
    h.on(Hls.Events.ERROR, (e, d) => {
      if (d.fatal) {
        const code = d.response ? d.response.code : 0;
        err.textContent = 'Flux indisponible (' + d.details + (code ? ', HTTP ' + code : '') + '). ' +
          (code === 0 ? 'Bloqué par le serveur de la chaîne (CORS) ou hors ligne.'
                      : 'Hors ligne ou géo-bloqué.');
      }
    });
  } else {
    v.src = url;
  }
</script>
"""


def player(url):
    components.html(PLAYER_HTML.replace("__URL__", json.dumps(url)), height=440)


# -------------------------------------------------------------- État
st.session_state.setdefault("favs", {})
st.session_state.setdefault("shown", PAGE_SIZE)


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


# ------------------------------------------------------- Lecteur (modale)
@st.dialog("▶ Pavel TV", width="large")
def watch(ch):
    st.markdown(f"#### 🔴 {ch['name']}")
    known = PROBES.get(ch["url"])
    if known and not known[0]:
        st.warning(f"Ce flux risque de ne pas se lire ici : {known[1]}.")
    player(ch["url"])
    is_fav = ch["url"] in st.session_state.favs
    st.button(
        "💔 Retirer des favoris" if is_fav else "❤️ Ajouter aux favoris",
        key="dlg_fav", on_click=toggle_fav, args=(ch,),
    )
    st.caption(
        "📡 Sur TV : Chrome ⋮ → « Enregistrer, partager et caster » → « Caster… », "
        "ou copiez ce lien dans VLC / une appli Cast."
    )
    st.code(ch["url"], language=None)


# ---------------------------------------------------------- Widgets
def card(ch, prefix, i):
    with st.container(key=f"card_{prefix}_{i}"):
        if ch["logo"]:
            img = (f'<img src="{html.escape(ch["logo"], quote=True)}" alt="" '
                   f'loading="lazy" referrerpolicy="no-referrer">')
        else:
            img = '<span class="ph">📺</span>'
        heart = "❤️ " if ch["url"] in st.session_state.favs else ""
        fl = f"{flag(ch['country'])} " if ch["country"] else ""
        st.markdown(
            f'<div class="tile">{img}</div>'
            f'<div class="cname">{heart}{fl}{html.escape(ch["name"])}</div>',
            unsafe_allow_html=True,
        )
        if st.button("▶ Regarder", key=f"play_{prefix}_{i}", type="primary"):
            watch(ch)


def grid(items, prefix, per_row=6):
    for start in range(0, len(items), per_row):
        cols = st.columns(per_row)
        for j, col in enumerate(cols):
            idx = start + j
            if idx >= len(items):
                break
            with col:
                card(items[idx], prefix, idx)


def block_title(text, count=None):
    badge = f"<small>{count}</small>" if count is not None else ""
    st.markdown(f'<div class="bt">{html.escape(text)}{badge}</div>', unsafe_allow_html=True)


# ------------------------------------------------------ Barre latérale
st.markdown(CSS, unsafe_allow_html=True)

with st.sidebar:
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">{LOGO_SVG}'
        f'<div class="brand-name" style="font-size:26px">PAVEL<span>TV</span></div></div>',
        unsafe_allow_html=True,
    )
    nav = st.radio("Navigation", NAV, key="nav", label_visibility="collapsed")
    with st.expander("⚙️ Réglages"):
        only_playable = st.checkbox(
            "Masquer les flux qui ne marchent pas ici", value=True,
            help="Teste chaque flux et ne garde que ceux que le navigateur peut lire.",
        )
        https_only = st.checkbox("Flux HTTPS uniquement", value=True)
        logo_only = st.checkbox("Seulement les chaînes avec logo", value=False)
        custom_url = st.text_input("Ma liste M3U (URL)", placeholder="https://…/liste.m3u")
    with st.expander("💾 Sauvegarder / restaurer les favoris"):
        st.download_button(
            "Télécharger mes favoris",
            json.dumps(list(st.session_state.favs.values()), ensure_ascii=False),
            file_name="favoris.json", mime="application/json",
        )
        up = st.file_uploader("Restaurer", type="json")
        if up is not None:
            try:
                for c in json.load(up):
                    st.session_state.favs[c["url"]] = c
                st.success("Favoris restaurés.")
            except Exception:
                st.error("Fichier invalide.")

# ------------------------------------------------------ Chargement
sources = (
    [(f"{BASE}/countries/{c}.m3u", c) for c in COUNTRY_BLOCKS]
    + [(f"{BASE}/{p}", "") for p in CATEGORY_FILES.values()]
    + [(f"{BASE}/index.m3u", "")]
)
with st.spinner("Chargement des chaînes…"):
    pools = fetch_all(sources)

country_lists = {c: pools[f"{BASE}/countries/{c}.m3u"] for c in COUNTRY_BLOCKS}
category_lists = {k: pools[f"{BASE}/{p}"] for k, p in CATEGORY_FILES.items()}
ALL = dedupe([*country_lists.values(), *category_lists.values(), pools[f"{BASE}/index.m3u"]])

RAW_BLOCKS = {}
for c in COUNTRY_BLOCKS:
    RAW_BLOCKS[c] = sort_channels(country_lists[c] or [])
for k in CATEGORY_FILES:
    RAW_BLOCKS[k] = sort_channels(category_lists[k] or [])
RAW_BLOCKS["canal"] = sort_channels([c for c in ALL if CANAL.search(c["name"])])
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
        count = f"{len(view)} lisible(s)"
    else:
        view, more = chs[:shown], len(chs) > shown
        count = f"{len(chs)} chaîne(s)"
    st.caption(count)
    if not view:
        st.info("Aucune chaîne à afficher ici. Essayez de décocher « Masquer les flux qui ne "
                "marchent pas ici » dans ⚙️ Réglages, ou choisissez une autre rubrique.")
    grid(view, "g")
    if more:
        st.button("Afficher plus ⬇", key="more", on_click=more_channels)


def back_button():
    st.button("← Accueil", key="back", on_click=go, args=(HOME,))


# ------------------------------------------------------------- Page
st.markdown(HERO, unsafe_allow_html=True)
if any(v is None for v in pools.values()):
    st.caption("⚠️ Certaines listes n'ont pas pu être chargées (réseau). Rechargez la page.")

query = st.text_input(
    "Recherche", placeholder="🔍  Rechercher une chaîne (TF1, Canal+, Eurosport…)",
    label_visibility="collapsed",
)

if query.strip():
    q = query.strip().lower()
    block_title(f"Résultats pour « {query.strip()} »")
    hits = apply_filters(sort_channels([c for c in ALL if q in c["name"].lower()]))
    paged_grid(hits, ("search", q, https_only, logo_only, only_playable))

elif nav == HOME:
    full = {b["id"]: apply_filters(RAW_BLOCKS[b["id"]]) for b in BLOCKS}
    picks = {}
    if only_playable:
        urls = [c["url"] for bid, lst in full.items() if bid not in PROBE_EXEMPT
                for c in lst[:CANDIDATES]]
        with st.spinner("Test des flux (première visite : quelques secondes)…"):
            ok = probe_many(urls)
    for b in BLOCKS:
        lst = full[b["id"]][:CANDIDATES]
        if only_playable and b["id"] not in PROBE_EXEMPT:
            lst = [c for c in lst if ok.get(c["url"])]
        picks[b["id"]] = lst[:PER_BLOCK]

    if st.session_state.favs:
        block_title("⭐ Mes favoris", len(st.session_state.favs))
        grid(list(st.session_state.favs.values())[:PER_BLOCK], "fav")
        st.button("Voir tout ›", key="all_fav", on_click=go, args=(FAVS,))

    for b in BLOCKS:
        items = picks[b["id"]]
        if not items and b["id"] != "canal":
            continue
        block_title(b["label"], len(full[b["id"]]))
        if items:
            grid(items, b["id"])
            st.button("Voir tout ›", key=f"all_{b['id']}", on_click=go, args=(b["label"],))
        else:
            st.info("Aucune chaîne Canal+ dans les listes publiques actuelles.")
    st.caption("Astuce : « Voir tout » affiche toutes les chaînes d'un bloc. "
               "Les blocs vides sont masqués car aucun de leurs flux n'est lisible ici.")

elif nav == FAVS:
    back_button()
    block_title("⭐ Mes favoris", len(st.session_state.favs))
    favs = list(st.session_state.favs.values())
    if favs:
        grid(favs, "favpage")
    else:
        st.info("Aucun favori pour l'instant. Ouvrez une chaîne et cliquez sur « Ajouter aux favoris ».")

elif nav in BLOCK_BY_LABEL:
    b = BLOCK_BY_LABEL[nav]
    back_button()
    block_title(b["label"])
    raw = RAW_BLOCKS[b["id"]]
    sel = "Tous"
    if b["id"] in FILTERABLE:
        present = sorted({c["country"] for c in raw if c["country"]},
                         key=lambda c: (COUNTRY_PRIORITY.get(c, 99), COUNTRIES.get(c, c)))
        sel = st.selectbox(
            "Pays", ["Tous", *present], key=f"cf_{b['id']}",
            format_func=lambda c: "🌐 Tous les pays" if c == "Tous"
            else f"{flag(c)} {COUNTRIES.get(c, c.upper())}",
        )
    if sel != "Tous":
        raw = [c for c in raw if c["country"] == sel]
    if b["id"] == "canal":
        st.caption("Beaucoup de flux Canal+ sont payants ou protégés : certains peuvent ne pas se lire.")
    paged_grid(apply_filters(raw), (b["id"], sel, https_only, logo_only, only_playable),
               exempt=b["id"] in PROBE_EXEMPT)

elif nav == LANG:
    back_button()
    block_title("🗣️ Chaînes par langue")
    lang = st.selectbox("Langue", list(LANGS.keys()))
    data = fetch_all([(f"{BASE}/languages/{LANGS[lang]}.m3u", "")]).popitem()[1]
    if data is None:
        st.error("Liste inaccessible pour le moment.")
    else:
        paged_grid(apply_filters(sort_channels(data)), ("lang", lang, https_only, logo_only, only_playable))

elif nav == COUNTRY:
    back_button()
    block_title("🌍 Chaînes par pays")
    cc = st.selectbox("Pays", PICKABLE_COUNTRIES,
                      format_func=lambda c: f"{flag(c)} {COUNTRIES[c]}")
    data = fetch_all([(f"{BASE}/countries/{cc}.m3u", cc)]).popitem()[1]
    if data is None:
        st.error("Liste inaccessible pour le moment.")
    else:
        paged_grid(apply_filters(sort_channels(data)), ("country", cc, https_only, logo_only, only_playable))

elif nav == CUSTOM:
    back_button()
    block_title("📎 Ma liste M3U")
    if not custom_url.strip():
        st.info("Collez l'adresse de votre liste .m3u dans ⚙️ Réglages (barre latérale).")
    else:
        data = fetch_all([(custom_url.strip(), "")]).popitem()[1]
        if data is None:
            st.error("Impossible de charger cette liste.")
        else:
            paged_grid(apply_filters(sort_channels(data)),
                       ("custom", custom_url, https_only, logo_only, only_playable))
