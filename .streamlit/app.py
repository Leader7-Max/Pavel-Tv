import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import requests
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="GlobalTV Stream", page_icon="📺", layout="wide")

BASE = "https://iptv-org.github.io/iptv"
PAGE_SIZE = 48

# Chaînes « les plus regardées » (liste choisie à la main, ordre = priorité)
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
    "fr": "France", "be": "Belgique", "ch": "Suisse", "ca": "Canada",
    "gb": "Royaume-Uni", "uk": "Royaume-Uni", "us": "États-Unis",
    "es": "Espagne", "de": "Allemagne", "it": "Italie", "pt": "Portugal",
    "ma": "Maroc", "dz": "Algérie", "tn": "Tunisie", "sn": "Sénégal",
    "ci": "Côte d'Ivoire", "tr": "Turquie", "br": "Brésil", "mx": "Mexique",
    "ar": "Argentine", "ru": "Russie", "in": "Inde", "ae": "Émirats arabes unis",
    "qa": "Qatar", "eg": "Égypte", "nl": "Pays-Bas", "pl": "Pologne",
}
PICKABLE_COUNTRIES = [c for c in COUNTRIES if c != "uk"]

SECTIONS = {
    "🔥 Populaires": None,
    "🇫🇷 Chaînes françaises": [f"{BASE}/countries/fr.m3u"],
    "⚽ Sport": [f"{BASE}/categories/sports.m3u"],
    "📰 Actualités": [f"{BASE}/categories/news.m3u"],
    "🎬 Divertissement": [f"{BASE}/categories/entertainment.m3u"],
    "📚 Documentaires": [f"{BASE}/categories/documentary.m3u"],
}
FILTERABLE = ["⚽ Sport", "📰 Actualités", "🎬 Divertissement", "📚 Documentaires"]

ATTR = re.compile(r'([\w-]+)="([^"]*)"')
COUNTRY_IN_ID = re.compile(r"\.([a-z]{2})(?:@|$)")


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


def parse_m3u(text):
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
                    "country": m.group(1) if m else "",
                    "key": norm(name),
                })
            attrs = name = None
    return out


@st.cache_data(ttl=3600, show_spinner="Chargement des chaînes…")
def load_playlist(url):
    r = requests.get(url, timeout=30, headers={"User-Agent": "GlobalTVStream/1.0"})
    r.raise_for_status()
    return parse_m3u(r.text)


def load_many(urls):
    result, seen = [], set()
    for u in urls:
        try:
            for ch in load_playlist(u):
                if ch["url"] not in seen:
                    seen.add(ch["url"])
                    result.append(ch)
        except Exception as e:
            st.warning(f"Liste inaccessible : {u} ({e})")
    return result


def sort_channels(chs):
    return sorted(chs, key=lambda c: (RANK.get(c["key"], 999), 0 if c["logo"] else 1, c["name"].lower()))


# ---------- Test des flux ----------
@st.cache_resource
def probe_cache():
    return {}


PROBES = probe_cache()


