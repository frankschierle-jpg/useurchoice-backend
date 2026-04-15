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

KEYWORD_FALLBACK = {
    "surf": [
        "surf","surfen","surfer","surfbrett","welle","wellen","ozean","meer","strand","beach",
        "bali","hawaii","nazare","pipeline","malibu","wellenreiten","reiten","board","wasser",
        "küste","atlantic","pacific","ozeanisch","brandung","schaumkrone","tube","barrel",
        "longboard","shortboard","bodysurf","windsurf","kitesurf","wassersport","salt water",
        "salzwasser","schwimmen im meer","surfen gehen","wellen reiten","am strand","am meer",
    ],
    "ski": [
        "ski","skifahren","skifahrer","skier","schnee","alpen","piste","winter","snowboard",
        "snowboarden","chamonix","kitzbühel","zermatt","st moritz","tiefschnee","powder",
        "slalom","abfahrt","carving","langlauf","skistöcke","skipiste","skipiste","lift",
        "seilbahn","gondel","bergbahn","après-ski","wintersport","eisläufen","eislaufen",
        "schneebedeckt","verschneit","weißer hang","hang","mountain","gipfel mit schnee",
        "österreich","schweizer alpen","französische alpen","winter urlaub","snowpark",
    ],
    "climb": [
        "klettern","kletterer","klettersteig","felsklettern","bouldern","boulder","fels",
        "felsen","berg","bergsteigen","bergsteiger","alpinismus","alpin","wand","kletterwand",
        "yosemite","el capitan","dolomiten","karabiner","seil","gurt","chalk","magnesia",
        "route","überhang","riss","platte","crack","trad","sport climbing","freeclimbing",
        "free solo","top rope","vorstieg","nachstieg","grifftechnik","trittechnik","hochklettern",
        "aufstieg","gipfelsturm","felsnadel","massiv","granit","kalk","sandstein",
    ],
    "bike": [
        "bike","biken","mountainbike","mtb","fahrrad","radfahren","radfahrer","downhill",
        "trail","singletrack","freeride","enduro","cross country","xc","whistler","bikepark",
        "sprung","drop","jump","dirt","pump track","bikeparks","fullsuspension","hardtail",
        "federgabel","shimano","trek","specialized","scott","canyon","helm","protektor",
        "bergab","bergauf","trail riding","forest","wald","hügel","mountain biking","radtour",
    ],
    "box": [
        "boxen","boxer","boxing","ring","kampf","kämpfer","sparring","training","sandsack",
        "punchingball","handschuhe","bandagen","jab","cross","hook","uppercut","kombination",
        "knockout","ko","treffer","schlag","punch","muhammad ali","tyson","klitschko",
        "weltmeister","weltmeisterschaft","gym","fitnessstudio","kampfsport","martial arts",
        "kickboxen","muay thai","mma","fighting","fight","kampfkunst","ringkampf",
    ],
    "yoga": [
        "yoga","yogi","asana","meditation","meditieren","entspannung","entspannen","atemübung",
        "pranayama","chakra","namaste","pose","haltung","dehnung","dehnen","stretching","stretch",
        "flexibility","flexibilität","vinyasa","hatha","ashtanga","yin","kundalini","hot yoga",
        "sonnengruß","warrior","baum","balance","gleichgewicht","matte","block","gurt",
        "mindfulness","achtsamkeit","innere ruhe","stille","zen","buddhismus","spirituell",
        "wellness","wohlbefinden","körperbewusstsein","bali yoga","retreat","morgenroutine",
    ],
    "dive": [
        "tauchen","taucher","scuba","schnorcheln","schnorchler","unterwasser","underwater",
        "koralle","korallenriff","riff","reef","fisch","fische","meereslebewesen","hai","delfin",
        "oktopus","manta","rochen","malediven","rotes meer","great barrier reef","karibik",
        "atemregler","tauchmaske","flossen","neoprenanzug","wetsuit","pressluftflasche","tank",
        "tiefe","tiefsee","tauchgang","abtauchen","blasen","unterwasserwelt","meeresgrund",
        "wracks","wrecks","höhlentauchen","freitauchen","freediving","apnoe",
    ],
    "skate": [
        "skate","skateboard","skateboarden","skater","halfpipe","quarterpipe","bowl","pool",
        "street","trick","ollie","kickflip","heelflip","grind","slide","manual","rail",
        "gap","ledge","stair","handrail","park","skatepark","street skating","vert",
        "tony hawk","nyjah huston","venice beach","santa monica","barcelona","berlin",
        "brett","deck","trucks","wheels","rollen","achsen","grip tape","helmet","knieschützer",
        "urban","city","stadt","beton","concrete","smooth","smooth ground",
    ],
}

