import io
import json
import os
import re
import urllib.request
import zipfile
from pathlib import Path

# --- CONFIGURATION DU DÉPÔT SOURCE ---
REPO_OWNER = "MetaloxGit"
REPO_NAME = "music-records"

HISTORY_FILE = "processed_artists.json"
POSTS_DIR = "_posts"
MIN_PRODUCTS = 2  # Seuil minimal de produits pour générer un article sur un artiste

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")


def slugify(text):
  text = text.lower()
  text = re.sub(r"[^\w\s-]", "", text)
  return re.sub(r"[-\s]+", "-", text).strip("-")


def parse_item(content):
  """Extrait les données soit d'un objet JSON, soit d'un en-tête YAML Frontmatter."""
  try:
    data = json.loads(content)
    if isinstance(data, list):
      return data
    elif isinstance(data, dict):
      return [data]
  except Exception:
    pass

  match = re.search(r"^---\s*\n(.*?)\n---\s*\n?(.*)", content, re.DOTALL)
  if match:
    yaml_text, body = match.group(1), match.group(2)
    item = {}
    for line in yaml_text.splitlines():
      if ":" in line:
        k, v = line.split(":", 1)
        item[k.strip().lower()] = v.strip().strip('"').strip("'")
    item["body"] = body.strip()[:300]
    return [item]
  return []


def get_field(item, keys, default=""):
  for k in keys:
    if k in item and item[k]:
      return str(item[k]).strip()
  return default


def load_products_from_repo():
  print(
      "1. Téléchargement rapide de l'archive ZIP"
      f" ({REPO_OWNER}/{REPO_NAME})..."
  )

  zip_bytes = None
  for branch in ["main", "master"]:
    url = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/archive/refs/heads/{branch}.zip"
    req = urllib.request.Request(url, headers={"User-Agent": "Python-Script"})
    try:
      with urllib.request.urlopen(req) as response:
        zip_bytes = response.read()
        print(f"   Archive téléchargée depuis la branche '{branch}'.")
        break
    except Exception as e:
      print(f"   Échec sur la branche '{branch}': {e}")
      continue

  if not zip_bytes:
    print("Erreur : Impossible de télécharger l'archive du dépôt source.")
    return []

  products = []
  # Lecture directe en mémoire sans requêtes réseau individuelles
  with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
    for filename in z.namelist():
      if filename.endswith((".json", ".md", ".html")) and "/." not in filename:
        try:
          with z.open(filename) as f:
            content = f.read().decode("utf-8", errors="ignore")
            items = parse_item(content)
            for item in items:
              artist = get_field(
                  item, ["artist", "artiste", "band", "author", "groupe"]
              )
              title = get_field(item, ["title", "titre", "album", "name"])

              if artist and title:
                products.append({
                    "artist": artist,
                    "title": title,
                    "format": get_field(
                        item,
                        ["format", "media", "support", "type"],
                        "Support d'occasion",
                    ),
                    "price": get_field(item, ["price", "prix"], ""),
                    "url": get_field(
                        item,
                        ["url", "link", "lien", "buy_url"],
                        f"https://{REPO_OWNER.lower()}.github.io/{REPO_NAME}/",
                    ),
                    "description": get_field(
                        item, ["description", "body", "summary"], ""
                    )[:200],
                })
        except Exception:
          continue

  print(f"-> {len(products)} fiches produits chargées en quelques secondes.")
  return products


def clean_dead_links(valid_products):
  """Met à jour les liens des articles existants si le produit a été supprimé."""
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
  url = "https://models.inference.ai.azure.com/chat/completions"

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
      "model": "gpt-4o-mini",
      "temperature": 0.7,
  }).encode("utf-8")

  headers = {
      "Content-Type": "application/json",
      "Authorization": f"Bearer {GITHUB_TOKEN}",
  }

  req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
  with urllib.request.urlopen(req) as response:
    res = json.loads(response.read().decode("utf-8"))
    return res["choices"][0]["message"]["content"]


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
