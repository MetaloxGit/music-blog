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


import html
import hashlib
import math
import os
from PIL import Image, ImageDraw, ImageFont

def generate_cover_image(artist, title, format_name, output_path):
    """
    Génère une image 1000x1000 'Minimaliste Vectoriel Hybride'
    adaptée au format (Vinyle, CD, Cassette) avec dégradé radial et filigrane.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 1. Nettoyage des entités HTML (ex: &#x27; -> ')
    artist = html.unescape(artist or "Artiste Inconnu")
    title = html.unescape(title or "Album")
    format_clean_text = html.unescape(format_name or "VINYLE / CD")

    width, height = 1000, 1000

    # 2. Génération de couleurs dynamiques uniques (basées sur le hachage de l'artiste)
    h = hashlib.md5(artist.encode("utf-8")).hexdigest()
    # Couleur centrale
    r1, g1, b1 = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r1, g1, b1 = min(220, r1 + 50), min(220, g1 + 50), min(220, b1 + 50)
    # Couleur des bords (assombrie pour créer un dégradé radial doux)
    r2, g2, b2 = int(r1 * 0.25), int(g1 * 0.25), int(b1 * 0.25)

    # 3. Création du fond en dégradé radial
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    cx, cy = width / 2, height / 2
    max_dist = math.sqrt(cx**2 + cy**2)

    for r in range(int(max_dist), 0, -4):
        ratio = r / max_dist
        r_c = int(r1 * (1 - ratio) + r2 * ratio)
        g_c = int(g1 * (1 - ratio) + g2 * ratio)
        b_c = int(b1 * (1 - ratio) + b2 * ratio)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(r_c, g_c, b_c))

    # 4. Forme iconique en filigrane discret (~5% d'opacité)
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    watermark_color = (255, 255, 255, 18) # Opacité très faible

    fmt_lower = format_clean_text.lower()
    if "cd" in fmt_lower:
        # Forme CD (Anneau extérieur + centre)
        ov_draw.ellipse([180, 180, 820, 820], outline=watermark_color, width=10)
        ov_draw.ellipse([420, 420, 580, 580], outline=watermark_color, width=6)
        ov_draw.ellipse([460, 460, 540, 540], outline=watermark_color, width=4)
    elif "cassette" in fmt_lower or "k7" in fmt_lower:
        # Forme Cassette
        ov_draw.rounded_rectangle([180, 260, 820, 740], radius=35, outline=watermark_color, width=10)
        ov_draw.ellipse([310, 420, 450, 560], outline=watermark_color, width=6)
        ov_draw.ellipse([550, 420, 690, 560], outline=watermark_color, width=6)
        ov_draw.rectangle([280, 610, 720, 700], outline=watermark_color, width=4)
    else:
        # Forme Vinyle (Sillons concentriques)
        for radius in range(430, 120, -35):
            ov_draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=watermark_color, width=3)

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # 5. Polices de caractères
    try:
        font_artist = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 34)
        font_badge = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        font_icon = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    except Exception:
        font_artist = font_title = font_badge = font_icon = ImageFont.load_default()

    # 6. Macaron "OCCASION" (En haut à droite) - Badge Circulaire Jaune Vif
    draw.ellipse([780, 60, 940, 220], fill=(255, 204, 0))
    draw.text((860, 140), "OCCASION", fill=(0, 0, 0), font=font_badge, anchor="mm")

    # 7. Contenu Principal (Texte au centre)
    artist_text = artist.upper()
    if len(artist_text) > 28:
        artist_text = artist_text[:25] + "..."

    title_text = title
    if len(title_text) > 40:
        title_text = title_text[:37] + "..."

    draw.text((500, 450), artist_text, fill=(255, 255, 255), font=font_artist, anchor="mm")
    draw.text((500, 525), title_text, fill=(220, 220, 220), font=font_title, anchor="mm")

    # 8. Icône + Tag Format (En bas à gauche)
    draw.rounded_rectangle([50, 890, 330, 950], radius=12, fill=(0, 0, 0, 120), outline=(255, 255, 255, 60), width=2)

    # Dessin vectoriel simplifié de l'icône
    if "cd" in fmt_lower:
        draw.ellipse([70, 908, 102, 938], outline=(255, 255, 255), width=2)
        draw.ellipse([82, 919, 90, 927], fill=(255, 255, 255))
    elif "cassette" in fmt_lower or "k7" in fmt_lower:
        draw.rectangle([70, 910, 102, 934], outline=(255, 255, 255), width=2)
        draw.ellipse([76, 918, 82, 924], outline=(255, 255, 255), width=1)
        draw.ellipse([90, 918, 96, 924], outline=(255, 255, 255), width=1)
    else: # Vinyle
        draw.ellipse([70, 908, 102, 938], outline=(255, 255, 255), width=2)
        draw.ellipse([81, 918, 91, 928], outline=(255, 255, 255), width=1)

    draw.text((118, 922), format_clean_text.upper()[:14], fill=(255, 255, 255), font=font_icon, anchor="lm")

    # 9. Export WebP optimisé (Super léger ~10-15 Ko)
    img.save(output_path, "WEBP", quality=75, method=6)


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
            "temperature": 0.3,  # Température très basse = réponse stricte, factuelle et sans invention
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
    image_markdown = f"![{image_alt}]({{{{ site.baseurl }}}}/assets/images/posts/{image_filename})\n\n"

    # 3. Assemblage du fichier Markdown final (Frontmatter + Image + Contenu AI)
    full_post = f"""---
layout: post
title: "{target_artist} en vinyle ou CD d'occasion (collector)"
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
