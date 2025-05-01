import os
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import fitz  # PyMuPDF
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import traceback
import tempfile
import shutil

# Load environment variables
load_dotenv()

# Constants
MAX_PDF_SIZE_MB = 10  # Increased limit for PDF files
MAX_IMAGE_SIZE_MB = 5  # Separate limit for images
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
ALLOWED_PDF_EXTENSIONS = {'pdf'}

# --- Flask App Setup ---
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['SECRET_KEY'] = os.urandom(24)
app.config['MAX_CONTENT_LENGTH'] = MAX_PDF_SIZE_MB * 1024 * 1024

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- Helper Functions ---

def allowed_file(filename, file_type='pdf'):
    """Check if the file extension is allowed"""
    if '.' not in filename:
        return False
        
    ext = filename.rsplit('.', 1)[1].lower()
    if file_type == 'pdf':
        return ext in ALLOWED_PDF_EXTENSIONS
    return ext in ALLOWED_IMAGE_EXTENSIONS

def enhance_pdf(pdf_path):
    """
    Enhance a PDF document by:
    1. Improving text clarity
    2. Optimizing images within the PDF
    3. Standardizing formatting
    """
    try:
        # Create a temporary directory for processing
        temp_dir = tempfile.mkdtemp()
        enhanced_path = os.path.join(temp_dir, 'enhanced_' + os.path.basename(pdf_path))
        
        # Open the original PDF
        doc = fitz.open(pdf_path)
        
        # Create a new PDF with enhanced content
        new_doc = fitz.open()
        
        for page in doc:
            # Create a new page with the same dimensions
            new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
            
            # Get the page's text and images
            text = page.get_text()
            images = page.get_images()
            
            # Reinsert text with improved formatting
            if text.strip():
                rc = new_page.insert_text(
                    point=fitz.Point(50, 50),  # Adjust position as needed
                    text=text,
                    fontsize=11,  # Slightly larger font for better readability
                    fontname="helv",  # Standard font
                    color=(0, 0, 0),  # Black text
                )
            
            # Reinsert images with optimization
            for img in images:
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                
                # Create a temporary image file
                img_path = os.path.join(temp_dir, f"temp_img_{xref}.png")
                with open(img_path, "wb") as f:
                    f.write(image_bytes)
                
                # Reinsert the image (could add enhancement here)
                rect = fitz.Rect(50, 100, page.rect.width-50, page.rect.height-50)
                new_page.insert_image(rect, filename=img_path)
        
        # Save the enhanced PDF
        new_doc.save(enhanced_path)
        new_doc.close()
        doc.close()
        
        # Move the enhanced PDF to the uploads folder
        final_enhanced_path = os.path.join(
            app.config['UPLOAD_FOLDER'],
            'enhanced_' + os.path.basename(pdf_path)
        )
        shutil.move(enhanced_path, final_enhanced_path)
        
        return final_enhanced_path
    
    except Exception as e:
        print(f"PDF Enhancement Error: {str(e)}")
        traceback.print_exc()
        return None
    finally:
        # Clean up temporary directory
        if 'temp_dir' in locals() and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

def generate_pdf_preview(pdf_path):
    """Generate a preview image for the PDF"""
    try:
        doc = fitz.open(pdf_path)
        page = doc.load_page(0)  # First page
        pix = page.get_pixmap()
        
        preview_filename = f"preview_{os.path.basename(pdf_path)}.png"
        preview_path = os.path.join(app.config['UPLOAD_FOLDER'], preview_filename)
        pix.save(preview_path)
        
        return preview_path
    except Exception as e:
        print(f"Preview Generation Error: {str(e)}")
        return None

# --- Routes ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_and_process_file():
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file part in the request.'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'No file selected for upload.'}), 400

    if not allowed_file(file.filename):
        return jsonify({'status': 'error', 'message': 'Unsupported file type.'}), 400

    try:
        # Secure filename and save original
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower()
        original_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(original_path)

        # Process based on file type
        if file_ext == 'pdf':
            # Enhance the PDF
            enhanced_path = enhance_pdf(original_path)
            
            if not enhanced_path:
                return jsonify({'status': 'error', 'message': 'PDF enhancement failed.'}), 500
            
            # Generate previews
            original_preview = generate_pdf_preview(original_path)
            enhanced_preview = generate_pdf_preview(enhanced_path)
            
            return jsonify({
                'status': 'success',
                'original': f'/static/uploads/{filename}',
                'original_preview': f'/static/uploads/{os.path.basename(original_preview)}' if original_preview else None,
                'enhanced': f'/static/uploads/{os.path.basename(enhanced_path)}',
                'enhanced_preview': f'/static/uploads/{os.path.basename(enhanced_preview)}' if enhanced_preview else None,
                'message': 'PDF successfully enhanced!'
            })

        else:
            # Handle image files (if needed)
            return jsonify({
                'status': 'error',
                'message': 'Please upload PDF files only for enhancement.'
            }), 400

    except Exception as e:
        print(f"Upload Error: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': f'An error occurred during processing: {str(e)}'
        }), 500

@app.route('/static/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- Run App ---
if __name__ == '__main__':
    print("--- Starting PDF Enhancement Service ---")
    print(f"Upload folder: {os.path.abspath(app.config['UPLOAD_FOLDER'])}")
    print("Server running at: http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)