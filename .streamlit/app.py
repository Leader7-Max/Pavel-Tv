import json
import re

import requests
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="GlobalTV Stream", page_icon="📺", layout="wide")

BASE = "https://iptv-org.github.io/iptv"
SOURCES = {
    "Actualités": [f"{BASE}/categories/news.m3u"],
    "Sport": [f"{BASE}/categories/sports.m3u"],
    "Divertissement": [f"{BASE}/categories/entertainment.m3u"],
    "Documentaires": [f"{BASE}/categories/documentary.m3u"],
    "International": [f"{BASE}/languages/fra.m3u", f"{BASE}/languages/eng.m3u"],
}
ATTR = re.compile(r'([\w-]+)="([^"]*)"')
PAGE_SIZE = 48


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
                out.append({
                    "name": name,
                    "url": line,
                    "logo": attrs.get("tvg-logo") or "",
                    "group": attrs.get("group-title", ""),
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


def player(url):
    html = f"""
    <video id="v" controls autoplay playsinline
      style="width:100%;max-height:70vh;background:#000;border-radius:12px"></video>
    <p id="err" style="color:#ff6b6b;font-family:sans-serif"></p>
    <script src="https://cdn.jsdelivr.net/npm/hls.js@1.5.15"></script>
    <script>
      const url = {json.dumps(url)};
      const v = document.getElementById('v');
      const err = document.getElementById('err');
      if (window.Hls && Hls.isSupported()) {{
        const h = new Hls();
        h.loadSource(url);
        h.attachMedia(v);
        h.on(Hls.Events.ERROR, (e, d) => {{
          if (d.fatal) err.textContent = 'Flux indisponible (hors ligne, géo-bloqué ou CORS).';
        }});
      }} else {{
        v.src = url;
      }}
    </script>
    """
    components.html(html, height=480)


# ---------- État ----------
st.session_state.setdefault("favs", {})
st.session_state.setdefault("current", None)

# ---------- Barre latérale ----------
with st.sidebar:
    st.title("📺 GlobalTV Stream")
    section = st.radio("Catégorie", ["Tout", "⭐ Favoris", *SOURCES.keys()])
    https_only = st.checkbox(
        "Flux HTTPS uniquement", value=True,
        help="Les navigateurs bloquent les flux http:// sur un site en https.",
    )
    custom = st.text_input("Ma liste M3U (URL)", placeholder="https://…/liste.m3u")

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

# ---------- Données ----------
if custom.strip():
    channels = load_many([custom.strip()])
elif section == "⭐ Favoris":
    channels = list(st.session_state.favs.values())
elif section == "Tout":
    channels = load_many([u for urls in SOURCES.values() for u in urls])
else:
    channels = load_many(SOURCES[section])

if https_only:
    channels = [c for c in channels if c["url"].startswith("https")]

query = st.text_input("🔍 Rechercher une chaîne", placeholder="Ex. : BFM, Euronews, Eurosport…")
if query:
    q = query.lower()
    channels = [c for c in channels if q in c["name"].lower()]

# Pagination (remise à zéro quand le filtre change)
sig = (section, custom, https_only, query)
if st.session_state.get("sig") != sig:
    st.session_state.sig = sig
    st.session_state.shown = PAGE_SIZE

# ---------- Lecteur ----------
cur = st.session_state.current
if cur:
    st.subheader(f"🔴 {cur['name']}")
    player(cur["url"])
    st.caption(
        "📡 Pour la TV : dans Chrome, menu ⋮ → « Enregistrer, partager et caster » → « Caster… ». "
        "Ou copiez le lien ci-dessous dans VLC / une appli Cast."
    )
    st.code(cur["url"], language=None)

# ---------- Grille ----------
st.markdown(f"**{len(channels)} chaîne(s)**")
shown = st.session_state.shown
cols_per_row = 4
for row_start in range(0, min(shown, len(channels)), cols_per_row):
    cols = st.columns(cols_per_row)
    for offset, col in enumerate(cols):
        i = row_start + offset
        if i >= min(shown, len(channels)):
            break
        ch = channels[i]
        with col, st.container(border=True):
            if ch["logo"]:
                st.image(ch["logo"], width=64)
            st.caption(ch["name"])
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

if shown < len(channels):
    if st.button("Afficher plus"):
        st.session_state.shown += PAGE_SIZE
        st.rerun()
