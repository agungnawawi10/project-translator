from flask import Flask, render_template, request, jsonify, url_for
import cv2
import easyocr
import numpy as np
import os
import logging
import subprocess
import time
import shutil
from deep_translator import GoogleTranslator
from PIL import Image, ImageDraw, ImageFont

try:
    from imageio_ffmpeg import get_ffmpeg_exe
except ModuleNotFoundError:
    get_ffmpeg_exe = None

# 1. KONFIGURASI LOGGING
# Mengatur agar log tampil di terminal dengan format: [WAKTU] - [STATUS] - PESAN
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

app = Flask(__name__)

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def transcode_for_browser(source_path, target_path):
    if get_ffmpeg_exe is not None:
        ffmpeg_exe = get_ffmpeg_exe()
    else:
        ffmpeg_exe = shutil.which('ffmpeg')

    if not ffmpeg_exe:
        raise RuntimeError(
            'ffmpeg tidak ditemukan. Install imageio-ffmpeg atau tambahkan ffmpeg ke PATH.'
        )

    command = [
        ffmpeg_exe,
        '-y',
        '-i', source_path,
        '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart',
        '-an',
        target_path,
    ]
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

# Inisialisasi OCR
logging.info("Memulai inisialisasi EasyOCR Model (Bahasa Inggris)...")
start_ocr_init = time.time()
reader = easyocr.Reader(['en'])
logging.info(f"EasyOCR berhasil siap digunakan dalam {time.time() - start_ocr_init:.2f} detik.")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/translate_video', methods=['POST'])
def translate_video():
    if 'video' not in request.files:
        logging.warning("Menerima request, tetapi tidak ada file video yang dikirim.")
        return jsonify({'error': 'Tidak ada file video'}), 400
        
    file = request.files['video']
    if file.filename == '':
        logging.warning("Menerima file tanpa nama (kosong).")
        return jsonify({'error': 'Nama file kosong'}), 400

    # Catat waktu mulai pemrosesan video secara keseluruhan
    start_total_time = time.time()

    input_path = os.path.join(app.config['UPLOAD_FOLDER'], 'input_' + file.filename)
    output_filename = 'translated_' + os.path.splitext(file.filename)[0] + '.mp4'
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
    temp_output_path = output_path + '.tmp.mp4'
    
    logging.info(f"Menerima file: {file.filename}. Menyimpan ke sistem lokal...")
    file.save(input_path)

    # Membuka Video
    cap = cv2.VideoCapture(input_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    logging.info(f"Detail Video -> Total Frame: {total_frames} | FPS: {fps} | Resolusi: {width}x{height}")

    # Siapkan VideoWriter
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(temp_output_path, fourcc, fps, (width, height))

    last_seen_text = ""
    last_translated_text = ""
    current_frame_count = 0

    logging.info("--- Memulai Pemrosesan Frame-by-Frame & Analisis Citra ---")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        current_frame_count += 1
        
        # Log kemajuan setiap 5 frame sekali agar terminal tidak terlalu penuh banjir teks
        if current_frame_count % 5 == 0 or current_frame_count == 1 or current_frame_count == total_frames:
            logging.info(f"Memproses Frame {current_frame_count}/{total_frames} (Progress: {int((current_frame_count/total_frames)*100)}%)")

        # 2. PENGOLAHAN CITRA (Preprocessing)
        start_frame_process = time.time()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # 3. DETEKSI OPTICAL CHARACTER RECOGNITION (OCR)
        results = reader.readtext(gray)
        
        frame_texts = []
        for (bbox, text, prob) in results:
            if prob > 0.5:
                frame_texts.append(text)
                
                # Gambar kotak hijau penanda deteksi citra asli
                top_left = tuple(map(int, bbox[0]))
                bottom_right = tuple(map(int, bbox[2]))
                cv2.rectangle(frame, top_left, bottom_right, (0, 255, 0), 2)

        if frame_texts:
            current_text = " ".join(frame_texts)
            
            # Jika terdeteksi teks baru yang berbeda dari frame sebelumnya
            if current_text != last_seen_text:
                logging.info(f"[OCR Terdeteksi] di Frame {current_frame_count}: '{current_text}'")
                
                start_translate = time.time()
                try:
                    last_translated_text = GoogleTranslator(source='auto', target='id').translate(current_text)
                    last_seen_text = current_text
                    logging.info(f"[Translation Berhasil] Terjemahan: '{last_translated_text}' ({time.time() - start_translate:.2f} detik)")
                except Exception as e:
                    logging.error(f"Gagal menghubungi API Penerjemah: {str(e)}")

            # Tempel teks terjemahan ke video menggunakan Pillow
            pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil_img)
            font = ImageFont.load_default()
            
            text_position = (int(width/2) - 100, height - 50)
            draw.text(text_position, last_translated_text, fill="yellow", font=font)
            frame = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        # Simpan frame yang telah dimodifikasi
        out.write(frame)

    # Selesai, tutup semua objek
    cap.release()
    out.release()

    try:
        transcode_for_browser(temp_output_path, output_path)
    except Exception as e:
        logging.exception(f"Gagal melakukan transcoding video output: {str(e)}")
        if os.path.exists(temp_output_path):
            os.remove(temp_output_path)
        return jsonify({'error': 'Gagal membuat video yang kompatibel dengan browser'}), 500
    finally:
        if os.path.exists(temp_output_path):
            os.remove(temp_output_path)
    
    total_processing_time = time.time() - start_total_time
    logging.info("--- Pemrosesan Selesai ---")
    logging.info(f"Video Hasil berhasil disimpan ke: {output_path}")
    logging.info(f"Total durasi komputasi sistem: {total_processing_time:.2f} detik untuk {total_frames} frame.")

    return jsonify({
        'video_url': url_for('static', filename=f'uploads/{output_filename}')
    })

if __name__ == '__main__':
    app.run(debug=True)