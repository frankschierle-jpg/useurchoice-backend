import os
import uuid
import random
import cloudinary
import cloudinary.uploader
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import replicate
import httpx

cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://starswap.me")

app = FastAPI(title="StarSwap Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SPORT_VIDEOS = {
    "surf":  "https://videos.pexels.com/video-files/1918465/1918465-hd_1920_1080_30fps.mp4",
    "ski":   "https://videos.pexels.com/video-files/3551954/3551954-hd_1920_1080_30fps.mp4",
    "climb": "https://videos.pexels.com/video-files/4992801/4992801-hd_1920_1080_30fps.mp4",
    "bike":  "https://videos.pexels.com/video-files/5752729/5752729-hd_1920_1080_30fps.mp4",
    "box":   "https://videos.pexels.com/video-files/4761429/4761429-hd_1920_1080_30fps.mp4",
    "yoga":  "https://videos.pexels.com/video-files/3997927/3997927-hd_1920_1080_30fps.mp4",
    "dive":  "https://videos.pexels.com/video-files/3535473/3535473-hd_1920_1080_30fps.mp4",
    "skate": "https://videos.pexels.com/video-files/4792453/4792453-hd_1920_1080_30fps.mp4",
}

def detect_sport(text: str) -> str:
    t = text.lower()
    mapping = {
        "surf":  ["surf","welle","ozean","beach","bali","hawaii","meer"],
        "ski":   ["ski","schnee","alpen","piste","winter","snowboard"],
        "climb": ["kletter","fels","berg","bouldern","klettern"],
        "bike":  ["bike","fahrrad","downhill","trail","mtb","biken"],
        "box":   ["box","ring","kampf","boxen","sparring"],
        "yoga":  ["yoga","meditation","flow","pose"],
        "dive":  ["tauch","unterwasser","koralle","tauchen"],
        "skate": ["skate","halfpipe","skateboard","trick"],
    }
    for sport, keywords in mapping.items():
        if any(kw in t for kw in keywords):
            return sport
    return "surf"

@app.get("/")
def root():
    return {"status": "StarSwap Backend läuft ✅"}

@app.get("/health")
def health():
    return {"status": "ok"}

# ─── FOTO HOCHLADEN (Model Registrierung) ───
@app.post("/model/upload-photo")
async def upload_model_photo(
    photo: UploadFile = File(...),
    email: str = Form(...),
):
    try:
        photo_bytes = await photo.read()
        result = cloudinary.uploader.upload(
            photo_bytes,
            public_id=f"models/{email.replace('@','_').replace('.','_')}/face_{uuid.uuid4().hex[:8]}",
            overwrite=False,
        )
        return JSONResponse({
            "success": True,
            "photo_url": result["secure_url"],
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── VERIFIKATION ───
@app.post("/model/verify")
async def verify_model(
    photo: UploadFile = File(...),
    email: str = Form(...),
):
    try:
        photo_bytes = await photo.read()
        result = cloudinary.uploader.upload(
            photo_bytes,
            public_id=f"verified/{email.replace('@','_').replace('.','_')}_{uuid.uuid4().hex[:8]}",
            overwrite=False,
        )
        return JSONResponse({
            "success": True,
            "verified": True,
            "photo_url": result["secure_url"],
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── FACE SWAP ───
@app.post("/faceswap")
async def faceswap(
    prompt: str = Form(...),
    face_url: str = Form(...),
):
    try:
        sport = detect_sport(prompt)
        video_url = SPORT_VIDEOS.get(sport, SPORT_VIDEOS["surf"])

        print(f"Face URL: {face_url}")
        print(f"Video URL: {video_url}")
        print(f"Sport: {sport}")

        output = replicate.run(
            "codeplugtech/face-swap:278a81e7ebb22db98bcba54de985d22cc1abeead2754eb1f2af717247be69b34",
            input={
                "target_video": video_url,
                "swap_image": face_url,
            }
        )

        result_video_url = str(output)

        final = cloudinary.uploader.upload(
            result_video_url,
            resource_type="video",
            public_id=f"results/{uuid.uuid4().hex}",
            overwrite=True,
        )

        return JSONResponse({
            "success": True,
            "video_url": final["secure_url"],
            "sport": sport,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
