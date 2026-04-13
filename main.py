import os
import uuid
import cloudinary
import cloudinary.uploader
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import replicate

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
        "surf":  ["surf", "welle", "ozean", "beach", "bali", "hawaii", "meer"],
        "ski":   ["ski", "schnee", "alpen", "piste", "winter", "snowboard"],
        "climb": ["kletter", "fels", "berg", "bouldern", "klettern"],
        "bike":  ["bike", "fahrrad", "downhill", "trail", "mtb", "biken"],
        "box":   ["box", "ring", "kampf", "boxen", "sparring"],
        "yoga":  ["yoga", "meditation", "flow", "pose"],
        "dive":  ["tauch", "unterwasser", "koralle", "tauchen"],
        "skate": ["skate", "halfpipe", "skateboard", "trick"],
    }
    for sport, keywords in mapping.items():
        if any(kw in t for kw in keywords):
            return sport
    return "surf"

@app.get("/")
def root():
    return {"status": "FaceSwap Backend läuft ✅"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/faceswap")
async def faceswap(
    photo: UploadFile = File(...),
    prompt: str = Form(...),
):
    try:
        photo_bytes = await photo.read()
        upload_result = cloudinary.uploader.upload(
            photo_bytes,
            public_id=f"faces/temp_{uuid.uuid4().hex}",
            overwrite=True,
        )
        face_url = upload_result["secure_url"]

        sport = detect_sport(prompt)
        video_url = SPORT_VIDEOS.get(sport, SPORT_VIDEOS["surf"])

        os.environ["REPLICATE_API_TOKEN"] = os.environ.get("REPLICATE_API_TOKEN", "")

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
            "prompt": prompt,
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
