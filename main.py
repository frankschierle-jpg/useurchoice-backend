import os
import uuid
import base64
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

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

app = FastAPI(title="StarSwap Backend")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

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

async def verify_pose_with_ai(photo_bytes: bytes, pose_text: str) -> dict:
    """Nutzt GPT-4 Vision um zu prüfen ob die Pose im Foto stimmt."""
    try:
        image_b64 = base64.b64encode(photo_bytes).decode("utf-8")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o",
                    "max_tokens": 100,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"""Schau dir dieses Foto an. Die Person sollte folgende Pose zeigen: "{pose_text}"
                                    
Antworte NUR mit einem JSON-Objekt in diesem Format:
{{"match": true/false, "confidence": 0-100, "reason": "kurze Erklärung auf Deutsch"}}

Sei fair aber genau. Die Pose muss klar erkennbar sein."""
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{image_b64}",
                                        "detail": "low"
                                    }
                                }
                            ]
                        }
                    ]
                }
            )
        
        if resp.status_code != 200:
            print(f"OpenAI Fehler: {resp.text}")
            return {"match": True, "confidence": 50, "reason": "KI-Prüfung nicht verfügbar"}
        
        data = resp.json()
        text = data["choices"][0]["message"]["content"].strip()
        
        # JSON aus Antwort extrahieren
        import json, re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            result = json.loads(match.group())
            return result
        return {"match": True, "confidence": 50, "reason": "Konnte nicht ausgewertet werden"}
        
    except Exception as e:
        print(f"Pose-Prüfung Fehler: {e}")
        return {"match": True, "confidence": 50, "reason": "KI-Prüfung übersprungen"}

@app.get("/")
def root():
    return {"status": "StarSwap Backend läuft ✅"}

@app.get("/health")
def health():
    return {"status": "ok"}

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
        return JSONResponse({"success": True, "photo_url": result["secure_url"]})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/model/verify-pose")
async def verify_pose(
    photo: UploadFile = File(...),
    pose_text: str = Form(...),
    email: str = Form(...),
):
    """Prüft ob das Foto die geforderte Pose zeigt (GPT-4 Vision)."""
    try:
        photo_bytes = await photo.read()
        
        # KI-Abgleich
        result = await verify_pose_with_ai(photo_bytes, pose_text)
        
        confidence = result.get("confidence", 50)
        match = result.get("match", True)
        
        # Nur ablehnen wenn KI sehr sicher ist dass Pose falsch ist
        if not match and confidence > 75:
            return JSONResponse({
                "success": False,
                "verified": False,
                "confidence": confidence,
                "reason": result.get("reason", "Pose nicht erkannt — bitte nochmal versuchen"),
            })
        
        # Foto auf Cloudinary speichern
        upload = cloudinary.uploader.upload(
            photo_bytes,
            public_id=f"verified/{email.replace('@','_').replace('.','_')}_{uuid.uuid4().hex[:8]}",
            overwrite=False,
        )
        
        return JSONResponse({
            "success": True,
            "verified": True,
            "confidence": result.get("confidence", 100),
            "reason": result.get("reason", "Pose erkannt"),
            "photo_url": upload["secure_url"],
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/faceswap")
async def faceswap(
    prompt: str = Form(...),
    face_url: str = Form(...),
):
    try:
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
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
