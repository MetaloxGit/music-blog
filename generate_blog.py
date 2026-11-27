import csv
import io
import json
import html
import os
import re
import urllib.error
import urllib.request
import zipfile
import hashlib
import math
import os
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURATION DU DÉPÔT SOURCE ---
REPO_OWNER = "MetaloxGit"
REPO_NAME = "music-records"

HISTORY_FILE = "history.json"
POSTS_DIR = "_posts"
MIN_PRODUCTS = 1  # Seuil minimal de produits pour un artiste

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")




def _draw_with_shadow(ov_draw, draw_fn, cx, cy, size, fill_color, shadow_offset=(3, 3), shadow_alpha=150):
    """Dessine un motif vectoriel avec une légère ombre noire pour le contraste."""
    shadow_color = (0, 0, 0, shadow_alpha)
    draw_fn(ov_draw, cx + shadow_offset[0], cy + shadow_offset[1], size, shadow_color)
    draw_fn(ov_draw, cx, cy, size, fill_color)


def _motif_note(draw, cx, cy, size, color):
    """Note de musique (croche) bien visible."""
    w = max(3, int(size * 0.10))
    rx = size * 0.24
    ry = size * 0.17
    ny = cy + size * 0.26
    draw.ellipse([cx - rx * 1.2, ny - ry, cx + rx * 0.6, ny + ry], fill=color)
    stem_x = cx + rx * 0.6
    stem_top = cy - size * 0.42
    draw.line([(stem_x, ny), (stem_x, stem_top)], fill=color, width=w)
    draw.arc([stem_x, stem_top, stem_x + size * 0.38, stem_top + size * 0.38], start=270, end=90, fill=color, width=w)


def _motif_star(draw, cx, cy, size, color):
    """Étoile à 5 branches percutante."""
    w = max(2, int(size * 0.08))
    r_outer = size * 0.48
    r_inner = size * 0.21
    pts = []
    for i in range(10):
        ang = math.radians(i * 36 - 90)
        r = r_outer if i % 2 == 0 else r_inner
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    draw.polygon(pts, fill=color, outline=color)
    draw.line(pts + [pts[0]], fill=color, width=w)


def _motif_heart(draw, cx, cy, size, color):
    """Cœur plein bien marqué."""
    r = size * 0.22
    draw.ellipse([cx - r * 1.35, cy - r * 0.85, cx + r * 0.15, cy + r * 0.65], fill=color)
    draw.ellipse([cx - r * 0.15, cy - r * 0.85, cx + r * 1.35, cy + r * 0.65], fill=color)
    draw.polygon(
        [(cx - r * 1.28, cy + r * 0.15), (cx + r * 1.28, cy + r * 0.15), (cx, cy + r * 1.55)],
        fill=color,
    )


def _motif_vinyl(draw, cx, cy, size, color):
    """Mini vinyle avec macaron central."""
    r = size * 0.44
    w = max(2, int(size * 0.07))
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=w)
    r2 = r * 0.66
    draw.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], outline=color, width=max(1, w - 1))
    r3 = r * 0.24
    draw.ellipse([cx - r3, cy - r3, cx + r3, cy + r3], fill=color)


def _motif_bolt(draw, cx, cy, size, color):
    """Éclair dynamique."""
    s = size * 0.48
    pts = [
        (cx + s * 0.15, cy - s),
        (cx - s * 0.65, cy + s * 0.05),
        (cx - s * 0.05, cy + s * 0.05),
        (cx - s * 0.20, cy + s),
        (cx + s * 0.65, cy - s * 0.10),
        (cx + s * 0.05, cy - s * 0.10),
    ]
    draw.polygon(pts, fill=color)