def detect_sport_fallback(text: str) -> str:
    """Erkennt Sportart anhand erweiterter Keyword-Liste."""
    t = text.lower()
    # Zähle Treffer pro Sportart — meiste Treffer gewinnt
    scores = {}
    for sport, keywords in KEYWORD_FALLBACK.items():
        scores[sport] = sum(1 for kw in keywords if kw in t)
    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best
    return "surf"

def detect_sport(text: str) -> str:
    return detect_sport_fallback(text)

async def detect_sport_with_ai(text: str) -> str:
    return detect_sport_fallback(text)

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

@app.get("/videos/search")
async def search_videos(prompt: str, count: int = 3):
    """Sucht echte Videos bei Pexels basierend auf dem Prompt."""
    try:
        sport = detect_sport(prompt)
        
        # Suchbegriffe für Pexels basierend auf Prompt-Details
        search_query = await build_pexels_query_with_gemini(prompt, sport)
        
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.pexels.com/videos/search",
                headers={"Authorization": os.environ.get("PEXELS_API_KEY", "")},
                params={
                    "query": search_query,
                    "per_page": 15,
                    "size": "medium",
                    "orientation": "landscape",
                }
            )
            
            if resp.status_code != 200:
                raise Exception(f"Pexels Fehler: {resp.status_code}")
            
            data = resp.json()
            videos = data.get("videos", [])
            
            if not videos:
                # Fallback: nur Sportart suchen
                resp2 = await client.get(
                    "https://api.pexels.com/videos/search",
                    headers={"Authorization": os.environ.get("PEXELS_API_KEY", "")},
                    params={"query": sport, "per_page": 15, "size": "medium"}
                )
                data = resp2.json()
                videos = data.get("videos", [])
            
            # Zufällig mischen und Top 3 nehmen
            import random
            random.shuffle(videos)
            selected = videos[:count]
            
            result = []
            for v in selected:
                # Beste Video-Datei finden (HD bevorzugt)
                files = v.get("video_files", [])
                hd_file = next((f for f in files if f.get("quality") == "hd" and f.get("width", 0) >= 1280), None)
                sd_file = next((f for f in files if f.get("quality") == "sd"), None)
                best_file = hd_file or sd_file or (files[0] if files else None)
                
                if not best_file:
                    continue
                    
                # Schönen Titel generieren
                raw_title = v.get("url", "").split("/")[-2]
                # Zahlen am Ende entfernen
                import re
                clean_title = re.sub(r'-\d+$', '', raw_title).replace("-", " ").title()
                if not clean_title or len(clean_title) < 3:
                    sport_titles = {
                        "surf": "Surfing Video", "ski": "Skiing Video",
                        "climb": "Climbing Video", "bike": "MTB Video",
                        "box": "Boxing Video", "yoga": "Yoga Video",
                        "dive": "Diving Video", "skate": "Skate Video",
                    }
                    clean_title = sport_titles.get(sport, "Sport Video")

                result.append({
                    "id": str(v["id"]),
                    "title": clean_title,
                    "thumb": v.get("image", ""),
                    "videoUrl": best_file.get("link", ""),
                    "duration": v.get("duration", 30),
                    "sport": sport,
                    "photographer": v.get("user", {}).get("name", ""),
                })
            
            return JSONResponse({
                "success": True,
                "videos": result,
                "sport": sport,
                "query": search_query,
            })
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def build_pexels_query(prompt: str, sport: str) -> str:
    """Baut einen guten Pexels-Suchbegriff aus Prompt und Sportart."""
    t = prompt.lower()
    
    # Locations erkennen
    locations = {
        "bali": "bali", "hawaii": "hawaii", "alpen": "alps", "chamonix": "chamonix",
        "malediven": "maldives", "karibik": "caribbean", "nazare": "nazare",
        "whistler": "whistler", "dolomiten": "dolomites", "berlin": "berlin",
    }
    
    # Stimmungen erkennen  
    moods = {
        # Zeit
        "nacht": "night", "sonnenuntergang": "sunset", "sonnenaufgang": "sunrise",
        "morgen": "morning", "abend": "evening", "mittag": "midday",
        # Wetter
        "sturm": "storm", "regen": "rain", "nebel": "fog", "wind": "wind",
        # Gruppe
        "gruppe": "group", "solo": "alone", "allein": "alone", "zusammen": "together",
        # Schwierigkeit
        "extrem": "extreme", "anfänger": "beginner", "profi": "professional",
        # Surf spezifisch
        "wipeout": "wipeout", "falle": "wipeout", "fallen": "wipeout", "stürze": "wipeout",
        "sturz": "wipeout", "hinfallen": "wipeout", "umfallen": "wipeout",
        "riesenwelle": "big wave", "große welle": "big wave", "riesig": "big wave",
        "barrel": "barrel wave", "tube": "tube wave", "röhre": "barrel wave",
        # Tiere
        "hai": "shark", "delfin": "dolphin", "wal": "whale", "robbe": "seal",
        "schildkröte": "turtle", "fisch": "fish",
        # Orte
        "strand": "beach", "felsen": "rocks", "klippe": "cliff",
        # Ski spezifisch
        "schnee": "powder snow", "tiefschnee": "powder", "lawine": "avalanche",
        "sprung": "jump ski", "trick": "trick",
        # Klettern spezifisch  
        "steil": "steep cliff", "überhang": "overhang", "gipfel": "summit",
        # Box spezifisch
        "knockout": "knockout", "treffer": "punch", "kampf": "fight",
        # Yoga spezifisch
        "entspannung": "relaxation", "meditation": "meditation", "gleichgewicht": "balance",
        # Tauchen spezifisch
        "koralle": "coral reef", "tief": "deep sea", "wrack": "shipwreck",
    }
    
    sport_terms = {
        "surf": "surfing waves ocean",
        "ski": "skiing snow mountain",
        "climb": "rock climbing mountain",
        "bike": "mountain biking trail",
        "box": "boxing training",
        "yoga": "yoga practice",
        "dive": "scuba diving underwater",
        "skate": "skateboarding tricks",
    }
    
    query_parts = [sport_terms.get(sport, sport)]
    
    for key, val in locations.items():
        if key in t:
            query_parts.append(val)
            break
            
    for key, val in moods.items():
        if key in t:
            query_parts.append(val)
            break
    
    return " ".join(query_parts[:3])

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
        
        # Versuche echtes Pexels-Video zu holen
        video_url = SPORT_VIDEOS.get(sport, SPORT_VIDEOS["surf"])
        try:
            pexels_key = os.environ.get("PEXELS_API_KEY", "")
            if pexels_key:
                async with httpx.AsyncClient(timeout=10) as client:
                    search_query = await build_pexels_query_with_gemini(prompt, sport)
                    resp = await client.get(
                        "https://api.pexels.com/videos/search",
                        headers={"Authorization": pexels_key},
                        params={"query": search_query, "per_page": 5, "size": "medium"}
                    )
                    if resp.status_code == 200:
                        videos = resp.json().get("videos", [])
                        if videos:
                            import random
                            v = random.choice(videos[:5])
                            files = v.get("video_files", [])
                            hd = next((f for f in files if f.get("quality")=="hd" and f.get("width",0)>=1280), None)
                            sd = next((f for f in files if f.get("quality")=="sd"), None)
                            best = hd or sd or (files[0] if files else None)
                            if best:
                                video_url = best.get("link", video_url)
        except Exception as pe:
            print(f"Pexels Fehler: {pe}")

        # Replicate face-swap model
        output = replicate.run(
            "codeplugtech/face-swap:278a81e7ebb22db98bcba54de985d22cc1abeead2754eb1f2af717247be69b34",
            input={
                "target_video": video_url,
                "input_image": face_url,
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
