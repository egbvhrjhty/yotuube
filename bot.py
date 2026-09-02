import os
import random
import time
import json
import asyncio
import sys
import numpy as np
import subprocess
from PIL import Image, ImageDraw, ImageFont

# 🛠️ MoviePy PIL Error Fix 
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

import edge_tts
from moviepy.editor import AudioFileClip, TextClip, ColorClip, CompositeVideoClip, CompositeAudioClip
from moviepy.audio.AudioClip import AudioClip

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

# ================== CONFIGURATION ==================
OUTPUT_FOLDER = "./output"
TEMP_FOLDER = "./temp"
JSON_FILE_PATH = "./questions.json"
TOKENS_FOLDER = "./tokens"  
HINDI_FONT = "./NirmalaB.ttf"
BGM_FILE = "./bgm.mp3"
THUMBNAIL_FILE = "./output/thumbnail.jpg"

os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)

TOTAL_QUESTIONS = 100 # एक वीडियो में 100 सवाल

# ================== DATA LOGIC ==================
def get_100_questions():
    with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
        questions_list = json.load(f)
        
    if len(questions_list) < TOTAL_QUESTIONS:
        print(f"❌ सवाल कम हैं! केवल {len(questions_list)} बचे हैं। कम से कम 100 चाहिए।")
        sys.exit(1)

    selected_quizzes = questions_list[:TOTAL_QUESTIONS]
    remaining_quizzes = questions_list[TOTAL_QUESTIONS:]
    
    with open(JSON_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(remaining_quizzes, f, ensure_ascii=False, indent=4)
        
    print(f"🗑️ 100 सवाल निकाल लिए गए और JSON से डिलीट कर दिए गए। बचे हुए सवाल: {len(remaining_quizzes)}")
    return selected_quizzes

# ================== DUAL VOICE TTS ==================
async def generate_voice(text, filename, voice_type="male"):
    filepath = os.path.join(TEMP_FOLDER, filename)
    # लड़के की आवाज़ (सवाल के लिए)
    voice_name = "hi-IN-MadhurNeural" if voice_type == "male" else "hi-IN-SwaraNeural"
    try:
        communicate = edge_tts.Communicate(text, voice_name, rate="+15%", volume="+50%")
        await communicate.save(filepath)
        return filepath
    except Exception as e:
        print(f"TTS Error: {e}")
        return None

# ================== SYNTHETIC SFX ==================
def make_pop_sfx():
    return AudioClip(lambda t: np.vstack([np.sin(2 * np.pi * 500 * t) * np.exp(-25 * t)]*2).T, duration=0.2, fps=44100).volumex(1.5)

def make_tick_sfx(duration=5.0):
    def sound_wave(t):
        t_mod = t % 1.0
        click = np.sin(2 * np.pi * 1000 * t_mod) * np.exp(-60 * t_mod) # Heartbeat like tension
        return np.where(t_mod < 0.1, click, 0)
    return AudioClip(lambda t: np.vstack([sound_wave(t), sound_wave(t)]).T, duration=duration, fps=44100).volumex(2.0)

# ================== AUTO THUMBNAIL ==================
def create_thumbnail(first_question_text):
    print("🎨 Thumbnail बना रहा है...")
    img = Image.new('RGB', (1920, 1080), color = (20, 20, 50))
    d = ImageDraw.Draw(img)
    try:
        font_large = ImageFont.truetype(HINDI_FONT, 120)
        font_small = ImageFont.truetype(HINDI_FONT, 80)
    except:
        font_large = ImageFont.load_default()
        font_small = font_large

    d.text((100, 150), "🔥 100 MEGA GK QUIZ 🔥", fill=(255, 200, 0), font=font_large)
    d.text((100, 400), first_question_text[:50] + "...", fill=(255, 255, 255), font=font_small)
    d.text((100, 800), "99% लोग फेल! 🤔", fill=(255, 50, 50), font=font_large)
    
    img.save(THUMBNAIL_FILE)
    return THUMBNAIL_FILE

# ================== VIDEO GENERATOR LOOP ==================
async def make_video_chunk(quiz, index):
    print(f"\n🎬 रेंडर हो रहा है सवाल {index}/100: {quiz['question']}")
    
    # Levels Logic (Background Colors)
    if index <= 30: bg_color = (15, 32, 39) # Easy (Dark Blue)
    elif index <= 70: bg_color = (66, 39, 9) # Medium (Dark Orange)
    else: bg_color = (60, 10, 10) # Hard (Dark Red Suspense)

    # Clean text
    text_a = quiz['opt_a'].replace("A)", "").strip()
    text_b = quiz['opt_b'].replace("B)", "").strip()
    text_c = quiz['opt_c'].replace("C)", "").strip()
    correct_key = quiz['correct_key']
    correct_ans_text = text_a if correct_key == 'A' else text_b if correct_key == 'B' else text_c

    # 100th Question Logic (Mystery Question)
    is_last = (index == 100)
    speech_q = quiz['question']
    speech_opts = f"ए, {text_a}... बी, {text_b}... सी, {text_c}"
    speech_ans = "इसका जवाब आप कमेंट्स में बताइए!" if is_last else f"सही जवाब है, {correct_ans_text}"

    # Generate Voices (Male for Q, Female for Options/Ans)
    q_path = await generate_voice(speech_q, f"q_{index}.mp3", "male")
    opts_path = await generate_voice(speech_opts, f"o_{index}.mp3", "female")
    ans_path = await generate_voice(speech_ans, f"a_{index}.mp3", "female")

    aud_q = AudioFileClip(q_path).volumex(1.5)
    aud_opts = AudioFileClip(opts_path).volumex(1.2)
    aud_ans = AudioFileClip(ans_path).volumex(1.5)

    # Timing
    t = 0.0
    s_q = t; t += aud_q.duration + 0.5
    s_opts = t; t += aud_opts.duration + 0.5
    timer_dur = 5.0
    s_timer = t; t += timer_dur
    s_ans = t; t += aud_ans.duration + 1.5
    total = t

    # Visuals - Landscape 1920x1080
    bg = ColorClip(size=(1920, 1080), color=bg_color).set_duration(total).set_fps(24)
    
    # Progress Bar & Level Text
    lvl_text = "LEVEL: EASY" if index <= 30 else "LEVEL: MEDIUM" if index <= 70 else "LEVEL: HARD 🔥"
    lvl_clip = TextClip(lvl_text, fontsize=50, color='yellow', font='Arial-Bold').set_position((50, 40)).set_start(0).set_duration(total)
    prog_clip = TextClip(f"Q: {index}/100", fontsize=50, color='white', font='Arial-Bold').set_position((1650, 40)).set_start(0).set_duration(total)

    # Question Text
    q_clip = TextClip(quiz['question'], fontsize=80, color='white', font=HINDI_FONT, method='caption', size=(1700, None), align='center').set_position(('center', 150)).set_start(s_q).set_duration(total - s_q)

    # Options Alignment (Horizontal stacked)
    y_opts = 450
    opt_a_clip = TextClip(f"A) {text_a}", fontsize=70, color='white', font=HINDI_FONT).set_position((200, y_opts)).set_start(s_opts).set_duration(total - s_opts)
    opt_b_clip = TextClip(f"B) {text_b}", fontsize=70, color='white', font=HINDI_FONT).set_position((200, y_opts+120)).set_start(s_opts).set_duration(total - s_opts)
    opt_c_clip = TextClip(f"C) {text_c}", fontsize=70, color='white', font=HINDI_FONT).set_position((200, y_opts+240)).set_start(s_opts).set_duration(total - s_opts)

    pop = make_pop_sfx().set_start(s_opts)
    tick = make_tick_sfx(timer_dur).set_start(s_timer)

    # Timer Visual
    timer_vis = []
    for i in range(int(timer_dur)):
        tl = int(timer_dur) - i
        ts = s_timer + i
        n = TextClip(f"{tl}", fontsize=150, color='red' if tl<=3 else 'yellow', font='Arial-Bold').set_position(('center', 800)).set_start(ts).set_duration(1.0)
        timer_vis.append(n)

    # Answer Highlight
    ans_clip = None
    if not is_last:
        y_ans = y_opts if correct_key == 'A' else (y_opts+120) if correct_key == 'B' else (y_opts+240)
        ans_text = f"{correct_key}) " + (text_a if correct_key == 'A' else text_b if correct_key == 'B' else text_c)
        ans_clip = TextClip(ans_text, fontsize=75, color='#00FF00', font=HINDI_FONT).set_position((200, y_ans)).set_start(s_ans).set_duration(total - s_ans)

    final_audio = CompositeAudioClip([aud_q.set_start(s_q), aud_opts.set_start(s_opts), pop, tick, aud_ans.set_start(s_ans)])
    visuals = [bg, lvl_clip, prog_clip, q_clip, opt_a_clip, opt_b_clip, opt_c_clip] + timer_vis
    if ans_clip: visuals.append(ans_clip)
    
    if is_last:
        suspense_clip = TextClip("👇 कमेंट में अपना जवाब दें! 👇", fontsize=90, color='cyan', font=HINDI_FONT).set_position(('center', 800)).set_start(s_ans).set_duration(total - s_ans)
        visuals.append(suspense_clip)

    video = CompositeVideoClip(visuals).set_audio(final_audio)
    out_path = os.path.join(TEMP_FOLDER, f"chunk_{index}.mp4")
    video.write_videofile(out_path, codec="libx264", audio_codec="aac", fps=24, preset="ultrafast", logger=None)
    
    # Memory Cleanup (CRITICAL FOR GITHUB)
    for c in visuals: c.close()
    video.close(); final_audio.close(); aud_q.close(); aud_opts.close(); aud_ans.close()
    
    return out_path

# ================== MERGE & BGM (FFMPEG) ==================
def merge_videos_and_add_bgm(chunk_files):
    print("🔄 सारे 100 वीडियो जोड़े जा रहे हैं (FFmpeg Superfast)...")
    concat_txt = os.path.join(TEMP_FOLDER, "files.txt")
    with open(concat_txt, "w") as f:
        for chunk in chunk_files:
            f.write(f"file '{os.path.basename(chunk)}'\n")
    
    merged_no_bgm = os.path.join(OUTPUT_FOLDER, "merged_no_bgm.mp4")
    final_output = os.path.join(OUTPUT_FOLDER, "FINAL_UPLOAD.mp4")
    
    # 1. Join Chunks
    os.system(f"ffmpeg -f concat -safe 0 -i {concat_txt} -c copy {merged_no_bgm} -y")
    
    # 2. Add BGM (if exists)
    if os.path.exists(BGM_FILE):
        print("🎵 बैकग्राउंड म्यूजिक (BGM) मिक्स किया जा रहा है...")
        # Stream loop BGM, mix audio, map properly
        cmd = f'ffmpeg -i {merged_no_bgm} -stream_loop -1 -i {BGM_FILE} -filter_complex "[1:a]volume=0.1[bgm];[0:a][bgm]amix=inputs=2:duration=first[aout]" -map 0:v -map "[aout]" -c:v copy -c:a aac {final_output} -y'
        os.system(cmd)
    else:
        print("⚠️ bgm.mp3 नहीं मिला, बिना म्यूजिक के सेव कर रहे हैं।")
        os.rename(merged_no_bgm, final_output)
        
    return final_output

# ================== YOUTUBE UPLOAD ==================
def upload_to_youtube(video_file, thumbnail_file):
    print("🌐 YouTube सर्वर से कनेक्ट हो रहा है...")
    token_files = sorted([os.path.join(TOKENS_FOLDER, f) for f in os.listdir(TOKENS_FOLDER) if f.endswith('.json')])
    
    yt_title = "100 Most Important GK Questions in Hindi 🔥 | Mega Quiz Challenge | GK in Hindi"
    yt_desc = "इस वीडियो में 100 सबसे महत्वपूर्ण GK सवाल हैं जो आपके दिमाग को हिला देंगे! Easy से लेकर Hard लेवल तक! \n\n100वें सवाल का जवाब कमेंट में ज़रूर बताएं! 👇\n\n#gk #gkinhindi #megaquiz #gkquestions #education"
    
    request_body = {
        "snippet": {"title": yt_title, "description": yt_desc, "tags": ["gk", "hindi gk", "mega quiz", "100 gk questions"], "categoryId": "27"},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    }

    for token_path in token_files:
        try:
            creds = Credentials.from_authorized_user_file(token_path, ["https://www.googleapis.com/auth/youtube.upload"])
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(token_path, 'w') as tf: tf.write(creds.to_json())
                    
            youtube = build('youtube', 'v3', credentials=creds)
            
            # Upload Video
            media = MediaFileUpload(video_file, chunksize=-1, resumable=True)
            request = youtube.videos().insert(part="snippet,status", body=request_body, media_body=media)
            response = request.execute()
            video_id = response['id']
            print(f"✅ तहलका! लॉन्ग वीडियो LIVE हो गया: https://youtu.be/{video_id}")
            
            # Upload Thumbnail
            youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(thumbnail_file)).execute()
            print("✅ थंबनेल भी सफलतापूर्वक सेट हो गया!")
            return True
        except Exception as e:
            print(f"❌ अपलोड एरर ({token_path}): {e}")
            continue
    return False

# ================== MAIN EXECUTION ==================
async def main():
    print(f"🤖 GitHub Server चालू! {random.randint(5, 15)} मिनट का इंतज़ार कर रहा है...")
    time.sleep(random.randint(300, 900)) # 5 to 15 mins wait
    
    quizzes = get_100_questions()
    create_thumbnail(quizzes[0]['question'])
    
    chunk_files = []
    for i, quiz in enumerate(quizzes):
        chunk_path = await make_video_chunk(quiz, i+1)
        chunk_files.append(chunk_path)
        
    final_video = merge_videos_and_add_bgm(chunk_files)
    upload_to_youtube(final_video, THUMBNAIL_FILE)

if __name__ == "__main__":
    asyncio.run(main())
