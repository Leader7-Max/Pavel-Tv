"""
PAVEL TV
Application Streamlit de télévision en direct.

Fonctions :
- Interface moderne mobile / ordinateur
- Recherche de chaînes
- Catégories
- Pays
- Favoris
- Lecteur HLS
- Chaînes camerounaises
- Import M3U / M3U8
- Ajout manuel de flux autorisés
"""

import html
import re
import unicodedata
from urllib.parse import quote

import requests
import streamlit as st
import streamlit.components.v1 as components


# ============================================================
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="PAVEL TV",
    page_icon="📺",
    layout="wide",
    initial_sidebar_state="collapsed",
)

APP_NAME = "PAVEL TV"
REQUEST_TIMEOUT = 20
PAGE_SIZE = 36

# Playlist IPTV publique.
IPTV_BASE = "https://iptv-org.github.io/iptv"

COUNTRIES = {
    "🇨🇲 Cameroun": "cm",
    "🇫🇷 France": "fr",
    "🇨🇮 Côte d'Ivoire": "ci",
    "🇸🇳 Sénégal": "sn",
    "🇲🇦 Maroc": "ma",
    "🇩🇿 Algérie": "dz",
    "🇹🇳 Tunisie": "tn",
    "🇧🇪 Belgique": "be",
    "🇨🇭 Suisse": "ch",
    "🇨🇦 Canada": "ca",
    "🇬🇧 Royaume-Uni": "gb",
    "🇺🇸 États-Unis": "us",
    "🇪🇸 Espagne": "es",
    "🇩🇪 Allemagne": "de",
    "🇮🇹 Italie": "it",
    "🇵🇹 Portugal": "pt",
    "🇹🇷 Turquie": "tr",
    "🇧🇷 Brésil": "br",
    "🇲🇽 Mexique": "mx",
    "🇦🇷 Argentine": "ar",
    "🇮🇳 Inde": "in",
    "🇦🇪 Émirats arabes unis": "ae",
    "🇶🇦 Qatar": "qa",
    "🇪🇬 Égypte": "eg",
    "🇳🇱 Pays-Bas": "nl",
    "🇵🇱 Pologne": "pl",
}

CATEGORIES = {
    "⚽ Sports": "sports",
    "📰 Actualités": "news",
    "🎬 Divertissement": "entertainment",
    "🎥 Documentaires": "documentary",
    "🍿 Films": "movies",
    "📺 Séries": "series",
}


# ============================================================
# CHAÎNES CAMEROUNAISES / LIENS OFFICIELS
# ============================================================

CAMEROON_OFFICIAL = [
    {
        "name": "CRTV",
        "country": "Cameroun",
        "category": "Actualités",
        "logo": "https://upload.wikimedia.org/wikipedia/fr/5/5b/CRTV_logo.png",
        "url": "https://crtv.cm/live/crtv",
        "stream": "",
    },
    {
        "name": "CRTV News",
        "country": "Cameroun",
        "category": "Actualités",
        "logo": "",
        "url": "https://crtv.cm/live/crtv-news",
        "stream": "",
    },
    {
        "name": "CRTV Sport",
        "country": "Cameroun",
        "category": "Sports",
        "logo": "",
        "url": "https://sports.crtv.cm/live/",
        "stream": "",
    },
    {
        "name": "Canal 2 International",
        "country": "Cameroun",
        "category": "Divertissement",
        "logo": "",
        "url": "https://www.canal2international.net/",
        "stream": "",
    },
]


