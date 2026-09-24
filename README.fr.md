<p align="center">
  <img src="media/plaquestudio-banner.svg" alt="Plaque Studio — floutage automatique des plaques dans les vidéos dashcam" width="100%">
</p>

# Plaque Studio

**Floutage local des plaques d'immatriculation dans les vidéos.** Importez une vidéo, suivez le traitement, comparez le résultat à l'original et téléchargez un MP4 H.264 avec son audio.

**Langues :** [English](README.md) (par défaut) · Français

Ce projet ajoute une interface web au modèle YOLOv8 de [Dashcam Anonymizer](https://github.com/varungupta31/dashcam_anonymizer), créé par Varun Gupta. Les scripts d'origine pour les images et les vidéos restent présents. La [licence MIT](LICENSE) et l'attribution d'origine sont conservées.

## Démarrage avec Docker

Installez Docker Desktop ou Docker Engine avec Compose. Le premier démarrage nécessite Internet pour construire l'image et télécharger le modèle.

```bash
git clone https://github.com/Bouneh/dashcam-plate-blur-studio.git
cd dashcam-plate-blur-studio
docker compose up --build -d
```

Ouvrez **http://localhost:8001**. Si `model/best.pt` n'existe pas, le conteneur télécharge le modèle du projet d'origine et vérifie son empreinte SHA-256. Vous pouvez aussi placer un modèle compatible à cet emplacement avant le démarrage. Les poids restent sur votre ordinateur et sont exclus de Git.

```bash
docker compose logs -f studio
docker compose down
```

Le port hôte est `8001` par défaut. Pour le changer, créez un fichier `.env` local contenant par exemple `STUDIO_PORT=8088`, puis redémarrez Compose. Le service n'écoute que sur `127.0.0.1`.

## Sans Docker

Il faut Python 3.10 ou 3.11, ainsi que `ffmpeg` et `ffprobe` dans le PATH.

```bash
python -m venv .venv-web
# Activez .venv-web, ou utilisez directement son exécutable Python.
python -m pip install -r requirements-web.txt -r requirements-model.txt
python model_setup.py
python web_server.py --port 8001
```

Ouvrez **http://127.0.0.1:8001**. PyTorch utilise CUDA s'il est disponible ; sinon le traitement s'exécute sur CPU.

## Fonctionnement

L'interface accepte MP4, MOV, MKV, AVI, WebM, WMV, FLV et M4V, jusqu'à 4 Go par défaut. Elle propose trois intensités de flou, la progression, une comparaison et l'historique des traitements. Les fichiers restent dans `web_data/jobs/`. Le modèle fourni possède les classes `license` et `face` ; seule la classe `license` est floutée.

Les réglages principaux sont `STUDIO_PORT`, `DASHCAM_MAX_UPLOAD_GB`, `DASHCAM_DATA_DIR` et `DASHCAM_MODEL_PATH`. Les scripts historiques `blur_images.py` et `blur_videos.py` restent disponibles avec les fichiers YAML de `configs/`.

**Vérifiez chaque vidéo avant diffusion :** la détection automatique peut manquer une plaque. Cette application locale n'a pas d'authentification ; gardez-la accessible uniquement depuis votre machine.

## Licence et attribution

Basé sur [Dashcam Anonymizer de Varun Gupta](https://github.com/varungupta31/dashcam_anonymizer), distribué sous [licence MIT](LICENSE). Le modèle est téléchargé depuis la source indiquée par ce projet et vérifié avec SHA-256.
