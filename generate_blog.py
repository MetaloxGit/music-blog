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

    prompt = f"""Tu es un rédacteur spécialisé dans les supports musicaux physiques
d'occasion (vinyles, CD, cassettes audio et autres formats physiques).
Tu rédiges des articles de blog en français, naturels, informatifs et orientés SEO.

Ta mission est de rédiger un article consacré à l'artiste ou au groupe :
{artist}

==================================================
DONNÉES SOURCE
==================================================

Voici la liste EXACTE des produits actuellement disponibles :

{json.dumps(products_formatted, ensure_ascii=False, indent=2)}

RÈGLE ABSOLUE :
Les données produit ci-dessus sont ta source principale.
Ne complète jamais une information absente par une supposition.

Il vaut toujours mieux fournir moins d'informations que d'en inventer.

==================================================
1. FIABILITÉ — ZÉRO HALLUCINATION
==================================================

N'invente jamais :

- date de sortie ou d'enregistrement ;
- label ;
- numéro de catalogue ou de matrice ;
- pays de pressage ;
- édition ou pressage ;
- membres du groupe ;
- biographie ;
- discographie ;
- genre ou sous-genre musical ;
- influences ;
- anecdote ;
- classement ou certification ;
- ventes ou popularité ;
- rareté ou valeur financière ;
- état du produit ;
- caractéristique technique ;
- tracklist ;
- information historique.

Si une information n'est pas présente dans les données et qu'elle
n'est pas absolument générale et évidente, ne la mentionne pas.

Ne déduis jamais une information à partir du nom de l'artiste,
du titre de l'album, de la pochette ou du format.

Exemple :
si un produit indique uniquement "Vinyle", tu peux parler d'un vinyle,
mais tu ne dois pas inventer son année, son label ou son pressage.

Un artiste très connu doit être traité avec la même prudence
qu'un artiste totalement inconnu.

==================================================
2. FIDÉLITÉ AUX PRODUITS
==================================================

Crée UNE section H2 (`##`) pour CHAQUE produit présent dans le JSON.

N'oublie aucun produit.
N'invente aucun produit supplémentaire.

Pour chaque produit, utilise uniquement les informations réellement
disponibles.

La longueur de la présentation doit être proportionnelle aux données :

- description riche → présentation plus développée ;
- description courte → présentation concise ;
- description vide → présentation courte basée uniquement sur les
  informations certaines disponibles.

Ne remplis jamais artificiellement une description vide.

==================================================
3. URL DES PRODUITS
==================================================

Pour CHAQUE produit, insère obligatoirement son URL exacte
dans ce bouton :

[Découvrir cet exemplaire d'occasion](URL_EXACTE){{:target="_blank" rel="noopener"}}

Utilise exactement l'URL présente dans le champ "url" du JSON.

NE MODIFIE PAS l'URL.
NE RACCOURCIS PAS l'URL.
N'INVENTE AUCUNE URL.

Le bouton doit correspondre au produit présenté dans la section.

==================================================
4. INTRODUCTION
==================================================

Présente naturellement l'artiste et les supports disponibles.

Tu peux évoquer, lorsque les données le permettent :

- l'artiste ou le groupe ;
- les œuvres disponibles ;
- le plaisir de l'écoute physique ;
- la collection ;
- la seconde main ;
- l'intérêt de retrouver une œuvre sur support physique.

Si l'artiste est peu documenté ou si les données sont insuffisantes,
ne crée PAS de biographie.

Dans ce cas, concentre l'introduction sur les supports disponibles
et sur l'intérêt général de la collection physique.

Évite les introductions génériques répétitives comme :
"Depuis toujours, la musique..."
"Dans un monde de plus en plus numérique..."
"Les passionnés de musique savent..."

==================================================
5. DESCRIPTION DES PRODUITS
==================================================

Pour chaque produit, présente lorsque l'information est disponible :

- le titre ;
- le format ;
- les caractéristiques explicitement fournies ;
- les éléments de description utiles ;
- l'intérêt du support physique.

Ne transforme jamais une supposition en fait.

Évite les superlatifs non justifiés tels que :

"culte", "légendaire", "mythique", "incontournable",
"rarissime", "très recherché", "chef-d'œuvre", "pépite",
"collector", "trésor".

Utilise-les uniquement si les données fournies permettent réellement
de les justifier.

==================================================
6. VARIÉTÉ RÉDACTIONNELLE
==================================================

Chaque article doit avoir une rédaction naturelle et ne pas ressembler
à un modèle copié-collé.

Varie lorsque cela est pertinent :

- la longueur des paragraphes ;
- les transitions ;
- l'ordre des informations ;
- la structure des phrases ;
- le vocabulaire ;
- l'angle de présentation ;
- la façon de parler du support physique.

IMPORTANT :
La variation doit être sémantique et structurelle, pas seulement
basée sur des synonymes.

Ne répète pas systématiquement les mêmes formulations comme :

"Les amateurs de..."
"Les collectionneurs apprécieront..."
"Cette édition constitue..."
"Ce format permet de..."

==================================================
7. SECTION CONSEILS — ANTI-RÉPÉTITION
==================================================

Ajoute une section H2 consacrée à un ou deux conseils pratiques
concernant les supports physiques présents dans l'article.

Ne reproduis PAS systématiquement le même paragraphe sur :

- le nettoyage ;
- la brosse antistatique ;
- le stockage vertical ;
- les pochettes ;
- la poussière ;
- la manipulation par les bords.

Choisis les thèmes les plus pertinents parmi :

- nettoyage et entretien ;
- stockage et rangement ;
- humidité, chaleur et environnement ;
- manipulation des vinyles ;
- conservation des pochettes et livrets ;
- entretien des CD ;
- conservation des cassettes ;
- transport d'une collection ;
- organisation et classement ;
- erreurs fréquentes ;
- préservation des supports anciens ;
- protection contre la poussière ;
- préparation avant une première écoute ;
- organisation d'une collection de seconde main.

Ne cherche PAS à traiter toutes ces catégories.

Varie également la forme de la section :

- mini-checklist ;
- 3 conseils pratiques ;
- méthode en quelques étapes ;
- erreur fréquente à éviter ;
- problème et solution ;
- guide pratique ;
- "à faire / à éviter" ;
- conseil spécifique au format.

IMPORTANT :
Changer uniquement les mots ne constitue PAS une variation suffisante.

Par exemple, remplacer "nettoyer régulièrement ses vinyles"
par "entretenir régulièrement ses disques" reste le même conseil.

La variation doit porter sur le SUJET ou l'ANGLE, pas uniquement
sur la formulation.

Les conseils doivent rester simples, prudents et applicables.
N'invente pas de propriété particulière concernant un support.

==================================================
8. ANTI-RÉPÉTITION GLOBAL
==================================================

Évite les paragraphes génériques pouvant être copiés tels quels
d'un article à l'autre.

Évite également de répéter systématiquement :

- la même introduction ;
- les mêmes transitions ;
- le même ordre de présentation ;
- les mêmes conseils ;
- les mêmes exemples ;
- les mêmes conclusions.

Ne cherche cependant pas à varier artificiellement le contenu :
la pertinence et la fiabilité sont prioritaires sur la variété.

==================================================
9. STRUCTURE MARKDOWN
==================================================

Le H1 est généré par le programme appelant.

NE GÉNÈRE DONC AUCUN H1 (`#`).

Utilise uniquement des titres H2 (`##`) pour les sections.

N'utilise aucun H3 (`###`).

Chaque H2 doit être concis et faire MOINS DE 75 CARACTÈRES.

==================================================
10. FORMAT DE SORTIE
==================================================

Retourne UNIQUEMENT l'article final en Markdown.

Ne retourne aucune explication, analyse, note ou commentaire
destiné au programmeur.

Ne place pas le contenu dans un bloc de code Markdown.

Commence directement avec le contenu de l'article.

==================================================
11. CONTRÔLE FINAL SILENCIEUX
==================================================

Avant de répondre, vérifie silencieusement :

[ ] Tous les produits du JSON ont une section H2.
[ ] Aucun produit supplémentaire n'a été inventé.
[ ] Chaque produit possède son bouton avec son URL exacte.
[ ] Aucune URL n'a été inventée ou modifiée.
[ ] Aucun fait biographique non fourni n'a été inventé.
[ ] Aucun genre musical non confirmé n'a été ajouté.
[ ] Aucune date, édition, label ou caractéristique non fournie
    n'a été inventée.
[ ] Les informations inconnues ont été laissées de côté.
[ ] La section conseils est pertinente pour les formats présents.
[ ] La section conseils n'est pas un paragraphe générique recyclé.
[ ] Aucun H1 ou H3 n'est présent.
[ ] Tous les H2 font moins de 75 caractères.
[ ] La réponse contient uniquement du Markdown.
"""

    candidate_models = [
        "qwen/qwen-2.5-72b-instruct:free",           # 1. 72B - Le meilleur pour la rédaction en français
        "meta-llama/llama-3.3-70b-instruct:free",    # 2. 70B - Modèle phare, niveau GPT-4o
        "nvidia/nemotron-3-ultra:free",              # 3. 70B - Spécialisé, très structuré
        "google/gemini-2.0-flash-lite-001:free",     # 4. Architecture Gemini 2.0 - Très intelligent et fluide
        "google/gemma-2-9b-it:free",                 # 5. 9B - Dépasse largement la plupart des petits modèles
        "meta-llama/llama-3.1-8b-instruct:free",     # 6. 8B - Correct mais plus basique
        "dots-studio/dots-3-note-preview:free",      # 7. Modèle léger / spécialisé
        "inclusionai/ling-3.0-flash-vl:free",        # 8. Modèle ultra-léger axé vitesse
        "openrouter/free",                           # 9. Filet de sécurité final (choix auto)
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