def probe(url):
    """Teste un flux comme le ferait le navigateur. Retourne (ok, raison)."""
    if url in PROBES:
        return PROBES[url]
    try:
        r = requests.get(
            url, timeout=6, stream=True,
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


def playable_channels(chs, needed):
    """Teste les chaînes par lots jusqu'à en trouver `needed` de lisibles."""
    ok, i = [], 0
    while len(ok) < needed and i < len(chs):
        batch = chs[i:i + PAGE_SIZE]
        i += PAGE_SIZE
        with ThreadPoolExecutor(max_workers=24) as ex:
            results = list(ex.map(lambda c: probe(c["url"])[0], batch))
        ok += [c for c, good in zip(batch, results) if good]
    return ok[:needed]


PLAYER_HTML = """
<video id="v" controls autoplay playsinline
  style="width:100%;max-height:70vh;background:#000;border-radius:12px"></video>
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
    components.html(PLAYER_HTML.replace("__URL__", json.dumps(url)), height=480)


# ---------- État ----------
st.session_state.setdefault("favs", {})
st.session_state.setdefault("current", None)

# ---------- Barre latérale (1/2) ----------
with st.sidebar:
    st.title("📺 GlobalTV Stream")
    section = st.radio(
        "Rubrique",
        ["⭐ Favoris", *SECTIONS.keys(), "🗣️ Par langue", "🌍 Par pays"],
    )
    sub = None
    if section == "🗣️ Par langue":
        sub = st.selectbox("Langue", list(LANGS.keys()))
    elif section == "🌍 Par pays":
        sub = st.selectbox(
            "Pays", PICKABLE_COUNTRIES, format_func=lambda c: f"{flag(c)} {COUNTRIES[c]}"
        )
    only_playable = st.checkbox(
        "Masquer les flux qui ne marchent pas ici", value=True,
        help="Teste chaque flux et ne garde que ceux que le navigateur peut lire.",
    )
    https_only = st.checkbox(
        "Flux HTTPS uniquement", value=True,
        help="Les navigateurs bloquent les flux http:// sur un site en https.",
    )
    logo_only = st.checkbox("Seulement les chaînes avec logo", value=False)
    custom = st.text_input("Ma liste M3U (URL)", placeholder="https://…/liste.m3u")

# ---------- Données ----------
if custom.strip():
    channels = load_many([custom.strip()])
elif section == "⭐ Favoris":
    channels = list(st.session_state.favs.values())
elif section == "🔥 Populaires":
    pool = load_many([
        f"{BASE}/countries/fr.m3u", f"{BASE}/categories/sports.m3u",
        f"{BASE}/categories/news.m3u", f"{BASE}/languages/eng.m3u",
    ])
    best = {}
    for ch in sort_channels(pool):
        if ch["key"] in RANK and ch["key"] not in best:
            best[ch["key"]] = ch
    channels = sorted(best.values(), key=lambda c: RANK[c["key"]])
elif section == "🗣️ Par langue":
    channels = load_many([f"{BASE}/languages/{LANGS[sub]}.m3u"])
elif section == "🌍 Par pays":
    channels = load_many([f"{BASE}/countries/{sub}.m3u"])
else:
    channels = load_many(SECTIONS[section])

if section != "🔥 Populaires":
    channels = sort_channels(channels)

# ---------- Barre latérale (2/2) ----------
country_sel = "Tous"
with st.sidebar:
    if section in FILTERABLE:
        present = sorted({c["country"] for c in channels if c["country"]},
                         key=lambda c: (c != "fr", COUNTRIES.get(c, c)))
        country_sel = st.selectbox(
            "Pays", ["Tous", *present],
            format_func=lambda c: "🌐 Tous les pays" if c == "Tous"
            else f"{flag(c)} {COUNTRIES.get(c, c.upper())}",
        )
    with st.expander("Sauvegarder / restaurer les favoris"):
        st.download_button(
            "Télécharger mes favoris",
            json.dumps(list(st.session_state.favs.values()), ensure_ascii=False),
            file_name="favoris.json",
            mime="application/json",
        )
        up = st.file_uploader("Restaurer", type="json")
        if up is not None:
            try:
                for ch in json.load(up):
                    st.session_state.favs[ch["url"]] = ch
                st.success("Favoris restaurés.")
            except Exception:
                st.error("Fichier invalide.")

# ---------- Filtres ----------
if country_sel != "Tous":
    channels = [c for c in channels if c["country"] == country_sel]
if https_only:
    channels = [c for c in channels if c["url"].startswith("https")]
if logo_only:
    channels = [c for c in channels if c["logo"]]

query = st.text_input("🔍 Rechercher une chaîne", placeholder="Ex. : TF1, Euronews, Eurosport…")
if query:
    q = query.lower()
    channels = [c for c in channels if q in c["name"].lower()]

sig = (section, sub, country_sel, custom, https_only, logo_only, only_playable, query)
if st.session_state.get("sig") != sig:
    st.session_state.sig = sig
    st.session_state.shown = PAGE_SIZE

# ---------- Lecteur ----------
cur = st.session_state.current
if cur:
    st.subheader(f"🔴 {cur['name']}")
    good, reason = probe(cur["url"])
    if not good:
        st.warning(f"Ce flux risque de ne pas se lire ici : {reason}.")
    player(cur["url"])
    st.caption(
        "📡 Pour la TV : dans Chrome, menu ⋮ → « Enregistrer, partager et caster » → « Caster… ». "
        "Ou copiez le lien ci-dessous dans VLC / une appli Cast."
    )
    st.code(cur["url"], language=None)

# ---------- Grille ----------
if only_playable:
    with st.spinner("Test des flux en cours…"):
        view = playable_channels(channels, st.session_state.shown)
    more = len(view) >= st.session_state.shown
    st.markdown(f"### {section}  ·  {len(view)} chaîne(s) lisible(s)")
    if not view:
        st.info("Aucun flux lisible trouvé ici. Décochez « Masquer les flux qui ne marchent pas ici » "
                "pour voir toutes les chaînes, ou essayez une autre rubrique.")
else:
    view = channels[:st.session_state.shown]
    more = len(view) < len(channels)
    st.markdown(f"### {section}  ·  {len(channels)} chaîne(s)")

per_row = 4
for start in range(0, len(view), per_row):
    cols = st.columns(per_row)
    for offset, col in enumerate(cols):
        i = start + offset
        if i >= len(view):
            break
        ch = view[i]
        with col, st.container(border=True):
            if ch["logo"]:
                st.image(ch["logo"], width=72)
            else:
                st.markdown("<div style='font-size:42px;line-height:72px'>📺</div>",
                            unsafe_allow_html=True)
            label = f"{flag(ch['country'])} " if ch["country"] else ""
            st.caption(f"{label}{ch['name']}")
            b1, b2 = st.columns(2)
            if b1.button("▶ Lire", key=f"play_{i}"):
                st.session_state.current = ch
                st.rerun()
            is_fav = ch["url"] in st.session_state.favs
            if b2.button("♥" if is_fav else "♡", key=f"fav_{i}"):
                if is_fav:
                    del st.session_state.favs[ch["url"]]
                else:
                    st.session_state.favs[ch["url"]] = ch
                st.rerun()

if more:
    if st.button("Afficher plus"):
        st.session_state.shown += PAGE_SIZE
        st.rerun()