POPULAR_CHANNELS = [
    {
        "name": "CRTV",
        "country": "Cameroun",
        "category": "Actualités",
        "logo": "",
        "url": "https://crtv.cm/live/crtv",
        "stream": "",
    },
    {
        "name": "CRTV News",
        "country": "Cameroun",
        "category": "Actualités",
        "logo": "",
        "url": "https://crtv.cm/live/crtv-news",
        "stream": "",
    },
    {
        "name": "CRTV Sport",
        "country": "Cameroun",
        "category": "Sports",
        "logo": "",
        "url": "https://sports.crtv.cm/live/",
        "stream": "",
    },
    {
        "name": "Canal 2 International",
        "country": "Cameroun",
        "category": "Divertissement",
        "logo": "",
        "url": "https://www.canal2international.net/",
        "stream": "",
    },
    {
        "name": "France 2",
        "country": "France",
        "category": "Divertissement",
        "logo": "",
        "url": "",
        "stream": "",
    },
    {
        "name": "France 24",
        "country": "France",
        "category": "Actualités",
        "logo": "",
        "url": "",
        "stream": "",
    },
    {
        "name": "TV5Monde",
        "country": "France",
        "category": "Divertissement",
        "logo": "",
        "url": "",
        "stream": "",
    },
    {
        "name": "Euronews",
        "country": "International",
        "category": "Actualités",
        "logo": "",
        "url": "",
        "stream": "",
    },
    {
        "name": "BBC News",
        "country": "Royaume-Uni",
        "category": "Actualités",
        "logo": "",
        "url": "",
        "stream": "",
    },
    {
        "name": "DW",
        "country": "Allemagne",
        "category": "Actualités",
        "logo": "",
        "url": "",
        "stream": "",
    },
    {
        "name": "Al Jazeera",
        "country": "Qatar",
        "category": "Actualités",
        "logo": "",
        "url": "",
        "stream": "",
    },
    {
        "name": "Africa 24",
        "country": "International",
        "category": "Actualités",
        "logo": "",
        "url": "",
        "stream": "",
    },
]


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
<style>

html, body, [class*="css"] {
    font-family: Arial, Helvetica, sans-serif;
}

.stApp {
    background:
        radial-gradient(
            circle at top right,
            rgba(80, 110, 255, 0.16),
            transparent 30%
        ),
        radial-gradient(
            circle at bottom left,
            rgba(255, 40, 120, 0.10),
            transparent 28%
        ),
        #080a10;
    color: #ffffff;
}

.block-container {
    max-width: 1450px;
    padding-top: 1rem;
    padding-bottom: 3rem;
}

.hero {
    padding: 30px;
    border-radius: 25px;
    background:
        linear-gradient(
            135deg,
            rgba(28, 33, 55, 0.96),
            rgba(10, 12, 20, 0.98)
        );
    border: 1px solid rgba(255,255,255,0.08);
    margin-bottom: 25px;
    box-shadow: 0 20px 70px rgba(0,0,0,0.35);
}

.logo {
    font-size: 38px;
    font-weight: 900;
    letter-spacing: -1px;
}

.logo span {
    color: #8b7cff;
}

.subtitle {
    color: #aeb4c8;
    font-size: 15px;
    margin-top: 7px;
}

.section-title {
    font-size: 24px;
    font-weight: 800;
    margin-top: 28px;
    margin-bottom: 12px;
}

.channel-card {
    background: rgba(18, 21, 31, 0.95);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 18px;
    padding: 12px;
    min-height: 190px;
    transition: 0.2s;
}

.channel-card:hover {
    transform: translateY(-3px);
    border-color: rgba(139,124,255,0.5);
}

.channel-logo {
    width: 100%;
    height: 105px;
    object-fit: contain;
    background: #10131c;
    border-radius: 13px;
}

.channel-placeholder {
    width: 100%;
    height: 105px;
    border-radius: 13px;
    background:
        linear-gradient(
            135deg,
            #171b29,
            #0d0f16
        );
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 38px;
}

.channel-name {
    font-size: 15px;
    font-weight: 800;
    margin-top: 10px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.channel-meta {
    color: #8d94a8;
    font-size: 12px;
    margin-top: 4px;
}

.badge-live {
    display: inline-block;
    padding: 4px 8px;
    border-radius: 20px;
    background: rgba(255, 60, 80, 0.15);
    color: #ff7080;
    font-size: 10px;
    font-weight: 800;
}

.footer {
    text-align: center;
    color: #70778b;
    padding: 40px 10px 10px 10px;
    font-size: 12px;
}

div[data-testid="stButton"] > button {
    border-radius: 12px;
    min-height: 42px;
    font-weight: 700;
}

div[data-testid="stTextInput"] input {
    background: #11141d;
    color: white;
    border: 1px solid #282d3d;
    border-radius: 12px;
}

div[data-testid="stSelectbox"] > div {
    background: #11141d;
}

</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# OUTILS
# ============================================================

def normalize_text(value):
    value = str(value or "")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        char for char in value
        if not unicodedata.combining(char)
    )
    return value.lower().strip()


