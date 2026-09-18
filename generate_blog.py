import csv
import io
import json
import os
import re
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

# --- CONFIGURATION DU DÉPÔT SOURCE ---
REPO_OWNER = "MetaloxGit"
REPO_NAME = "music-records"

HISTORY_FILE = "history.json"
POSTS_DIR = "_posts"
MIN_PRODUCTS = 1  # Seuil minimal de produits pour un artiste

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")


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
                                    )[:200],
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
        print("Clé OPENROUTER_API_KEY manquante dans les secrets.")
        return f"Découvrez notre sélection de vinyles et CD d'occasion pour **{artist}**."

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

    prompt = f"""Tu es un disquaire d'occasion spécialiste des supports physiques d'époque et rédacteur SEO factuel.
Rédige un article de blog au format Markdown sur l'artiste ou groupe : {artist}.

Voici la liste EXACTE des produits physiques disponibles en stock (utilise STRICTEMENT ces données) :
{json.dumps(products_formatted, ensure_ascii=False, indent=2)}

--- CONSIGNES STRICTES DE RÉDACTION ET FIABILITÉ (ZERO HALLUCINATION) ---
1. **FIDÉLITÉ AUX DONNÉES PRODUIT** :
   - Tu dois créer une section H2 pour chaque produit listé dans la sélection JSON ci-dessus.
   - Tu dois OBLIGATOIREMENT insérer l'URL exacte présente dans le champ "url" du produit pour créer le bouton d'action Markdown : [Découvrir cet exemplaire d'occasion](INSERER_ICI_L_URL_EXACTE_DU_JSON){{:target="_blank" rel="noopener"}}.
   - Ne modifie JAMAIS l'URL fournie et n'invente aucun lien fictif.

2. **RIGUEUR FACTUELLE ET HISTORIQUE (INTERDICTION D'INVENTER)** :
   - Tu ne dois mentionner que des informations musicales et historiques 100% incontestables sur {artist} (genre musical principal, notoriété générale, pertinence du format vinyle/CD/cassette).
   - N'invente AUCUNE biographie de groupe. Si l'entité concerne un artiste peu documenté, parle uniquement du disque, de son pressage et du plaisir de chiner ce type d'enregistrement d'époque.
   - Ne catégorise PAS cet enregistrement dans un style musical précis si ce n'est pas explicitement mentionné dans le titre ou la description fournie.

3. **STRUCTURE DU CONTENU** :
   - Titre principal H1 : Accrocheur, orienté collection, seconde main et plaisir de l'écoute physique.
   - Introduction : Présentation factuelle de l'univers de {artist} et de l'intérêt d'acquérir ses oeuvres d'époque.
   - Sections H2 (une par produit) : Présentation de l'album/support, intérêt du format, et le bouton Markdown intégrant l'URL exacte du produit.
   - Section conseils : Recommandations pratiques et universelles pour nettoyer, préserver et stocker les disques et pochettes d'occasion.

4. **FORMATAGE** :
   - Ne rajoute PAS de balises de code autour du texte Markdown généré (ne mets pas de ```markdown au début ou à la fin).

5. **STRUCTURE ET SEO DES TITRES** :
   - Ne génère STRICTEMENT AUCUN titre `#` (H1) dans le texte.
   - Utilise uniquement des sous-titres de niveau 2 (`##`).
   - Tous tes sous-titres (`##` ou `###`) doivent être concis et faire MOINS DE 75 CARACTÈRES.
"""

    candidate_models = [
        "inclusionai/ling-3.0-flash-vl:free",       # 1. Ultra rapide (~140 tok/s)
        "dots-studio/dots-3-note-preview:free",      # 2. Très rapide (~91 tok/s)
        "google/gemini-2.0-flash-lite-001:free",     # 3. Très stable & réactif
        "nvidia/nemotron-3-ultra:free",              # 4. 100% de succès sur tes logs
        "meta-llama/llama-3.3-70b-instruct:free",   # 5. Modèle puissant (70B)
        "qwen/qwen-2.5-72b-instruct:free",           # 6. Très bon en français
        "meta-llama/llama-3.1-8b-instruct:free",     # 7. Secours rapide (8B)
        "google/gemma-2-9b-it:free",                 # 8. Secours (9B)
        "openrouter/free",                           # 9. Filet de sécurité final
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

                if "User Safety" in content or len(content) < 50:
                    print(f"   ⚠️ Le modèle {model_name} a renvoyé un message de sécurité ou texte trop court.")
                    continue

                print(f"   ✅ Succès avec le modèle : {model_name} !")
                return content

        except Exception as e:
            print(f"   ❌ Échec avec {model_name} ({e})")
            continue

    return f"Découvrez notre sélection de vinyles et CD d'occasion pour **{artist}**."


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

    full_post = f"""---
layout: post
title: "{target_artist} en vinyle ou CD d'occasion (collector)"
artist: "{target_artist}"
---

{content}
"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write(full_post)

    history.add(target_artist)
    save_history(history)
    print(f"4. Succès ! Article créé dans {filename}.")


if __name__ == "__main__":
    main()
