import os
import uuid
import base64
import random
import re
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

SPORT_KEYWORDS = {
    "surf":  ["surf","surfen","welle","wellen","ozean","meer","strand","beach","bali","hawaii","wellenreiten","brandung"],
    "ski":   ["ski","skifahren","schnee","alpen","piste","winter","snowboard","tiefschnee","powder","chamonix"],
    "climb": ["klettern","kletter","fels","felsen","berg","bouldern","wand","yosemite","dolomiten"],
    "bike":  ["bike","biken","mountainbike","mtb","fahrrad","downhill","trail","whistler"],
    "box":   ["boxen","boxer","ring","kampf","sparring","knockout","punch","schlag"],
    "yoga":  ["yoga","meditation","entspannung","dehnung","stretching","flow","pose"],
    "dive":  ["tauchen","tauch","unterwasser","koralle","riff","scuba","schnorcheln","malediven"],
    "skate": ["skate","skateboard","skateboarden","halfpipe","trick","ollie","kickflip"],
}

def detect_sport(text: str) -> str:
    t = text.lower()
    scores = {}
    for sport, keywords in SPORT_KEYWORDS.items():
        scores[sport] = sum(1 for kw in keywords if kw in t)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "surf"

async def build_pexels_query(prompt: str, sport: str) -> str:
    """Nutzt Gemini um den besten Pexels-Suchbegriff zu generieren."""
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    
    if gemini_key:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}",
                    json={"contents": [{"parts": [{"text": f"""Convert this German text to a short English Pexels video search query (max 4 words).
Text: "{prompt}"
Sport: {sport}
Reply ONLY with the search query, nothing else."""}]}]}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    query = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    query = re.sub(r'[^\w\s]', '', query)
                    query = ' '.join(query.split()[:4])
                    print(f"Gemini query: {query}")
                    return query
        except Exception as e:
            print(f"Gemini error: {e}")
    
    # Fallback
    sport_queries = {
        "surf": "surfing waves ocean", "ski": "skiing snow mountain",
        "climb": "rock climbing cliff", "bike": "mountain biking trail",
        "box": "boxing training fight", "yoga": "yoga meditation",
        "dive": "scuba diving underwater", "skate": "skateboarding tricks",
    }
    return sport_queries.get(sport, f"{sport} action sport")

@app.get("/")
def root():
    return {"status": "StarSwap Backend ✅"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/model/upload-photo")
async def upload_model_photo(photo: UploadFile = File(...), email: str = Form(...)):
    try:
        photo_bytes = await photo.read()
        result = cloudinary.uploader.upload(
            photo_bytes,
            public_id=f"models/{email.replace('@','_').replace('.','_')}/face_{uuid.uuid4().hex[:8]}",
        )
        return JSONResponse({"success": True, "photo_url": result["secure_url"]})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/model/verify")
async def verify_model(photo: UploadFile = File(...), email: str = Form(...)):
    try:
        photo_bytes = await photo.read()
        result = cloudinary.uploader.upload(
            photo_bytes,
            public_id=f"verified/{email.replace('@','_').replace('.','_')}_{uuid.uuid4().hex[:8]}",
        )
        return JSONResponse({"success": True, "verified": True, "photo_url": result["secure_url"]})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/videos/search")
async def search_videos(prompt: str, count: int = 3):
    try:
        sport = detect_sport(prompt)
        search_query = await build_pexels_query(prompt, sport)
        
        pexels_key = os.environ.get("PEXELS_API_KEY", "")
        if not pexels_key:
            raise Exception("Pexels API Key fehlt")
        
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.pexels.com/videos/search",
                headers={"Authorization": pexels_key},
                params={"query": search_query, "per_page": 15, "size": "medium", "orientation": "landscape"}
            )
            
            if resp.status_code != 200:
                raise Exception(f"Pexels {resp.status_code}")
            
            videos = resp.json().get("videos", [])
            
            if not videos:
                resp2 = await client.get(
                    "https://api.pexels.com/videos/search",
                    headers={"Authorization": pexels_key},
                    params={"query": sport + " sport action", "per_page": 15}
                )
                videos = resp2.json().get("videos", [])
            
            random.shuffle(videos)
            result = []
            for v in videos[:count]:
                files = v.get("video_files", [])
                hd = next((f for f in files if f.get("quality") == "hd" and f.get("width", 0) >= 1280), None)
                sd = next((f for f in files if f.get("quality") == "sd"), None)
                best = hd or sd or (files[0] if files else None)
                if not best:
                    continue
                raw = v.get("url", "").split("/")[-2]
                title = re.sub(r'-\d+$', '', raw).replace("-", " ").title()
                if len(title) < 3:
                    title = search_query.title()
                result.append({
                    "id": str(v["id"]),
                    "title": title,
                    "thumb": v.get("image", ""),
                    "videoUrl": best.get("link", ""),
                    "duration": v.get("duration", 30),
                    "sport": sport,
                })
            
            return JSONResponse({"success": True, "videos": result, "sport": sport, "query": search_query})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/faceswap")