def safe(value):
    return html.escape(str(value or ""))


def unique_channels(channels):
    result = []
    seen = set()

    for channel in channels:
        name = normalize_text(channel.get("name"))
        stream = str(channel.get("stream") or "").strip()
        url = str(channel.get("url") or "").strip()

        key = (
            name,
            stream or url,
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(channel)

    return result


# ============================================================
# M3U PARSER
# ============================================================

def parse_m3u(text):
    channels = []

    if not text:
        return channels

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    current = None

    for line in lines:

        if line.startswith("#EXTINF"):

            attrs = {}

            for key, value in re.findall(
                r'([\w-]+)="([^"]*)"',
                line
            ):
                attrs[key.lower()] = value

            title = line.split(",", 1)[1].strip() \
                if "," in line else attrs.get(
                    "tvg-name",
                    "Chaîne"
                )

            current = {
                "name": title,
                "logo": attrs.get(
                    "tvg-logo",
                    ""
                ),
                "group": attrs.get(
                    "group-title",
                    "Autres"
                ),
                "country": "",
                "category": attrs.get(
                    "group-title",
                    "Autres"
                ),
                "url": "",
                "stream": "",
            }

        elif not line.startswith("#") and current:
            current["stream"] = line
            channels.append(current)
            current = None

    return channels


# ============================================================
# CHARGEMENT DES PLAYLISTS PUBLIQUES
# ============================================================

@st.cache_data(ttl=3600, show_spinner=False)
def download_playlist(url):
    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "PAVEL-TV/1.0"
                )
            },
        )

        if response.status_code != 200:
            return []

        return parse_m3u(response.text)

    except Exception:
        return []


def country_playlist(code):
    return (
        f"{IPTV_BASE}/countries/{code}.m3u"
    )


def category_playlist(code):
    return (
        f"{IPTV_BASE}/categories/{code}.m3u"
    )


@st.cache_data(ttl=3600, show_spinner=False)
def load_country(code):
    channels = download_playlist(
        country_playlist(code)
    )

    for channel in channels:
        channel["country"] = code.upper()

    return channels


@st.cache_data(ttl=3600, show_spinner=False)
def load_category(code):
    channels = download_playlist(
        category_playlist(code)
    )

    return channels


# ============================================================
# TEST FLUX
# ============================================================

@st.cache_data(ttl=600, show_spinner=False)
def check_stream(url):
    if not url:
        return False

    try:
        response = requests.get(
            url,
            stream=True,
            timeout=8,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "PAVEL-TV/1.0"
                )
            },
        )

        return response.status_code < 400

    except Exception:
        return False


# ============================================================
# SESSION
# ============================================================

if "favorites" not in st.session_state:
    st.session_state.favorites = []

if "custom_channels" not in st.session_state:
    st.session_state.custom_channels = []

if "selected_channel" not in st.session_state:
    st.session_state.selected_channel = None

if "page" not in st.session_state:
    st.session_state.page = 0


# ============================================================
# FAVORIS
# ============================================================

def channel_key(channel):
    return (
        channel.get("name", "")
        + "|"
        + channel.get("stream", "")
        + "|"
        + channel.get("url", "")
    )


def is_favorite(channel):
    return (
        channel_key(channel)
        in st.session_state.favorites
    )


def toggle_favorite(channel):
    key = channel_key(channel)

    if key in st.session_state.favorites:
        st.session_state.favorites.remove(key)
    else:
        st.session_state.favorites.append(key)


# ============================================================
# LECTEUR
# ============================================================

def play_channel(channel):
    st.session_state.selected_channel = channel


