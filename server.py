import logging
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import cv2
import numpy as np
from pyzbar.pyzbar import decode
import zlib
import re
from datetime import datetime

# --- PRIVACY & SECURITY NOTICE ---
# This application is designed to be stateless and privacy-preserving.
# No images are written to the disk (processed in RAM only).
# No personal data (Name, DOB, Aadhaar Number) is logged or stored in a database.
# The API response returns only a boolean validation flag, not the user's specific age or DOB.
# ---------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI()

# --- HEALTH CHECK ---
@app.get("/")
def home():
    return {"status": "active", "message": "Privacy-Preserving Age Verification Online"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def smart_scan(img_array):
    """
    Scans the image using multiple strategies (Standard, Sharpened, Contrast, Rotated).
    """
    try:
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        
        if img is None:
            return None

        def try_decode(image):
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            return decode(gray)
        
        decoded = try_decode(img)
        if decoded: return decoded

        gaussian = cv2.GaussianBlur(img, (0, 0), 3)
        sharpened = cv2.addWeighted(img, 1.5, gaussian, -0.5, 0)
        decoded = try_decode(sharpened)
        if decoded: return decoded
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        decoded = decode(binary)
        if decoded: return decoded

        # 4. Rotated
        rotated = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        decoded = try_decode(rotated)
        if decoded: return decoded

        return None
    except Exception:
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
    """Decodes Aadhaar Secure QR data."""
    try:
        big_int = int(data_bytes.decode("utf-8"))
        byte_len = (big_int.bit_length() + 7) // 8
        binary_data = big_int.to_bytes(byte_len, byteorder='big')
        decompressed = zlib.decompress(binary_data, 16+zlib.MAX_WBITS)
        return decompressed.decode("latin-1")
    except:
        return data_bytes.decode("utf-8")


@app.post("/verify")
def verify_aadhaar(file: UploadFile = File(...)):
    """
    Verifies age from Aadhaar QR.
    Note: Synchronous definition (no 'async') ensures OpenCV runs in a 
    threadpool to prevent server blocking.
    """
    try:
        logger.info("New verification request received.")
        
        contents = file.file.read()
        nparr = np.frombuffer(contents, np.uint8)

        decoded_objects = smart_scan(nparr)

        del contents
        del nparr

        if not decoded_objects:
            logger.warning("Verification failed: No valid QR code detected.")
            return {"success": False, "message": "No QR code detected."}

        for obj in decoded_objects:
            try:
                text_data = decode_secure_qr(obj.data)
                
                match = re.search(r"([0-9]{2}-[0-9]{2}-[0-9]{4})", text_data)
                if not match:
                    match = re.search(r"([0-9]{4}-[0-9]{2}-[0-9]{2})", text_data)

                if match:
                    dob = match.group(1)
                    age = calculate_exact_age(dob)
                    
                    logger.info("QR decoded successfully. Age calculated internally.")

                    return {
                        "success": True, 
                        "is_under_18": age < 18
                    }
                
            except Exception:
                logger.error("Error parsing QR data structure.")
                continue

        logger.info("Verification failed: QR found but DOB unreadable.")
        return {"success": False, "message": "Could not verify age from this QR."}

    except Exception:
        logger.error("Internal server error during verification.")
        return {"success": False, "message": "Internal processing error."}
