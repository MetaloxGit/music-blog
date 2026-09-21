import os
import re
import json
import random
import requests
import unicodedata
from datetime import datetime

# 1. Configuration des clés et API
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Liste des modèles ordonnés du plus puissant/qualitatif au moins puissant
CANDIDATE_MODELS = [
    "qwen/qwen-2.5-72b-instruct:free",           # 1. 72B - Excellent en français
    "meta-llama/llama-3.3-70b-instruct:free",   # 2. 70B - Très puissant et fluide
    "nvidia/nemotron-3-ultra:free",              # 3. 70B - Très bien structuré
    "google/gemini-2.0-flash-lite-001:free",     # 4. Gemini 2.0 - Réactif et intelligent
    "google/gemma-2-9b-it:free",                 # 5. 9B - Très bon compromis
    "meta-llama/llama-3.1-8b-instruct:free",     # 6. 8B - Secours rapide
    "dots-studio/dots-3-note-preview:free",      # 7. Secours léger
    "inclusionai/ling-3.0-flash-vl:free",        # 8. Secours ultra-rapide
    "openrouter/free",                           # 9. Filet de sécurité final
]

def slugify(value):
    """ Génère un slug propre pour le nom du fichier """
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('utf-8')
    value = re.sub(r'[^\w\s-]', '', value).lower()
    return re.sub(r'[-\s]+', '-', value).strip('-')

def call_openrouter(prompt):
    """ Appelle OpenRouter en bouclant sur la liste des modèles """
    if not OPENROUTER_API_KEY:
        raise ValueError("La variable d'environnement OPENROUTER_API_KEY n'est pas définie.")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "[https://github.com/MetaloxGit/music-blog](https://github.com/MetaloxGit/music-blog)",
        "X-Title": "Music Blog Automated Generator"
    }

    for model in CANDIDATE_MODELS:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Tu es un rédacteur web expert en musique d'occasion et en SEO. Tu rédiges en français parfait."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7
        }
        try:
            print(f"Tentative de génération avec le modèle : {model}...")
            response = requests.post("[https://openrouter.ai/api/v1/chat/completions](https://openrouter.ai/api/v1/chat/completions)", headers=headers, json=payload, timeout=60)
            if response.status_code == 200:
                data = response.json()
                text = data['choices'][0]['message']['content']
                print(f"✅ Succès avec {model}")
                return text
            else:
                print(f"⚠️ Échec {model} (Status {response.status_code}): {response.text}")
        except Exception as e:
            print(f"❌ Erreur avec {model}: {e}")

    raise RuntimeError("Tous les modèles d'IA ont échoué.")

def clean_llm_output(text):
    """ Retire les blocs de code Markdown (```markdown ... ```) si l'IA en ajoute """
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text

def main():
    # Exemple de chargement / sélection d'un produit (À adapter selon la source de tes données/JSON)
    # Remplace cette partie si tu récupères tes produits depuis un fichier externe
    product = {
        "artist": "Pink Floyd",
        "title": "The Dark Side of the Moon",
        "format": "33 Tours (Vinyle)",
        "url": "https://exemple.com/produit/pink-floyd-dark-side",
        "description": "Édition originale d'époque en très bon état (VG+), pochette ouvrante."
    }

    target_artist = product.get("artist", "Musique Vintage")
    target_title = product.get("title", "Album Collector")
    target_format = product.get("format", "Vinyle / CD")
    target_url = product.get("url", "#")
    target_description = product.get("description", "Support physique d'époque en très bon état.")

    # Prompt demandant à l'IA de tout générer (Front Matter YAML + Titre SEO + Corps de l'article)
    prompt = f"""
Tu es un rédacteur expert en musique, vinyles et supports physiques collectors.
Rédige un article complet au format Markdown pour un blog spécialisé.

INFORMATIONS SUR LE PRODUIT :
- Artiste / Groupe : {target_artist}
- Titre / Objet : {target_title}
- Format / Support : {target_format}
- Lien du produit : {target_url}
- Description / État : {target_description}

CONSIGNES STRICTES :

1. EN-TÊTE FRONT MATTER (YAML) :
- Génère le bloc Front Matter YAML au tout début de l'article entre deux lignes `---`.
- `title:` Génère un titre SEO ULTRA ATTRACTIF et unique de 70 CARACTÈRES MAXIMUM (espaces compris).
  Structure du titre : [Artiste ou Genre] - [Titre Objet] ([Format]) : [Intention SEO]
  Exemples :
  * Pink Floyd - The Wall (Vinyle 33T) : Guide Collector
  * Daft Punk - Discovery (CD Occasion) : Où le trouver ?
  * Jazz Hard Bop - Compilation (Cassette) : Pépite Rare
- `description:` Rédige une meta-description attrayante sous les 150 caractères.

2. LIEN PRODUIT (SECU & SEO) :
- Tu dois OBLIGATOIREMENT insérer au moins un bouton/lien Markdown d'action vers l'offre en utilisant EXACTEMENT cette syntaxe :
  [{target_title} d'occasion sur la boutique]({target_url}){{{{:target="_blank" rel="noopener"}}}}

3. CONTENU :
- Rédige un article captivant d'environ 300-500 mots.
- Structuré avec des titres H2 (`##`).
- Donne des détails sur l'album/objet, son intérêt collector, des conseils d'écoute et de conservation.

FORMAT DE SORTIE ATTENDU (Commence directement par les trois tirés du Front Matter) :
---
layout: post
title: "VOTRE_TITRE_SEO_ICI"
description: "VOTRE_DESCRIPTION_ICI"
---

## Titre de section...
Corps du texte...
"""

    # Génération par l'IA
    raw_content = call_openrouter(prompt)
    final_content = clean_llm_output(raw_content)

    # Création du fichier dans _posts/
    today = datetime.now().strftime("%Y-%m-%d")
    post_slug = slugify(f"{target_artist}-{target_title}")
    filename = f"{today}-{post_slug}.md"
    
    os.makedirs("_posts", exist_ok=True)
    filepath = os.path.join("_posts", filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(final_content)

    print(f"🎉 Article généré avec succès dans : {filepath}")

if __name__ == "__main__":
    main()
