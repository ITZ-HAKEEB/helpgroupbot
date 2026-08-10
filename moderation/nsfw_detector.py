import os
import base64
import requests
import json
import logging
import subprocess

logger = logging.getLogger(__name__)

# Fallback API key if not found in environmental config.
DEFAULT_OPENROUTER_KEY = ""

def get_openrouter_api_key():
    return os.getenv("OPENROUTER_API_KEY") or DEFAULT_OPENROUTER_KEY

def extract_frame_from_webm(file_path):
    """
    Extracts the first frame of a .webm file using ffmpeg.
    Returns the path to the extracted image, or None if it fails.
    """
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return None

    output_path = file_path + ".jpg"
    try:
        # Run ffmpeg command to extract first frame:
        # -y to overwrite if exists
        # -i input
        # -vframes 1 output
        # -f image2 force image format
        cmd = [
            "ffmpeg",
            "-y",
            "-i", file_path,
            "-vframes", "1",
            "-f", "image2",
            output_path
        ]
        # Execute ffmpeg quietly
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path
        else:
            logger.error(f"FFmpeg ran but output file is missing or empty: {output_path}")
            return None
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg frame extraction failed for {file_path}: {e.stderr.decode('utf-8', errors='ignore')}")
        return None
    except FileNotFoundError:
        logger.error("ffmpeg command not found on the system. Webm analysis is unavailable.")
        return None
    except Exception as e:
        logger.error(f"Unexpected error extracting frame from webm: {e}")
        return None

def check_nsfw_via_openrouter(file_path, threshold=0.7):
    """
    Checks if an image/sticker at file_path contains NSFW/adult content.
    Returns (is_nsfw: bool, score: float or None)
    """
    try:
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return False, None

        # Determine MIME type based on extension
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".webm":
            # Extract first frame
            frame_path = extract_frame_from_webm(file_path)
            if not frame_path:
                logger.error("Failed to extract frame from webm sticker.")
                return False, None
            # Use the extracted frame path for the rest of processing
            file_path_to_read = frame_path
            mime_type = "image/jpeg"
        elif ext == ".png":
            file_path_to_read = file_path
            mime_type = "image/png"
        elif ext == ".webp":
            file_path_to_read = file_path
            mime_type = "image/webp"
        else:
            file_path_to_read = file_path
            mime_type = "image/jpeg"

        # Read file and encode to base64
        with open(file_path_to_read, "rb") as f:
            encoded_image = base64.b64encode(f.read()).decode("utf-8")
        
        # Cleanup temporary frame file if created
        if ext == ".webm" and file_path_to_read != file_path:
            try:
                os.remove(file_path_to_read)
            except Exception:
                pass

        data_uri = f"data:{mime_type};base64,{encoded_image}"

        api_key = get_openrouter_api_key()
        
        # Query OpenRouter Reranker API
        # Query is aimed at detecting sexually explicit content
        query = "sexually explicit, nude, nsfw, pornographic, adult content, nudity, sexual organs"
        
        payload = {
            "model": "nvidia/llama-nemotron-rerank-vl-1b-v2:free",
            "query": query,
            "documents": [
                {"image": data_uri}
            ],
            "top_n": 1
        }

        response = requests.post(
            url="https://openrouter.ai/api/v1/rerank",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            data=json.dumps(payload),
            timeout=15
        )

        if response.status_code != 200:
            logger.error(f"OpenRouter Rerank request failed: Status {response.status_code}, Response: {response.text}")
            return False, None

        results = response.json()
        if "results" in results and len(results["results"]) > 0:
            result = results["results"][0]
            relevance_score = result.get("relevance_score", 0.0)
            logger.info(f"NSFW Check result - Relevance Score: {relevance_score} against Threshold: {threshold}")
            if relevance_score >= threshold:
                return True, relevance_score
            return False, relevance_score
        else:
            logger.error(f"Unexpected response format from OpenRouter: {results}")
            return False, None

    except Exception as e:
        logger.error(f"Error checking NSFW status via OpenRouter: {e}")
        return False, None
