import os
import glob
import json
import cv2
import pybboxes as pbx
import yaml
import argparse
from ultralytics import YOLO
import shutil
from rich.console import Console
from rich.progress import track
from natsort import natsorted
from os.path import join as osj

# --- INITIALISATION ---
console = Console()

# 1. On définit le chemin ABSOLU du dossier courant pour éviter les erreurs relatives
BASE_DIR = os.getcwd()
OUTPUT_DIR_NAME = "yolo_run_final" # Nom unique pour ce dossier
# Chemin complet : /mnt/c/Users/.../yolo_run_final
FULL_OUTPUT_PATH = os.path.join(BASE_DIR, OUTPUT_DIR_NAME)

# Nettoyage préventif radical
if os.path.exists(FULL_OUTPUT_PATH):
    try:
        shutil.rmtree(FULL_OUTPUT_PATH)
    except:
        pass
# On nettoie aussi le dossier 'runs' qui nous embête depuis le début
if os.path.exists("runs"):
    try:
        shutil.rmtree("runs")
    except:
        pass

parser = argparse.ArgumentParser()
parser.add_argument("--config", help = "path of the training configuartion file", required = True)
args = parser.parse_args()

console.print(f"Reading the Configuration file from {args.config}", style="bold green")
with open(args.config, 'r') as f:
    try:
        config = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        print(exc)

console.print("Loading YOLO Model...", style="bold green")
model = YOLO(config["model_path"])

# --- ETAPE 1 : DETECTION (YOLO) ---
if(config["generate_detections"]):
    console.print("Generating YOLO Detections...", style="bold green")

    # STRATEGIE ABSOLUE : On donne le chemin complet à YOLO
    predict_args = {
        "source": config['videos_path'],
        "save": False,
        "save_txt": True,
        "conf": config['detection_conf_thresh'],
        "project": BASE_DIR,        # Racine : Dossier du projet
        "name": OUTPUT_DIR_NAME,    # Nom : yolo_run_final
        "exist_ok": True
    }

    device = 'cuda:0' if config["gpu_avail"] else 'cpu'
    # Lancement de la détection
    model(**predict_args, device=device)

# Recherche des vidéos sources
video_extensions = ['*.mp4', '*.avi', '*.mov', '*.mkv', '*.wmv', '*.flv']
videos = []
for ext in video_extensions:
    videos.extend(glob.glob(os.path.join(config['videos_path'], ext)))
videos = natsorted(videos)

# --- ETAPE 2 : ANALYSE DES RESULTATS ---
if(config["generate_jsons"]):
    print(f"Generating JSONs for {len(videos)} videos")
    for video in track(videos):
        vid_name, _ = os.path.splitext(os.path.basename(video))

        vid = cv2.VideoCapture(video)
        height = vid.get(cv2.CAP_PROP_FRAME_HEIGHT)
        width = vid.get(cv2.CAP_PROP_FRAME_WIDTH)
        vid.release()

        data_dict = {}

        # On cherche EXACTEMENT là où on a dit à YOLO d'écrire
        # Chemin : .../dashcam_anonymizer/yolo_run_final/labels/nom_video*.txt
        labels_dir = os.path.join(FULL_OUTPUT_PATH, 'labels')
        search_pattern = os.path.join(labels_dir, f'{vid_name}*.txt')

        found_files = glob.glob(search_pattern)
        annot_dir = natsorted(found_files)

        # Debugging vital : Afficher où on cherche si on ne trouve rien
        if not annot_dir:
            print(f"DEBUG: Cherché dans : {search_pattern}")
            print(f"DEBUG: Contenu du dossier labels ({labels_dir}) :")
            try:
                print(os.listdir(labels_dir))
            except:
                print("Le dossier labels n'existe pas (YOLO n'a rien détecté ou erreur chemin)")

        try:
            for file in annot_dir:
                if (os.path.basename(file).endswith('.txt')):
                    frame_num = 1
                    fname = os.path.basename(file).replace(".txt", "")
                    if "_" in fname:
                        try:
                            frame_num = int(fname.split("_")[-1])
                        except:
                            pass

                    with open(file, 'r') as fin:
                        for line in fin.readlines():
                            parts = line.split()
                            bbox_yolo = [float(item) for item in parts[1:]]
                            voc_bbox = pbx.convert_bbox(bbox_yolo, from_type="yolo", to_type="voc", image_size=(width,height))

                            if(frame_num not in data_dict.keys()):
                                data_dict[frame_num] = []
                            data_dict[frame_num].append(voc_bbox)

            if(not os.path.exists("annot_jsons/")):
                os.mkdir("annot_jsons")
            with open("annot_jsons/"+str(vid_name)+".json", 'w') as f:
                json.dump(data_dict, f)

        except Exception as e:
            print(f'Error processing annotations for {video}: {e}')

def blur_regions(image, regions):
    for region in regions:
        x1,y1,x2,y2 = region
        x1, y1, x2, y2 = round(x1), round(y1), round(x2), round(y2)
        y1, y2 = max(0, y1), min(image.shape[0], y2)
        x1, x2 = max(0, x1), min(image.shape[1], x2)

        if x1 < x2 and y1 < y2:
            roi = image[y1:y2, x1:x2]
            blur_k = config["blur_radius"] if config["blur_radius"] % 2 != 0 else config["blur_radius"] + 1
            try:
                blurred_roi = cv2.GaussianBlur(roi, (blur_k, blur_k), 0)
                image[y1:y2, x1:x2] = blurred_roi
            except:
                pass
    return image

# --- ETAPE 3 : FLOUTAGE ET EXPORT ---
if not(os.path.exists(config["output_folder"])):
    os.mkdir(config["output_folder"])

anonymized_videos_path = config["output_folder"]

for video in track(videos):
    vid_name, _ = os.path.splitext(os.path.basename(video))
    json_path = f'annot_jsons/{vid_name}.json'

    if(os.path.exists(json_path)):
        with open(json_path) as F:
            data = json.load(F)

            if not data:
                console.print(f"JSON empty for {vid_name}, copying original.", style="bold yellow")
                shutil.copy(video, osj(anonymized_videos_path, os.path.basename(video)))
                continue

            video_capture = cv2.VideoCapture(video)
            out_vid_path = osj(anonymized_videos_path, vid_name + '.mp4')

            frame_width = int(video_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = video_capture.get(cv2.CAP_PROP_FPS)

            # Codec MP4V
            output_video = cv2.VideoWriter(out_vid_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (frame_width, frame_height))

            count = 1
            while True:
                ret, frame = video_capture.read()
                if not ret:
                    break

                if str(count) in data:
                    frame = blur_regions(frame, data[str(count)])
                elif count in data:
                    frame = blur_regions(frame, data[count])

                output_video.write(frame)
                count+=1

            video_capture.release()
            output_video.release()
        print(f"Processed Video {vid_name}")
    else:
        console.print(f"No objects detected for {video}", style="bold yellow")
        try:
            shutil.copy(video, osj(anonymized_videos_path, os.path.basename(video)))
        except shutil.SameFileError:
            pass

# Nettoyage final
if os.path.exists(FULL_OUTPUT_PATH):
    try:
        shutil.rmtree(FULL_OUTPUT_PATH)
    except:
        pass
if os.path.exists("annot_jsons/"):
    try:
        shutil.rmtree("annot_jsons/")
    except:
        pass

console.print(f"DONE! Videos saved in: {anonymized_videos_path}", style="bold green")