def _motif_wave(draw, cx, cy, size, color):
    """Barres d'onde / égaliseur audio."""
    bar_w = max(4, int(size * 0.11))
    gap = max(4, int(size * 0.08))
    heights = [0.35, 0.75, 1.0, 0.65, 0.40]
    total_w = len(heights) * bar_w + (len(heights) - 1) * gap
    start_x = cx - total_w / 2
    max_h = size * 0.75
    for i, h_ratio in enumerate(heights):
        bh = max_h * h_ratio
        x0 = start_x + i * (bar_w + gap)
        y0 = cy - bh / 2
        y1 = cy + bh / 2
        draw.rounded_rectangle([x0, y0, x0 + bar_w, y1], radius=max(2, bar_w // 2), fill=color)


def _motif_diamond(draw, cx, cy, size, color):
    """Losange / diamant lumineux."""
    r = size * 0.45
    pts = [(cx, cy - r), (cx + r * 0.85, cy), (cx, cy + r), (cx - r * 0.85, cy)]
    draw.polygon(pts, fill=color)


def generate_cover_image(artist, title, format_name, output_path):
    """
    Génère une pochette 500x500 WebP légère avec dégradé inversé
    (centre sombre, bords colorés) et motifs grands, contrastés et variés.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    artist_clean = html.unescape(artist or "Artiste Inconnu")
    title_clean = html.unescape(title or "Album")
    raw_fmt = html.unescape(format_name or "").lower()

    if "cd" in raw_fmt:
        label_badge = "CD AUDIO"
    elif "cassette" in raw_fmt or "k7" in raw_fmt:
        label_badge = "CASSETTE"
    elif "vinyle" in raw_fmt or "33t" in raw_fmt or "45t" in raw_fmt or "lp" in raw_fmt:
        label_badge = "DISQUE VINYLE"
    else:
        label_badge = "MUSIQUE"

    width, height = 500, 500
    seed_str = f"{artist_clean}|{title_clean}".encode("utf-8")
    h = hashlib.md5(seed_str).hexdigest()

    # Dégradé inversé : centre très sombre (15%), bords vifs
    r2, g2, b2 = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r2, g2, b2 = min(220, r2 + 50), min(220, g2 + 50), min(220, b2 + 50)
    r1, g1, b1 = int(r2 * 0.15), int(g2 * 0.15), int(b2 * 0.15)

    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    cx, cy = width / 2, height / 2
    max_dist = math.sqrt(cx**2 + cy**2)

    for r in range(int(max_dist), 0, -3):
        ratio = r / max_dist
        r_c = int(r1 * (1 - ratio) + r2 * ratio)
        g_c = int(g1 * (1 - ratio) + g2 * ratio)
        b_c = int(b1 * (1 - ratio) + b2 * ratio)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(r_c, g_c, b_c))

    # Calque transparent pour filigrane et motifs percutants
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    watermark_color = (255, 255, 255, 16)

    variant = int(h[6:8], 16) % 4
    if "cd" in raw_fmt:
        ov_draw.ellipse([90, 90, 410, 410], outline=watermark_color, width=5)
        ov_draw.ellipse([210, 210, 290, 290], outline=watermark_color, width=3)
    elif "cassette" in raw_fmt or "k7" in raw_fmt:
        ov_draw.rounded_rectangle([90, 130, 410, 370], radius=18, outline=watermark_color, width=5)
        ov_draw.ellipse([155, 210, 225, 280], outline=watermark_color, width=3)
        ov_draw.ellipse([275, 210, 345, 280], outline=watermark_color, width=3)
    else:
        step = 18 if variant % 2 == 0 else 24
        for radius in range(215, 60, -step):
            ov_draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=watermark_color, width=2)

    # Palette de couleurs vives et contrastées (quasi opaques : alpha = 225)
    punchy_palette = [
        (0, 240, 255, 225),   # Cyan électrique
        (255, 210, 0, 225),   # Jaune doré
        (255, 75, 145, 225),  # Rose / corail vif
        (80, 255, 155, 225),  # Vert menthe néon
        (255, 135, 45, 225),  # Orange punchy
        (175, 120, 255, 225), # Violet lumineux
    ]

    motif_fns = {
        "note": _motif_note,
        "star": _motif_star,
        "heart": _motif_heart,
        "vinyl": _motif_vinyl,
        "bolt": _motif_bolt,
        "wave": _motif_wave,
        "diamond": _motif_diamond,
    }
    motif_keys = list(motif_fns.keys())

    # 3 emplacements élargis autour du centre (évite le bloc titre central et le badge OCCASION)
    motif_spots = [
        (82, 112, 46),
        (125, 365, 42),
        (405, 355, 44),
    ]

    for idx, (mx, my, msize) in enumerate(motif_spots):
        m_idx = (int(h[8 + idx * 2 : 10 + idx * 2], 16) + idx * 2) % len(motif_keys)
        c_idx = (int(h[14 + idx * 2 : 16 + idx * 2], 16) + idx) % len(punchy_palette)
        fn = motif_fns[motif_keys[m_idx]]
        col = punchy_palette[c_idx]
        _draw_with_shadow(ov_draw, fn, mx, my, msize, col, shadow_offset=(3, 3), shadow_alpha=150)

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Polices
    try:
        font_artist = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
        font_badge = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 11)
        font_icon = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 10)
    except Exception:
        font_artist = font_title = font_badge = font_icon = ImageFont.load_default()

    # Macaron OCCASION
    draw.ellipse([390, 30, 470, 110], fill=(255, 204, 0))
    draw.text((430, 70), "OCCASION", fill=(0, 0, 0), font=font_badge, anchor="mm")

    # Textes centraux
    artist_text = artist_clean.upper()
    if len(artist_text) > 28:
        artist_text = artist_text[:25] + "..."

    title_text = title_clean
    if len(title_text) > 40:
        title_text = title_text[:37] + "..."

    draw.text((250, 225), artist_text, fill=(255, 255, 255), font=font_artist, anchor="mm")
    draw.text((250, 262), title_text, fill=(220, 220, 220), font=font_title, anchor="mm")

    # Badge bas gauche
    draw.rounded_rectangle(
        [25, 445, 185, 475],
        radius=6,
        fill=(0, 0, 0),
        outline=(255, 255, 255),
        width=1,
    )

    if "cd" in raw_fmt:
        draw.ellipse([35, 454, 51, 466], outline=(255, 255, 255), width=1)
        draw.ellipse([41, 459, 45, 461], fill=(255, 255, 255))
    elif "cassette" in raw_fmt or "k7" in raw_fmt:
        draw.rectangle([35, 455, 51, 465], outline=(255, 255, 255), width=1)
    else:
        draw.ellipse([35, 454, 51, 466], outline=(255, 255, 255), width=1)
        draw.ellipse([41, 458, 45, 462], outline=(255, 255, 255), width=1)

    draw.text((58, 460), label_badge, fill=(255, 255, 255), font=font_icon, anchor="lm")

    img.save(output_path, "WEBP", quality=50, method=6)



def slugify(text):
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "-", text).strip("-")


def get_field(item, keys, default=""):
    if not isinstance(item, dict):
        return default

    item_lower = {str(k).lower().strip(): v for k, v in item.items()}

    for k in keys:
        k_lower = k.lower().strip()
        if k_lower in item_lower and item_lower[k_lower] is not None:
            val = str(item_lower[k_lower]).strip()
            if val and val.lower() not in ["none", "null", "undefined", ""]:
                return val
    return default


def parse_item(content, filename=""):
    # 1. Tente JSON classique
    try:
        data = json.loads(content)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return [data]
    except Exception:
        pass

    # 2. Tente JSON Lines
    try:
        lines = [
            json.loads(line)
            for line in content.splitlines()
            if line.strip().startswith("{")
        ]
        if lines:
            return lines
    except Exception:
        pass

    # 3. Tente CSV
    if filename.endswith(".csv") or ("," in content and "\n" in content):
        try:
            reader = csv.DictReader(content.splitlines())
            csv_items = list(reader)
            if csv_items and len(csv_items[0]) > 1:
                return csv_items
        except Exception:
            pass

    # 4. Tente Frontmatter YAML
    match = re.search(r"^---\s*\n(.*?)\n---\s*\n?(.*)", content, re.DOTALL)
    if match:
        yaml_text, body = match.group(1), match.group(2)
        item = {}
        for line in yaml_text.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                item[k.strip()] = v.strip().strip('"').strip("'")
        item["body"] = body.strip()[:300]
        return [item]

    # 5. Tente HTML
    if (
        filename.endswith((".html", ".htm"))
        or "<html" in content.lower()
        or "<meta" in content.lower()
    ):
        item = {}

        json_ld_matches = re.findall(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            content,
            re.DOTALL | re.IGNORECASE,
        )
        for json_str in json_ld_matches:
            try:
                ld = json.loads(json_str.strip())
                if isinstance(ld, dict):
                    item.update(ld)
                elif isinstance(ld, list) and len(ld) > 0 and isinstance(ld[0], dict):
                    item.update(ld[0])
            except Exception:
                pass

        meta_matches = re.findall(
            r'<meta\s+(?:name|property|itemprop)=["\']([^"\']+)["\']\s+content=["\']([^"\']+)["\']',
            content,
            re.IGNORECASE,
        )
        for meta_name, meta_val in meta_matches:
            item[meta_name] = meta_val

        meta_matches_inv = re.findall(
            r'<meta\s+content=["\']([^"\']+)["\']\s+(?:name|property|itemprop)=["\']([^"\']+)["\']',
            content,
            re.IGNORECASE,
        )
        for meta_val, meta_name in meta_matches_inv:
            item[meta_name] = meta_val

        title_match = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE)
        if title_match and "title" not in item:
            item["title"] = title_match.group(1).strip()

        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", content, re.IGNORECASE)
        if h1_match and "h1" not in item:
            clean_h1 = re.sub(r"<[^>]+>", "", h1_match.group(1)).strip()
            item["h1"] = clean_h1

        # 📍 EXTRACTION DU BLOC DIV.DESC (État + Texte)
        desc_match = re.search(
            r'<div\s+class=["\']desc["\'][^>]*>(.*?)</div>',
            content,
            re.DOTALL | re.IGNORECASE,
        )
        if desc_match:
            raw_desc = desc_match.group(1)
            # Nettoyage des balises HTML et entités
            clean_desc = re.sub(r"<br\s*/?>", " ", raw_desc)
            clean_desc = clean_desc.replace("&nbsp;", " ")
            clean_desc = re.sub(r"<[^>]+>", " ", clean_desc)
            clean_desc = re.sub(r"\s+", " ", clean_desc).strip()
            item["description"] = html.unescape(clean_desc)

        if item:
            return [item]

    return []


def load_products_from_repo():
    print(
        "1. Téléchargement rapide de l'archive ZIP"
        f" ({REPO_OWNER}/{REPO_NAME})..."
    )

    zip_bytes = None
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Python-Urllib/3.11"
        )
    }

    for branch in ["main", "master"]:
        url = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/archive/refs/heads/{branch}.zip"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as res:
                zip_bytes = res.read()
                print(f"   Archive téléchargée depuis la branche '{branch}'.")
                break
        except Exception as e:
            print(f"   Échec sur la branche '{branch}': {e}")
            continue

    if not zip_bytes:
        print("Erreur : Impossible de télécharger l'archive du dépôt source.")
        return []

    products = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        all_namelist = z.namelist()

        for zip_path in all_namelist:
            ext = os.path.splitext(zip_path)[1].lower()
            filename = os.path.basename(zip_path)

            if ext in [".html", ".htm"] and not filename.startswith("item_"):
                continue

            if "/." in zip_path or zip_path.endswith("/"):
                continue

            parts = zip_path.split("/")
            rel_path = "/".join(parts[1:]) if len(parts) > 1 else zip_path

            if ext in [".json", ".md", ".html", ".htm", ".csv", ".txt"]:
                try:
                    with z.open(zip_path) as f:
                        content = f.read().decode("utf-8", errors="ignore")
                        items = parse_item(content, rel_path)

                        default_product_url = (
                            f"https://{REPO_OWNER.lower()}.github.io/{REPO_NAME}/{rel_path}"
                        )

                        for item in items:
                            artist = get_field(
                                item,
                                [
                                    "artist",
                                    "artiste",
                                    "band",
                                    "author",
                                    "groupe",
                                    "byartist",
                                    "brand",
                                ],
                            )
                            title = get_field(
                                item,
                                [
                                    "title",
                                    "titre",
                                    "album",
                                    "name",
                                    "product_name",
                                    "h1",
                                    "og:title",
                                ],
                            )

                            if not artist and title and " - " in title:
                                t_parts = title.split(" - ", 1)
                                artist = t_parts[0].strip()
                                title = t_parts[1].strip()

                            if artist and title:
                                products.append({
                                    "artist": artist,
                                    "title": title,
                                    "format": get_field(
                                        item,
                                        ["format", "media", "support", "type", "category"],
                                        "Support d'occasion",
                                    ),
                                    "price": get_field(
                                        item, ["price", "prix", "amount"], ""
                                    ),
                                    "url": get_field(
                                        item,
                                        ["url", "link", "lien", "buy_url", "og:url"],
                                        default_product_url,
                                    ),
                                    "description": get_field(
                                        item,
                                        ["description", "body", "summary", "og:description"],
                                        "",
                                    ),
                                })
                except Exception:
                    continue

    print(f"-> {len(products)} fiches produits chargées.")
    return products


def clean_dead_links(valid_products):
    if not Path(POSTS_DIR).exists():
        return

    print("2. Nettoyage des liens morts dans les anciens articles...")
    valid_urls = {p["url"] for p in valid_products if p.get("url")}
    fallback_store_url = f"https://{REPO_OWNER.lower()}.github.io/{REPO_NAME}/"

    for post_file in Path(POSTS_DIR).glob("*.md"):
        content = post_file.read_text(encoding="utf-8")

        def link_replacer(match):
            text = match.group(1)
            url = match.group(2)

            if (
                REPO_NAME in url
                and url not in valid_urls
                and url != fallback_store_url
            ):
                print(f"   [Lien mort corrigé dans {post_file.name}] : {url}")
                return (
                    f"[{text} (Épuisé - Voir le catalogue)]({fallback_store_url})"
                )
            return match.group(0)

        new_content = re.sub(
            r"\[([^\]]+)\]\((https?://[^\)]+)\)", link_replacer, content
        )

        if new_content != content:
            post_file.write_text(new_content, encoding="utf-8")


def load_history():
    if Path(HISTORY_FILE).exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(list(history), f, ensure_ascii=False, indent=2)


def generate_article_with_ai(artist, products):
    url = "https://openrouter.ai/api/v1/chat/completions"
    api_key = os.environ.get("OPENROUTER_API_KEY")

    if not api_key:
        # Stop immédiat si la clé API est absente
        raise RuntimeError("❌ Clé OPENROUTER_API_KEY manquante dans les secrets GitHub.")

    # Formatage propre des données pour l'IA
    products_formatted = [
        {
            "titre": p.get("title"),
            "format": p.get("format"),
            "prix": p.get("price"),
            "url": p.get("url"),
            "description_fournie": p.get("description", "")
        }
        for p in products[:10]
    ]

    # --- NETTOYAGE DES CARACTÈRES HTML ---
    artist = html.unescape(artist)

    for p in products_formatted:
        for key, value in p.items():
            if isinstance(value, str):
                p[key] = html.unescape(value)

    prompt = f"""Tu es un journaliste musical expert, collectionneur passionné et disquaire spécialisé dans les supports physiques d'occasion (vinyles, CD, cassettes audio).
Tu rédiges des articles de blog en français, immersifs, très documentés, naturels et optimisés pour le référencement naturel (SEO).
- Langue obligatoire : L'intégralité du texte (analyses, descriptions, commentaires) doit être rédigée exclusivement en français. Aucune phrase ou paragraphe entier ne doit être rédigé en anglais.
- Jargon autorisé : Conserve uniquement les anglicismes et termes techniques légitimes du vocabulaire des collectionneurs (ex. pressing, inner sleeve, jewel case, gatefold, mint, VG+, artwork, tracklist ...), mais toujours intégrés au sein de phrases françaises.
Ta mission est de rédiger un article d'expertise consacré à l'artiste ou au groupe :
{artist}

==================================================
1. DONNÉES SOURCE (FICHE(S) PRODUIT(S))
==================================================

Voici la liste EXACTE du ou des produits actuellement disponibles :

{json.dumps(products_formatted, ensure_ascii=False, indent=2)}

RÈGLE ABSOLUE :
Les données JSON ci-dessus sont ta seule source de vérité pour le matériel. Ne complète jamais une donnée absente par une supposition.

==================================================
2. FIABILITÉ ET ADAPTATION SELON L'ARTISTE
==================================================

- Artiste très connu : Axe sur sa discographie, la place de l'œuvre dans sa carrière, les anecdotes de studio ou le contexte historique réellement avéré.
- Artiste obscur ou inconnu : Ne cherche sous aucun prétexte à inventer une biographie, une discographie ou des faits historiques (règle absolue : zéro hallucination). Aborde cet enregistrement sous l'angle du mystère, de la « chîne » (digging), de la scène underground d'époque et des caractéristiques sonores du GENRE MUSICAL. Exploite uniquement les indices visuels et physiques réels (matrices, label, pressage, pochette).
- N'invente jamais : date de sortie, numéro de matrice, pays de pressage, liste des titres ou composition du groupe si l'information n'est pas dans le JSON.

==================================================
3. STYLE, TON ET LEXIQUE DISQUAIRE
==================================================

- Ton : Passionné, expert, crédible et immersif.
- Lexique d'expert : Utilise le vocabulaire technique des collectionneurs quand c'est pertinent (pressage d'époque, masterisation, matrix, gatefold, VG+, mint, dynamique sonore, digger, private press, grille Goldmine).
- Interdictions : Aucune introduction générique ou bateau d'IA ("Dans cet article", "Dans un monde de plus en plus numérique", "Il est important de noter"). Attaque directement le sujet dès la première ligne.

==================================================
4. FIDÉLITÉ AUX PRODUITS, ÉTAT ET LIENS
==================================================

- Crée UNE section H2 (`##`) pour CHAQUE produit présent dans le JSON. N'en oublie aucun et n'en invente aucun.

- Analyse la description de chaque produit dans le JSON :
  * Si elle contient des indications d'état (ex. "État pochette", "État disque", ou des grades comme VG++, EX, M-, Mint, Goldmine), tu DOIS rédiger un paragraphe d'expert disquaire analysant la qualité de conservation et d'écoute de cet exemplaire précis.
  * Si la description est très courte ou sans mention d'état, ne brode pas de faux détails techniques : oriente la présentation sur la culture du support (le charme de l'analogique, la nostalgie du pressage) et les critères de collection Goldmine.

- Pour CHAQUE produit, insère obligatoirement le lien d'achat en gras avec le titre exact du disque :

**[-> Découvrir : TITRE_DU_DISQUE](__URL_PRODUIT_0__){{:target="_blank" rel="noopener"}}**

(⚠️ Exemples d'application :
- Si le 1er produit se nomme "Besombe + Django Contre Zorro", écris :
  **[-> Découvrir : Besombe + Django Contre Zorro](__URL_PRODUIT_0__){{:target="_blank" rel="noopener"}}**
- Remplace le chiffre "0" par l'index du produit : __URL_PRODUIT_0__ pour le premier, __URL_PRODUIT_1__ pour le deuxième, etc. N'écris JAMAIS d'adresse http réelle dans le texte).

==================================================
5. SECTION CONSEILS (CONSERVATION / ENTRETIEN)
==================================================

Ajoute une section H2 (`##`) consacrée à 1 conseil pratique d'expert concernant les supports physiques traités dans l'article.
Varie les thèmes d'un article à l'autre (nettoyage, brosse antistatique, rangement vertical, sous-pochettes doublées, préservation des boîtiers/livrets).

==================================================
6. CONTRAINTES DE FORMATAGE MARKDOWN
==================================================

- AUCUN H1 (`#`) : Le titre principal est géré en amont. Ne génère aucun `#`.
- AUCUN H3 (`###`) : Utilise uniquement des titres H2 (`##`).
- Longueur des H2 : Tous les titres H2 doivent faire MOINS DE 75 CARACTÈRES.
- Format de réponse : Retourne UNIQUEMENT l'article final en Markdown brut, sans bloc de code (pas de ```markdown), sans commentaire ni note introductive.
"""

    print("--- CONTENU DU JSON ENVOYÉ À L'IA ---")
    print(json.dumps(products_formatted, ensure_ascii=False, indent=2))

    candidate_models = [
    # 1. Le maître incontesté en open-weights (70B) - Excellent en français et rédaction
    "meta-llama/llama-3.3-70b-instruct:free",
    
    # 2. Mastodonte MoE NVIDIA (550B total) - Très haute capacité de structuration
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    
    # 3. Modèle géant 118B - Très performant sur le suivi d'instructions complexes
    "poolside/laguna-s-2.1:free",
    
    # 4. Modèle NVIDIA 120B MoE - Rédaction longue et haute précision
    "nvidia/nemotron-3-super-120b-a12b:free",
    
    # 5. Modèle Google Gemma 31B - Très fluide pour la génération de contenu
    "google/gemma-4-31b-it:free",
    
    # 6. Modèle GLM haut de gamme - Excellent pour le texte structuré
    "z-ai/glm-5.2:free"
    ]

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": f"https://github.com/{REPO_OWNER}/{REPO_NAME}",
        "X-Title": "Music Record Blog Generator",
    }

    for model_name in candidate_models:
        print(f"   -> Essai avec le modèle : {model_name}...")
        payload = json.dumps({
            "messages": [
                {
                    "role": "system",
                    "content": "Tu es un rédacteur et disquaire professionnel. Tu ne rédiges que des faits vérifiés et incontestables, sans jamais inventer d'anecdotes ou de détails fictifs.",
                },
                {"role": "user", "content": prompt},
            ],
            "model": model_name,
            "temperature": 0.2,  # Température très basse = réponse stricte, factuelle et sans invention
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                res = json.loads(response.read().decode("utf-8"))
                content = res["choices"][0]["message"]["content"].strip()

                # 1. Nettoyage des balises Markdown (```markdown) au début/fin
                content = re.sub(r"^```markdown\s*", "", content, flags=re.MULTILINE)
                content = re.sub(r"^```\s*", "", content, flags=re.MULTILINE)
                content = re.sub(r"```$", "", content, flags=re.MULTILINE).strip()

                # 2. Remplacement automatique des URL par les vraies adresses du JSON
                for idx, p in enumerate(products_formatted):
                    placeholder = f"__URL_PRODUIT_{idx}__"
                    real_url = p.get("url", "")
                    content = content.replace(placeholder, real_url)

                # Sécurité au cas où l'IA aurait écrit "URL_EXACTE"
                if products_formatted:
                    content = content.replace("URL_EXACTE", products_formatted[0].get("url", ""))

                # 3. Contrôle de validité de la réponse
                if "User Safety" in content or len(content) < 100:
                    print(f"   ⚠️ Le modèle {model_name} a renvoyé un message de sécurité ou un texte trop court.")
                    continue

                print(f"   ✅ Succès avec le modèle : {model_name} !")
                return content

        except Exception as e:
            print(f"   ❌ Échec avec {model_name} ({e})")
            continue

    raise RuntimeError("❌ Échec global : aucun modèle IA disponible n'a réussi à générer l'article.")

def main():
    products = load_products_from_repo()
    if not products:
        print("Aucun produit trouvé dans le dépôt source.")
        return

    clean_dead_links(products)
    history = load_history()

    grouped = {}
    for p in products:
        art = p["artist"]
        grouped.setdefault(art, []).append(p)

    target_artist = None
    target_products = []

    for artist, items in grouped.items():
        if artist not in history and len(items) >= MIN_PRODUCTS:
            target_artist = artist
            target_products = items
            break

    if not target_artist:
        print("Aucun nouvel artiste éligible à traiter aujourd'hui.")
        return

    print(
        f"3. Génération de l'article pour {target_artist} ({len(target_products)} référence(s))..."
    )
    content = generate_article_with_ai(target_artist, target_products)

    Path(POSTS_DIR).mkdir(exist_ok=True)

    today_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{POSTS_DIR}/{today_str}-{slugify(target_artist)}.md"

# --- GÉNÉRATION DE L'IMAGE ET ÉCRITURE DE L'ARTICLE ---
    slug_artist = slugify(target_artist)
    image_filename = f"{slug_artist}.webp"
    image_rel_path = f"assets/images/posts/{image_filename}"
    image_abs_path = os.path.join(os.getcwd(), image_rel_path)

    first_p = target_products[0] if target_products else {}
    first_title = first_p.get("title", "")
    first_format = first_p.get("format", "Occasion")

    # 1. Création de l'image WebP sur le disque
    generate_cover_image(target_artist, first_title, first_format, image_abs_path)

    # 2. Lien Markdown vers l'image
    image_alt = f"{target_artist} - {first_title} ({first_format})"
    image_markdown = f'<img src="{{{{ site.baseurl }}}}/assets/images/posts/{image_filename}" alt="{image_alt}" style="width: 60%; min-width: 280px; max-width: 500px; height: auto; display: block; margin: 0 auto 1.5rem auto;" />\n'

    # 3. Assemblage du fichier Markdown final (Frontmatter + Image + Contenu AI)
    full_post = f"""---
layout: post
title: "{target_artist} en vinyle ou CD collector - Astuce/Conseil de collectionneur"
artist: "{target_artist}"
---

{image_markdown}{content}
"""

    # 4. Enregistrement
    with open(filename, "w", encoding="utf-8") as f:
        f.write(full_post)



    history.add(target_artist)
    save_history(history)
    print(f"4. Succès ! Article créé dans {filename}.")


if __name__ == "__main__":
    main()
