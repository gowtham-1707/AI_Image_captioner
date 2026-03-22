import io
import os
import time
import uuid
import zipfile

import streamlit as st
from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration
import torch
from prometheus_client import Counter, Gauge, Histogram, Summary, start_http_server

# ── START PROMETHEUS SERVER ───────────────────────────────────────────────────
try:
    start_http_server(8001)
except:
    pass  # already running

@st.cache_resource
def create_metrics():
    images_processed = Counter(
        "captioner_images_processed_total",
        "Total images processed",
        ["mode", "status"]
    )
    requests_total = Counter(
        "captioner_requests_total",
        "Total requests made to the app",
        ["mode", "session_id"]
    )
    errors_total = Counter(
        "captioner_errors_total",
        "Total errors during processing",
        ["mode", "error_type"]
    )
    zip_uploads = Counter(
        "captioner_zip_uploads_total",
        "Total ZIP files uploaded"
    )
    active_requests = Gauge(
        "captioner_active_requests",
        "Images currently being processed",
        ["mode"]
    )
    model_memory = Gauge(
        "captioner_model_memory_bytes",
        "Approximate RAM used by the BLIP model"
    )
    bulk_queue = Gauge(
        "captioner_bulk_queue_size",
        "Images still waiting in the current bulk batch"
    )
    inference_latency = Histogram(
        "captioner_inference_latency_seconds",
        "Time taken to generate one caption",
        ["mode"],
        buckets=[0.5, 1, 2, 4, 8, 15, 30]
    )
    image_size_hist = Histogram(
        "captioner_image_size_bytes",
        "Size of each uploaded image in bytes",
        ["mode"],
        buckets=[10240, 102400, 512000, 1048576, 5242880]
    )
    caption_len_hist = Histogram(
        "captioner_caption_length_chars",
        "Number of characters in each generated caption",
        ["mode"],
        buckets=[10, 20, 40, 60, 100, 150]
    )
    inference_summary = Summary(
        "captioner_inference_duration_summary",
        "Summary of inference durations",
        ["mode"]
    )
    image_size_summary = Summary(
        "captioner_image_size_summary",
        "Summary of uploaded image sizes",
        ["mode"]
    )
    caption_word_summary = Summary(
        "captioner_caption_words_summary",
        "Summary of caption word counts",
        ["mode"]
    )

    return {
        "images_processed":     images_processed,
        "requests_total":       requests_total,
        "errors_total":         errors_total,
        "zip_uploads":          zip_uploads,
        "active_requests":      active_requests,
        "model_memory":         model_memory,
        "bulk_queue":           bulk_queue,
        "inference_latency":    inference_latency,
        "image_size_hist":      image_size_hist,
        "caption_len_hist":     caption_len_hist,
        "inference_summary":    inference_summary,
        "image_size_summary":   image_size_summary,
        "caption_word_summary": caption_word_summary,
    }


@st.cache_resource(show_spinner="Loading AI model... (first time only)")
def load_model():
    processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
    model     = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
    model.eval()
    return processor, model

def generate_caption(image, processor, model, mode, m):
    img_bytes = image.tobytes()
    m["image_size_hist"].labels(mode=mode).observe(len(img_bytes))
    m["image_size_summary"].labels(mode=mode).observe(len(img_bytes))

    inputs = processor(images=image, return_tensors="pt")
    t0 = time.perf_counter()
    with torch.no_grad():
        output = model.generate(**inputs, max_new_tokens=50)
    latency = time.perf_counter() - t0

    caption = processor.decode(output[0], skip_special_tokens=True)

    m["inference_latency"].labels(mode=mode).observe(latency)
    m["inference_summary"].labels(mode=mode).observe(latency)
    m["caption_len_hist"].labels(mode=mode).observe(len(caption))
    m["caption_word_summary"].labels(mode=mode).observe(len(caption.split()))

    return caption, latency

st.set_page_config(page_title="Image Captioner", layout="wide")

m                = create_metrics()
processor, model = load_model()