async def faceswap(prompt: str = Form(...), face_url: str = Form(...)):
    try:
        print(f"face_url: {face_url}")
        print(f"prompt: {prompt}")
        
        if not face_url or face_url.strip() == "":
            raise HTTPException(status_code=400, detail="Kein Gesichtsfoto! Bitte als Model neu registrieren.")
        
        sport = detect_sport(prompt)
        
        # Pexels Video holen
        video_url = SPORT_VIDEOS.get(sport, SPORT_VIDEOS["surf"])
        try:
            pexels_key = os.environ.get("PEXELS_API_KEY", "")
            if pexels_key:
                search_query = await build_pexels_query(prompt, sport)
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(
                        "https://api.pexels.com/videos/search",
                        headers={"Authorization": pexels_key},
                        params={"query": search_query, "per_page": 5, "size": "medium"}
                    )
                    if resp.status_code == 200:
                        videos = resp.json().get("videos", [])
                        if videos:
                            v = random.choice(videos[:5])
                            files = v.get("video_files", [])
                            hd = next((f for f in files if f.get("quality")=="hd" and f.get("width",0)>=1280), None)
                            sd = next((f for f in files if f.get("quality")=="sd"), None)
                            best = hd or sd or (files[0] if files else None)
                            if best:
                                video_url = best.get("link", video_url)
        except Exception as pe:
            print(f"Pexels error: {pe}")
        
        print(f"video_url: {video_url}")
        
        print(f"Starting face swap with face_url: {face_url}")
        print(f"Video URL: {video_url}")
        
        # Cloudinary URL zu PNG konvertieren
        if "cloudinary.com" in face_url and "/image/upload/" in face_url:
            parts = face_url.split("/image/upload/")
            face_url_png = parts[0] + "/image/upload/f_png/" + parts[1]
            # Extension ersetzen
            if "." in face_url_png.split("/")[-1]:
                base = face_url_png.rsplit(".", 1)[0]
                face_url_png = base + ".png"
        else:
            face_url_png = face_url
            
        print(f"face_url_png: {face_url_png}")
        
        # Face-Swap mit codeplugtech/face-swap
        output = replicate.run(
            "codeplugtech/face-swap:278a81e7ebb22db98bcba54de985d22cc1abeead2754eb1f2af717247be69b34",
            input={
                "target_video": video_url,
                "swap_image": face_url_png,
                "input_image": face_url_png,
            }
        )
        print(f"Face-swap output: {output}")
        
        result_url = str(output)
        final = cloudinary.uploader.upload(
            result_url, resource_type="video",
            public_id=f"results/{uuid.uuid4().hex}", overwrite=True,
        )
        
        return JSONResponse({"success": True, "video_url": final["secure_url"], "sport": sport})
    except HTTPException:
        raise
    except Exception as e:
        print(f"Faceswap error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
