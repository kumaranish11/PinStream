import os
import re
import json
import logging
from urllib.parse import urlparse, urljoin
from flask import Flask, render_template, request, jsonify, Response, stream_template
import requests
from bs4 import BeautifulSoup
import trafilatura

# Configure logging
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key")

# Headers to mimic a real browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

def is_valid_pinterest_url(url):
    """Check if URL is a valid Pinterest pin URL"""
    try:
        # Add protocol if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            
        parsed = urlparse(url)
        valid_domains = ['pinterest.com', 'www.pinterest.com', 'pin.it', 'pinterest.co.uk', 'br.pinterest.com']
        
        # Check domain
        if parsed.netloc.lower() not in valid_domains:
            return False
            
        # For pin.it, any path is valid as it's a redirect service
        if parsed.netloc.lower() == 'pin.it':
            return True
            
        # For pinterest domains, check for pin in path
        path_lower = parsed.path.lower()
        return '/pin/' in path_lower or path_lower.startswith('/pin/')
        
    except Exception as e:
        logging.debug(f"URL validation error: {e}")
        return False

def extract_pin_id(url):
    """Extract Pinterest pin ID from URL"""
    patterns = [
        r'/pin/(\d+)',
        r'pin-(\d+)',
        r'id=(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def detect_pinterest_video(soup, page_content, pin_id, url):
    """Advanced Pinterest video detection using multiple methods"""
    
    # Method 1: Look for JSON-LD structured data
    video_url = find_video_in_structured_data(soup)
    if video_url:
        return video_url
    
    # Method 2: Search for Pinterest API calls in page content
    video_url = find_video_in_api_calls(page_content, pin_id)
    if video_url:
        return video_url
    
    # Method 3: Look for video elements and data attributes
    video_url = find_video_in_elements(soup)
    if video_url:
        return video_url
    
    # Method 4: Extract from Pinterest's internal data structures
    video_url = find_video_in_internal_data(page_content, pin_id)
    if video_url:
        return video_url
    
    # Method 5: Mobile user-agent approach
    video_url = try_mobile_extraction(url)
    if video_url:
        return video_url
    
    return None

def find_video_in_structured_data(soup):
    """Look for video URLs in JSON-LD structured data"""
    try:
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    # Look for video-related fields
                    for key in ['contentUrl', 'embedUrl', 'videoUrl', 'url']:
                        if key in data and isinstance(data[key], str):
                            if '.mp4' in data[key] or 'video' in data[key].lower():
                                return data[key]
                    
                    # Check nested objects
                    if 'video' in data and isinstance(data['video'], dict):
                        video_obj = data['video']
                        for key in ['contentUrl', 'embedUrl', 'url']:
                            if key in video_obj:
                                return video_obj[key]
            except (json.JSONDecodeError, AttributeError):
                continue
    except Exception as e:
        logging.debug(f"Structured data extraction error: {e}")
    return None

def find_video_in_api_calls(page_content, pin_id):
    """Look for video URLs in Pinterest API responses embedded in page"""
    try:
        # Advanced Pinterest CDN patterns
        cdn_patterns = [
            rf'https://v1\.pinimg\.com/videos/[^"\']*{pin_id}[^"\']*\.mp4[^"\']*',
            r'https://v1\.pinimg\.com/videos/[^"\']+\.mp4[^"\']*',
            r'https://i\.pinimg\.com/videos/[^"\']+\.mp4[^"\']*',
            r'https://v\d*\.pinimg\.com/[^"\']*\.mp4[^"\']*',
            r'"video_url":"([^"]+\.mp4[^"]*)"',
            r'"contentUrl":"([^"]+\.mp4[^"]*)"',
            r'"embedUrl":"([^"]+\.mp4[^"]*)"',
        ]
        
        for pattern in cdn_patterns:
            matches = re.findall(pattern, page_content, re.IGNORECASE)
            if matches:
                for match in matches:
                    video_url = match if isinstance(match, str) else match[0] if match else None
                    if video_url and len(video_url) > 20:
                        # Clean up URL
                        video_url = video_url.replace('\\u002F', '/').replace('\\', '')
                        if 'http' in video_url:
                            return video_url
    except Exception as e:
        logging.debug(f"API calls extraction error: {e}")
    return None

def find_video_in_elements(soup):
    """Look for video URLs in HTML elements"""
    try:
        # Check video and source elements
        video_elements = soup.find_all(['video', 'source'])
        for element in video_elements:
            src = element.get('src') or element.get('data-src')
            if src and ('.mp4' in src or 'video' in src.lower()):
                return src
        
        # Check for data attributes containing video URLs
        all_elements = soup.find_all(attrs={'data-video-url': True}) + \
                      soup.find_all(attrs={'data-src': True}) + \
                      soup.find_all(attrs={'data-content-url': True})
        
        for element in all_elements:
            for attr in element.attrs:
                if 'video' in attr.lower() or 'src' in attr.lower():
                    value = element.attrs[attr]
                    if isinstance(value, str) and ('.mp4' in value or 'video' in value.lower()):
                        return value
    except Exception as e:
        logging.debug(f"Element extraction error: {e}")
    return None

def find_video_in_internal_data(page_content, pin_id):
    """Look for video URLs in Pinterest's internal JavaScript data"""
    try:
        # Look for Pinterest's internal data structures
        js_patterns = [
            r'window\.__PWS_DATA__\s*=\s*({.+?});',
            r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
            r'"videos":\s*\[([^\]]+)\]',
            r'"video":\s*({[^}]+})',
        ]
        
        for pattern in js_patterns:
            matches = re.findall(pattern, page_content, re.DOTALL)
            for match in matches:
                try:
                    # Try to find video URLs in the matched content
                    video_patterns = [
                        r'https://[^"\']*\.mp4[^"\']*',
                        r'https://v\d*\.pinimg\.com/[^"\']+',
                    ]
                    
                    for video_pattern in video_patterns:
                        video_matches = re.findall(video_pattern, str(match))
                        if video_matches:
                            return video_matches[0]
                except Exception:
                    continue
    except Exception as e:
        logging.debug(f"Internal data extraction error: {e}")
    return None

def try_mobile_extraction(url):
    """Try extracting video using mobile user agent"""
    try:
        mobile_headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        
        response = requests.get(url, headers=mobile_headers, timeout=10)
        response.raise_for_status()
        
        # Look for mobile-specific video patterns
        patterns = [
            r'"videoUrl":"([^"]+)"',
            r'"video_url":"([^"]+)"',
            r'src="([^"]*\.mp4[^"]*)"',
            r'data-video="([^"]+)"',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, response.text)
            if matches:
                video_url = matches[0].replace('\\u002F', '/').replace('\\', '')
                if 'http' in video_url:
                    return video_url
    except Exception as e:
        logging.debug(f"Mobile extraction error: {e}")
    return None

def extract_pinterest_metadata(url):
    """Extract metadata from Pinterest pin page with advanced video detection"""
    try:
        # Follow redirects for pin.it URLs
        response = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        page_content = response.text
        
        metadata = {
            'title': None,
            'description': None,
            'image_url': None,
            'video_url': None,
            'author': None,
            'site_name': 'Pinterest'
        }
        
        # Extract pin ID for targeted video search
        pin_id = extract_pin_id(response.url)
        logging.info(f"Extracted pin ID: {pin_id}")
        
        # Try multiple advanced video detection methods
        video_url = detect_pinterest_video(soup, page_content, pin_id, url)
        if video_url:
            metadata['video_url'] = video_url
            logging.info(f"Video found: {video_url}")
        else:
            logging.info("No video detected - this appears to be an image-only pin")
        
        # Extract title
        title_tag = soup.find('meta', property='og:title') or soup.find('title')
        if title_tag:
            metadata['title'] = title_tag.get('content') if title_tag.get('content') else title_tag.get_text()
        
        # Extract description
        desc_tag = soup.find('meta', property='og:description') or soup.find('meta', attrs={'name': 'description'})
        if desc_tag:
            metadata['description'] = desc_tag.get('content')
        
        # Extract image URL
        img_tag = soup.find('meta', property='og:image')
        if img_tag:
            metadata['image_url'] = img_tag.get('content')
        
        # Use fallback Open Graph video detection if advanced detection failed
        if not metadata['video_url']:
            video_sources = [
                soup.find('meta', property='og:video'),
                soup.find('meta', property='og:video:url'),
                soup.find('meta', property='og:video:secure_url'),
                soup.find('meta', property='twitter:player:stream'),
            ]
            
            for video_tag in video_sources:
                if video_tag and video_tag.get('content'):
                    video_url = video_tag.get('content')
                    if any(ext in video_url.lower() for ext in ['.mp4', '.webm', '.mov']) or 'video' in video_url.lower():
                        metadata['video_url'] = video_url
                        break
            
            # Look for video URLs in all script tags
            if not metadata['video_url']:
                all_scripts = soup.find_all('script')
                for script in all_scripts:
                    if script.string:
                        import re
                        # Look for video URL patterns
                        video_patterns = [
                            r'"(https?://[^"]*\.mp4[^"]*)"',
                            r'"(https?://[^"]*\.webm[^"]*)"',
                            r'"(https?://[^"]*\.mov[^"]*)"',
                            r'"(https?://[^"]*video[^"]*\.mp4[^"]*)"',
                            r'"videoUrl":"([^"]+)"',
                            r'"contentUrl":"([^"]+)"',
                            r'"video_url":"([^"]+)"'
                        ]
                        
                        for pattern in video_patterns:
                            matches = re.findall(pattern, script.string, re.IGNORECASE)
                            for match in matches:
                                if ('video' in match.lower() or 
                                    any(ext in match.lower() for ext in ['.mp4', '.webm', '.mov'])):
                                    metadata['video_url'] = match
                                    break
                            if metadata['video_url']:
                                break
                        if metadata['video_url']:
                            break
        
        # Pinterest-specific video detection patterns
        if not metadata['video_url']:
            # Look for Pinterest video containers and data attributes
            video_containers = soup.find_all(['div', 'video', 'source'], 
                                           attrs={'data-test-id': re.compile(r'video', re.I)})
            for container in video_containers:
                # Check data attributes
                for attr in container.attrs:
                    if 'src' in attr.lower() or 'url' in attr.lower():
                        value = container.attrs[attr]
                        if isinstance(value, str) and ('video' in value.lower() or '.mp4' in value.lower()):
                            metadata['video_url'] = value
                            break
                if metadata['video_url']:
                    break
        
        # Enhanced Pinterest video detection using API patterns
        if not metadata['video_url']:
            try:
                # Extract pin ID from URL
                pin_id_match = re.search(r'/pin/(\d+)', response.url)
                if pin_id_match:
                    pin_id = pin_id_match.group(1)
                    
                    # Look for Pinterest's internal video API endpoints in page content
                    page_content = response.text
                    
                    # Search for video-related Pinterest CDN URLs
                    video_cdn_patterns = [
                        r'(https://v1\.pinimg\.com/videos/[^"\']+\.mp4[^"\']*)',
                        r'(https://i\.pinimg\.com/videos/[^"\']+\.mp4[^"\']*)',
                        r'(https://v\d*\.pinimg\.com/[^"\']*\.mp4[^"\']*)',
                        r'(https://[^"\']*pinterest[^"\']*\.mp4[^"\']*)',
                        f'(https://[^"\']*{pin_id}[^"\']*\.mp4[^"\']*)'
                    ]
                    
                    for pattern in video_cdn_patterns:
                        matches = re.findall(pattern, page_content, re.IGNORECASE)
                        if matches:
                            # Take the first valid-looking video URL
                            for match in matches:
                                if len(match) > 20:  # Filter out very short matches
                                    metadata['video_url'] = match
                                    logging.info(f"Found video URL via CDN pattern: {match}")
                                    break
                            if metadata['video_url']:
                                break
            except Exception as e:
                logging.debug(f"Pinterest API detection error: {e}")
        
        # Trafilatura-based content analysis for video URLs
        if not metadata['video_url'] and downloaded:
            try:
                # Extract raw text content which might contain video URLs
                text_content = trafilatura.extract(downloaded, include_links=True, include_images=True)
                if text_content:
                    # Look for video URLs in extracted content
                    video_url_patterns = [
                        r'(https://[^\s]+\.mp4[^\s]*)',
                        r'(https://[^\s]+\.webm[^\s]*)',
                        r'(https://[^\s]+\.mov[^\s]*)',
                        r'(https://v\d*\.pinimg\.com/[^\s]+)',
                        r'(https://[^\s]*pinterest[^\s]*video[^\s]*)'
                    ]
                    
                    for pattern in video_url_patterns:
                        matches = re.findall(pattern, text_content, re.IGNORECASE)
                        if matches:
                            metadata['video_url'] = matches[0]
                            logging.info(f"Found video URL via trafilatura: {matches[0]}")
                            break
            except Exception as e:
                logging.debug(f"Trafilatura video detection error: {e}")
        
        # Extract author/creator info
        author_tag = soup.find('meta', property='og:site_name') or soup.find('meta', attrs={'name': 'author'})
        if author_tag:
            metadata['author'] = author_tag.get('content')
        
        # Try alternative extraction if no video found
        if not metadata['video_url']:
            logging.info("No video found with primary methods, trying alternative extraction...")
            alternative_video = try_alternative_video_extraction(url)
            if alternative_video:
                metadata['video_url'] = alternative_video
        
        # Log final results
        logging.info(f"Metadata extraction complete for {url}")
        logging.info(f"Title: {metadata.get('title', 'N/A')}")
        logging.info(f"Video URL found: {'Yes' if metadata.get('video_url') else 'No'}")
        if metadata.get('video_url'):
            logging.info(f"Video URL: {metadata['video_url']}")
        
        return metadata
        
    except requests.RequestException as e:
        logging.error(f"Request error for {url}: {e}")
        raise Exception(f"Failed to fetch Pinterest page: {str(e)}")
    except Exception as e:
        logging.error(f"Parsing error for {url}: {e}")
        raise Exception(f"Failed to parse Pinterest page: {str(e)}")

def try_alternative_video_extraction(url):
    """Alternative method to extract video using different approach"""
    try:
        # Try with different headers to mimic mobile browser
        mobile_headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
        
        response = requests.get(url, headers=mobile_headers, timeout=10, allow_redirects=True)
        response.raise_for_status()
        
        # Look for mobile-specific video patterns
        content = response.text
        mobile_video_patterns = [
            r'"videoUrl":"([^"]+)"',
            r'"video_url":"([^"]+)"',
            r'"contentUrl":"([^"]+\.mp4[^"]*)"',
            r'data-video-url="([^"]+)"',
            r'src="([^"]*\.mp4[^"]*)"'
        ]
        
        for pattern in mobile_video_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                video_url = matches[0].replace('\\u002F', '/').replace('\\', '')
                if 'http' in video_url and ('.mp4' in video_url or 'video' in video_url):
                    logging.info(f"Found video URL via mobile extraction: {video_url}")
                    return video_url
                    
        return None
        
    except Exception as e:
        logging.debug(f"Alternative extraction failed: {e}")
        return None

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/inspect', methods=['POST'])
def inspect_pin():
    """Inspect Pinterest pin and return metadata"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        if not is_valid_pinterest_url(url):
            return jsonify({'error': 'Please provide a valid Pinterest pin URL'}), 400
        
        metadata = extract_pinterest_metadata(url)
        
        return jsonify({
            'success': True,
            'metadata': metadata,
            'downloadable': bool(metadata.get('video_url'))
        })
        
    except Exception as e:
        logging.error(f"Inspection error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/download')
def download_video():
    """Stream video file to user"""
    try:
        video_url = request.args.get('video_url')
        filename = request.args.get('filename', 'pinterest_video.mp4')
        
        if not video_url:
            return jsonify({'error': 'Video URL is required'}), 400
        
        # Sanitize filename
        filename = re.sub(r'[^\w\-_\.]', '_', filename)
        if not filename.endswith(('.mp4', '.webm', '.mov', '.avi')):
            filename += '.mp4'
        
        # Stream the video file
        try:
            response = requests.get(video_url, headers=HEADERS, stream=True, timeout=30)
            response.raise_for_status()
            
            def generate():
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk
            
            return Response(
                generate(),
                mimetype='video/mp4',
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}"',
                    'Content-Type': 'video/mp4'
                }
            )
            
        except requests.RequestException as e:
            logging.error(f"Download error: {e}")
            return jsonify({'error': 'Failed to download video. The video may be protected or unavailable.'}), 500
            
    except Exception as e:
        logging.error(f"Download error: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
