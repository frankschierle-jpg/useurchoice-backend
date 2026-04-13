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

VERIFICATION_POSES = [
    "Hebe deine rechte Hand über den Kopf",
    "Zeige ein Peace-Zeichen mit beiden Händen",
    "Lege beide Hände auf die Wangen",
    "Zeige einen Daumen hoch mit der linken Hand",
    "Verschränke die Arme vor der Brust",
    "Zeige drei Finger mit der rechten Hand",
    "Lege eine Hand auf die Schulter",
    "Zeige ein Herzzeichen mit beiden Händen",
]

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

async def send_verification_email(email: str, pose: str, token: str):
    verify_url = f"{FRONTEND_URL}?verify={token}"
    html = f"""
    <div style="font-family: 'Helvetica Neue', sans-serif; max-width: 600px; margin: 0 auto; background: #060810; color: #e8ecf4; padding: 40px; border-radius: 16px;">
      <div style="text-align: center; margin-bottom: 32px;">
        <h1 style="font-size: 28px; font-weight: 800; margin: 0;">
          <span style="color: #f59e0b;">STAR</span><span style="color: #e8ecf4;">SWAP</span>
        </h1>
        <p style="color: #5a5e6b; margin-top: 8px;">Model Verifikation</p>
      </div>
      
      <h2 style="font-size: 20px; margin-bottom: 16px;">Dein Profil ist fast fertig! ⭐</h2>
      <p style="color: #8892a4; line-height: 1.6; margin-bottom: 24px;">
        Um dein Model-Profil zu bestätigen, mache bitte ein Foto von dir in dieser Pose:
      </p>
      
      <div style="background: #0c1018; border: 2px solid #f59e0b; border-radius: 12px; padding: 24px; text-align: center; margin-bottom: 32px;">
        <div style="font-size: 48px; margin-bottom: 12px;">🤳</div>
        <div style="font-size: 20px; font-weight: 700; color: #f59e0b;">{pose}</div>
      </div>
      
      <p style="color: #8892a4; margin-bottom: 24px;">
        Lade das Foto auf StarSwap hoch um dein Profil zu aktivieren:
      </p>
      
      <a href="{verify_url}" style="display: block; background: linear-gradient(135deg, #f59e0b, #d97706); color: #000; text-decoration: none; padding: 16px; border-radius: 12px; text-align: center; font-weight: 800; font-size: 16px;">
        ✅ Profil verifizieren →
      </a>
      
      <p style="color: #2e3446; font-size: 11px; margin-top: 24px; text-align: center;">
        Dieser Link ist 24 Stunden gültig.
      </p>
    </div>
    """
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={
                "from": "StarSwap <verify@starswap.me>",
                "to": [email],
                "subject": "⭐ StarSwap — Verifiziere dein Model-Profil",
                "html": html,
            }
        )
        if resp.status_code not in (200, 201):
            raise Exception(f"Mail-Fehler: {resp.text}")

@app.get("/")
def root():
    return {"status": "StarSwap Backend läuft ✅"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/model/send-verification")
async def send_verification(email: str = Form(...)):
    try:
        pose = random.choice(VERIFICATION_POSES)
        token = uuid.uuid4().hex
        await send_verification_email(email, pose, token)
        return JSONResponse({"success": True, "token": token, "pose": pose})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/model/verify")
async def verify_model(
    photo: UploadFile = File(...),
    token: str = Form(...),
    email: str = Form(...),
):
    try:
        photo_bytes = await photo.read()
        result = cloudinary.uploader.upload(
            photo_bytes,
            public_id=f"verified/{uuid.uuid4().hex}",
            overwrite=True,
        )
        return JSONResponse({
            "success": True,
            "verified": True,
            "photo_url": result["secure_url"],
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/faceswap")
async def faceswap(
    photo: UploadFile = File(...),
    prompt: str = Form(...),
    model_email: str = Form(default=""),
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

        output = replicate.run(
            "codeplugtech/face-swap:278a81e7ebb22db98bcba54de985d22cc1abeead2754eb1f2af717247be69b34",
            input={"target_video": video_url, "swap_image": face_url}
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
            "tokens_earned": 9,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
