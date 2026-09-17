import os
import io
import json
import re
import urllib.request
import zipfile
from pathlib import Path
from datetime import datetime

# Configurations
# Détection automatique du dépôt sur GitHub Actions
github_repo = os.getenv("GITHUB_REPOSITORY", "MetaloxGit/music-records")
if "/" in github_repo:
    REPO_OWNER, REPO_NAME = github_repo.split("/", 1)
else:
    REPO_OWNER = "MetaloxGit"
    REPO_NAME = "music-records"
MIN_PRODUCTS = 1
POSTS_DIR = "_posts"
HISTORY_FILE = "history.json"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


def slugify(text):
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "-", text).strip("-")


def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(list(history), f, ensure_ascii=False, indent=2)


def get_field(item, keys, default=""):
    if isinstance(item, dict):
        for k in keys:
            if k in item and item[k]:
                return str(item[k]).strip()
    return default


def parse_item(content, rel_path):
    items = []
    if rel_path.endswith(".json"):
        try:
            data = json.loads(content)
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = [data]
        except Exception:
            pass
    return items


def clean_dead_links(products):
    pass


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
                                    "by",
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


def generate_article_with_ai(artist, products):
    print(f"Génération de l'article pour {artist} via OpenRouter...")

    prompt = f"""Rédige un article de blog attrayant en français sur l'artiste ou groupe musical '{artist}'.
Voici les fiches produits disponibles dans le catalogue d'occasion :
{json.dumps(products[:10], ensure_ascii=False, indent=2)}

L'article doit présenter l'artiste, sa discographie marquante, et mettre en valeur la sélection de vinyles/CDs ci-dessus.
Formate le tout en Markdown direct, sans inclure de bloc de code autour."""

    req_data = {
        "model": "openrouter/free",
        "messages": [{"role": "user", "content": prompt}],
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com",
        "X-Title": "Jekyll Auto Blog",
    }

    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(req_data).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as res:
            response_data = json.loads(res.read().decode("utf-8"))
            return response_data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Erreur lors de l'appel AI : {e}")
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
        artist = p.get("artist", "")
        if artist:
            grouped.setdefault(artist, []).append(p)

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
title: "{target_artist} en vinyles et CD d'occasion : Sélection & Guide collector"
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
