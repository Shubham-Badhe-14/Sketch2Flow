
import os
import glob
from fastapi import APIRouter, HTTPException, BackgroundTasks
from backend.app.core.config import settings
from backend.app.services.storage import StorageService
from backend.app.services.preprocessing import ImagePreprocessor
from backend.app.services.ocr import OCRService
from backend.app.services.vision.stub import StubVisionProvider
from backend.app.services.vision.prompts import FLOWCHART_PROMPT
from backend.app.services.inference import InferenceEngine
from backend.app.services.mermaid.generator import MermaidGenerator
from backend.app.services.mermaid.renderer import MermaidRenderer
from loguru import logger

router = APIRouter()

# In-memory status store for MVP (use Redis/DB in prod)
JOB_STATUS = {}

async def run_pipeline(job_id: str):
    logger.info(f"Starting pipeline for job {job_id}")
    JOB_STATUS[job_id] = "processing"
    
    try:
        job_dir = StorageService.get_job_dir(job_id)
        # Find input file
        input_files = glob.glob(os.path.join(job_dir, "*.*"))
        # Exclude generated outputs
        common_outputs = ["diagram.mmd", "diagram.png", "diagram.svg"]
        input_path = next((f for f in input_files if os.path.basename(f) not in common_outputs and not os.path.basename(f).startswith("debug_")), None)
        
        if not input_path:
            raise FileNotFoundError("Input file not found")

        # 1. Preprocessing
        logger.info(f"Step 1: Preprocessing {input_path}")
        image = ImagePreprocessor.load_image(input_path)
        processed_image = ImagePreprocessor.preprocess(image, debug_output_dir=job_dir)
        
        # 2. OCR (Optional dependency, might skip if vision is strong)
        logger.info("Step 2: OCR Extraction")
        ocr_service = OCRService() # Should be singleton in prod
        ocr_results = ocr_service.extract_text(processed_image)
        logger.info(f"OCR found {len(ocr_results)} text items")

        # 3. Vision Analysis
        logger.info(f"Step 3: Vision Analysis (Provider: {settings.VISION_PROVIDER})")
        
        vision_provider = None
        if settings.VISION_PROVIDER == "openai":
            from backend.app.services.vision.openai import OpenAIVisionProvider
            vision_provider = OpenAIVisionProvider()
        elif settings.VISION_PROVIDER == "gemini":
            from backend.app.services.vision.gemini import GeminiVisionProvider
            vision_provider = GeminiVisionProvider()
        else:
            from backend.app.services.vision.stub import StubVisionProvider
            vision_provider = StubVisionProvider()

        vision_data = await vision_provider.analyze(
            image, 
            FLOWCHART_PROMPT,
            status_callback=lambda status: JOB_STATUS.update({job_id: status})
        )

        # 4. Structure Inference
        logger.info("Step 4: Structure Inference")
        inference_engine = InferenceEngine()
        diagram = inference_engine.build_graph(vision_data, ocr_results)

        # 5. Code Generation
        logger.info("Step 5: Mermaid Code Generation")
        mermaid_code = MermaidGenerator.generate_code(diagram)
        
        mermaid_path = os.path.join(job_dir, "diagram.mmd")
        with open(mermaid_path, "w") as f:
            f.write(mermaid_code)

        # 6. Rendering
        logger.info("Step 6: Rendering")
        renderer = MermaidRenderer()
        try:
            png_path = await renderer.render(mermaid_code, output_format="png")
            # Move result to job dir if not already there (renderer returns path)
            final_png_path = os.path.join(job_dir, "diagram.png")
            if png_path != final_png_path:
                import shutil
                shutil.move(png_path, final_png_path)
        except Exception as e:
            logger.warning(f"Rendering failed (likely missing CLI): {e}")
            # Non-fatal if we just want the code
            JOB_STATUS[job_id] = "completed_with_warnings" 
            return

        JOB_STATUS[job_id] = "completed"
        logger.info(f"Job {job_id} completed successfully")

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        JOB_STATUS[job_id] = f"failed: {str(e)}"

@router.post("/process/{job_id}")
async def process_diagram(job_id: str, background_tasks: BackgroundTasks):
    """
    Trigger the processing pipeline for a given job ID.
    """
    if job_id in JOB_STATUS and JOB_STATUS[job_id] in ["processing", "completed"]:
        return {"message": "Job already exists", "job_id": job_id, "status": JOB_STATUS[job_id]}

    background_tasks.add_task(run_pipeline, job_id)
    JOB_STATUS[job_id] = "queued"
    return {"message": "Processing started", "job_id": job_id}

@router.get("/status/{job_id}")
async def get_status(job_id: str):
    """
    Get the status of a processing job.
    """
    status = JOB_STATUS.get(job_id, "not_found")
    return {"status": status, "job_id": job_id}