params = sum(p.numel() for p in model.parameters())
m["model_memory"].set(params * 4)

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())[:8]
session_id = st.session_state.session_id

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title(" Settings")
mode = st.sidebar.radio("Choose Mode", ["Single Image", "Bulk (ZIP)"])
st.sidebar.markdown("---")
st.sidebar.markdown(f"**Session ID:** `{session_id}`")
st.sidebar.markdown("**Metrics:** [localhost:8001/metrics](http://localhost:8001/metrics)")

st.title(" AI Image Captioner")
st.caption("Powered by BLIP · Monitored with Prometheus")

if mode == "Single Image":
    st.header("Single Image Mode")
    uploaded = st.file_uploader("Upload an image", type=["jpg", "jpeg", "png", "bmp", "webp"])

    if uploaded and st.button("Generate Caption", type="primary"):
        m["active_requests"].labels(mode="single").inc()
        m["requests_total"].labels(mode="single", session_id=session_id).inc()

        try:
            with st.spinner("Running inference..."):
                raw     = uploaded.read()
                image   = Image.open(io.BytesIO(raw)).convert("RGB")
                caption, latency = generate_caption(image, processor, model, "single", m)

            m["images_processed"].labels(mode="single", status="success").inc()

            col1, col2 = st.columns(2)
            with col1:
                st.image(image, caption="Uploaded Image", use_column_width=True)
            with col2:
                st.success("Caption generated!")
                st.markdown(f"### Caption\n> {caption}")
                st.metric("Time taken", f"{latency:.2f}s")
                st.metric("Caption length", f"{len(caption)} chars")

        except Exception as e:
            m["errors_total"].labels(mode="single", error_type=type(e).__name__).inc()
            m["images_processed"].labels(mode="single", status="error").inc()
            st.error(f"Something went wrong: {e}")

        finally:
            m["active_requests"].labels(mode="single").dec()

# ── Bulk ZIP Mode ─────────────────────────────────────────────────────────────
else:
    st.header("Bulk Mode — Upload a ZIP")
    uploaded_zip = st.file_uploader("Upload a ZIP of images", type=["zip"])

    if uploaded_zip and st.button("Process ZIP", type="primary"):
        m["active_requests"].labels(mode="bulk").inc()
        m["requests_total"].labels(mode="bulk", session_id=session_id).inc()
        m["zip_uploads"].inc()

        try:
            valid_ext = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
            results   = []

            with zipfile.ZipFile(io.BytesIO(uploaded_zip.read())) as zf:
                names = [n for n in zf.namelist()
                         if os.path.splitext(n)[1].lower() in valid_ext
                         and not n.startswith("__MACOSX")]

                m["bulk_queue"].set(len(names))
                progress = st.progress(0, text="Starting...")

                for i, name in enumerate(names):
                    m["bulk_queue"].set(len(names) - i)

                    try:
                        img_bytes = zf.read(name)
                        image     = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                        caption, latency = generate_caption(image, processor, model, "bulk", m)
                        m["images_processed"].labels(mode="bulk", status="success").inc()
                        results.append({"file": name, "caption": caption, "latency": latency})

                    except Exception as e:
                        m["errors_total"].labels(mode="bulk", error_type=type(e).__name__).inc()
                        m["images_processed"].labels(mode="bulk", status="error").inc()
                        results.append({"file": name, "caption": f"ERROR: {e}", "latency": None})

                    progress.progress((i + 1) / len(names), text=f"{i+1}/{len(names)} done")

            m["bulk_queue"].set(0)
            st.success(f" Processed {len(results)} images!")

            for r in results:
                with st.expander(f" {r['file']}"):
                    if r["latency"]:
                        st.write(f"**Caption:** {r['caption']}")
                        st.write(f"**Time:** {r['latency']:.2f}s")
                    else:
                        st.error(r["caption"])

        except Exception as e:
            m["errors_total"].labels(mode="bulk", error_type=type(e).__name__).inc()
            st.error(f"Failed to process ZIP: {e}")

        finally:
            m["active_requests"].labels(mode="bulk").dec()