def render_player(channel):
    if not channel:
        return

    name = channel.get("name", "Chaîne")
    stream = channel.get("stream", "")
    official_url = channel.get("url", "")

    st.markdown(
        f"""
        <div class="hero">
            <div class="logo">
                ▶️ <span>{safe(name)}</span>
            </div>
            <div class="subtitle">
                Lecture de la chaîne
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if stream:

        escaped_stream = html.escape(
            stream,
            quote=True,
        )

        player_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport"
      content="width=device-width, initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>

<style>
html,body {{
    margin:0;
    padding:0;
    background:#05060a;
}}

video {{
    width:100%;
    height:auto;
    max-height:650px;
    background:#000;
    border-radius:16px;
}}
</style>
</head>

<body>

<video id="video"
       controls
       autoplay
       playsinline>
</video>

<script>

const video = document.getElementById("video");
const url = "{escaped_stream}";

function showError(message) {{
    document.body.innerHTML =
        "<div style='color:white;padding:30px;"
        + "font-family:Arial;text-align:center;'>"
        + "⚠️ " + message
        + "</div>";
}}

if (video.canPlayType("application/vnd.apple.mpegurl")) {{

    video.src = url;

    video.addEventListener(
        "error",
        function() {{
            showError(
                "Impossible de lire ce flux."
            );
        }}
    );

}} else if (
    window.Hls &&
    Hls.isSupported()
) {{

    const hls = new Hls({{
        enableWorker: true,
        lowLatencyMode: true,
    }});

    hls.loadSource(url);
    hls.attachMedia(video);

    hls.on(
        Hls.Events.ERROR,
        function(event, data) {{

            if (data.fatal) {{
                showError(
                    "Le flux est indisponible."
                );
                hls.destroy();
            }}

        }}
    );

}} else {{

    showError(
        "Votre navigateur ne prend pas "
        + "en charge ce format vidéo."
    );

}}

</script>

</body>
</html>
"""

        components.html(
            player_html,
            height=680,
            scrolling=False,
        )

    elif official_url:

        st.info(
            "Cette chaîne ne fournit pas de flux "
            "M3U/M3U8 intégré. Utilise son accès officiel."
        )

        st.link_button(
            "🔴 Ouvrir le direct officiel",
            official_url,
            use_container_width=True,
        )

    else:

        st.warning(
            "Aucun flux disponible pour cette chaîne."
        )


# ============================================================
# CARTE CHAÎNE
# ============================================================

def render_card(channel):

    name = channel.get(
        "name",
        "Chaîne",
    )

    logo = channel.get(
        "logo",
        "",
    )

    country = channel.get(
        "country",
        "",
    )

    category = channel.get(
        "category",
        channel.get(
            "group",
            "TV",
        ),
    )

    if logo:

        image_html = (
            f'<img class="channel-logo" '
            f'src="{html.escape(logo, quote=True)}">'
        )

    else:

        image_html = (
            '<div class="channel-placeholder">'
            '📺'
            '</div>'
        )

    st.markdown(
        f"""
        <div class="channel-card">
            {image_html}
            <div class="channel-name">
                {safe(name)}
            </div>
            <div class="channel-meta">
                {safe(country)}
                {" • " if country else ""}
                {safe(category)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)

    with col1:

        if st.button(
            "▶️ Voir",
            key="watch_" + channel_key(channel),
            use_container_width=True,
        ):
            play_channel(channel)

    with col2:

        fav_text = (
            "★" if is_favorite(channel)
            else "☆"
        )

        if st.button(
            fav_text,
            key="fav_" + channel_key(channel),
            use_container_width=True,
        ):
            toggle_favorite(channel)
            st.rerun()


# ============================================================
# GRILLE
# ============================================================

def render_grid(channels):

    if not channels:

        st.info(
            "Aucune chaîne trouvée."
        )
        return

    start = (
        st.session_state.page
        * PAGE_SIZE
    )

    current = channels[
        start:start + PAGE_SIZE
    ]

    cols = st.columns(4)

    for index, channel in enumerate(current):

        with cols[index % 4]:
            render_card(channel)

    total_pages = max(
        1,
        (
            len(channels)
            + PAGE_SIZE
            - 1
        ) // PAGE_SIZE,
    )

    if total_pages > 1:

        st.markdown(
            "---"
        )

        left, middle, right = st.columns(
            [1, 2, 1]
        )

        with left:

            if st.button(
                "⬅️ Précédent",
                disabled=(
                    st.session_state.page <= 0
                ),
                use_container_width=True,
            ):

                st.session_state.page -= 1
                st.rerun()

        with middle:

            st.markdown(
                f"""
                <div style="text-align:center;
                            padding:10px;">
                    Page
                    <b>
                        {st.session_state.page + 1}
                    </b>
                    / {total_pages}
                </div>
                """,
                unsafe_allow_html=True,
            )

        with right:

            if st.button(
                "Suivant ➡️",
                disabled=(
                    st.session_state.page
                    >= total_pages - 1
                ),
                use_container_width=True,
            ):

                st.session_state.page += 1
                st.rerun()


# ============================================================
# CHARGEMENT PRINCIPAL
# ============================================================

@st.cache_data(ttl=3600, show_spinner=False)
def get_default_channels():

    channels = []

    channels.extend(
        CAMEROON_OFFICIAL
    )

    channels.extend(
        load_country("cm")
    )

    return unique_channels(
        channels
    )


# ============================================================
# HEADER
# ============================================================

st.markdown(
    """
    <div class="hero">
        <div class="logo">
            📺 PAVEL <span>TV</span>
        </div>

        <div class="subtitle">
            Télévision en direct • Sports • Actualités
            • Divertissement • Monde
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown(
        "## ⚙️ PAVEL TV"
    )

    st.markdown(
        "### Navigation"
    )

    navigation = st.radio(
        "Section",
        [
            "🏠 Accueil",
            "🇨🇲 Cameroun",
            "⭐ Favoris",
            "🌍 Pays",
            "📂 Catégories",
            "➕ Ajouter une chaîne",
        ],
        label_visibility="collapsed",
    )

    st.markdown("---")

    st.markdown(
        "### 🔎 Recherche"
    )

    search_sidebar = st.text_input(
        "Rechercher",
        placeholder="Nom de chaîne...",
        label_visibility="collapsed",
    )


# ============================================================
# RECHERCHE
# ============================================================

search_top = st.text_input(
    "🔎 Rechercher une chaîne",
    placeholder=(
        "Exemple : Canal 2, CRTV, France 24..."
    ),
)


# ============================================================
# PLAYER
# ============================================================

if st.session_state.selected_channel:

    render_player(
        st.session_state.selected_channel
    )

    if st.button(
        "✕ Fermer le lecteur",
        use_container_width=True,
    ):

        st.session_state.selected_channel = None
        st.rerun()


# ============================================================
# DONNÉES
# ============================================================

all_channels = []

all_channels.extend(
    CAMEROON_OFFICIAL
)

all_channels.extend(
    POPULAR_CHANNELS
      )
      all_channels.extend(
    st.session_state.custom_channels
)


# ============================================================
# NAVIGATION
# ============================================================

if navigation == "🏠 Accueil":

    st.markdown(
        '<div class="section-title">'
        '🇨🇲 Chaînes camerounaises'
        '</div>',
        unsafe_allow_html=True,
    )

    cameroon = unique_channels(
        CAMEROON_OFFICIAL
        + load_country("cm")
    )

    render_grid(
        cameroon
    )

    st.markdown(
        '<div class="section-title">'
        '🔥 Chaînes populaires'
        '</div>',
        unsafe_allow_html=True,
    )

    render_grid(
        unique_channels(
            POPULAR_CHANNELS
        )
    )


elif navigation == "🇨🇲 Cameroun":

    st.markdown(
        '<div class="section-title">'
        '🇨🇲 Télévision camerounaise'
        '</div>',
        unsafe_allow_html=True,
    )

    cameroon = unique_channels(
        CAMEROON_OFFICIAL
        + load_country("cm")
    )

    if search_top or search_sidebar:

        query = normalize_text(
            search_top
            or search_sidebar
        )

        cameroon = [
            c
            for c in cameroon
            if query in normalize_text(
                c.get("name")
            )
        ]

    render_grid(
        cameroon
    )


elif navigation == "⭐ Favoris":

    favorites = [
        channel
        for channel in unique_channels(
            all_channels
        )
        if is_favorite(channel)
    ]

    st.markdown(
        '<div class="section-title">'
        '⭐ Mes chaînes favorites'
        '</div>',
        unsafe_allow_html=True,
    )

    render_grid(
        favorites
    )


elif navigation == "🌍 Pays":

    country_name = st.selectbox(
        "Choisir un pays",
        list(COUNTRIES.keys()),
    )

    code = COUNTRIES[
        country_name
    ]

    st.markdown(
        f"""
        <div class="section-title">
            {safe(country_name)}
        </div>
        """,
        unsafe_allow_html=True,
    )

    channels = load_country(
        code
    )

    render_grid(
        channels
    )


elif navigation == "📂 Catégories":

    category_name = st.selectbox(
        "Choisir une catégorie",
        list(CATEGORIES.keys()),
    )

    code = CATEGORIES[
        category_name
    ]

    st.markdown(
        f"""
        <div class="section-title">
            {safe(category_name)}
        </div>
        """,
        unsafe_allow_html=True,
    )

    channels = load_category(
        code
    )
    render_grid(
        channels
    )


elif navigation == "➕ Ajouter une chaîne":

    st.markdown(
        '<div class="section-title">'
        '➕ Ajouter un flux'
        '</div>',
        unsafe_allow_html=True,
    )

    st.info(
        "Ajoute uniquement des flux que tu as "
        "le droit d'utiliser."
    )

    tab1, tab2, tab3 = st.tabs(
        [
            "🔗 URL M3U/M3U8",
            "📋 Texte M3U",
            "📁 Fichier M3U",
        ]
    )

    with tab1:

        name = st.text_input(
            "Nom de la chaîne",
            key="manual_name",
        )

        stream = st.text_input(
            "URL du flux M3U8",
            key="manual_stream",
        )

        logo = st.text_input(
            "URL du logo (facultatif)",
            key="manual_logo",
        )

        if st.button(
            "➕ Ajouter",
            use_container_width=True,
        ):

            if name and stream:

                st.session_state.custom_channels.append(
                    {
                        "name": name,
                        "country": "Personnalisé",
                        "category": "Mes chaînes",
                        "logo": logo,
                        "url": "",
                        "stream": stream,
                    }
                )

                st.success(
                    "Chaîne ajoutée."
                )

                st.rerun()

            else:

                st.warning(
                    "Indique le nom et le flux."
                )

    with tab2:

        m3u_text = st.text_area(
            "Colle ici ton contenu M3U",
            height=250,
        )

        if st.button(
            "📥 Importer M3U",
            use_container_width=True,
        ):

            imported = parse_m3u(
                m3u_text
            )

            if imported:

                st.session_state.custom_channels.extend(
                    imported
                )

                st.success(
                    f"{len(imported)} chaîne(s) importée(s)."
                )

                st.rerun()

            else:

                st.error(
                    "Aucune chaîne trouvée."
                )

    with tab3:

        uploaded = st.file_uploader(
            "Choisir un fichier M3U",
            type=[
                "m3u",
                "m3u8",
                "txt",
            ],
        )

        if uploaded:

            content = uploaded.read().decode(
                "utf-8",
                errors="ignore",
            )

            imported = parse_m3u(
                content
            )

            st.write(
                f"{len(imported)} chaîne(s) détectée(s)."
            )

            if st.button(
                "📥 Ajouter les chaînes",
                use_container_width=True,
            ):

                st.session_state.custom_channels.extend(
                    imported
                )

                st.success(
                    "Import terminé."
                )

                st.rerun()

    if st.session_state.custom_channels:

        st.markdown(
            "---"
        )

        st.markdown(
            "### 📺 Mes chaînes"
        )

        render_grid(
            st.session_state.custom_channels
        )


# ============================================================
# RECHERCHE GLOBALE
# ============================================================

if search_top or search_sidebar:

    query = normalize_text(
        search_top
        or search_sidebar
    )

    results = []

    # Recherche dans les données locales.
    for channel in unique_channels(
        all_channels
    ):

        haystack = normalize_text(
            " ".join(
                [
                    str(channel.get("name", "")),
                    str(channel.get("country", "")),str(channel.get("category", "")),
                    str(channel.get("group", "")),
                ]
            )
        )

        if query in haystack:
            results.append(
                channel
            )

    # Recherche complémentaire dans le Cameroun.
    for channel in load_country("cm"):

        haystack = normalize_text(
            channel.get("name", "")
        )

        if query in haystack:
            results.append(
                channel
            )

    results = unique_channels(
        results
    )

    st.markdown(
        f"""
        <div class="section-title">
            🔎 Résultats : {len(results)}
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_grid(
        results
    )


# ============================================================
# FOOTER
# ============================================================

st.markdown(
    """
    <div class="footer">
        <b>PAVEL TV</b> • Application de télévision
        <br>
        Les flux personnalisés doivent être utilisés
        conformément aux droits et conditions de leurs fournisseurs.
    </div>
    """,
    unsafe_allow_html=True,
)
