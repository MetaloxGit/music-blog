import csv
import io
import json
import os
import re
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

# --- CONFIGURATION DU DÉPÔT SOURCE ---
REPO_OWNER = "MetaloxGit"
REPO_NAME = "music-records"

HISTORY_FILE = "processed_artists.json"
POSTS_DIR = "_posts"
MIN_PRODUCTS = (
    2  # Seuil minimal de produits pour générer un article sur un artiste
)

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
        (
            r'<meta\s+(?:name|property|itemprop)=["\']([^"\']+)["\']\s+content=["\']([^"\']+)["\']'
        ),
        content,
        re.IGNORECASE,
    )
    for meta_name, meta_val in meta_matches:
      item[meta_name] = meta_val

    meta_matches_inv = re.findall(
        (
            r'<meta\s+content=["\']([^"\']+)["\']\s+(?:name|property|itemprop)=["\']([^"\']+)["\']'
        ),
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
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
      return set(json.load(f))
  return set()


def save_history(history):
  with open(HISTORY_FILE, "w", encoding="utf-8") as f:
    json.dump(list(history), f, ensure_ascii=False, indent=2)





def generate_article_with_ai(artist, products):
  url = "https://openrouter.ai/api/v1/chat/completions"
  api_key = os.environ.get("OPENROUTER_API_KEY")

  if not api_key:
    raise Exception(
        "La variable OPENROUTER_API_KEY est manquante dans les Secrets GitHub."
    )

  prompt = f"""Tu es un disquaire passionné d'occasion et rédacteur web SEO.
Rédige un article de blog au format Markdown sur l'artiste ou groupe : {artist}.

Voici une sélection de ses supports physiques d'occasion actuellement disponibles dans le bac :
{json.dumps(products, ensure_ascii=False, indent=2)}

Consignes de rédaction :
1. Titre principal (H1) accrocheur orienté collection, seconde main et plaisir de l'écoute physique (vinyles, CD, cassettes).
2. Introduction valorisant l'univers musical de {artist} et l'intérêt d'acquérir ses oeuvres d'époque en support physique d'occasion.
3. Pour chaque référence listée : une section H2 avec analyse de l'album/objet, l'atout du format et un bouton d'action Markdown direct vers sa fiche produit : [Découvrir cet exemplaire d'occasion]({{URL_PRODUIT}}).
4. Conseils pour entretenir et préserver ses disques d'occasion de cet artiste.
5. Vocabulaire précis du secteur (pressage d'époque, master, pochette, vinyle, cassette, état).
6. Ne remets pas de balises de code autour du texte Markdown généré.
"""

  payload = json.dumps({
      "messages": [
          {
              "role": "system",
              "content": (
                  "Tu es un spécialiste de la musique d'occasion et de la"
                  " rédaction SEO."
              ),
          },
          {"role": "user", "content": prompt},
      ],
      "model": "google/gemma-2-9b-it:free",
      "temperature": 0.7,
  }).encode("utf-8")

  headers = {
      "Content-Type": "application/json",
      "Authorization": f"Bearer {api_key}",
      "HTTP-Referer": f"https://github.com/{REPO_OWNER}/{REPO_NAME}",
      "X-Title": "Music Record Blog Generator",
  }

  req = urllib.request.Request(
      url, data=payload, headers=headers, method="POST"
  )

  try:
    with urllib.request.urlopen(req, timeout=60) as response:
      res = json.loads(response.read().decode("utf-8"))
      return res["choices"][0]["message"]["content"]
  except urllib.error.HTTPError as e:
    error_body = e.read().decode("utf-8", errors="ignore")
    raise Exception(f"Erreur API ({e.code}) : {error_body}") from e
  except Exception as e:
    raise Exception(f"Échec de connexion réseau : {e}") from e





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
      f"3. Génération de l'article pour {target_artist} ({len(target_products)}"
      " référence(s))..."
  )
  content = generate_article_with_ai(target_artist, target_products)

  Path(POSTS_DIR).mkdir(exist_ok=True)
  filename = f"{POSTS_DIR}/{slugify(target_artist)}.md"

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
