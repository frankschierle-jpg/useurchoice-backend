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
        
        # Sport-Szene Prompt auf Englisch übersetzen für Kling
        sport_prompts = {
            "surf": "The person in the reference image is surfing massive ocean waves in Bali, wearing a wetsuit, riding a surfboard, dramatic ocean spray, sunny day, action sports photography",
            "ski": "The person in the reference image is skiing down a steep snowy mountain, wearing ski gear and helmet, powder snow flying, alpine scenery, fast action sports",
            "climb": "The person in the reference image is rock climbing on a dramatic vertical cliff face, wearing climbing harness and helmet, reaching for a hold, mountain backdrop, extreme sport",
            "bike": "The person in the reference image is mountain biking downhill on a forest trail, wearing helmet and protective gear, jumping over a rocky section, action sport",
            "box": "The person in the reference image is boxing in a professional ring, wearing boxing gloves and shorts, throwing a powerful punch, dramatic lighting, sports action",
            "yoga": "The person in the reference image is doing advanced yoga poses on a peaceful beach at sunrise, wearing yoga clothes, serene atmosphere",
            "dive": "The person in the reference image is scuba diving underwater in a tropical coral reef, wearing diving gear, surrounded by colorful fish and coral",
            "skate": "The person in the reference image is skateboarding in an urban skatepark, wearing protective gear, performing a trick on a halfpipe, action sports",
        }
        
        # Gemini baut aus Schlagworten einen perfekten Kling-Prompt
        base_prompt = sport_prompts.get(sport, f"person doing {sport}, action sport, cinematic")
        video_prompt = base_prompt
        try:
            gemini_key = os.environ.get("GEMINI_API_KEY", "")
            if gemini_key:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}",
                        json={"contents": [{"parts": [{"text": f"""You are a video prompt engineer for Kling AI (image-to-video model).
                        
The user uploaded a face photo as reference image. Create a detailed English prompt that:
1. Starts with "The person in the reference image is..."
2. Places them in an action sport scene
3. Includes all details from the user's keywords

User keywords: "{prompt}"
Detected sport: {sport}
Base scene: {base_prompt}

Rules:
- Max 40 words
- Very specific about the sport action
- Include location, lighting, mood from keywords
- Make it cinematic and dynamic
- Reply ONLY with the prompt, nothing else"""}]}]}
                    )
                    if resp.status_code == 200:
                        video_prompt = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                        # Anführungszeichen entfernen falls vorhanden
                        video_prompt = video_prompt.strip('"').strip("'")
                        print(f"Gemini video prompt: {video_prompt}")
        except Exception as ge:
            print(f"Gemini prompt error: {ge}")
            video_prompt = base_prompt

        print(f"Using video prompt: {video_prompt}")
        
        # Schritt 1: Kling generiert Sport-Video (ohne Gesicht)
        print(f"Schritt 1 - Generiere Sport-Video: {video_prompt}")
        kling_output = replicate.run(
            "kwaivgi/kling-v1.6-standard",
            input={
                "prompt": video_prompt,
                "duration": "5",
                "aspect_ratio": "16:9",
                "negative_prompt": "blurry, low quality, text, watermark, face",
            }
        )
        
        if isinstance(kling_output, list):
            sport_video_url = str(kling_output[0])
        elif hasattr(kling_output, 'url'):
            sport_video_url = str(kling_output.url)
        else:
            sport_video_url = str(kling_output)
            
        print(f"Schritt 1 fertig - Sport video: {sport_video_url}")
        
        # Schritt 2: xrunda/hello — echter Video Face-Swap
        print(f"Schritt 2 - Video Face-Swap: {face_url_png}")
        faceswap_output = replicate.run(
            "xrunda/hello:104b4a39315349db50880757bc8c1c996c5309e3aa11286b0a3c84dab81fd440",
            input={
                "source": sport_video_url,
                "target": face_url_png,
            }
        )
        
        if isinstance(faceswap_output, list):
            output = str(faceswap_output[0])
        elif hasattr(faceswap_output, 'url'):
            output = str(faceswap_output.url)
        else:
            output = str(faceswap_output)
            
        print(f"Schritt 2 fertig - output: {output}")
        
        print(f"Video output: {output}")
        result_url = str(output)
        
        print(f"result_url: {result_url}")
        
        # Audio generieren mit MusicGen
        audio_url = None
        try:
            # Musik-Prompt basierend auf Sport und Stimmung
            # Realistische Umgebungsgeräusche statt Musik
            sound_prompts = {
                "surf": "ocean waves crashing, seagulls calling, wind on beach, water splashing, surfer breathing heavily",
                "ski": "wind howling on mountain, skis on snow, heavy breathing, snow crunching, distant avalanche rumble",
                "climb": "wind on mountain cliff, heavy breathing and grunting, rocks scraping, rope tension sounds, birds of prey calling, distant thunder",
                "bike": "mountain bike wheels on gravel trail, heavy breathing, wind rushing, chain rattling, leaves rustling",
                "box": "boxing gloves hitting, heavy breathing and grunting, gym ambience, crowd cheering, punching bag impact",
                "yoga": "birds singing, gentle breeze, peaceful nature sounds, calm breathing, distant water stream",
                "dive": "underwater bubbles, scuba breathing regulator, ocean ambience, fish swimming, deep water pressure sounds",
                "skate": "skateboard wheels on concrete, urban street sounds, crowd cheering, board tricks landing, city ambience",
            }
            music_prompt = sound_prompts.get(sport, "outdoor sport ambient sounds, heavy breathing, nature")
            
            # User-Prompt für Stimmungsanpassung
            if any(w in prompt.lower() for w in ["nacht","night","dunkel","dark"]):
                music_prompt += ", night crickets, owls, dark atmospheric sounds"
            if any(w in prompt.lower() for w in ["regen","rain","sturm","storm"]):
                music_prompt += ", rain falling, thunder in distance, wet surface sounds"
            if any(w in prompt.lower() for w in ["extrem","extreme","wild","crazy"]):
                music_prompt += ", intense heavy breathing, adrenaline rush sounds"
            if any(w in prompt.lower() for w in ["gruppe","group","team"]):
                music_prompt += ", multiple people breathing, team cheering"
                
            print(f"Music prompt: {music_prompt}")
            
            audio_output = replicate.run(
                "meta/musicgen:671ac645ce5e552cc63a54a2bbff63fcf798043055d2dac5fc9e36a837eedcfb",
                input={
                    "prompt": music_prompt,
                    "duration": 8,
                    "model_version": "stereo-melody-large",
                    "output_format": "mp3",
                }
            )
            if audio_output:
                audio_url = str(audio_output)
                print(f"Audio URL: {audio_url}")
        except Exception as ae:
            print(f"Audio generation error: {ae}")
        
        print(f"Replicate result: {result_url}")
        
        # Cloudinary Upload — resource_type auto erkennt ob video oder bild
        try:
            final = cloudinary.uploader.upload(
                result_url,
                resource_type="auto",
                public_id=f"results/{uuid.uuid4().hex}",
                overwrite=True,
            )
            final_url = final["secure_url"]
        except Exception as cu:
            print(f"Cloudinary upload fehler: {cu}")
            # Direkt Replicate URL zurückgeben
            final_url = result_url
        
        return JSONResponse({
            "success": True, 
            "video_url": final_url, 
            "audio_url": audio_url,
            "sport": sport,
            "prompt_used": video_prompt,
        })
    except HTTPException:
        raise
    except Exception as e:
        print(f"Faceswap error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
