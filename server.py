from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import cv2
import numpy as np
from pyzbar.pyzbar import decode
import zlib
import re
from datetime import datetime

app = FastAPI()

# --- HEALTH CHECK (Required for Hugging Face/Render) ---
@app.get("/")
def home():
    return {"status": "active", "message": "Aadhaar Backend Online", "docs_url": "/docs"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- HELPER FUNCTIONS ---

def smart_scan(img_array):
    """
    Scans the image using multiple high-definition strategies.
    1. Standard Scan
    2. Sharpened (for blurry dots)
    3. High Contrast (for glare)
    4. Rotated (for vertical photos)
    """
    try:
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        
        # SAFETY CHECK: If image is corrupt, return None immediately
        if img is None:
            return None

        def try_decode(image):
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            return decode(gray)
        
        # 1. Standard
        decoded = try_decode(img)
        if decoded: return decoded

        # 2. Sharpened
        gaussian = cv2.GaussianBlur(img, (0, 0), 3)
        sharpened = cv2.addWeighted(img, 1.5, gaussian, -0.5, 0)
        decoded = try_decode(sharpened)
        if decoded: return decoded

        # 3. High Contrast (Binary Threshold)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        decoded = decode(binary)
        if decoded: return decoded

        # 4. Rotated
        rotated = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        decoded = try_decode(rotated)
        if decoded: return decoded

        return None
    except Exception as e:
        print(f"Error in smart_scan: {e}")
        return None

def calculate_exact_age(dob_string):
    """Calculates age accurately down to the specific day."""
    try:
        if "-" in dob_string:
            parts = dob_string.split("-")
            if len(parts[0]) == 4:
                year, month, day = map(int, parts)
            else: 
                day, month, year = map(int, parts)
        elif "/" in dob_string:
            day, month, year = map(int, dob_string.split("/"))
        
        birth_date = datetime(year, month, day)
        today = datetime.now()
        
        age = today.year - birth_date.year
        if (today.month, today.day) < (birth_date.month, birth_date.day):
            age -= 1
            
        return age
    except:
        return 0

def decode_secure_qr(data_bytes):
    """
    Handles both OLD Aadhaar (XML Text) and NEW Aadhaar (Secure Number).
    """
    try:
        # Try new secure QR (BigInt compressed)
        big_int = int(data_bytes.decode("utf-8"))
        byte_len = (big_int.bit_length() + 7) // 8
        binary_data = big_int.to_bytes(byte_len, byteorder='big')
        decompressed = zlib.decompress(binary_data, 16+zlib.MAX_WBITS)
        return decompressed.decode("latin-1")
    except:
        # Fallback to old QR (plain text)
        return data_bytes.decode("utf-8")

# --- MAIN ENDPOINT ---

@app.post("/verify")
def verify_aadhaar(file: UploadFile = File(...)):
    """
    Main verification endpoint.
    NOTE: Removed 'async' to allow FastAPI to run this in a threadpool.
    This prevents OpenCV from blocking the server.
    """
    try:
        print(f"Processing: {file.filename}") 
        
        # Read file synchronously (faster for threadpool)
        contents = file.file.read()
        nparr = np.frombuffer(contents, np.uint8)

        decoded_objects = smart_scan(nparr)

        if not decoded_objects:
            return {"success": False, "message": "No QR code detected. Try cropping exactly to the QR."}

        for obj in decoded_objects:
            try:
                # DECODE
                text_data = decode_secure_qr(obj.data)
                
                # Regex for DD-MM-YYYY or YYYY-MM-DD
                match = re.search(r"([0-9]{2}-[0-9]{2}-[0-9]{4})", text_data)
                if not match:
                    match = re.search(r"([0-9]{4}-[0-9]{2}-[0-9]{2})", text_data)

                if match:
                    dob = match.group(1)
                    age = calculate_exact_age(dob)
                    
                    print(f"Verified: Age {age}")

                    return {
                        "success": True, 
                        "age": age, 
                        "is_under_18": age < 18,
                        "dob": dob
                    }
                
            except Exception as e:
                print(f"Error processing QR data: {e}")

        return {"success": False, "message": "QR found, but could not read DOB."}

    except Exception as e:
        print(f"Critical Error: {e}")
        return {"success": False, "message": "Server error processing image."}
