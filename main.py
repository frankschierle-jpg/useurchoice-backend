import os
import uuid
import shutil
import tempfile
import traceback
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import cloudinary
import cloudinary.uploader
import insightface
from insightface.app import FaceAnalysis
from insightface.model_zoo import get_model

# ─── CONFIG ───
cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
)

app = FastAPI(title="FaceSwap Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── LOAD MODELS (einmalig beim Start) ───
print("⏳ Lade FaceAnalysis Modell...")
face_analyzer = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
face_analyzer.prepare(ctx_id=0, det_size=(640, 640))

print("⏳ Lade Face-Swap Modell...")
swapper = get_model("inswapper_128.onnx", download=True, download_zip=True, providers=["CPUExecutionProvider"])
print("✅ Modelle geladen!")

# ─── SPORT VIDEO URLS (Cloudinary oder direkter Link) ───
SPORT_VIDEOS = {
    "surf":  "https://www.pexels.com/download/video/1918465/",
    "ski":   "https://www.pexels.com/download/video/3551954/",
    "climb": "https://www.pexels.com/download/video/4992801/",
    "bike":  "https://www.pexels.com/download/video/5752729/",
    "box":   "https://www.pexels.com/download/video/4761429/",
    "yoga":  "https://www.pexels.com/download/video/3997927/",
    "dive":  "https://www.pexels.com/download/video/3535473/",
    "skate": "https://www.pexels.com/download/video/4792453/",
}

def detect_sport_from_text(text: str) -> str:
    """Erkennt Sportart aus dem Eingabetext."""
    text = text.lower()
    mapping = {
        "surf": ["surf", "welle", "meer", "ozean", "beach", "bali", "hawaii"],
        "ski":  ["ski", "schnee", "alpen", "piste", "winter", "chamonix"],
        "climb":["kletter", "fels", "berg", "bouldern", "wand"],
        "bike": ["bike", "fahrrad", "downhill", "trail", "mtb"],
        "box":  ["box", "ring", "kampf", "punch", "sparring"],
        "yoga": ["yoga", "meditation", "flow", "pose"],
        "dive": ["tauch", "unterwasser", "koralle", "meer", "tief"],
        "skate":["skate", "halfpipe", "trick", "board"],
    }
    for sport, keywords in mapping.items():
        if any(kw in text for kw in keywords):
            return sport
    return "surf"  # Default

def swap_faces_in_video(source_face_img: np.ndarray, video_path: str, output_path: str):
    """Setzt Gesicht aus source_face_img in jedes Frame des Videos ein."""
    # Gesicht aus Quellbild extrahieren
    source_faces = face_analyzer.get(source_face_img)
    if not source_faces:
        raise ValueError("Kein Gesicht im hochgeladenen Foto erkannt. Bitte ein deutliches Frontalbild verwenden.")
    source_face = source_faces[0]

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Maximal 10 Sekunden verarbeiten (Performance)
    max_frames = int(fps * 10)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret or frame_count >= max_frames:
            break

        # Gesichter im Frame finden
        target_faces = face_analyzer.get(frame)
        if target_faces:
            # Größtes Gesicht im Frame nehmen
            target_face = max(target_faces, key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]))
            frame = swapper.get(frame, target_face, source_face, paste_back=True)

        out.write(frame)
        frame_count += 1

    cap.release()
    out.release()
    print(f"✅ {frame_count} Frames verarbeitet")

# ─── ENDPOINTS ───

@app.get("/")
def root():
    return {"status": "FaceSwap Backend läuft ✅", "version": "1.0"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/faceswap")
async def faceswap(
    photo: UploadFile = File(..., description="Gesichtsfoto des Users"),
    prompt: str = Form(..., description="Textbeschreibung was der User sehen möchte"),
):
    tmp_dir = tempfile.mkdtemp()
    try:
        # 1. Foto einlesen
        photo_bytes = await photo.read()
        nparr = np.frombuffer(photo_bytes, np.uint8)
        source_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if source_img is None:
            raise HTTPException(status_code=400, detail="Foto konnte nicht gelesen werden.")

        # 2. Sportart aus Prompt erkennen
        sport = detect_sport_from_text(prompt)
        print(f"📝 Prompt: '{prompt}' → Sportart: {sport}")

        # 3. Passende Video-URL holen
        video_url = SPORT_VIDEOS.get(sport, SPORT_VIDEOS["surf"])

        # 4. Video herunterladen
        import urllib.request
        video_path = os.path.join(tmp_dir, "input.mp4")
        print(f"⬇️ Lade Video: {video_url}")
        req = urllib.request.Request(video_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            with open(video_path, "wb") as f:
                f.write(response.read())

        # 5. Face-Swap durchführen
        output_path = os.path.join(tmp_dir, f"output_{uuid.uuid4().hex}.mp4")
        print("🔄 Starte Face-Swap...")
        swap_faces_in_video(source_img, video_path, output_path)

        # 6. Auf Cloudinary hochladen
        print("☁️ Lade auf Cloudinary hoch...")
        result = cloudinary.uploader.upload(
            output_path,
            resource_type="video",
            public_id=f"faceswap/{uuid.uuid4().hex}",
            overwrite=True,
        )
        video_result_url = result["secure_url"]
        print(f"✅ Video fertig: {video_result_url}")

        return JSONResponse({
            "success": True,
            "video_url": video_result_url,
            "sport": sport,
            "prompt": prompt,
        })

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Fehler: {str(e)}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
